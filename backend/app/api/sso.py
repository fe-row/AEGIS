"""
SSO Routes — OpenID Connect authentication endpoints.
"""
import secrets
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import get_db
from app.config import get_settings
from app.schemas.schemas import SSOAuthorizeResponse, SSOCallbackRequest, LoginResponse
from app.services.sso import SSOService
from app.utils.redis_client import get_redis
from app.logging_config import get_logger

logger = get_logger("sso_routes")
settings = get_settings()

router = APIRouter(prefix="/auth/sso", tags=["SSO"])

# SECURITY: SSO state TTL (10 minutes to complete the flow)
SSO_STATE_TTL = 600


@router.get("/authorize", response_model=SSOAuthorizeResponse)
async def sso_authorize():
    """Initiate SSO login — returns the IdP authorization URL."""
    if not settings.SSO_ENABLED:
        raise HTTPException(status_code=400, detail="SSO is not enabled")

    state = secrets.token_urlsafe(32)

    # SECURITY FIX: Store state in Redis to validate on callback (anti-CSRF)
    redis = await get_redis()
    await redis.setex(f"sso:state:{state}", SSO_STATE_TTL, "1")

    authorize_url = await SSOService.get_authorize_url_async(state)

    return SSOAuthorizeResponse(authorize_url=authorize_url)


@router.post("/callback", response_model=LoginResponse)
async def sso_callback(
    data: SSOCallbackRequest,
    db: AsyncSession = Depends(get_db),
):
    """Handle SSO callback — exchanges code for tokens and creates/links user."""
    if not settings.SSO_ENABLED:
        raise HTTPException(status_code=400, detail="SSO is not enabled")

    # SECURITY FIX: Validate state parameter (anti-CSRF)
    if not data.state:
        raise HTTPException(status_code=400, detail="Missing state parameter")

    redis = await get_redis()
    state_key = f"sso:state:{data.state}"
    stored = await redis.get(state_key)
    if not stored:
        logger.warning("sso_invalid_state", state=data.state[:8])
        raise HTTPException(status_code=400, detail="Invalid or expired SSO state")

    # Delete state immediately (single-use)
    await redis.delete(state_key)

    try:
        result = await SSOService.authenticate(db, data.code)
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.error("sso_auth_error", error=str(e))
        raise HTTPException(status_code=500, detail="SSO authentication failed")

    return LoginResponse(
        access_token=result["access_token"],
        refresh_token=result["refresh_token"],
        expires_in=result["expires_in"],
    )

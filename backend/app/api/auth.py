from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.database import get_db
from app.models.entities import User, UserAPIKey
from app.schemas.schemas import (
    UserCreate, UserLogin, TokenResponse, UserOut,
    RefreshRequest, APIKeyCreate, APIKeyCreated, APIKeyOut,
)
from app.middleware.auth_middleware import (
    hash_password, verify_password, create_access_token,
    create_refresh_token, decode_token, get_current_user,
)
from app.utils.crypto import generate_api_key
from app.utils.jwt_blacklist import blacklist_token
from app.services.audit_service import AuditService
from app.logging_config import get_logger

logger = get_logger("auth")
router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register", response_model=UserOut, status_code=201)
async def register(data: UserCreate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == data.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(
        email=data.email,
        hashed_password=hash_password(data.password),
        full_name=data.full_name,
        organization=data.organization,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    logger.info("user_registered", user_id=str(user.id))
    return user


@router.post("/login", response_model=TokenResponse)
async def login(data: UserLogin, request: Request, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == data.email))
    user = result.scalar_one_or_none()

    ip = request.client.host if request.client else "unknown"

    if not user or not verify_password(data.password, user.hashed_password):
        logger.warning("login_failed", email=data.email, ip=ip)
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account disabled")

    access_token, expires_in, access_jti = create_access_token(user.id)
    refresh_token, refresh_jti = create_refresh_token(user.id)

    logger.info("user_logged_in", user_id=str(user.id), ip=ip)
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=expires_in,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(data: RefreshRequest, db: AsyncSession = Depends(get_db)):
    payload = decode_token(data.refresh_token, expected_type="refresh")
    user_id = payload.get("sub")
    old_jti = payload.get("jti", "")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    # Blacklist old refresh token (rotation)
    if old_jti:
        await blacklist_token(old_jti, ttl_seconds=86400 * 30)

    access_token, expires_in, _ = create_access_token(user.id)
    new_refresh, _ = create_refresh_token(user.id)

    return TokenResponse(access_token=access_token, refresh_token=new_refresh, expires_in=expires_in)


@router.post("/logout")
async def logout_endpoint(
    request: Request,
    user: User = Depends(get_current_user),
):
    """FIX: Actually invalidates the current token."""
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        try:
            payload = decode_token(token)
            jti = payload.get("jti", "")
            if jti:
                from app.config import get_settings
                settings = get_settings()
                await blacklist_token(jti, settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60)
        except Exception:
            pass

    logger.info("user_logged_out", user_id=str(user.id))
    return {"status": "logged_out"}


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)):
    return user


# ── API Keys ──

@router.post("/api-keys", response_model=APIKeyCreated, status_code=201)
async def create_api_key_endpoint(
    data: APIKeyCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    raw_key, key_hash = generate_api_key()
    api_key = UserAPIKey(
        user_id=user.id, key_hash=key_hash,
        key_prefix=raw_key[:12], name=data.name, scopes=data.scopes,
    )
    db.add(api_key)
    await db.commit()
    await db.refresh(api_key)
    return APIKeyCreated(
        id=api_key.id, key_prefix=api_key.key_prefix, name=api_key.name,
        scopes=api_key.scopes, is_active=api_key.is_active,
        created_at=api_key.created_at, raw_key=raw_key,
    )


@router.get("/api-keys", response_model=list[APIKeyOut])
async def list_api_keys(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    result = await db.execute(
        select(UserAPIKey).where(UserAPIKey.user_id == user.id).order_by(UserAPIKey.created_at.desc())
    )
    return list(result.scalars().all())
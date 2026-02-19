import uuid
import hmac
from datetime import datetime, timezone, timedelta
from fastapi import Depends, HTTPException, status, Security, Request
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt as pyjwt
import bcrypt
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.config import get_settings
from app.models.database import get_db
from app.models.entities import User, UserAPIKey
from app.utils.crypto import hash_api_key
from app.utils.jwt_blacklist import is_token_blacklisted

settings = get_settings()
security_scheme = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def create_access_token(user_id: uuid.UUID) -> tuple[str, int, str]:
    """Returns (token, expires_in_seconds, jti)."""
    jti = str(uuid.uuid4())
    expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    exp = datetime.now(timezone.utc) + expires
    payload = {
        "sub": str(user_id),
        "exp": exp,
        "iat": datetime.now(timezone.utc),
        "type": "access",
        "jti": jti,
    }
    token = pyjwt.encode(payload, settings.jwt_signing_key, algorithm=settings.JWT_ALGORITHM)
    return token, int(expires.total_seconds()), jti


def create_mfa_token(user_id: uuid.UUID) -> tuple[str, str]:
    """Short-lived token for MFA challenge. Cannot be used as access token.
    Returns (token, jti)."""
    jti = str(uuid.uuid4())
    expires = timedelta(minutes=5)  # 5 min to complete MFA
    exp = datetime.now(timezone.utc) + expires
    payload = {
        "sub": str(user_id),
        "exp": exp,
        "iat": datetime.now(timezone.utc),
        "type": "mfa_challenge",
        "jti": jti,
    }
    token = pyjwt.encode(payload, settings.jwt_signing_key, algorithm=settings.JWT_ALGORITHM)
    return token, jti


def create_refresh_token(user_id: uuid.UUID) -> tuple[str, str]:
    """Returns (token, jti)."""
    jti = str(uuid.uuid4())
    expires = timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    exp = datetime.now(timezone.utc) + expires
    payload = {
        "sub": str(user_id),
        "exp": exp,
        "iat": datetime.now(timezone.utc),
        "type": "refresh",
        "jti": jti,
    }
    token = pyjwt.encode(payload, settings.jwt_signing_key, algorithm=settings.JWT_ALGORITHM)
    return token, jti


def decode_token(token: str, expected_type: str = "access") -> dict:
    try:
        payload = pyjwt.decode(
            token, settings.jwt_verification_key,
            algorithms=[settings.JWT_ALGORITHM],
        )
        if payload.get("type") != expected_type:
            raise HTTPException(status_code=401, detail="Invalid token type")
        return payload
    except pyjwt.exceptions.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


def set_auth_cookies(
    response: JSONResponse,
    access_token: str,
    refresh_token: str,
    access_max_age: int | None = None,
    refresh_max_age: int | None = None,
):
    """Set HttpOnly cookies for access and refresh tokens."""
    is_prod = settings.ENVIRONMENT != "development"
    access_max_age = access_max_age or (settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60)
    refresh_max_age = refresh_max_age or (settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400)

    response.set_cookie(
        key="aegis_access",
        value=access_token,
        httponly=True,
        secure=is_prod,
        samesite="lax",
        max_age=access_max_age,
        path="/",
    )
    response.set_cookie(
        key="aegis_refresh",
        value=refresh_token,
        httponly=True,
        secure=is_prod,
        samesite="lax",
        max_age=refresh_max_age,
        path="/api/v1/auth",  # Only sent to auth endpoints
    )


def clear_auth_cookies(response: JSONResponse):
    """Remove auth cookies on logout."""
    response.delete_cookie("aegis_access", path="/")
    response.delete_cookie("aegis_refresh", path="/api/v1/auth")


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Security(security_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Supports JWT Bearer + API key (aegis_xxx) + X-API-Key header + HttpOnly cookies."""
    token = None

    if credentials:
        token = credentials.credentials
    else:
        api_key = request.headers.get("x-api-key")
        if api_key:
            return await _auth_via_api_key(api_key, db)
        # SECURITY: Fall back to HttpOnly cookie
        token = request.cookies.get("aegis_access")

    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    if token.startswith("aegis_"):
        return await _auth_via_api_key(token, db)

    # JWT auth
    payload = decode_token(token, "access")

    # SECURITY: Block mfa_challenge tokens from being used as access tokens
    if payload.get("type") == "mfa_challenge":
        raise HTTPException(status_code=401, detail="MFA challenge token cannot be used for API access")

    # Check blacklist
    jti = payload.get("jti", "")
    if jti and await is_token_blacklisted(jti):
        raise HTTPException(status_code=401, detail="Token has been revoked")

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User inactive or not found")
    return user


async def _auth_via_api_key(raw_key: str, db: AsyncSession) -> User:
    key_hash = hash_api_key(raw_key)
    key_prefix = raw_key[:12]

    # SECURITY FIX: Filter by prefix first to avoid loading all keys
    result = await db.execute(
        select(UserAPIKey).where(
            UserAPIKey.is_active == True,
            UserAPIKey.key_prefix == key_prefix,
        )
    )
    # Timing-safe comparison on the filtered set
    api_key = None
    for api_key_row in result.scalars().all():
        if hmac.compare_digest(api_key_row.key_hash, key_hash):
            api_key = api_key_row
            break

    if not api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")

    if api_key.expires_at and api_key.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail="API key expired")

    api_key.last_used_at = datetime.now(timezone.utc)

    result = await db.execute(select(User).where(User.id == api_key.user_id))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User inactive")

    await db.commit()
    return user
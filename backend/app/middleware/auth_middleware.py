import uuid
import hmac
from datetime import datetime, timezone, timedelta
from fastapi import Depends, HTTPException, status, Security, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.config import get_settings
from app.models.database import get_db
from app.models.entities import User, UserAPIKey
from app.utils.crypto import hash_api_key
from app.utils.jwt_blacklist import is_token_blacklisted

settings = get_settings()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security_scheme = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


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
    token = jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
    return token, int(expires.total_seconds()), jti


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
    token = jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
    return token, jti


def decode_token(token: str, expected_type: str = "access") -> dict:
    try:
        payload = jwt.decode(
            token, settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM],
        )
        if payload.get("type") != expected_type:
            raise HTTPException(status_code=401, detail="Invalid token type")
        return payload
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Security(security_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Supports JWT Bearer + API key (aegis_xxx) + X-API-Key header."""
    token = None

    if credentials:
        token = credentials.credentials
    else:
        api_key = request.headers.get("x-api-key")
        if api_key:
            return await _auth_via_api_key(api_key, db)

    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    if token.startswith("aegis_"):
        return await _auth_via_api_key(token, db)

    # JWT auth
    payload = decode_token(token, "access")

    # FIX: Check blacklist
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
    result = await db.execute(
        select(UserAPIKey).where(
            UserAPIKey.is_active == True,
        )
    )
    # Timing-safe: compare all active keys with constant-time comparison
    for api_key_row in result.scalars().all():
        if hmac.compare_digest(api_key_row.key_hash, key_hash):
            api_key = api_key_row
            break
    else:
        api_key = None

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
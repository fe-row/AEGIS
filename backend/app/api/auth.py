from fastapi import APIRouter, Depends, HTTPException, Request, Query
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.database import get_db
from app.models.entities import User, UserAPIKey, UserRole
from app.schemas.schemas import (
    UserCreate, UserLogin, TokenResponse, UserOut,
    RefreshRequest, APIKeyCreate, APIKeyCreated, APIKeyOut,
    MFASetupResponse, MFAVerifyRequest, MFAChallengeRequest, LoginResponse,
    UserRoleUpdate, PasswordChange,
)
from app.middleware.auth_middleware import (
    hash_password, verify_password, create_access_token,
    create_refresh_token, create_mfa_token, decode_token, get_current_user,
    set_auth_cookies, clear_auth_cookies,
)
from app.utils.crypto import generate_api_key, encrypt_secret, decrypt_secret
from app.utils.jwt_blacklist import blacklist_token, is_token_blacklisted
from app.services.audit_service import AuditService
from app.services.mfa import MFAService
from app.services.rbac import require_permission
from app.logging_config import get_logger

logger = get_logger("auth")
router = APIRouter(prefix="/auth", tags=["Authentication"])

# ── Account Lockout ──
MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_SECONDS = 900  # 15 minutes


async def _check_lockout(identifier: str) -> None:
    """Check if an account/IP is locked out due to failed attempts."""
    from app.utils.redis_client import get_redis
    redis = await get_redis()
    key = f"lockout:{identifier}"
    attempts = await redis.get(key)
    if attempts and int(attempts) >= MAX_LOGIN_ATTEMPTS:
        ttl = await redis.ttl(key)
        raise HTTPException(
            status_code=429,
            detail=f"Account locked. Try again in {max(ttl, 0)} seconds.",
        )


async def _record_failed_attempt(identifier: str) -> None:
    """Increment failed login counter with TTL."""
    from app.utils.redis_client import get_redis
    redis = await get_redis()
    key = f"lockout:{identifier}"
    pipe = redis.pipeline()
    pipe.incr(key)
    pipe.expire(key, LOCKOUT_SECONDS)
    await pipe.execute()


async def _clear_lockout(identifier: str) -> None:
    """Clear lockout counter on successful login."""
    from app.utils.redis_client import get_redis
    redis = await get_redis()
    await redis.delete(f"lockout:{identifier}")


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


@router.post("/login", response_model=LoginResponse)
async def login(data: UserLogin, request: Request, db: AsyncSession = Depends(get_db)):
    ip = request.client.host if request.client else "unknown"
    lockout_key = f"{data.email}:{ip}"

    # SECURITY: Check account lockout
    await _check_lockout(lockout_key)

    result = await db.execute(select(User).where(User.email == data.email))
    user = result.scalar_one_or_none()

    if not user or not user.hashed_password or not verify_password(data.password, user.hashed_password):
        await _record_failed_attempt(lockout_key)
        logger.warning("login_failed", email=data.email, ip=ip)
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account disabled")

    # Clear lockout on successful password verification
    await _clear_lockout(lockout_key)

    # MFA check: if enabled, return mfa_required + short-lived MFA token
    if user.mfa_enabled:
        mfa_token, mfa_jti = create_mfa_token(user.id)
        logger.info("mfa_challenge_issued", user_id=str(user.id), ip=ip)
        return LoginResponse(mfa_required=True, mfa_token=mfa_token)

    access_token, expires_in, access_jti = create_access_token(user.id)
    refresh_token, refresh_jti = create_refresh_token(user.id)

    logger.info("user_logged_in", user_id=str(user.id), ip=ip)
    body = LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=expires_in,
    )
    response = JSONResponse(content=body.model_dump())
    set_auth_cookies(response, access_token, refresh_token, access_max_age=expires_in)
    return response


@router.post("/mfa/challenge", response_model=LoginResponse)
async def mfa_challenge(data: MFAChallengeRequest, request: Request, db: AsyncSession = Depends(get_db)):
    """Verify MFA code after login to obtain full tokens."""
    # SECURITY FIX: Verify the temporary MFA token (type=mfa_challenge, NOT access)
    try:
        payload = decode_token(data.mfa_token, expected_type="mfa_challenge")
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired MFA token")

    user_id = payload.get("sub")
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user or not user.is_active or not user.mfa_enabled:
        raise HTTPException(status_code=401, detail="Invalid request")

    # SECURITY: Account lockout for MFA attempts too
    ip = request.client.host if request.client else "unknown"
    lockout_key = f"mfa:{user.email}:{ip}"
    await _check_lockout(lockout_key)

    # SECURITY FIX: Decrypt mfa_secret before verification
    decrypted_secret = decrypt_secret(user.mfa_secret) if user.mfa_secret else None

    # Try TOTP code first
    if decrypted_secret and MFAService.verify_code(decrypted_secret, data.code):
        pass  # Valid TOTP
    else:
        # Try backup code
        idx = MFAService.verify_backup_code(data.code, user.mfa_backup_codes or [])
        if idx is None:
            await _record_failed_attempt(lockout_key)
            logger.warning("mfa_failed", user_id=str(user.id))
            raise HTTPException(status_code=401, detail="Invalid MFA code")
        # Remove used backup code
        codes = list(user.mfa_backup_codes)
        codes.pop(idx)
        user.mfa_backup_codes = codes
        await db.commit()

    await _clear_lockout(lockout_key)

    # Blacklist the MFA token so it can't be reused
    mfa_jti = payload.get("jti", "")
    if mfa_jti:
        await blacklist_token(mfa_jti, ttl_seconds=300)

    access_token, expires_in, _ = create_access_token(user.id)
    refresh_token, _ = create_refresh_token(user.id)

    logger.info("mfa_verified", user_id=str(user.id))
    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=expires_in,
    )


# ── MFA Setup ──

@router.post("/mfa/setup", response_model=MFASetupResponse)
async def mfa_setup(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Generate MFA secret and backup codes. Must call /mfa/verify to activate."""
    if user.mfa_enabled:
        raise HTTPException(status_code=400, detail="MFA already enabled")

    secret = MFAService.generate_secret()
    provisioning_uri = MFAService.get_provisioning_uri(secret, user.email)
    backup_codes = MFAService.generate_backup_codes()

    # SECURITY FIX: Encrypt secret before storing in DB
    user.mfa_secret = encrypt_secret(secret)
    await db.commit()

    return MFASetupResponse(
        secret=secret,
        provisioning_uri=provisioning_uri,
        backup_codes=backup_codes,
    )


@router.post("/mfa/verify")
async def mfa_verify(
    data: MFAVerifyRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Verify TOTP code to activate MFA. Called after /mfa/setup."""
    if user.mfa_enabled:
        raise HTTPException(status_code=400, detail="MFA already enabled")
    if not user.mfa_secret:
        raise HTTPException(status_code=400, detail="Call /mfa/setup first")

    # SECURITY FIX: Decrypt secret before verification
    decrypted_secret = decrypt_secret(user.mfa_secret)
    if not MFAService.verify_code(decrypted_secret, data.code):
        raise HTTPException(status_code=400, detail="Invalid code — check your authenticator app")

    # Activate MFA and store hashed backup codes (secret already encrypted from setup)
    backup_codes = MFAService.generate_backup_codes()
    user.mfa_enabled = True
    user.mfa_backup_codes = [MFAService.hash_backup_code(c) for c in backup_codes]
    await db.commit()

    logger.info("mfa_enabled", user_id=str(user.id))
    return {"status": "mfa_enabled", "backup_codes": backup_codes}


@router.post("/mfa/disable")
async def mfa_disable(
    data: MFAVerifyRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Disable MFA. Requires current TOTP code for confirmation."""
    if not user.mfa_enabled:
        raise HTTPException(status_code=400, detail="MFA not enabled")

    # SECURITY FIX: Decrypt before verification
    decrypted_secret = decrypt_secret(user.mfa_secret)
    if not MFAService.verify_code(decrypted_secret, data.code):
        raise HTTPException(status_code=400, detail="Invalid code")

    user.mfa_enabled = False
    user.mfa_secret = None
    user.mfa_backup_codes = []
    await db.commit()

    logger.info("mfa_disabled", user_id=str(user.id))
    return {"status": "mfa_disabled"}


# ── Standard Auth ──

@router.post("/refresh")
async def refresh(request: Request, data: RefreshRequest | None = None, db: AsyncSession = Depends(get_db)):
    # Support both JSON body and HttpOnly cookie for refresh token
    raw_refresh = data.refresh_token if data and data.refresh_token else request.cookies.get("aegis_refresh")
    if not raw_refresh:
        raise HTTPException(status_code=401, detail="Refresh token required")

    payload = decode_token(raw_refresh, expected_type="refresh")
    user_id = payload.get("sub")
    old_jti = payload.get("jti", "")

    # SECURITY: Prevent refresh token replay — check if already used
    if old_jti and await is_token_blacklisted(old_jti):
        logger.warning("refresh_token_replay", jti=old_jti, user_id=user_id)
        raise HTTPException(status_code=401, detail="Refresh token already used")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    # Blacklist old refresh token (rotation)
    if old_jti:
        await blacklist_token(old_jti, ttl_seconds=86400 * 30)

    access_token, expires_in, _ = create_access_token(user.id)
    new_refresh, _ = create_refresh_token(user.id)

    body = {"access_token": access_token, "refresh_token": new_refresh, "expires_in": expires_in}
    response = JSONResponse(content=body)
    set_auth_cookies(response, access_token, new_refresh, access_max_age=expires_in)
    return response


@router.post("/logout")
async def logout_endpoint(
    request: Request,
    user: User = Depends(get_current_user),
):
    """Invalidates the current token and clears auth cookies."""
    auth_header = request.headers.get("authorization", "")
    token = None
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
    elif request.cookies.get("aegis_access"):
        token = request.cookies.get("aegis_access")

    if token:
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
    response = JSONResponse(content={"status": "logged_out"})
    clear_auth_cookies(response)
    return response


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)):
    return user


# ── Role Management ──

# SECURITY: Role hierarchy — higher number = higher privilege
ROLE_HIERARCHY = {
    UserRole.VIEWER: 0,
    UserRole.AGENT_DEVELOPER: 1,
    UserRole.FINANCE_AUDITOR: 1,
    UserRole.SECURITY_MANAGER: 2,
    UserRole.ADMIN: 3,
    UserRole.OWNER: 4,
}


@router.put("/users/{user_id}/role", response_model=UserOut)
async def update_user_role(
    user_id: str,
    data: UserRoleUpdate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_permission("users:write")),
):
    """Assign a built-in role to a user. Requires users:write permission."""
    from uuid import UUID

    # SECURITY: Prevent role escalation above caller's level
    caller_level = ROLE_HIERARCHY.get(admin.role, 0)
    target_level = ROLE_HIERARCHY.get(data.role, 99)
    if target_level >= caller_level:
        raise HTTPException(
            status_code=403,
            detail="Cannot assign a role equal to or above your own",
        )

    # Prevent self-role-change
    if str(admin.id) == user_id:
        raise HTTPException(status_code=403, detail="Cannot change your own role")

    result = await db.execute(select(User).where(User.id == UUID(user_id)))
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    target.role = data.role
    await db.commit()
    await db.refresh(target)
    logger.info("role_updated", user_id=user_id, new_role=data.role.value, by=str(admin.id))
    return target


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
async def list_api_keys(
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(UserAPIKey)
        .where(UserAPIKey.user_id == user.id)
        .order_by(UserAPIKey.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all())


@router.delete("/api-keys/{key_id}", status_code=204)
async def revoke_api_key(
    key_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Revoke (deactivate) an API key. Only the owner can revoke their own keys."""
    from uuid import UUID
    result = await db.execute(
        select(UserAPIKey).where(
            UserAPIKey.id == UUID(key_id),
            UserAPIKey.user_id == user.id,
        )
    )
    api_key = result.scalar_one_or_none()
    if not api_key:
        raise HTTPException(status_code=404, detail="API key not found")

    api_key.is_active = False
    await db.commit()
    logger.info("api_key_revoked", key_id=key_id, user_id=str(user.id))


# ── Password Change ──

@router.post("/change-password")
async def change_password(
    data: PasswordChange,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Change password. Requires current password for verification."""
    if not user.hashed_password:
        raise HTTPException(status_code=400, detail="Account uses SSO — cannot change password")

    if not verify_password(data.current_password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Current password is incorrect")

    # Prevent reuse of the same password
    if verify_password(data.new_password, user.hashed_password):
        raise HTTPException(status_code=400, detail="New password must differ from current password")

    user.hashed_password = hash_password(data.new_password)
    await db.commit()

    # SECURITY: Invalidate the current session token after password change
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        old_token = auth_header[7:]
        try:
            old_payload = decode_token(old_token, "access")
            old_jti = old_payload.get("jti", "")
            if old_jti:
                await blacklist_token(old_jti)
        except Exception:
            pass  # Token was already valid (we're authenticated)

    # Issue fresh tokens so the user isn't logged out
    new_access, expires_in, _ = create_access_token(user.id)
    new_refresh, _ = create_refresh_token(user.id)

    logger.info("password_changed_sessions_invalidated", user_id=str(user.id))
    return {
        "status": "password_changed",
        "access_token": new_access,
        "refresh_token": new_refresh,
        "expires_in": expires_in,
    }
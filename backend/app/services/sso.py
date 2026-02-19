"""
SSO Service — OpenID Connect (OIDC) integration.
Supports Okta, Azure AD (Entra ID), and Google Workspace.
Uses authlib for OIDC discovery and token exchange.
"""
import uuid
from typing import Optional
from dataclasses import dataclass

import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.config import get_settings
from app.models.entities import User, UserRole
from app.middleware.auth_middleware import (
    create_access_token,
    create_refresh_token,
    hash_password,
)
from app.logging_config import get_logger

logger = get_logger("sso")
settings = get_settings()


@dataclass
class OIDCConfig:
    """Cached OIDC provider configuration."""
    authorization_endpoint: str
    token_endpoint: str
    userinfo_endpoint: str
    issuer: str


_oidc_config_cache: Optional[OIDCConfig] = None


class SSOService:
    """OpenID Connect SSO service."""

    @staticmethod
    async def get_oidc_config() -> OIDCConfig:
        """Discover OIDC endpoints from the provider's well-known URL."""
        global _oidc_config_cache
        if _oidc_config_cache:
            return _oidc_config_cache

        discovery_url = settings.SSO_DISCOVERY_URL
        if not discovery_url:
            raise ValueError("SSO_DISCOVERY_URL is not configured")

        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(discovery_url)
            resp.raise_for_status()
            data = resp.json()

        _oidc_config_cache = OIDCConfig(
            authorization_endpoint=data["authorization_endpoint"],
            token_endpoint=data["token_endpoint"],
            userinfo_endpoint=data["userinfo_endpoint"],
            issuer=data["issuer"],
        )
        return _oidc_config_cache

    @staticmethod
    def get_authorize_url(state: str) -> str:
        """Build the authorization redirect URL (synchronous if config cached)."""
        import asyncio
        config = asyncio.get_event_loop().run_until_complete(
            SSOService.get_oidc_config()
        ) if not _oidc_config_cache else _oidc_config_cache

        params = {
            "client_id": settings.SSO_CLIENT_ID,
            "redirect_uri": settings.SSO_REDIRECT_URI,
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
        }
        query = "&".join(f"{k}={v}" for k, v in params.items())
        return f"{config.authorization_endpoint}?{query}"

    @staticmethod
    async def get_authorize_url_async(state: str) -> str:
        """Build the authorization redirect URL (async)."""
        config = await SSOService.get_oidc_config()
        params = {
            "client_id": settings.SSO_CLIENT_ID,
            "redirect_uri": settings.SSO_REDIRECT_URI,
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
        }
        query = "&".join(f"{k}={v}" for k, v in params.items())
        return f"{config.authorization_endpoint}?{query}"

    @staticmethod
    async def exchange_code(code: str) -> dict:
        """Exchange authorization code for tokens and fetch user info."""
        config = await SSOService.get_oidc_config()

        async with httpx.AsyncClient(timeout=10) as client:
            # Exchange code for tokens
            token_resp = await client.post(
                config.token_endpoint,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": settings.SSO_REDIRECT_URI,
                    "client_id": settings.SSO_CLIENT_ID,
                    "client_secret": settings.SSO_CLIENT_SECRET,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            token_resp.raise_for_status()
            tokens = token_resp.json()

            # Fetch user info
            userinfo_resp = await client.get(
                config.userinfo_endpoint,
                headers={"Authorization": f"Bearer {tokens['access_token']}"},
            )
            userinfo_resp.raise_for_status()
            userinfo = userinfo_resp.json()

        return {
            "sub": userinfo.get("sub"),
            "email": userinfo.get("email"),
            "name": userinfo.get("name", userinfo.get("email", "")),
            "provider": settings.SSO_PROVIDER,
        }

    @staticmethod
    async def find_or_create_user(db: AsyncSession, sso_info: dict) -> User:
        """Find existing user by SSO subject or email, or create a new one."""
        # Try by SSO subject ID first
        result = await db.execute(
            select(User).where(
                User.sso_provider == sso_info["provider"],
                User.sso_subject_id == sso_info["sub"],
            )
        )
        user = result.scalar_one_or_none()
        if user:
            logger.info("sso_login_existing", user_id=str(user.id))
            return user

        # Try by email (link existing account)
        result = await db.execute(
            select(User).where(User.email == sso_info["email"])
        )
        user = result.scalar_one_or_none()
        if user:
            # SECURITY FIX: If user has a password, don't auto-link.
            # This prevents an attacker from registering the same email on the IdP
            # and hijacking an existing account. The user must log in with their
            # password first and explicitly link SSO from their account settings.
            if user.hashed_password:
                logger.warning(
                    "sso_auto_link_blocked",
                    user_id=str(user.id),
                    reason="existing_password_account",
                )
                raise ValueError(
                    "An account with this email already exists. "
                    "Log in with your password first, then link SSO from settings."
                )

            # SSO-only account (no password) — safe to link
            user.sso_provider = sso_info["provider"]
            user.sso_subject_id = sso_info["sub"]
            await db.commit()
            await db.refresh(user)
            logger.info("sso_account_linked", user_id=str(user.id))
            return user

        # Create new user
        user = User(
            email=sso_info["email"],
            full_name=sso_info["name"],
            hashed_password=None,
            sso_provider=sso_info["provider"],
            sso_subject_id=sso_info["sub"],
            role=UserRole.VIEWER,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        logger.info("sso_user_created", user_id=str(user.id))
        return user

    @staticmethod
    async def authenticate(
        db: AsyncSession, code: str
    ) -> dict:
        """Full SSO authentication flow: exchange code → find/create user → issue JWT."""
        sso_info = await SSOService.exchange_code(code)
        user = await SSOService.find_or_create_user(db, sso_info)

        if not user.is_active:
            raise ValueError("Account is disabled")

        access_token, expires_in, _ = create_access_token(user.id)
        refresh_token, _ = create_refresh_token(user.id)

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_in": expires_in,
            "user": user,
        }

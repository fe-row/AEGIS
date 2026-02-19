"""
RBAC Service — Granular Role-Based Access Control for human users.
Supports both the enum-based role on User AND custom Role entities.
"""
from typing import Optional
from functools import wraps
from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.database import get_db
from app.models.entities import User, UserRole, Role, UserRoleAssignment
from app.middleware.auth_middleware import get_current_user
from app.logging_config import get_logger

logger = get_logger("rbac")

# ── Default permission sets per built-in role ──

ROLE_PERMISSIONS: dict[UserRole, set[str]] = {
    UserRole.OWNER: {
        "agents:read", "agents:write", "agents:delete",
        "wallets:read", "wallets:write",
        "audit:read", "audit:export",
        "proxy:execute",
        "hitl:decide",
        "users:read", "users:write", "users:delete",
        "roles:read", "roles:write",
        "settings:read", "settings:write",
        "dashboard:read",
        "policies:read", "policies:write",
        "secrets:read", "secrets:write",
    },
    UserRole.ADMIN: {
        "agents:read", "agents:write", "agents:delete",
        "wallets:read", "wallets:write",
        "audit:read", "audit:export",
        "proxy:execute",
        "hitl:decide",
        "users:read", "users:write",
        "roles:read", "roles:write",
        "settings:read", "settings:write",
        "dashboard:read",
        "policies:read", "policies:write",
        "secrets:read", "secrets:write",
    },
    UserRole.SECURITY_MANAGER: {
        "agents:read", "agents:write",
        "audit:read", "audit:export",
        "hitl:decide",
        "users:read",
        "roles:read",
        "settings:read",
        "dashboard:read",
        "policies:read", "policies:write",
    },
    UserRole.FINANCE_AUDITOR: {
        "agents:read",
        "wallets:read",
        "audit:read", "audit:export",
        "dashboard:read",
    },
    UserRole.AGENT_DEVELOPER: {
        "agents:read", "agents:write",
        "wallets:read",
        "proxy:execute",
        "dashboard:read",
        "policies:read",
        "secrets:read", "secrets:write",
    },
    UserRole.VIEWER: {
        "agents:read",
        "wallets:read",
        "audit:read",
        "dashboard:read",
    },
}


class RBACService:
    """Checks user permissions combining built-in role + custom role assignments."""

    @staticmethod
    async def get_user_permissions(
        user: User,
        db: Optional[AsyncSession] = None,
    ) -> set[str]:
        """Get all permissions for a user (built-in role + custom roles)."""
        # Superadmin bypasses everything
        if user.is_superadmin:
            return {"*"}

        perms = set(ROLE_PERMISSIONS.get(user.role, set()))

        # Add permissions from custom role assignments
        if db:
            result = await db.execute(
                select(UserRoleAssignment)
                .options(selectinload(UserRoleAssignment.role))
                .where(UserRoleAssignment.user_id == user.id)
            )
            for assignment in result.scalars().all():
                if assignment.role and assignment.role.permissions:
                    perms.update(assignment.role.permissions)

        return perms

    @staticmethod
    async def check_permission(
        user: User,
        permission: str,
        db: Optional[AsyncSession] = None,
    ) -> bool:
        """Check if user has a specific permission."""
        if user.is_superadmin:
            return True
        # Fast path: check built-in role first (avoids DB query)
        builtin_perms = ROLE_PERMISSIONS.get(user.role, set())
        if permission in builtin_perms:
            return True
        # Slow path: check custom role assignments
        perms = await RBACService.get_user_permissions(user, db)
        return permission in perms

    @staticmethod
    async def assign_role(
        db: AsyncSession,
        user_id,
        role_id,
        assigned_by=None,
    ) -> UserRoleAssignment:
        """Assign a custom role to a user."""
        assignment = UserRoleAssignment(
            user_id=user_id,
            role_id=role_id,
            assigned_by=assigned_by,
        )
        db.add(assignment)
        await db.commit()
        await db.refresh(assignment)
        logger.info("role_assigned", user_id=str(user_id), role_id=str(role_id))
        return assignment

    @staticmethod
    async def remove_role(db: AsyncSession, user_id, role_id) -> bool:
        """Remove a custom role assignment."""
        result = await db.execute(
            select(UserRoleAssignment).where(
                UserRoleAssignment.user_id == user_id,
                UserRoleAssignment.role_id == role_id,
            )
        )
        assignment = result.scalar_one_or_none()
        if assignment:
            await db.delete(assignment)
            await db.commit()
            logger.info("role_removed", user_id=str(user_id), role_id=str(role_id))
            return True
        return False


def require_permission(permission: str):
    """FastAPI dependency: requires the current user to have a permission."""
    async def _checker(
        user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> User:
        has_perm = await RBACService.check_permission(user, permission, db)
        if not has_perm:
            logger.warning(
                "permission_denied",
                user_id=str(user.id),
                permission=permission,
                role=user.role.value,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission '{permission}' required",
            )
        return user
    return _checker

"""
Admin API routes for user and system management.
Provides admin-only endpoints for managing users, roles, and system settings.
"""

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models import User, UserRole
from app.routes.auth import get_current_user

router = APIRouter(prefix="/api/admin", tags=["admin"])


class UserListResponse(BaseModel):
    users: List[dict]
    total_count: int


class RoleUpdateRequest(BaseModel):
    role: str


class UserStatusResponse(BaseModel):
    id: int
    email: str
    name: str
    role: str
    is_active: bool


def require_admin(current_user: User = Depends(get_current_user)):
    """Dependency to require admin role."""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions"
        )
    return current_user


@router.get("/users", response_model=UserListResponse)
async def list_all_users(
    admin_user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    """List all users (admin only)."""
    result = await session.execute(select(User))
    users = result.scalars().all()

    user_list = [
        {
            "id": user.id,
            "email": user.email,
            "name": user.name,
            "role": user.role.value,
            "is_active": user.is_active,
            "created_at": user.created_at,
            "updated_at": user.updated_at,
        }
        for user in users
    ]

    return UserListResponse(users=user_list, total_count=len(user_list))


@router.put("/users/{user_id}/role", response_model=UserStatusResponse)
async def update_user_role(
    user_id: int,
    request: RoleUpdateRequest,
    admin_user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    """Update user role (admin only)."""
    # Get target user
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    # Validate role
    try:
        new_role = UserRole(request.role)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid role"
        )

    # Update role
    user.role = new_role
    await session.commit()
    await session.refresh(user)

    return UserStatusResponse(
        id=user.id,
        email=user.email,
        name=user.name,
        role=user.role.value,
        is_active=user.is_active,
    )


@router.put("/users/{user_id}/deactivate", response_model=UserStatusResponse)
async def deactivate_user(
    user_id: int,
    admin_user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    """Deactivate user account (admin only)."""
    # Get target user
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    # Deactivate user
    user.is_active = False
    await session.commit()
    await session.refresh(user)

    return UserStatusResponse(
        id=user.id,
        email=user.email,
        name=user.name,
        role=user.role.value,
        is_active=user.is_active,
    )

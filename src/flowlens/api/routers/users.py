"""User management API endpoints.

Admin-only endpoints for managing local users.
"""

import math
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import func, select, update

from flowlens.api.dependencies import AdminUser, DbSession, Pagination
from flowlens.api.routers.auth import get_client_info
from flowlens.common.exceptions import NotFoundError, ValidationError
from flowlens.models.auth import AuthAuditLog, AuthEventType, AuthSession, User
from flowlens.schemas.auth import (
    PasswordResetRequest,
    UserCreate,
    UserList,
    UserResponse,
    UserUpdate,
)
from flowlens.services.auth_service import hash_password, validate_password_policy

router = APIRouter(prefix="/users", tags=["User Management"])


@router.get("", response_model=UserList)
async def list_users(
    _user: AdminUser,
    db: DbSession,
    pagination: Pagination,
    is_active: bool | None = None,
    is_local: bool | None = None,
    role: str | None = None,
    search: str | None = None,
) -> UserList:
    """List all users with optional filtering.

    Admin only.
    """
    query = select(User)

    # Apply filters
    if is_active is not None:
        query = query.where(User.is_active == is_active)

    if is_local is not None:
        query = query.where(User.is_local == is_local)

    if role:
        query = query.where(User.role == role)

    if search:
        search_pattern = f"%{search}%"
        query = query.where(
            (User.email.ilike(search_pattern)) | (User.name.ilike(search_pattern))
        )

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query) or 0

    # Apply pagination and ordering
    query = (
        query.order_by(User.created_at.desc())
        .offset(pagination.offset)
        .limit(pagination.page_size)
    )

    result = await db.execute(query)
    users = list(result.scalars().all())

    return UserList(
        items=[UserResponse.model_validate(u) for u in users],
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
        pages=math.ceil(total / pagination.page_size) if total > 0 else 0,
    )


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    request: Request,
    body: UserCreate,
    admin: AdminUser,
    db: DbSession,
) -> UserResponse:
    """Create a new local user.

    Admin only.
    """
    ip_address, user_agent = get_client_info(request)

    # Check if email already exists
    existing = await db.execute(
        select(User).where(User.email == body.email.lower())
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A user with this email already exists",
        )

    # Validate password
    try:
        validate_password_policy(body.password)
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=e.message,
        )

    # Create user
    user = User(
        email=body.email.lower(),
        name=body.name,
        role=body.role.value,
        is_active=True,
        is_local=True,
        hashed_password=hash_password(body.password),
    )

    db.add(user)

    # Log the event
    audit_log = AuthAuditLog.create_event(
        event_type=AuthEventType.USER_CREATED,
        user_id=user.id,
        email=user.email,
        ip_address=ip_address,
        user_agent=user_agent,
        success=True,
        event_details={
            "admin_id": admin.sub,
            "role": user.role,
        },
    )
    db.add(audit_log)

    await db.commit()
    await db.refresh(user)

    return UserResponse.model_validate(user)


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: uuid.UUID,
    _admin: AdminUser,
    db: DbSession,
) -> UserResponse:
    """Get a user by ID.

    Admin only.
    """
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    return UserResponse.model_validate(user)


@router.patch("/{user_id}", response_model=UserResponse)
async def update_user(
    request: Request,
    user_id: uuid.UUID,
    body: UserUpdate,
    admin: AdminUser,
    db: DbSession,
) -> UserResponse:
    """Update a user.

    Admin only.
    """
    ip_address, user_agent = get_client_info(request)

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    # Track changes for audit log
    changes = {}

    # Update fields if provided
    if body.email is not None:
        new_email = body.email.lower()
        if new_email != user.email:
            # Check if new email is already in use
            existing = await db.execute(
                select(User).where(User.email == new_email, User.id != user_id)
            )
            if existing.scalar_one_or_none():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="A user with this email already exists",
                )
            changes["email"] = {"old": user.email, "new": new_email}
            user.email = new_email

    if body.name is not None and body.name != user.name:
        changes["name"] = {"old": user.name, "new": body.name}
        user.name = body.name

    if body.role is not None and body.role.value != user.role:
        changes["role"] = {"old": user.role, "new": body.role.value}
        user.role = body.role.value

    if body.is_active is not None and body.is_active != user.is_active:
        changes["is_active"] = {"old": user.is_active, "new": body.is_active}
        user.is_active = body.is_active

        # If deactivating, revoke all sessions
        if not body.is_active:
            await db.execute(
                update(AuthSession)
                .where(
                    AuthSession.user_id == user_id,
                    AuthSession.revoked_at.is_(None),
                )
                .values(revoked_at=datetime.now(timezone.utc))
            )

    # Log the update
    if changes:
        audit_log = AuthAuditLog.create_event(
            event_type=AuthEventType.USER_UPDATED,
            user_id=user.id,
            email=user.email,
            ip_address=ip_address,
            user_agent=user_agent,
            success=True,
            event_details={
                "admin_id": admin.sub,
                "changes": changes,
            },
        )
        db.add(audit_log)

    await db.commit()
    await db.refresh(user)

    return UserResponse.model_validate(user)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_user(
    request: Request,
    user_id: uuid.UUID,
    admin: AdminUser,
    db: DbSession,
) -> None:
    """Deactivate a user (soft delete).

    Admin only. This revokes all active sessions.
    """
    ip_address, user_agent = get_client_info(request)

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    # Prevent self-deactivation
    if str(user_id) == admin.sub:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot deactivate your own account",
        )

    # Deactivate user
    user.is_active = False

    # Revoke all sessions
    await db.execute(
        update(AuthSession)
        .where(
            AuthSession.user_id == user_id,
            AuthSession.revoked_at.is_(None),
        )
        .values(revoked_at=datetime.now(timezone.utc))
    )

    # Log the event
    audit_log = AuthAuditLog.create_event(
        event_type=AuthEventType.USER_DEACTIVATED,
        user_id=user.id,
        email=user.email,
        ip_address=ip_address,
        user_agent=user_agent,
        success=True,
        event_details={"admin_id": admin.sub},
    )
    db.add(audit_log)

    await db.commit()


@router.post("/{user_id}/reset-password", status_code=status.HTTP_204_NO_CONTENT)
async def reset_user_password(
    request: Request,
    user_id: uuid.UUID,
    body: PasswordResetRequest,
    admin: AdminUser,
    db: DbSession,
) -> None:
    """Reset a user's password.

    Admin only. This revokes all active sessions.
    """
    from flowlens.services.auth_service import AuthService

    ip_address, user_agent = get_client_info(request)

    auth_service = AuthService(db)

    try:
        await auth_service.reset_password(
            user_id=user_id,
            new_password=body.new_password,
            admin_id=uuid.UUID(admin.sub),
            ip_address=ip_address,
            user_agent=user_agent,
        )
    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=e.message,
        )


@router.post("/{user_id}/unlock", status_code=status.HTTP_204_NO_CONTENT)
async def unlock_user(
    request: Request,
    user_id: uuid.UUID,
    admin: AdminUser,
    db: DbSession,
) -> None:
    """Unlock a locked user account.

    Admin only.
    """
    ip_address, user_agent = get_client_info(request)

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    # Unlock the account
    user.locked_until = None
    user.failed_login_attempts = 0

    # Log the event
    audit_log = AuthAuditLog.create_event(
        event_type=AuthEventType.ACCOUNT_UNLOCKED,
        user_id=user.id,
        email=user.email,
        ip_address=ip_address,
        user_agent=user_agent,
        success=True,
        event_details={"admin_id": admin.sub},
    )
    db.add(audit_log)

    await db.commit()

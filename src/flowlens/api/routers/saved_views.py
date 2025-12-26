"""Saved Views API endpoints for topology view management."""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select, update

from flowlens.api.dependencies import AuthenticatedUser, DbSession, Pagination
from flowlens.models.saved_view import SavedView
from flowlens.schemas.saved_view import (
    SavedViewCreate,
    SavedViewResponse,
    SavedViewSummary,
    SavedViewUpdate,
)

router = APIRouter(prefix="/saved-views", tags=["saved-views"])


@router.get("", response_model=list[SavedViewSummary])
async def list_saved_views(
    db: DbSession,
    user: AuthenticatedUser,
    pagination: Pagination,
    include_public: bool = True,
) -> list[SavedViewSummary]:
    """List saved views.

    Returns user's own views and optionally public views.
    """
    # Build query
    query = select(SavedView)

    # Filter by ownership or public
    conditions = []
    if user.sub:
        conditions.append(SavedView.created_by == user.sub)
    if include_public:
        conditions.append(SavedView.is_public == True)

    if conditions:
        from sqlalchemy import or_
        query = query.where(or_(*conditions))

    # Order by access count (most used first), then created date
    query = query.order_by(
        SavedView.is_default.desc(),
        SavedView.access_count.desc(),
        SavedView.created_at.desc(),
    )

    # Apply pagination
    query = query.offset(pagination.offset).limit(pagination.limit)

    result = await db.execute(query)
    views = result.scalars().all()

    return [SavedViewSummary.model_validate(v) for v in views]


@router.post("", response_model=SavedViewResponse, status_code=status.HTTP_201_CREATED)
async def create_saved_view(
    view_data: SavedViewCreate,
    db: DbSession,
    user: AuthenticatedUser,
) -> SavedViewResponse:
    """Create a new saved view."""
    # If setting as default, unset other defaults for this user
    if view_data.is_default:
        await db.execute(
            update(SavedView)
            .where(SavedView.created_by == user.sub)
            .where(SavedView.is_default == True)
            .values(is_default=False)
        )

    # Create view
    view = SavedView(
        name=view_data.name,
        description=view_data.description,
        created_by=user.sub,
        is_public=view_data.is_public,
        is_default=view_data.is_default,
        config=view_data.config.model_dump(),
    )

    db.add(view)
    await db.commit()
    await db.refresh(view)

    return SavedViewResponse.model_validate(view)


@router.get("/{view_id}", response_model=SavedViewResponse)
async def get_saved_view(
    view_id: UUID,
    db: DbSession,
    user: AuthenticatedUser,
) -> SavedViewResponse:
    """Get a saved view by ID.

    Also increments the access count.
    """
    result = await db.execute(
        select(SavedView).where(SavedView.id == view_id)
    )
    view = result.scalar_one_or_none()

    if not view:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Saved view {view_id} not found",
        )

    # Check access permissions
    if not view.is_public and view.created_by != user.sub:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this view",
        )

    # Update access tracking
    view.access_count += 1
    view.last_accessed_at = datetime.utcnow()
    await db.commit()
    await db.refresh(view)

    return SavedViewResponse.model_validate(view)


@router.patch("/{view_id}", response_model=SavedViewResponse)
async def update_saved_view(
    view_id: UUID,
    view_data: SavedViewUpdate,
    db: DbSession,
    user: AuthenticatedUser,
) -> SavedViewResponse:
    """Update a saved view."""
    result = await db.execute(
        select(SavedView).where(SavedView.id == view_id)
    )
    view = result.scalar_one_or_none()

    if not view:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Saved view {view_id} not found",
        )

    # Only owner can update
    if view.created_by != user.sub:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only update your own views",
        )

    # If setting as default, unset other defaults
    if view_data.is_default:
        await db.execute(
            update(SavedView)
            .where(SavedView.created_by == user.sub)
            .where(SavedView.id != view_id)
            .where(SavedView.is_default == True)
            .values(is_default=False)
        )

    # Update fields
    update_data = view_data.model_dump(exclude_unset=True)
    if "config" in update_data and update_data["config"]:
        update_data["config"] = view_data.config.model_dump()

    for field, value in update_data.items():
        setattr(view, field, value)

    await db.commit()
    await db.refresh(view)

    return SavedViewResponse.model_validate(view)


@router.delete("/{view_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_saved_view(
    view_id: UUID,
    db: DbSession,
    user: AuthenticatedUser,
) -> None:
    """Delete a saved view."""
    result = await db.execute(
        select(SavedView).where(SavedView.id == view_id)
    )
    view = result.scalar_one_or_none()

    if not view:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Saved view {view_id} not found",
        )

    # Only owner can delete
    if view.created_by != user.sub:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only delete your own views",
        )

    await db.delete(view)
    await db.commit()


@router.get("/default", response_model=SavedViewResponse | None)
async def get_default_view(
    db: DbSession,
    user: AuthenticatedUser,
) -> SavedViewResponse | None:
    """Get the user's default view if one exists."""
    result = await db.execute(
        select(SavedView)
        .where(SavedView.created_by == user.sub)
        .where(SavedView.is_default == True)
    )
    view = result.scalar_one_or_none()

    if not view:
        return None

    # Update access tracking
    view.access_count += 1
    view.last_accessed_at = datetime.utcnow()
    await db.commit()
    await db.refresh(view)

    return SavedViewResponse.model_validate(view)

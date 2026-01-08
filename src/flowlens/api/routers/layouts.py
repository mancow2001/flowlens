"""Application Layouts API endpoints for persistent view positioning."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, Path, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from flowlens.api.dependencies import DbSession, ViewerUser, AnalystUser
from flowlens.models.asset import Application
from flowlens.models.layout import ApplicationLayout, AssetGroup
from flowlens.schemas.layout import (
    ApplicationLayoutResponse,
    AssetGroupCreate,
    AssetGroupResponse,
    AssetGroupUpdate,
    LayoutPositionsUpdate,
    LayoutUpdate,
)

router = APIRouter(prefix="/applications/{application_id}/layouts", tags=["layouts"])


async def get_application_or_404(db: DbSession, application_id: UUID) -> Application:
    """Get application by ID or raise 404."""
    result = await db.execute(
        select(Application).where(Application.id == application_id)
    )
    application = result.scalar_one_or_none()
    if not application:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Application {application_id} not found",
        )
    return application


async def get_layout_or_404(
    db: DbSession, application_id: UUID, hop_depth: int
) -> ApplicationLayout:
    """Get layout by application ID and hop depth or raise 404."""
    result = await db.execute(
        select(ApplicationLayout)
        .where(ApplicationLayout.application_id == application_id)
        .where(ApplicationLayout.hop_depth == hop_depth)
        .options(selectinload(ApplicationLayout.asset_groups))
    )
    layout = result.scalar_one_or_none()
    if not layout:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Layout for application {application_id} at hop depth {hop_depth} not found",
        )
    return layout


@router.get("/{hop_depth}", response_model=ApplicationLayoutResponse | None)
async def get_layout(
    application_id: UUID,
    hop_depth: int = Path(..., ge=1, le=5),
    db: DbSession = None,
    _user: ViewerUser = None,
) -> ApplicationLayoutResponse | None:
    """Get layout for an application at a specific hop depth.

    Returns null if no layout has been saved yet.
    """
    await get_application_or_404(db, application_id)

    result = await db.execute(
        select(ApplicationLayout)
        .where(ApplicationLayout.application_id == application_id)
        .where(ApplicationLayout.hop_depth == hop_depth)
        .options(selectinload(ApplicationLayout.asset_groups))
    )
    layout = result.scalar_one_or_none()

    if not layout:
        return None

    return ApplicationLayoutResponse.from_model(layout)


@router.put("/{hop_depth}", response_model=ApplicationLayoutResponse)
async def save_layout(
    application_id: UUID,
    data: LayoutUpdate,
    hop_depth: int = Path(..., ge=1, le=5),
    db: DbSession = None,
    user: AnalystUser = None,
) -> ApplicationLayoutResponse:
    """Save or update layout for an application at a specific hop depth.

    Creates the layout if it doesn't exist, otherwise updates it.
    """
    await get_application_or_404(db, application_id)

    # Try to find existing layout
    result = await db.execute(
        select(ApplicationLayout)
        .where(ApplicationLayout.application_id == application_id)
        .where(ApplicationLayout.hop_depth == hop_depth)
        .options(selectinload(ApplicationLayout.asset_groups))
    )
    layout = result.scalar_one_or_none()

    if layout:
        # Update existing layout
        if data.positions is not None:
            # Convert NodePosition objects to dicts
            layout.positions = {k: {"x": v.x, "y": v.y} for k, v in data.positions.items()}
        if data.viewport is not None:
            layout.viewport = data.viewport.model_dump()
        layout.modified_by = user.email if hasattr(user, 'email') else str(user.id)
    else:
        # Create new layout
        positions = {}
        if data.positions:
            positions = {k: {"x": v.x, "y": v.y} for k, v in data.positions.items()}

        viewport = None
        if data.viewport:
            viewport = data.viewport.model_dump()

        layout = ApplicationLayout(
            application_id=application_id,
            hop_depth=hop_depth,
            positions=positions,
            viewport=viewport,
            modified_by=user.email if hasattr(user, 'email') else str(user.id),
        )
        db.add(layout)

    await db.commit()
    await db.refresh(layout)

    # Reload with groups
    result = await db.execute(
        select(ApplicationLayout)
        .where(ApplicationLayout.id == layout.id)
        .options(selectinload(ApplicationLayout.asset_groups))
    )
    layout = result.scalar_one()

    return ApplicationLayoutResponse.from_model(layout)


@router.patch("/{hop_depth}/positions", response_model=ApplicationLayoutResponse)
async def update_positions(
    application_id: UUID,
    data: LayoutPositionsUpdate,
    hop_depth: int = Path(..., ge=1, le=5),
    db: DbSession = None,
    user: AnalystUser = None,
) -> ApplicationLayoutResponse:
    """Batch update node positions for a layout.

    Merges with existing positions (doesn't replace the entire positions dict).
    Creates the layout if it doesn't exist.
    """
    await get_application_or_404(db, application_id)

    # Try to find existing layout
    result = await db.execute(
        select(ApplicationLayout)
        .where(ApplicationLayout.application_id == application_id)
        .where(ApplicationLayout.hop_depth == hop_depth)
        .options(selectinload(ApplicationLayout.asset_groups))
    )
    layout = result.scalar_one_or_none()

    # Convert NodePosition objects to dicts
    new_positions = {k: {"x": v.x, "y": v.y} for k, v in data.positions.items()}

    if layout:
        # Merge with existing positions
        existing_positions = layout.positions or {}
        existing_positions.update(new_positions)
        layout.positions = existing_positions
        layout.modified_by = user.email if hasattr(user, 'email') else str(user.id)
    else:
        # Create new layout with these positions
        layout = ApplicationLayout(
            application_id=application_id,
            hop_depth=hop_depth,
            positions=new_positions,
            modified_by=user.email if hasattr(user, 'email') else str(user.id),
        )
        db.add(layout)

    await db.commit()
    await db.refresh(layout)

    # Reload with groups
    result = await db.execute(
        select(ApplicationLayout)
        .where(ApplicationLayout.id == layout.id)
        .options(selectinload(ApplicationLayout.asset_groups))
    )
    layout = result.scalar_one()

    return ApplicationLayoutResponse.from_model(layout)


@router.delete("/{hop_depth}", status_code=status.HTTP_204_NO_CONTENT)
async def reset_layout(
    application_id: UUID,
    hop_depth: int = Path(..., ge=1, le=5),
    db: DbSession = None,
    _user: AnalystUser = None,
) -> None:
    """Reset (delete) layout for an application at a specific hop depth.

    After reset, the view will use auto-calculated positions.
    """
    await get_application_or_404(db, application_id)

    result = await db.execute(
        select(ApplicationLayout)
        .where(ApplicationLayout.application_id == application_id)
        .where(ApplicationLayout.hop_depth == hop_depth)
    )
    layout = result.scalar_one_or_none()

    if layout:
        await db.delete(layout)
        await db.commit()


# Asset Group endpoints


@router.post(
    "/{hop_depth}/groups",
    response_model=AssetGroupResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_group(
    application_id: UUID,
    data: AssetGroupCreate,
    hop_depth: int = Path(..., ge=1, le=5),
    db: DbSession = None,
    user: AnalystUser = None,
) -> AssetGroupResponse:
    """Create an asset group in a layout.

    Creates the layout if it doesn't exist.
    """
    await get_application_or_404(db, application_id)

    # Get or create layout
    result = await db.execute(
        select(ApplicationLayout)
        .where(ApplicationLayout.application_id == application_id)
        .where(ApplicationLayout.hop_depth == hop_depth)
    )
    layout = result.scalar_one_or_none()

    if not layout:
        # Create layout first
        layout = ApplicationLayout(
            application_id=application_id,
            hop_depth=hop_depth,
            positions={},
            modified_by=user.email if hasattr(user, 'email') else str(user.id),
        )
        db.add(layout)
        await db.flush()

    # Create group
    group = AssetGroup(
        layout_id=layout.id,
        name=data.name,
        color=data.color,
        asset_ids=data.asset_ids,
        position_x=data.position_x,
        position_y=data.position_y,
    )
    db.add(group)
    await db.commit()
    await db.refresh(group)

    return AssetGroupResponse.model_validate(group)


@router.get("/{hop_depth}/groups", response_model=list[AssetGroupResponse])
async def list_groups(
    application_id: UUID,
    hop_depth: int = Path(..., ge=1, le=5),
    db: DbSession = None,
    _user: ViewerUser = None,
) -> list[AssetGroupResponse]:
    """List all asset groups in a layout."""
    await get_application_or_404(db, application_id)

    result = await db.execute(
        select(ApplicationLayout)
        .where(ApplicationLayout.application_id == application_id)
        .where(ApplicationLayout.hop_depth == hop_depth)
        .options(selectinload(ApplicationLayout.asset_groups))
    )
    layout = result.scalar_one_or_none()

    if not layout:
        return []

    return [AssetGroupResponse.model_validate(g) for g in layout.asset_groups]


@router.patch("/{hop_depth}/groups/{group_id}", response_model=AssetGroupResponse)
async def update_group(
    application_id: UUID,
    group_id: UUID,
    data: AssetGroupUpdate,
    hop_depth: int = Path(..., ge=1, le=5),
    db: DbSession = None,
    user: AnalystUser = None,
) -> AssetGroupResponse:
    """Update an asset group."""
    await get_application_or_404(db, application_id)

    # Get the group
    result = await db.execute(
        select(AssetGroup)
        .join(ApplicationLayout)
        .where(ApplicationLayout.application_id == application_id)
        .where(ApplicationLayout.hop_depth == hop_depth)
        .where(AssetGroup.id == group_id)
    )
    group = result.scalar_one_or_none()

    if not group:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Asset group {group_id} not found",
        )

    # Update fields
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(group, field, value)

    # Update layout modified_by
    result = await db.execute(
        select(ApplicationLayout).where(ApplicationLayout.id == group.layout_id)
    )
    layout = result.scalar_one()
    layout.modified_by = user.email if hasattr(user, 'email') else str(user.id)

    await db.commit()
    await db.refresh(group)

    return AssetGroupResponse.model_validate(group)


@router.delete(
    "/{hop_depth}/groups/{group_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_group(
    application_id: UUID,
    group_id: UUID,
    hop_depth: int = Path(..., ge=1, le=5),
    db: DbSession = None,
    _user: AnalystUser = None,
) -> None:
    """Delete an asset group."""
    await get_application_or_404(db, application_id)

    # Get the group
    result = await db.execute(
        select(AssetGroup)
        .join(ApplicationLayout)
        .where(ApplicationLayout.application_id == application_id)
        .where(ApplicationLayout.hop_depth == hop_depth)
        .where(AssetGroup.id == group_id)
    )
    group = result.scalar_one_or_none()

    if not group:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Asset group {group_id} not found",
        )

    await db.delete(group)
    await db.commit()

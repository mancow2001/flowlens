"""Maintenance Windows API endpoints for alert suppression."""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select, text

from flowlens.api.dependencies import AuthenticatedUser, DbSession, Pagination
from flowlens.models.maintenance_window import MaintenanceWindow
from flowlens.schemas.maintenance import (
    ActiveMaintenanceCheck,
    MaintenanceWindowCreate,
    MaintenanceWindowList,
    MaintenanceWindowResponse,
    MaintenanceWindowSummary,
    MaintenanceWindowUpdate,
)

router = APIRouter(prefix="/maintenance", tags=["maintenance"])


@router.get("", response_model=MaintenanceWindowList)
async def list_maintenance_windows(
    db: DbSession,
    user: AuthenticatedUser,
    pagination: Pagination,
    is_active: bool | None = Query(None, alias="isActive"),
    include_past: bool = Query(False, alias="includePast"),
    environment: str | None = None,
    datacenter: str | None = None,
) -> MaintenanceWindowList:
    """List maintenance windows with filtering and pagination."""
    query = select(MaintenanceWindow)

    if is_active is not None:
        query = query.where(MaintenanceWindow.is_active == is_active)

    # By default, don't include past windows
    if not include_past:
        query = query.where(MaintenanceWindow.end_time >= datetime.utcnow())

    if environment:
        query = query.where(MaintenanceWindow.environments.any(environment))
    if datacenter:
        query = query.where(MaintenanceWindow.datacenters.any(datacenter))

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query) or 0

    # Order by start_time
    query = query.order_by(MaintenanceWindow.start_time.asc())

    # Apply pagination
    query = query.offset(pagination.offset).limit(pagination.page_size)

    result = await db.execute(query)
    windows = result.scalars().all()

    items = [
        MaintenanceWindowSummary(
            id=w.id,
            name=w.name,
            start_time=w.start_time,
            end_time=w.end_time,
            is_active=w.is_active,
            is_recurring=w.is_recurring,
            suppress_alerts=w.suppress_alerts,
            environments=w.environments,
            datacenters=w.datacenters,
            asset_count=len(w.asset_ids) if w.asset_ids else 0,
            suppressed_alerts_count=w.suppressed_alerts_count,
        )
        for w in windows
    ]

    return MaintenanceWindowList(
        items=items,
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
    )


@router.get("/active", response_model=list[MaintenanceWindowSummary])
async def get_active_windows(
    db: DbSession,
    user: AuthenticatedUser,
) -> list[MaintenanceWindowSummary]:
    """Get all currently active maintenance windows."""
    now = datetime.utcnow()
    query = select(MaintenanceWindow).where(
        MaintenanceWindow.is_active == True,
        MaintenanceWindow.start_time <= now,
        MaintenanceWindow.end_time >= now,
    ).order_by(MaintenanceWindow.end_time.asc())

    result = await db.execute(query)
    windows = result.scalars().all()

    return [
        MaintenanceWindowSummary(
            id=w.id,
            name=w.name,
            start_time=w.start_time,
            end_time=w.end_time,
            is_active=w.is_active,
            is_recurring=w.is_recurring,
            suppress_alerts=w.suppress_alerts,
            environments=w.environments,
            datacenters=w.datacenters,
            asset_count=len(w.asset_ids) if w.asset_ids else 0,
            suppressed_alerts_count=w.suppressed_alerts_count,
        )
        for w in windows
    ]


@router.get("/check/{asset_id}", response_model=ActiveMaintenanceCheck)
async def check_asset_maintenance(
    asset_id: UUID,
    db: DbSession,
    user: AuthenticatedUser,
    environment: str | None = None,
    datacenter: str | None = None,
) -> ActiveMaintenanceCheck:
    """Check if an asset is currently in a maintenance window."""
    # Use the database function
    result = await db.execute(
        text("""
            SELECT * FROM get_active_maintenance_windows(
                :asset_id,
                :environment,
                :datacenter
            )
        """),
        {
            "asset_id": asset_id,
            "environment": environment,
            "datacenter": datacenter,
        },
    )
    rows = result.fetchall()

    windows = [
        MaintenanceWindowSummary(
            id=row.id,
            name=row.name,
            start_time=row.start_time,
            end_time=row.end_time,
            is_active=True,
            is_recurring=False,
            suppress_alerts=row.suppress_alerts,
            environments=None,
            datacenters=None,
            asset_count=0,
            suppressed_alerts_count=0,
        )
        for row in rows
    ]

    return ActiveMaintenanceCheck(
        asset_id=asset_id,
        in_maintenance=len(windows) > 0,
        windows=windows,
    )


@router.get("/{window_id}", response_model=MaintenanceWindowResponse)
async def get_maintenance_window(
    window_id: UUID,
    db: DbSession,
    user: AuthenticatedUser,
) -> MaintenanceWindowResponse:
    """Get maintenance window by ID."""
    result = await db.execute(
        select(MaintenanceWindow).where(MaintenanceWindow.id == window_id)
    )
    window = result.scalar_one_or_none()

    if not window:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Maintenance window {window_id} not found",
        )

    return MaintenanceWindowResponse(
        id=window.id,
        name=window.name,
        description=window.description,
        asset_ids=window.asset_ids,
        environments=window.environments,
        datacenters=window.datacenters,
        start_time=window.start_time,
        end_time=window.end_time,
        is_recurring=window.is_recurring,
        recurrence_rule=window.recurrence_rule,
        suppress_alerts=window.suppress_alerts,
        suppress_notifications=window.suppress_notifications,
        is_active=window.is_active,
        created_by=window.created_by,
        suppressed_alerts_count=window.suppressed_alerts_count,
        tags=window.tags,
        created_at=window.created_at,
        updated_at=window.updated_at,
    )


@router.post("", response_model=MaintenanceWindowResponse, status_code=status.HTTP_201_CREATED)
async def create_maintenance_window(
    data: MaintenanceWindowCreate,
    db: DbSession,
    user: AuthenticatedUser,
) -> MaintenanceWindowResponse:
    """Create a new maintenance window."""
    window = MaintenanceWindow(
        name=data.name,
        description=data.description,
        asset_ids=data.asset_ids,
        environments=data.environments,
        datacenters=data.datacenters,
        start_time=data.start_time,
        end_time=data.end_time,
        is_recurring=data.is_recurring,
        recurrence_rule=data.recurrence_rule,
        suppress_alerts=data.suppress_alerts,
        suppress_notifications=data.suppress_notifications,
        created_by=data.created_by,
        tags=data.tags,
    )

    db.add(window)
    await db.flush()
    await db.refresh(window)

    return MaintenanceWindowResponse(
        id=window.id,
        name=window.name,
        description=window.description,
        asset_ids=window.asset_ids,
        environments=window.environments,
        datacenters=window.datacenters,
        start_time=window.start_time,
        end_time=window.end_time,
        is_recurring=window.is_recurring,
        recurrence_rule=window.recurrence_rule,
        suppress_alerts=window.suppress_alerts,
        suppress_notifications=window.suppress_notifications,
        is_active=window.is_active,
        created_by=window.created_by,
        suppressed_alerts_count=window.suppressed_alerts_count,
        tags=window.tags,
        created_at=window.created_at,
        updated_at=window.updated_at,
    )


@router.patch("/{window_id}", response_model=MaintenanceWindowResponse)
async def update_maintenance_window(
    window_id: UUID,
    data: MaintenanceWindowUpdate,
    db: DbSession,
    user: AuthenticatedUser,
) -> MaintenanceWindowResponse:
    """Update a maintenance window."""
    result = await db.execute(
        select(MaintenanceWindow).where(MaintenanceWindow.id == window_id)
    )
    window = result.scalar_one_or_none()

    if not window:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Maintenance window {window_id} not found",
        )

    # Update fields
    update_data = data.model_dump(exclude_unset=True)

    # Validate time range if both are being updated
    if 'start_time' in update_data and 'end_time' in update_data:
        if update_data['end_time'] <= update_data['start_time']:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="end_time must be after start_time",
            )
    elif 'end_time' in update_data and update_data['end_time'] <= window.start_time:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="end_time must be after start_time",
        )
    elif 'start_time' in update_data and window.end_time <= update_data['start_time']:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="start_time must be before end_time",
        )

    for field, value in update_data.items():
        setattr(window, field, value)

    await db.flush()
    await db.refresh(window)

    return MaintenanceWindowResponse(
        id=window.id,
        name=window.name,
        description=window.description,
        asset_ids=window.asset_ids,
        environments=window.environments,
        datacenters=window.datacenters,
        start_time=window.start_time,
        end_time=window.end_time,
        is_recurring=window.is_recurring,
        recurrence_rule=window.recurrence_rule,
        suppress_alerts=window.suppress_alerts,
        suppress_notifications=window.suppress_notifications,
        is_active=window.is_active,
        created_by=window.created_by,
        suppressed_alerts_count=window.suppressed_alerts_count,
        tags=window.tags,
        created_at=window.created_at,
        updated_at=window.updated_at,
    )


@router.delete("/{window_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_maintenance_window(
    window_id: UUID,
    db: DbSession,
    user: AuthenticatedUser,
) -> None:
    """Delete a maintenance window."""
    result = await db.execute(
        select(MaintenanceWindow).where(MaintenanceWindow.id == window_id)
    )
    window = result.scalar_one_or_none()

    if not window:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Maintenance window {window_id} not found",
        )

    await db.delete(window)
    await db.flush()


@router.post("/{window_id}/cancel", response_model=MaintenanceWindowResponse)
async def cancel_maintenance_window(
    window_id: UUID,
    db: DbSession,
    user: AuthenticatedUser,
) -> MaintenanceWindowResponse:
    """Cancel (deactivate) a maintenance window."""
    result = await db.execute(
        select(MaintenanceWindow).where(MaintenanceWindow.id == window_id)
    )
    window = result.scalar_one_or_none()

    if not window:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Maintenance window {window_id} not found",
        )

    window.is_active = False
    await db.flush()
    await db.refresh(window)

    return MaintenanceWindowResponse(
        id=window.id,
        name=window.name,
        description=window.description,
        asset_ids=window.asset_ids,
        environments=window.environments,
        datacenters=window.datacenters,
        start_time=window.start_time,
        end_time=window.end_time,
        is_recurring=window.is_recurring,
        recurrence_rule=window.recurrence_rule,
        suppress_alerts=window.suppress_alerts,
        suppress_notifications=window.suppress_notifications,
        is_active=window.is_active,
        created_by=window.created_by,
        suppressed_alerts_count=window.suppressed_alerts_count,
        tags=window.tags,
        created_at=window.created_at,
        updated_at=window.updated_at,
    )

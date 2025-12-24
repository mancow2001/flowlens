"""Changes API router.

Endpoints for viewing and managing change events.
"""

from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from flowlens.api.dependencies import DbSession, Pagination
from flowlens.common.logging import get_logger
from flowlens.models.asset import Asset
from flowlens.models.change import Alert, ChangeEvent, ChangeType
from flowlens.models.dependency import Dependency
from flowlens.schemas.change import (
    AssetChangeDetail,
    ChangeEventCreate,
    ChangeEventListResponse,
    ChangeEventResponse,
    ChangeEventSummary,
    ChangeTimeline,
    ChangeTypeCount,
    DependencyChangeDetail,
)

logger = get_logger(__name__)
router = APIRouter(prefix="/changes", tags=["changes"])


@router.get("", response_model=ChangeEventListResponse)
async def list_changes(
    db: AsyncSession = Depends(DbSession),
    pagination: Pagination = Depends(),
    change_type: str | None = None,
    asset_id: UUID | None = None,
    dependency_id: UUID | None = None,
    is_processed: bool | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
) -> ChangeEventListResponse:
    """List change events with filtering and pagination.

    Args:
        db: Database session.
        pagination: Pagination parameters.
        change_type: Filter by change type.
        asset_id: Filter by related asset.
        dependency_id: Filter by related dependency.
        is_processed: Filter by processed status.
        since: Filter by detection time start.
        until: Filter by detection time end.

    Returns:
        Paginated list of change events.
    """
    # Build query
    query = select(ChangeEvent).order_by(ChangeEvent.detected_at.desc())

    if change_type:
        query = query.where(ChangeEvent.change_type == change_type)
    if asset_id:
        query = query.where(ChangeEvent.asset_id == asset_id)
    if dependency_id:
        query = query.where(ChangeEvent.dependency_id == dependency_id)
    if is_processed is not None:
        query = query.where(ChangeEvent.is_processed == is_processed)
    if since:
        query = query.where(ChangeEvent.detected_at >= since)
    if until:
        query = query.where(ChangeEvent.detected_at <= until)

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query) or 0

    # Apply pagination
    query = query.offset(pagination.offset).limit(pagination.limit)

    # Execute query
    result = await db.execute(query)
    events = result.scalars().all()

    # Get alert counts for each event
    event_responses = []
    for event in events:
        alert_count = await db.scalar(
            select(func.count(Alert.id)).where(Alert.change_event_id == event.id)
        ) or 0

        response = ChangeEventResponse.model_validate(event)
        response.alerts_count = alert_count
        event_responses.append(response)

    # Get summary
    summary = await _get_change_summary(db)

    return ChangeEventListResponse(
        items=event_responses,
        total=total,
        page=pagination.page,
        page_size=pagination.limit,
        summary=summary,
    )


@router.get("/summary", response_model=ChangeEventSummary)
async def get_change_summary(
    db: AsyncSession = Depends(DbSession),
) -> ChangeEventSummary:
    """Get summary of change event counts.

    Args:
        db: Database session.

    Returns:
        Change event summary.
    """
    return await _get_change_summary(db)


async def _get_change_summary(db: AsyncSession) -> ChangeEventSummary:
    """Get change event summary from database.

    Args:
        db: Database session.

    Returns:
        Change event summary counts.
    """
    # Total count
    total = await db.scalar(select(func.count(ChangeEvent.id))) or 0

    # Count by type
    type_result = await db.execute(
        select(ChangeEvent.change_type, func.count(ChangeEvent.id))
        .group_by(ChangeEvent.change_type)
    )
    by_type = {row[0]: row[1] for row in type_result.fetchall()}

    # Unprocessed count
    unprocessed = await db.scalar(
        select(func.count(ChangeEvent.id)).where(ChangeEvent.is_processed == False)
    ) or 0

    # Last 24 hours
    since_24h = datetime.utcnow() - timedelta(hours=24)
    last_24h = await db.scalar(
        select(func.count(ChangeEvent.id)).where(ChangeEvent.detected_at >= since_24h)
    ) or 0

    # Last 7 days
    since_7d = datetime.utcnow() - timedelta(days=7)
    last_7d = await db.scalar(
        select(func.count(ChangeEvent.id)).where(ChangeEvent.detected_at >= since_7d)
    ) or 0

    return ChangeEventSummary(
        total=total,
        by_type=by_type,
        unprocessed=unprocessed,
        last_24h=last_24h,
        last_7d=last_7d,
    )


@router.get("/types", response_model=list[ChangeTypeCount])
async def list_change_types(
    db: AsyncSession = Depends(DbSession),
) -> list[ChangeTypeCount]:
    """Get counts of each change type.

    Args:
        db: Database session.

    Returns:
        List of change type counts.
    """
    result = await db.execute(
        select(ChangeEvent.change_type, func.count(ChangeEvent.id))
        .group_by(ChangeEvent.change_type)
        .order_by(func.count(ChangeEvent.id).desc())
    )

    return [
        ChangeTypeCount(change_type=row[0], count=row[1])
        for row in result.fetchall()
    ]


@router.get("/timeline", response_model=ChangeTimeline)
async def get_change_timeline(
    db: AsyncSession = Depends(DbSession),
    period: str = Query("day", pattern="^(hour|day|week)$"),
    days: int = Query(7, ge=1, le=90),
) -> ChangeTimeline:
    """Get change event timeline for visualization.

    Args:
        db: Database session.
        period: Aggregation period (hour, day, week).
        days: Number of days to include.

    Returns:
        Timeline data.
    """
    since = datetime.utcnow() - timedelta(days=days)

    # Truncate function based on period
    if period == "hour":
        trunc_func = func.date_trunc("hour", ChangeEvent.detected_at)
    elif period == "week":
        trunc_func = func.date_trunc("week", ChangeEvent.detected_at)
    else:
        trunc_func = func.date_trunc("day", ChangeEvent.detected_at)

    result = await db.execute(
        select(
            trunc_func.label("period"),
            ChangeEvent.change_type,
            func.count(ChangeEvent.id).label("count"),
        )
        .where(ChangeEvent.detected_at >= since)
        .group_by(trunc_func, ChangeEvent.change_type)
        .order_by(trunc_func)
    )

    # Transform to timeline format
    timeline_data: dict[str, dict[str, int]] = {}
    for row in result.fetchall():
        period_str = row.period.isoformat() if row.period else "unknown"
        if period_str not in timeline_data:
            timeline_data[period_str] = {"timestamp": period_str, "total": 0}
        timeline_data[period_str][row.change_type] = row.count
        timeline_data[period_str]["total"] += row.count

    return ChangeTimeline(
        period=period,
        data=list(timeline_data.values()),
    )


@router.get("/{change_id}", response_model=ChangeEventResponse)
async def get_change(
    change_id: UUID,
    db: AsyncSession = Depends(DbSession),
) -> ChangeEventResponse:
    """Get a specific change event by ID.

    Args:
        change_id: Change event ID.
        db: Database session.

    Returns:
        Change event details.
    """
    result = await db.execute(
        select(ChangeEvent).where(ChangeEvent.id == change_id)
    )
    event = result.scalar_one_or_none()

    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Change event not found: {change_id}",
        )

    # Get alert count
    alert_count = await db.scalar(
        select(func.count(Alert.id)).where(Alert.change_event_id == event.id)
    ) or 0

    response = ChangeEventResponse.model_validate(event)
    response.alerts_count = alert_count

    return response


@router.get("/{change_id}/alerts", response_model=list[dict])
async def get_change_alerts(
    change_id: UUID,
    db: AsyncSession = Depends(DbSession),
) -> list[dict]:
    """Get alerts associated with a change event.

    Args:
        change_id: Change event ID.
        db: Database session.

    Returns:
        List of related alerts.
    """
    # Verify change exists
    event = await db.scalar(
        select(ChangeEvent.id).where(ChangeEvent.id == change_id)
    )

    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Change event not found: {change_id}",
        )

    result = await db.execute(
        select(Alert)
        .where(Alert.change_event_id == change_id)
        .order_by(Alert.created_at.desc())
    )
    alerts = result.scalars().all()

    return [
        {
            "id": str(a.id),
            "title": a.title,
            "message": a.message,
            "severity": a.severity,
            "is_acknowledged": a.is_acknowledged,
            "is_resolved": a.is_resolved,
            "created_at": a.created_at.isoformat(),
        }
        for a in alerts
    ]


@router.get("/dependency/{dependency_id}", response_model=list[DependencyChangeDetail])
async def get_dependency_changes(
    dependency_id: UUID,
    db: AsyncSession = Depends(DbSession),
    limit: int = Query(50, ge=1, le=200),
) -> list[DependencyChangeDetail]:
    """Get change history for a dependency.

    Args:
        dependency_id: Dependency ID.
        db: Database session.
        limit: Maximum number of changes.

    Returns:
        List of dependency changes.
    """
    # Get dependency details
    dep_result = await db.execute(
        select(Dependency).where(Dependency.id == dependency_id)
    )
    dep = dep_result.scalar_one_or_none()

    if not dep:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dependency not found: {dependency_id}",
        )

    # Get asset names
    src_asset = await db.scalar(
        select(Asset.name).where(Asset.id == dep.source_asset_id)
    ) or "Unknown"
    tgt_asset = await db.scalar(
        select(Asset.name).where(Asset.id == dep.target_asset_id)
    ) or "Unknown"

    # Get change events for this dependency
    result = await db.execute(
        select(ChangeEvent)
        .where(ChangeEvent.dependency_id == dependency_id)
        .order_by(ChangeEvent.detected_at.desc())
        .limit(limit)
    )
    events = result.scalars().all()

    return [
        DependencyChangeDetail(
            dependency_id=dependency_id,
            source_asset_id=dep.source_asset_id,
            source_asset_name=src_asset,
            target_asset_id=dep.target_asset_id,
            target_asset_name=tgt_asset,
            target_port=dep.target_port,
            protocol=dep.protocol,
            change_type=e.change_type,
            first_seen=dep.first_seen,
            last_seen=dep.last_seen,
            bytes_total=dep.bytes_total,
        )
        for e in events
    ]


@router.get("/asset/{asset_id}", response_model=list[AssetChangeDetail])
async def get_asset_changes(
    asset_id: UUID,
    db: AsyncSession = Depends(DbSession),
    limit: int = Query(50, ge=1, le=200),
) -> list[AssetChangeDetail]:
    """Get change history for an asset.

    Args:
        asset_id: Asset ID.
        db: Database session.
        limit: Maximum number of changes.

    Returns:
        List of asset changes.
    """
    # Get asset details
    asset_result = await db.execute(
        select(Asset).where(Asset.id == asset_id)
    )
    asset = asset_result.scalar_one_or_none()

    if not asset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Asset not found: {asset_id}",
        )

    # Get change events for this asset
    result = await db.execute(
        select(ChangeEvent)
        .where(ChangeEvent.asset_id == asset_id)
        .order_by(ChangeEvent.detected_at.desc())
        .limit(limit)
    )
    events = result.scalars().all()

    return [
        AssetChangeDetail(
            asset_id=asset_id,
            asset_name=asset.name,
            asset_type=asset.asset_type.value if asset.asset_type else None,
            ip_address=asset.ip_address,
            change_type=e.change_type,
            previous_state=e.previous_state,
            new_state=e.new_state,
        )
        for e in events
    ]


@router.post("/{change_id}/process", response_model=ChangeEventResponse)
async def mark_change_processed(
    change_id: UUID,
    db: AsyncSession = Depends(DbSession),
) -> ChangeEventResponse:
    """Mark a change event as processed.

    Args:
        change_id: Change event ID.
        db: Database session.

    Returns:
        Updated change event.
    """
    result = await db.execute(
        select(ChangeEvent).where(ChangeEvent.id == change_id)
    )
    event = result.scalar_one_or_none()

    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Change event not found: {change_id}",
        )

    event.is_processed = True
    event.processed_at = datetime.utcnow()

    await db.commit()
    await db.refresh(event)

    return ChangeEventResponse.model_validate(event)

"""Dependency API endpoints."""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from flowlens.api.dependencies import (
    AdminUser,
    AnalystUser,
    DbSession,
    Pagination,
    Sorting,
    TimeRange,
    ViewerUser,
)
from flowlens.models.asset import Asset
from flowlens.models.dependency import Dependency, DependencyHistory
from flowlens.schemas.dependency import (
    AssetInfo,
    DependencyCreate,
    DependencyHistoryEntry,
    DependencyList,
    DependencyResponse,
    DependencySummary,
    DependencyUpdate,
    DependencyWithAssets,
)

router = APIRouter(prefix="/dependencies", tags=["dependencies"])


@router.get("", response_model=DependencyList)
async def list_dependencies(
    db: DbSession,
    _user: ViewerUser,
    pagination: Pagination,
    sorting: Sorting,
    time_range: TimeRange,
    source_asset_id: UUID | None = Query(None, alias="sourceAssetId"),
    target_asset_id: UUID | None = Query(None, alias="targetAssetId"),
    target_port: int | None = Query(None, alias="targetPort", ge=0, le=65535),
    protocol: int | None = Query(None, ge=0, le=255),
    is_critical: bool | None = Query(None, alias="isCritical"),
    is_confirmed: bool | None = Query(None, alias="isConfirmed"),
    include_historical: bool = Query(False, alias="includeHistorical"),
) -> DependencyList:
    """List dependencies with filtering and pagination."""
    # Build query
    query = select(Dependency)

    if not include_historical:
        query = query.where(Dependency.valid_to.is_(None))

    # Apply filters
    if source_asset_id:
        query = query.where(Dependency.source_asset_id == source_asset_id)
    if target_asset_id:
        query = query.where(Dependency.target_asset_id == target_asset_id)
    if target_port is not None:
        query = query.where(Dependency.target_port == target_port)
    if protocol is not None:
        query = query.where(Dependency.protocol == protocol)
    if is_critical is not None:
        query = query.where(Dependency.is_critical == is_critical)
    if is_confirmed is not None:
        query = query.where(Dependency.is_confirmed == is_confirmed)

    # Time range filter
    if time_range.start_time:
        query = query.where(Dependency.last_seen >= time_range.start_time)
    if time_range.end_time:
        query = query.where(Dependency.first_seen <= time_range.end_time)

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query) or 0

    # Apply sorting
    if sorting.sort_by:
        sort_column = getattr(Dependency, sorting.sort_by, Dependency.last_seen)
        if sorting.ascending:
            query = query.order_by(sort_column.asc())
        else:
            query = query.order_by(sort_column.desc())
    else:
        query = query.order_by(Dependency.last_seen.desc())

    # Apply pagination
    query = query.offset(pagination.offset).limit(pagination.page_size)

    # Load related assets
    query = query.options(
        selectinload(Dependency.source_asset),
        selectinload(Dependency.target_asset),
    )

    # Execute query
    result = await db.execute(query)
    dependencies = result.scalars().all()

    # Build response with asset info
    items = []
    for d in dependencies:
        source_info = None
        target_info = None

        if d.source_asset:
            source_info = AssetInfo(
                id=d.source_asset.id,
                name=d.source_asset.name,
                ip_address=str(d.source_asset.ip_address),
                hostname=d.source_asset.hostname,
                is_critical=d.source_asset.is_critical,
            )

        if d.target_asset:
            target_info = AssetInfo(
                id=d.target_asset.id,
                name=d.target_asset.name,
                ip_address=str(d.target_asset.ip_address),
                hostname=d.target_asset.hostname,
                is_critical=d.target_asset.is_critical,
            )

        items.append(DependencySummary(
            id=d.id,
            source_asset_id=d.source_asset_id,
            target_asset_id=d.target_asset_id,
            target_port=d.target_port,
            protocol=d.protocol,
            bytes_total=d.bytes_total,
            bytes_last_24h=d.bytes_last_24h,
            last_seen=d.last_seen,
            valid_to=d.valid_to,
            is_critical=d.is_critical,
            source_asset=source_info,
            target_asset=target_info,
        ))

    return DependencyList(
        items=items,
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
        pages=(total + pagination.page_size - 1) // pagination.page_size,
    )


@router.get("/{dependency_id}", response_model=DependencyWithAssets)
async def get_dependency(
    dependency_id: UUID,
    db: DbSession,
    _user: ViewerUser,
) -> DependencyWithAssets:
    """Get dependency by ID with asset info."""
    query = (
        select(Dependency)
        .where(Dependency.id == dependency_id)
        .options(
            selectinload(Dependency.source_asset),
            selectinload(Dependency.target_asset),
        )
    )
    result = await db.execute(query)
    dep = result.scalar_one_or_none()

    if not dep:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dependency {dependency_id} not found",
        )

    return DependencyWithAssets(
        id=dep.id,
        source_asset_id=dep.source_asset_id,
        target_asset_id=dep.target_asset_id,
        target_port=dep.target_port,
        protocol=dep.protocol,
        dependency_type=dep.dependency_type,
        is_critical=dep.is_critical,
        is_confirmed=dep.is_confirmed,
        is_ignored=dep.is_ignored,
        description=dep.description,
        tags=dep.tags,
        metadata=dep.metadata,
        bytes_total=dep.bytes_total,
        packets_total=dep.packets_total,
        flows_total=dep.flows_total,
        bytes_last_24h=dep.bytes_last_24h,
        bytes_last_7d=dep.bytes_last_7d,
        first_seen=dep.first_seen,
        last_seen=dep.last_seen,
        valid_from=dep.valid_from,
        valid_to=dep.valid_to,
        avg_latency_ms=dep.avg_latency_ms,
        p95_latency_ms=dep.p95_latency_ms,
        discovered_by=dep.discovered_by,
        created_at=dep.created_at,
        updated_at=dep.updated_at,
        source_asset=AssetInfo(
            id=dep.source_asset.id,
            name=dep.source_asset.name,
            ip_address=str(dep.source_asset.ip_address),
            hostname=dep.source_asset.hostname,
            is_critical=dep.source_asset.is_critical,
        ),
        target_asset=AssetInfo(
            id=dep.target_asset.id,
            name=dep.target_asset.name,
            ip_address=str(dep.target_asset.ip_address),
            hostname=dep.target_asset.hostname,
            is_critical=dep.target_asset.is_critical,
        ),
    )


@router.post("", response_model=DependencyResponse, status_code=status.HTTP_201_CREATED)
async def create_dependency(
    data: DependencyCreate,
    db: DbSession,
    _user: AnalystUser,
) -> DependencyResponse:
    """Create a manual dependency."""
    # Verify source asset exists
    source = await db.execute(
        select(Asset).where(
            Asset.id == data.source_asset_id,
            Asset.deleted_at.is_(None),
        )
    )
    if not source.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Source asset {data.source_asset_id} not found",
        )

    # Verify target asset exists
    target = await db.execute(
        select(Asset).where(
            Asset.id == data.target_asset_id,
            Asset.deleted_at.is_(None),
        )
    )
    if not target.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Target asset {data.target_asset_id} not found",
        )

    # Check for existing dependency
    existing = await db.execute(
        select(Dependency).where(
            Dependency.source_asset_id == data.source_asset_id,
            Dependency.target_asset_id == data.target_asset_id,
            Dependency.target_port == data.target_port,
            Dependency.protocol == data.protocol,
            Dependency.valid_to.is_(None),
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Dependency already exists",
        )

    # Create dependency
    dep = Dependency(
        source_asset_id=data.source_asset_id,
        target_asset_id=data.target_asset_id,
        target_port=data.target_port,
        protocol=data.protocol,
        dependency_type=data.dependency_type,
        is_critical=data.is_critical,
        is_confirmed=True,  # Manual dependencies are confirmed
        is_ignored=data.is_ignored,
        description=data.description,
        tags=data.tags,
        metadata=data.metadata,
        discovered_by="manual",
    )

    db.add(dep)
    await db.flush()
    await db.refresh(dep)

    return DependencyResponse.model_validate(dep)


@router.put("/{dependency_id}", response_model=DependencyResponse)
async def update_dependency(
    dependency_id: UUID,
    data: DependencyUpdate,
    db: DbSession,
    _user: AnalystUser,
) -> DependencyResponse:
    """Update a dependency."""
    result = await db.execute(
        select(Dependency).where(
            Dependency.id == dependency_id,
            Dependency.valid_to.is_(None),
        )
    )
    dep = result.scalar_one_or_none()

    if not dep:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dependency {dependency_id} not found",
        )

    # Update fields
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(dep, field, value)

    await db.flush()
    await db.refresh(dep)

    return DependencyResponse.model_validate(dep)


@router.delete("/{dependency_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_dependency(
    dependency_id: UUID,
    db: DbSession,
    _user: AdminUser,
) -> None:
    """Mark a dependency as invalid (soft delete)."""
    result = await db.execute(
        select(Dependency).where(
            Dependency.id == dependency_id,
            Dependency.valid_to.is_(None),
        )
    )
    dep = result.scalar_one_or_none()

    if not dep:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dependency {dependency_id} not found",
        )

    dep.invalidate()
    await db.flush()


@router.get("/{dependency_id}/history", response_model=list[DependencyHistoryEntry])
async def get_dependency_history(
    dependency_id: UUID,
    db: DbSession,
    _user: ViewerUser,
    limit: int = Query(50, ge=1, le=100),
) -> list[DependencyHistoryEntry]:
    """Get history of changes for a dependency."""
    result = await db.execute(
        select(DependencyHistory)
        .where(DependencyHistory.dependency_id == dependency_id)
        .order_by(DependencyHistory.changed_at.desc())
        .limit(limit)
    )
    history = result.scalars().all()

    return [DependencyHistoryEntry.model_validate(h) for h in history]


@router.get("/asset/{asset_id}/outbound", response_model=list[DependencySummary])
async def get_asset_outbound_dependencies(
    asset_id: UUID,
    db: DbSession,
    _user: ViewerUser,
) -> list[DependencySummary]:
    """Get all outbound dependencies of an asset (what it depends on)."""
    result = await db.execute(
        select(Dependency)
        .where(
            Dependency.source_asset_id == asset_id,
            Dependency.valid_to.is_(None),
        )
        .order_by(Dependency.bytes_last_24h.desc())
    )
    dependencies = result.scalars().all()

    return [DependencySummary.model_validate(d) for d in dependencies]


@router.get("/asset/{asset_id}/inbound", response_model=list[DependencySummary])
async def get_asset_inbound_dependencies(
    asset_id: UUID,
    db: DbSession,
    _user: ViewerUser,
) -> list[DependencySummary]:
    """Get all inbound dependencies of an asset (what depends on it)."""
    result = await db.execute(
        select(Dependency)
        .where(
            Dependency.target_asset_id == asset_id,
            Dependency.valid_to.is_(None),
        )
        .order_by(Dependency.bytes_last_24h.desc())
    )
    dependencies = result.scalars().all()

    return [DependencySummary.model_validate(d) for d in dependencies]


@router.post("/refresh-rolling-bytes", response_model=dict)
async def refresh_rolling_bytes(
    db: DbSession,
    _user: AnalystUser,
) -> dict:
    """Refresh bytes_last_24h and bytes_last_7d for all active dependencies.

    This recalculates rolling window metrics from flow aggregates.
    Useful for backfilling existing dependencies.
    """
    from flowlens.resolution.dependency_builder import DependencyBuilder

    builder = DependencyBuilder()
    updated = await builder.refresh_rolling_bytes(db)

    return {"updated": updated, "message": f"Refreshed rolling bytes for {updated} dependencies"}

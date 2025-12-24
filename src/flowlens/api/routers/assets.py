"""Asset API endpoints."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.orm import selectinload

from flowlens.api.dependencies import AuthenticatedUser, DbSession, Pagination, Sorting
from flowlens.models.asset import Asset, AssetType, Service
from flowlens.models.dependency import Dependency
from flowlens.schemas.asset import (
    AssetCreate,
    AssetList,
    AssetResponse,
    AssetSummary,
    AssetUpdate,
    AssetWithServices,
    ServiceResponse,
)
from flowlens.schemas.dependency import AssetInfo, DependencyWithAssets

router = APIRouter(prefix="/assets", tags=["assets"])


@router.get("", response_model=AssetList)
async def list_assets(
    db: DbSession,
    user: AuthenticatedUser,
    pagination: Pagination,
    sorting: Sorting,
    asset_type: AssetType | None = Query(None, alias="assetType"),
    environment: str | None = None,
    datacenter: str | None = None,
    team: str | None = None,
    is_internal: bool | None = Query(None, alias="isInternal"),
    is_critical: bool | None = Query(None, alias="isCritical"),
    search: str | None = None,
) -> AssetList:
    """List assets with filtering and pagination."""
    # Build query
    query = select(Asset).where(Asset.deleted_at.is_(None))

    # Apply filters
    if asset_type:
        query = query.where(Asset.asset_type == asset_type)
    if environment:
        query = query.where(Asset.environment == environment)
    if datacenter:
        query = query.where(Asset.datacenter == datacenter)
    if team:
        query = query.where(Asset.team == team)
    if is_internal is not None:
        query = query.where(Asset.is_internal == is_internal)
    if is_critical is not None:
        query = query.where(Asset.is_critical == is_critical)
    if search:
        search_filter = f"%{search}%"
        query = query.where(
            Asset.name.ilike(search_filter)
            | Asset.hostname.ilike(search_filter)
            | cast(Asset.ip_address, String).ilike(search_filter)
        )

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query) or 0

    # Apply sorting
    if sorting.sort_by:
        sort_column = getattr(Asset, sorting.sort_by, Asset.last_seen)
        if sorting.ascending:
            query = query.order_by(sort_column.asc())
        else:
            query = query.order_by(sort_column.desc())
    else:
        query = query.order_by(Asset.last_seen.desc())

    # Apply pagination
    query = query.offset(pagination.offset).limit(pagination.page_size)

    # Execute query
    result = await db.execute(query)
    assets = result.scalars().all()

    # Build response
    items = [
        AssetSummary(
            id=a.id,
            name=a.name,
            display_name=a.display_name,
            asset_type=a.asset_type,
            ip_address=str(a.ip_address),
            hostname=a.hostname,
            is_internal=a.is_internal,
            is_critical=a.is_critical,
            last_seen=a.last_seen,
        )
        for a in assets
    ]

    return AssetList(
        items=items,
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
        pages=(total + pagination.page_size - 1) // pagination.page_size,
    )


@router.get("/{asset_id}", response_model=AssetWithServices)
async def get_asset(
    asset_id: UUID,
    db: DbSession,
    user: AuthenticatedUser,
) -> AssetWithServices:
    """Get asset by ID with services."""
    query = (
        select(Asset)
        .where(Asset.id == asset_id, Asset.deleted_at.is_(None))
        .options(selectinload(Asset.services))
    )
    result = await db.execute(query)
    asset = result.scalar_one_or_none()

    if not asset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Asset {asset_id} not found",
        )

    # Build services list
    services = [
        ServiceResponse(
            id=s.id,
            asset_id=s.asset_id,
            port=s.port,
            protocol=s.protocol,
            name=s.name,
            service_type=s.service_type,
            version=s.version,
            first_seen=s.first_seen,
            last_seen=s.last_seen,
            bytes_total=s.bytes_total,
            connections_total=s.connections_total,
        )
        for s in asset.services
    ]

    return AssetWithServices(
        id=asset.id,
        name=asset.name,
        display_name=asset.display_name,
        asset_type=asset.asset_type,
        ip_address=str(asset.ip_address),
        hostname=asset.hostname,
        fqdn=asset.fqdn,
        mac_address=asset.mac_address,
        subnet=str(asset.subnet) if asset.subnet else None,
        vlan_id=asset.vlan_id,
        datacenter=asset.datacenter,
        environment=asset.environment,
        country_code=asset.country_code,
        city=asset.city,
        is_internal=asset.is_internal,
        is_critical=asset.is_critical,
        criticality_score=asset.criticality_score,
        owner=asset.owner,
        team=asset.team,
        external_id=asset.external_id,
        description=asset.description,
        tags=asset.tags,
        metadata=asset.extra_data,
        first_seen=asset.first_seen,
        last_seen=asset.last_seen,
        bytes_in_total=asset.bytes_in_total,
        bytes_out_total=asset.bytes_out_total,
        connections_in=asset.connections_in,
        connections_out=asset.connections_out,
        created_at=asset.created_at,
        updated_at=asset.updated_at,
        services=services,
    )


@router.post("", response_model=AssetResponse, status_code=status.HTTP_201_CREATED)
async def create_asset(
    data: AssetCreate,
    db: DbSession,
    user: AuthenticatedUser,
) -> AssetResponse:
    """Create a new asset."""
    # Check for duplicate IP
    existing = await db.execute(
        select(Asset).where(
            Asset.ip_address == str(data.ip_address),
            Asset.deleted_at.is_(None),
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Asset with IP {data.ip_address} already exists",
        )

    # Create asset
    asset = Asset(
        name=data.name,
        display_name=data.display_name,
        asset_type=data.asset_type,
        ip_address=str(data.ip_address),
        hostname=data.hostname,
        fqdn=data.fqdn,
        mac_address=data.mac_address,
        subnet=data.subnet,
        vlan_id=data.vlan_id,
        datacenter=data.datacenter,
        environment=data.environment,
        is_internal=data.is_internal,
        is_critical=data.is_critical,
        criticality_score=data.criticality_score,
        owner=data.owner,
        team=data.team,
        external_id=data.external_id,
        description=data.description,
        tags=data.tags,
        metadata=data.metadata,
    )

    db.add(asset)
    await db.flush()
    await db.refresh(asset)

    return AssetResponse.model_validate(asset)


@router.put("/{asset_id}", response_model=AssetResponse)
async def update_asset(
    asset_id: UUID,
    data: AssetUpdate,
    db: DbSession,
    user: AuthenticatedUser,
) -> AssetResponse:
    """Update an asset."""
    result = await db.execute(
        select(Asset).where(Asset.id == asset_id, Asset.deleted_at.is_(None))
    )
    asset = result.scalar_one_or_none()

    if not asset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Asset {asset_id} not found",
        )

    # Update fields
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(asset, field, value)

    await db.flush()
    await db.refresh(asset)

    return AssetResponse.model_validate(asset)


@router.delete("/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_asset(
    asset_id: UUID,
    db: DbSession,
    user: AuthenticatedUser,
) -> None:
    """Soft delete an asset."""
    result = await db.execute(
        select(Asset).where(Asset.id == asset_id, Asset.deleted_at.is_(None))
    )
    asset = result.scalar_one_or_none()

    if not asset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Asset {asset_id} not found",
        )

    asset.soft_delete()
    await db.flush()


@router.get("/{asset_id}/services", response_model=list[ServiceResponse])
async def get_asset_services(
    asset_id: UUID,
    db: DbSession,
    user: AuthenticatedUser,
) -> list[ServiceResponse]:
    """Get services running on an asset."""
    # Verify asset exists
    asset_result = await db.execute(
        select(Asset.id).where(Asset.id == asset_id, Asset.deleted_at.is_(None))
    )
    if not asset_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Asset {asset_id} not found",
        )

    # Get services
    result = await db.execute(
        select(Service)
        .where(Service.asset_id == asset_id)
        .order_by(Service.port)
    )
    services = result.scalars().all()

    return [ServiceResponse.model_validate(s) for s in services]


@router.get("/{asset_id}/dependencies", response_model=list[DependencyWithAssets])
async def get_asset_dependencies(
    asset_id: UUID,
    db: DbSession,
    user: AuthenticatedUser,
    direction: Literal["upstream", "downstream", "both"] = Query("both"),
) -> list[DependencyWithAssets]:
    """Get dependencies for an asset.

    Args:
        asset_id: The asset ID.
        direction: Filter by direction - upstream (assets that connect TO this asset),
                   downstream (assets this asset connects TO), or both.
    """
    # Verify asset exists
    asset_result = await db.execute(
        select(Asset.id).where(Asset.id == asset_id, Asset.deleted_at.is_(None))
    )
    if not asset_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Asset {asset_id} not found",
        )

    # Build query based on direction
    if direction == "upstream":
        # Dependencies where this asset is the target (others connect TO it)
        query = select(Dependency).where(
            Dependency.target_asset_id == asset_id,
            Dependency.valid_to.is_(None),
        )
    elif direction == "downstream":
        # Dependencies where this asset is the source (it connects TO others)
        query = select(Dependency).where(
            Dependency.source_asset_id == asset_id,
            Dependency.valid_to.is_(None),
        )
    else:
        # Both directions
        query = select(Dependency).where(
            or_(
                Dependency.source_asset_id == asset_id,
                Dependency.target_asset_id == asset_id,
            ),
            Dependency.valid_to.is_(None),
        )

    # Load related assets
    query = query.options(
        selectinload(Dependency.source_asset),
        selectinload(Dependency.target_asset),
    ).order_by(Dependency.last_seen.desc())

    result = await db.execute(query)
    dependencies = result.scalars().all()

    # Build response
    response = []
    for dep in dependencies:
        source_info = AssetInfo(
            id=dep.source_asset.id,
            name=dep.source_asset.name,
            ip_address=str(dep.source_asset.ip_address),
            hostname=dep.source_asset.hostname,
            is_critical=dep.source_asset.is_critical,
        )
        target_info = AssetInfo(
            id=dep.target_asset.id,
            name=dep.target_asset.name,
            ip_address=str(dep.target_asset.ip_address),
            hostname=dep.target_asset.hostname,
            is_critical=dep.target_asset.is_critical,
        )

        response.append(DependencyWithAssets(
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
            metadata=dep.extra_data,
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
            source_asset=source_info,
            target_asset=target_info,
        ))

    return response

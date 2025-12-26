"""Gateway API endpoints.

Provides endpoints for viewing and managing gateway relationships.
"""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from flowlens.api.dependencies import get_db
from fastapi import Depends
from flowlens.common.logging import get_logger
from flowlens.models.asset import Asset
from flowlens.models.gateway import AssetGateway
from flowlens.schemas.gateway import (
    AssetGatewayResponse,
    GatewayClientsResponse,
    GatewayForAssetResponse,
    GatewayListResponse,
    GatewayRelationship,
    GatewayTopologyData,
    GatewayTopologyEdge,
    GatewayTopologyNode,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/gateways", tags=["gateways"])


@router.get("", response_model=GatewayListResponse)
async def list_gateways(
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    asset_id: UUID | None = None,
    role: str | None = None,
    min_confidence: float = Query(0.0, ge=0.0, le=1.0),
) -> GatewayListResponse:
    """List gateway relationships.

    Optionally filter by source/gateway asset or gateway role.
    """
    query = (
        select(AssetGateway)
        .where(AssetGateway.valid_to.is_(None))
        .where(AssetGateway.confidence >= min_confidence)
    )

    if asset_id:
        query = query.where(
            (AssetGateway.source_asset_id == asset_id)
            | (AssetGateway.gateway_asset_id == asset_id)
        )

    if role:
        query = query.where(AssetGateway.gateway_role == role)

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    count_result = await db.execute(count_query)
    total = count_result.scalar() or 0

    # Paginate
    query = (
        query.order_by(AssetGateway.bytes_total.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(query)
    gateways = result.scalars().all()

    items = [AssetGatewayResponse.model_validate(g) for g in gateways]

    return GatewayListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/for-asset/{asset_id}", response_model=GatewayForAssetResponse)
async def get_gateways_for_asset(
    asset_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> GatewayForAssetResponse:
    """Get all gateways used by a specific asset."""
    # Get the asset
    asset_result = await db.execute(
        select(Asset).where(Asset.id == asset_id, Asset.deleted_at.is_(None))
    )
    asset = asset_result.scalar_one_or_none()

    if not asset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Asset {asset_id} not found",
        )

    # Get gateway relationships with gateway asset info
    result = await db.execute(
        select(AssetGateway, Asset)
        .join(Asset, Asset.id == AssetGateway.gateway_asset_id)
        .where(
            AssetGateway.source_asset_id == asset_id,
            AssetGateway.valid_to.is_(None),
        )
        .order_by(AssetGateway.traffic_share.desc().nullslast())
    )

    relationships = []
    for gateway, gateway_asset in result.fetchall():
        relationships.append(
            GatewayRelationship(
                gateway_id=gateway.id,
                gateway_asset_id=gateway.gateway_asset_id,
                gateway_ip=str(gateway_asset.ip_address),
                gateway_name=gateway_asset.name,
                gateway_role=gateway.gateway_role,
                is_default=gateway.is_default_gateway,
                traffic_share=gateway.traffic_share,
                bytes_total=gateway.bytes_total,
                confidence=gateway.confidence,
                last_seen=gateway.last_seen,
            )
        )

    return GatewayForAssetResponse(
        asset_id=asset.id,
        asset_ip=str(asset.ip_address),
        asset_name=asset.name,
        gateways=relationships,
        total_gateways=len(relationships),
    )


@router.get("/clients/{gateway_asset_id}", response_model=GatewayClientsResponse)
async def get_gateway_clients(
    gateway_asset_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> GatewayClientsResponse:
    """Get all assets that use this gateway."""
    # Get the gateway asset
    gateway_result = await db.execute(
        select(Asset).where(Asset.id == gateway_asset_id, Asset.deleted_at.is_(None))
    )
    gateway_asset = gateway_result.scalar_one_or_none()

    if not gateway_asset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Gateway asset {gateway_asset_id} not found",
        )

    # Get client relationships with source asset info
    result = await db.execute(
        select(AssetGateway, Asset)
        .join(Asset, Asset.id == AssetGateway.source_asset_id)
        .where(
            AssetGateway.gateway_asset_id == gateway_asset_id,
            AssetGateway.valid_to.is_(None),
        )
        .order_by(AssetGateway.bytes_total.desc())
    )

    clients = []
    for gateway, source_asset in result.fetchall():
        clients.append(
            GatewayRelationship(
                gateway_id=gateway.id,
                gateway_asset_id=gateway.source_asset_id,
                gateway_ip=str(source_asset.ip_address),
                gateway_name=source_asset.name,
                gateway_role=gateway.gateway_role,
                is_default=gateway.is_default_gateway,
                traffic_share=gateway.traffic_share,
                bytes_total=gateway.bytes_total,
                confidence=gateway.confidence,
                last_seen=gateway.last_seen,
            )
        )

    return GatewayClientsResponse(
        gateway_id=gateway_asset.id,
        gateway_ip=str(gateway_asset.ip_address),
        gateway_name=gateway_asset.name,
        clients=clients,
        total_clients=len(clients),
    )


@router.get("/topology", response_model=GatewayTopologyData)
async def get_gateway_topology(
    db: AsyncSession = Depends(get_db),
    min_confidence: float = Query(0.6, ge=0.0, le=1.0),
    as_of: datetime | None = None,
) -> GatewayTopologyData:
    """Get gateway relationships as topology data for visualization."""
    # Query for gateway relationships
    query = select(AssetGateway).where(AssetGateway.confidence >= min_confidence)

    if as_of:
        query = query.where(
            AssetGateway.valid_from <= as_of,
            (AssetGateway.valid_to.is_(None)) | (AssetGateway.valid_to > as_of),
        )
    else:
        query = query.where(AssetGateway.valid_to.is_(None))

    result = await db.execute(query)
    gateways = result.scalars().all()

    # Collect unique asset IDs
    asset_ids = set()
    for g in gateways:
        asset_ids.add(g.source_asset_id)
        asset_ids.add(g.gateway_asset_id)

    if not asset_ids:
        return GatewayTopologyData(
            nodes=[],
            edges=[],
            generated_at=datetime.utcnow(),
        )

    # Fetch assets
    asset_result = await db.execute(
        select(Asset).where(Asset.id.in_(asset_ids), Asset.deleted_at.is_(None))
    )
    assets = {a.id: a for a in asset_result.scalars().all()}

    # Build nodes
    nodes = []
    for asset_id, asset in assets.items():
        # Check if this asset is a gateway
        is_gateway = any(g.gateway_asset_id == asset_id for g in gateways)
        client_count = sum(1 for g in gateways if g.gateway_asset_id == asset_id)

        nodes.append(
            GatewayTopologyNode(
                id=str(asset_id),
                name=asset.name,
                ip_address=str(asset.ip_address),
                asset_type=asset.asset_type.value if asset.asset_type else "unknown",
                is_gateway=is_gateway,
                client_count=client_count,
            )
        )

    # Build edges
    edges = []
    for g in gateways:
        edges.append(
            GatewayTopologyEdge(
                id=str(g.id),
                source=str(g.source_asset_id),
                target=str(g.gateway_asset_id),
                gateway_role=g.gateway_role,
                is_default=g.is_default_gateway,
                traffic_share=g.traffic_share,
                confidence=g.confidence,
                bytes_total=g.bytes_total,
            )
        )

    return GatewayTopologyData(
        nodes=nodes,
        edges=edges,
        generated_at=datetime.utcnow(),
    )


@router.get("/{gateway_id}", response_model=AssetGatewayResponse)
async def get_gateway(
    gateway_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> AssetGatewayResponse:
    """Get a specific gateway relationship by ID."""
    result = await db.execute(
        select(AssetGateway).where(AssetGateway.id == gateway_id)
    )
    gateway = result.scalar_one_or_none()

    if not gateway:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Gateway relationship {gateway_id} not found",
        )

    return AssetGatewayResponse.model_validate(gateway)

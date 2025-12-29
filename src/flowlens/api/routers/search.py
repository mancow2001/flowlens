"""Unified search API endpoint."""

from fastapi import APIRouter, Query
from sqlalchemy import String, cast, or_, select
from sqlalchemy.orm import aliased

from flowlens.api.dependencies import AuthenticatedUser, DbSession
from flowlens.models.asset import Asset
from flowlens.models.dependency import Dependency
from flowlens.schemas.search import (
    AssetInfo,
    AssetMatch,
    ConnectionMatch,
    SearchResponse,
)

router = APIRouter(prefix="/search", tags=["search"])


@router.get("", response_model=SearchResponse)
async def unified_search(
    db: DbSession,
    user: AuthenticatedUser,
    q: str | None = Query(None, description="Simple text search for assets"),
    source: str | None = Query(None, description="Source IP or hostname pattern"),
    destination: str | None = Query(None, description="Destination IP or hostname pattern"),
    port: int | None = Query(None, ge=0, le=65535, description="Target port"),
    limit: int = Query(10, ge=1, le=50, description="Maximum results"),
) -> SearchResponse:
    """Unified search endpoint.

    - If only 'q' is provided: search assets by name, IP, or hostname
    - If source, destination, or port provided: search connections/dependencies
    """
    assets: list[AssetMatch] = []
    connections: list[ConnectionMatch] = []

    # Simple asset search mode
    if q and not source and not destination and port is None:
        search_filter = f"%{q}%"
        query = (
            select(Asset)
            .where(
                Asset.deleted_at.is_(None),
                or_(
                    Asset.name.ilike(search_filter),
                    Asset.hostname.ilike(search_filter),
                    cast(Asset.ip_address, String).ilike(search_filter),
                ),
            )
            .order_by(Asset.last_seen.desc())
            .limit(limit)
        )
        result = await db.execute(query)
        for asset in result.scalars().all():
            # Handle asset_type which could be an enum or a string
            if hasattr(asset.asset_type, 'value'):
                asset_type_str = asset.asset_type.value
            elif asset.asset_type:
                asset_type_str = str(asset.asset_type)
            else:
                asset_type_str = "unknown"

            assets.append(
                AssetMatch(
                    id=asset.id,
                    name=asset.name,
                    display_name=asset.display_name,
                    asset_type=asset_type_str,
                    ip_address=str(asset.ip_address),
                    hostname=asset.hostname,
                    is_internal=asset.is_internal,
                    is_critical=asset.is_critical,
                    last_seen=asset.last_seen,
                )
            )

    # Advanced connection search mode
    if source or destination or port is not None:
        # Create aliases for joining assets
        SourceAsset = aliased(Asset, name="source_asset")
        TargetAsset = aliased(Asset, name="target_asset")

        query = (
            select(Dependency, SourceAsset, TargetAsset)
            .join(SourceAsset, Dependency.source_asset_id == SourceAsset.id)
            .join(TargetAsset, Dependency.target_asset_id == TargetAsset.id)
            .where(
                Dependency.valid_to.is_(None),
                SourceAsset.deleted_at.is_(None),
                TargetAsset.deleted_at.is_(None),
            )
        )

        # Apply source filter
        if source:
            source_filter = f"%{source}%"
            query = query.where(
                or_(
                    SourceAsset.name.ilike(source_filter),
                    SourceAsset.hostname.ilike(source_filter),
                    cast(SourceAsset.ip_address, String).ilike(source_filter),
                )
            )

        # Apply destination filter
        if destination:
            dest_filter = f"%{destination}%"
            query = query.where(
                or_(
                    TargetAsset.name.ilike(dest_filter),
                    TargetAsset.hostname.ilike(dest_filter),
                    cast(TargetAsset.ip_address, String).ilike(dest_filter),
                )
            )

        # Apply port filter
        if port is not None:
            query = query.where(Dependency.target_port == port)

        query = query.order_by(Dependency.last_seen.desc()).limit(limit)

        result = await db.execute(query)
        for dep, src_asset, tgt_asset in result.all():
            connections.append(
                ConnectionMatch(
                    id=dep.id,
                    source=AssetInfo(
                        id=src_asset.id,
                        name=src_asset.name,
                        ip_address=str(src_asset.ip_address),
                        hostname=src_asset.hostname,
                        is_critical=src_asset.is_critical,
                    ),
                    target=AssetInfo(
                        id=tgt_asset.id,
                        name=tgt_asset.name,
                        ip_address=str(tgt_asset.ip_address),
                        hostname=tgt_asset.hostname,
                        is_critical=tgt_asset.is_critical,
                    ),
                    target_port=dep.target_port,
                    protocol=dep.protocol,
                    bytes_last_24h=dep.bytes_last_24h or 0,
                    last_seen=dep.last_seen,
                )
            )

    return SearchResponse(assets=assets, connections=connections)

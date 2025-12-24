"""Topology API endpoints for graph queries."""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select, text

from flowlens.api.dependencies import AuthenticatedUser, DbSession
from flowlens.models.asset import Asset
from flowlens.models.dependency import Dependency
from flowlens.schemas.topology import (
    PathResult,
    SubgraphRequest,
    TopologyEdge,
    TopologyFilter,
    TopologyGraph,
    TopologyNode,
    TraversalNode,
    TraversalResult,
)

router = APIRouter(prefix="/topology", tags=["topology"])


@router.post("/graph", response_model=TopologyGraph)
async def get_topology_graph(
    filters: TopologyFilter,
    db: DbSession,
    user: AuthenticatedUser,
) -> TopologyGraph:
    """Get topology graph with optional filtering.

    Returns nodes and edges for visualization.
    """
    # Build asset query
    asset_query = select(Asset).where(Asset.deleted_at.is_(None))

    if filters.asset_ids:
        asset_query = asset_query.where(Asset.id.in_(filters.asset_ids))
    if filters.asset_types:
        asset_query = asset_query.where(Asset.asset_type.in_(filters.asset_types))
    if filters.environments:
        asset_query = asset_query.where(Asset.environment.in_(filters.environments))
    if filters.datacenters:
        asset_query = asset_query.where(Asset.datacenter.in_(filters.datacenters))
    if not filters.include_external:
        asset_query = asset_query.where(Asset.is_internal == True)

    # Get assets
    asset_result = await db.execute(asset_query)
    assets = asset_result.scalars().all()
    asset_ids = {a.id for a in assets}

    # Build nodes
    nodes = [
        TopologyNode(
            id=a.id,
            name=a.name,
            label=a.display_name or a.name,
            asset_type=a.asset_type.value,
            ip_address=str(a.ip_address),
            is_internal=a.is_internal,
            is_critical=a.is_critical,
            environment=a.environment,
            datacenter=a.datacenter,
            connections_in=a.connections_in,
            connections_out=a.connections_out,
        )
        for a in assets
    ]

    # Build dependency query
    dep_query = select(Dependency).where(
        Dependency.source_asset_id.in_(asset_ids),
        Dependency.target_asset_id.in_(asset_ids),
        Dependency.valid_to.is_(None),
    )

    if filters.min_bytes_24h > 0:
        dep_query = dep_query.where(Dependency.bytes_last_24h >= filters.min_bytes_24h)

    # Handle point-in-time query
    if filters.as_of:
        dep_query = select(Dependency).where(
            Dependency.source_asset_id.in_(asset_ids),
            Dependency.target_asset_id.in_(asset_ids),
            Dependency.valid_from <= filters.as_of,
            (Dependency.valid_to.is_(None)) | (Dependency.valid_to > filters.as_of),
        )

    # Get dependencies
    dep_result = await db.execute(dep_query)
    dependencies = dep_result.scalars().all()

    # Map protocol numbers to names
    protocol_names = {6: "TCP", 17: "UDP", 1: "ICMP"}

    # Build edges
    edges = [
        TopologyEdge(
            id=d.id,
            source=d.source_asset_id,
            target=d.target_asset_id,
            target_port=d.target_port,
            protocol=d.protocol,
            protocol_name=protocol_names.get(d.protocol),
            service_type=d.dependency_type,
            bytes_total=d.bytes_total,
            bytes_last_24h=d.bytes_last_24h,
            is_critical=d.is_critical,
            last_seen=d.last_seen,
        )
        for d in dependencies
    ]

    return TopologyGraph(
        nodes=nodes,
        edges=edges,
        generated_at=datetime.utcnow(),
    )


@router.get("/downstream/{asset_id}", response_model=TraversalResult)
async def get_downstream_dependencies(
    asset_id: UUID,
    db: DbSession,
    user: AuthenticatedUser,
    max_depth: int = Query(5, ge=1, le=10, alias="maxDepth"),
) -> TraversalResult:
    """Get downstream dependencies (what this asset depends on).

    Uses recursive CTE for graph traversal.
    """
    # Verify asset exists
    asset_result = await db.execute(
        select(Asset).where(Asset.id == asset_id, Asset.deleted_at.is_(None))
    )
    root_asset = asset_result.scalar_one_or_none()

    if not root_asset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Asset {asset_id} not found",
        )

    # Call the database function
    result = await db.execute(
        text("SELECT * FROM get_downstream_dependencies(:asset_id, :max_depth)"),
        {"asset_id": asset_id, "max_depth": max_depth},
    )
    rows = result.fetchall()

    nodes = [
        TraversalNode(
            asset_id=row.asset_id,
            asset_name=row.asset_name,
            depth=row.depth,
            path=list(row.path),
            target_port=row.target_port,
            protocol=row.protocol,
            bytes_total=row.bytes_total,
            last_seen=row.last_seen,
        )
        for row in rows
    ]

    return TraversalResult(
        root_asset_id=asset_id,
        direction="downstream",
        max_depth=max_depth,
        nodes=nodes,
        total_nodes=len(nodes),
    )


@router.get("/upstream/{asset_id}", response_model=TraversalResult)
async def get_upstream_dependencies(
    asset_id: UUID,
    db: DbSession,
    user: AuthenticatedUser,
    max_depth: int = Query(5, ge=1, le=10, alias="maxDepth"),
) -> TraversalResult:
    """Get upstream dependencies (what depends on this asset).

    Uses recursive CTE for graph traversal.
    """
    # Verify asset exists
    asset_result = await db.execute(
        select(Asset).where(Asset.id == asset_id, Asset.deleted_at.is_(None))
    )
    root_asset = asset_result.scalar_one_or_none()

    if not root_asset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Asset {asset_id} not found",
        )

    # Call the database function
    result = await db.execute(
        text("SELECT * FROM get_upstream_dependencies(:asset_id, :max_depth)"),
        {"asset_id": asset_id, "max_depth": max_depth},
    )
    rows = result.fetchall()

    nodes = [
        TraversalNode(
            asset_id=row.asset_id,
            asset_name=row.asset_name,
            depth=row.depth,
            path=list(row.path),
            target_port=row.target_port,
            protocol=row.protocol,
            bytes_total=row.bytes_total,
            last_seen=row.last_seen,
        )
        for row in rows
    ]

    return TraversalResult(
        root_asset_id=asset_id,
        direction="upstream",
        max_depth=max_depth,
        nodes=nodes,
        total_nodes=len(nodes),
    )


@router.get("/path", response_model=PathResult)
async def find_path(
    db: DbSession,
    user: AuthenticatedUser,
    source_id: UUID = Query(..., alias="sourceId"),
    target_id: UUID = Query(..., alias="targetId"),
    max_depth: int = Query(10, ge=1, le=20, alias="maxDepth"),
) -> PathResult:
    """Find path between two assets.

    Returns the shortest path if one exists.
    """
    # Verify both assets exist
    for aid, name in [(source_id, "Source"), (target_id, "Target")]:
        result = await db.execute(
            select(Asset).where(Asset.id == aid, Asset.deleted_at.is_(None))
        )
        if not result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"{name} asset {aid} not found",
            )

    # Use BFS to find shortest path
    result = await db.execute(
        text("""
            WITH RECURSIVE path_search AS (
                SELECT
                    source_asset_id,
                    target_asset_id,
                    ARRAY[source_asset_id, target_asset_id] AS path,
                    1 AS depth
                FROM dependencies
                WHERE source_asset_id = :source_id
                  AND valid_to IS NULL

                UNION ALL

                SELECT
                    d.source_asset_id,
                    d.target_asset_id,
                    ps.path || d.target_asset_id,
                    ps.depth + 1
                FROM path_search ps
                JOIN dependencies d ON d.source_asset_id = ps.target_asset_id
                WHERE ps.depth < :max_depth
                  AND d.valid_to IS NULL
                  AND NOT d.target_asset_id = ANY(ps.path)
            )
            SELECT path, depth
            FROM path_search
            WHERE target_asset_id = :target_id
            ORDER BY depth
            LIMIT 1
        """),
        {"source_id": source_id, "target_id": target_id, "max_depth": max_depth},
    )
    row = result.fetchone()

    if not row:
        return PathResult(
            source_id=source_id,
            target_id=target_id,
            path_exists=False,
        )

    path = list(row.path)

    # Get edges along the path
    edges = []
    for i in range(len(path) - 1):
        edge_result = await db.execute(
            select(Dependency).where(
                Dependency.source_asset_id == path[i],
                Dependency.target_asset_id == path[i + 1],
                Dependency.valid_to.is_(None),
            )
        )
        dep = edge_result.scalar_one_or_none()
        if dep:
            edges.append(
                TopologyEdge(
                    id=dep.id,
                    source=dep.source_asset_id,
                    target=dep.target_asset_id,
                    target_port=dep.target_port,
                    protocol=dep.protocol,
                    bytes_total=dep.bytes_total,
                    bytes_last_24h=dep.bytes_last_24h,
                    is_critical=dep.is_critical,
                    last_seen=dep.last_seen,
                )
            )

    return PathResult(
        source_id=source_id,
        target_id=target_id,
        path_exists=True,
        path=path,
        path_length=row.depth,
        edges=edges,
    )


@router.post("/subgraph", response_model=TopologyGraph)
async def get_subgraph(
    request: SubgraphRequest,
    db: DbSession,
    user: AuthenticatedUser,
) -> TopologyGraph:
    """Get subgraph centered on an asset.

    Returns nodes and edges within the specified depth.
    """
    center_id = request.center_asset_id

    # Get upstream and/or downstream nodes
    node_ids: set[UUID] = {center_id}

    if request.direction in ("upstream", "both"):
        result = await db.execute(
            text("SELECT asset_id FROM get_upstream_dependencies(:aid, :depth)"),
            {"aid": center_id, "depth": request.depth},
        )
        for row in result.fetchall():
            node_ids.add(row.asset_id)

    if request.direction in ("downstream", "both"):
        result = await db.execute(
            text("SELECT asset_id FROM get_downstream_dependencies(:aid, :depth)"),
            {"aid": center_id, "depth": request.depth},
        )
        for row in result.fetchall():
            node_ids.add(row.asset_id)

    # Use the graph endpoint with the discovered node IDs
    filters = TopologyFilter(
        asset_ids=list(node_ids),
        include_external=request.include_external,
        as_of=request.as_of,
    )

    return await get_topology_graph(filters, db, user)

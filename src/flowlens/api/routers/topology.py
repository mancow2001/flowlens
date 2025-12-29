"""Topology API endpoints for graph queries."""

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select, text

from flowlens.api.cache import get_topology_cache
from flowlens.api.dependencies import DbSession, ViewerUser
from flowlens.common.config import get_settings
from flowlens.common.logging import get_logger
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

logger = get_logger(__name__)

router = APIRouter(prefix="/topology", tags=["topology"])


async def get_cidr_classifications(db: DbSession, ip_addresses: list[str]) -> dict[str, dict]:
    """Get CIDR classifications for a batch of IP addresses.

    Returns a dict mapping IP address to classification attributes.
    Returns empty dict if classification_rules table doesn't exist yet or any error occurs.
    """
    if not ip_addresses:
        return {}

    try:
        # First check if the classification_rules table exists and has rows
        table_check = await db.execute(
            text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_name = 'classification_rules'
                )
            """)
        )
        table_exists = table_check.scalar()
        if not table_exists:
            return {}

        # Check if there are any active rules
        count_check = await db.execute(
            text("SELECT COUNT(*) FROM classification_rules WHERE is_active = true")
        )
        rule_count = count_check.scalar()
        if not rule_count:
            return {}

        # Build a query that gets classifications for all IPs in one go
        # Using a lateral join with the classification function
        result = await db.execute(
            text("""
                SELECT
                    ip_addr,
                    cr.environment,
                    cr.datacenter,
                    cr.location,
                    cr.asset_type,
                    cr.is_internal
                FROM unnest(CAST(:ip_addrs AS inet[])) AS ip_addr
                LEFT JOIN LATERAL (
                    SELECT
                        environment,
                        datacenter,
                        location,
                        asset_type,
                        is_internal
                    FROM classification_rules
                    WHERE is_active = true
                      AND ip_addr <<= cidr
                    ORDER BY masklen(cidr) DESC, priority ASC
                    LIMIT 1
                ) cr ON true
            """),
            {"ip_addrs": ip_addresses},
        )

        classifications = {}
        for row in result.fetchall():
            ip = str(row.ip_addr)
            classifications[ip] = {
                "environment": row.environment,
                "datacenter": row.datacenter,
                "location": row.location,
                "asset_type": row.asset_type,
                "is_internal": row.is_internal,
            }

        return classifications
    except Exception:
        # If any query fails, rollback and return empty to let topology work without classification
        try:
            await db.rollback()
        except Exception:
            pass
        return {}


@router.post("/graph", response_model=TopologyGraph)
async def get_topology_graph(
    filters: TopologyFilter,
    db: DbSession,
    _user: ViewerUser,
) -> TopologyGraph:
    """Get topology graph with optional filtering.

    Returns nodes and edges for visualization.
    When use_cidr_classification is True (default), environment, datacenter,
    and location are dynamically determined from CIDR classification rules.

    Note: Results are limited by API_TOPOLOGY_MAX_NODES and API_TOPOLOGY_MAX_EDGES
    settings to ensure performance on large graphs.
    """
    settings = get_settings()
    cache = get_topology_cache()

    # Try cache first (only for non-temporal queries without specific asset IDs)
    use_cache = (
        settings.api.topology_cache_ttl_seconds > 0
        and filters.as_of is None
        and not filters.asset_ids  # Don't cache specific asset queries
    )

    if use_cache:
        cache_key = cache.make_key("topology:graph", filters.model_dump(mode="json"))
        if cached := cache.get(cache_key):
            logger.debug("Topology cache hit", cache_key=cache_key)
            return cached

    # Build asset query
    asset_query = select(Asset).where(Asset.deleted_at.is_(None))

    if filters.asset_ids:
        asset_query = asset_query.where(Asset.id.in_(filters.asset_ids))
    if filters.asset_types:
        asset_query = asset_query.where(Asset.asset_type.in_(filters.asset_types))
    # Note: environment/datacenter/location filtering happens after CIDR classification
    if not filters.include_external:
        asset_query = asset_query.where(Asset.is_internal == True)

    # Get assets
    asset_result = await db.execute(asset_query)
    assets = asset_result.scalars().all()

    # Get CIDR classifications if enabled
    classifications = {}
    if filters.use_cidr_classification and assets:
        ip_addresses = [str(a.ip_address) for a in assets]
        classifications = await get_cidr_classifications(db, ip_addresses)

    # Build nodes with CIDR-based attributes
    nodes = []
    for a in assets:
        ip_str = str(a.ip_address)
        cidr_class = classifications.get(ip_str, {})

        # Use CIDR classification if available, otherwise fall back to asset fields
        environment = cidr_class.get("environment") or a.environment
        datacenter = cidr_class.get("datacenter") or a.datacenter
        location = cidr_class.get("location")
        is_internal = cidr_class.get("is_internal") if cidr_class.get("is_internal") is not None else a.is_internal

        nodes.append(TopologyNode(
            id=a.id,
            name=a.name,
            label=a.display_name or a.name,
            asset_type=a.asset_type.value if hasattr(a.asset_type, 'value') else a.asset_type,
            ip_address=ip_str,
            is_internal=is_internal,
            is_critical=a.is_critical,
            environment=environment,
            datacenter=datacenter,
            location=location,
            connections_in=a.connections_in,
            connections_out=a.connections_out,
        ))

    # Apply environment/datacenter/location filters after CIDR classification
    if filters.environments:
        nodes = [n for n in nodes if n.environment in filters.environments]
    if filters.datacenters:
        nodes = [n for n in nodes if n.datacenter in filters.datacenters]
    if filters.locations:
        nodes = [n for n in nodes if n.location in filters.locations]

    # Get the filtered asset IDs
    asset_ids = {n.id for n in nodes}

    # Handle empty asset_ids case (IN () is invalid SQL)
    if not asset_ids:
        empty_result = TopologyGraph(
            nodes=[],
            edges=[],
            generated_at=datetime.now(timezone.utc),
        )
        return empty_result

    # Apply node limit to prevent memory issues on large graphs
    max_nodes = settings.api.topology_max_nodes
    if len(asset_ids) > max_nodes:
        logger.warning(
            "Topology query exceeded max nodes, truncating",
            requested=len(asset_ids),
            max_nodes=max_nodes,
        )
        # Keep the first N nodes (could be improved with prioritization)
        asset_ids = set(list(asset_ids)[:max_nodes])

    # Build dependency query
    # Handle point-in-time query vs current state
    if filters.as_of:
        dep_query = select(Dependency).where(
            Dependency.source_asset_id.in_(asset_ids),
            Dependency.target_asset_id.in_(asset_ids),
            Dependency.valid_from <= filters.as_of,
            (Dependency.valid_to.is_(None)) | (Dependency.valid_to > filters.as_of),
        )
    else:
        dep_query = select(Dependency).where(
            Dependency.source_asset_id.in_(asset_ids),
            Dependency.target_asset_id.in_(asset_ids),
            Dependency.valid_to.is_(None),
        )

    # Apply min bytes filter (works for both current and historical queries)
    if filters.min_bytes_24h > 0:
        dep_query = dep_query.where(Dependency.bytes_last_24h >= filters.min_bytes_24h)

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

    # Apply edge limit
    max_edges = settings.api.topology_max_edges
    if len(edges) > max_edges:
        logger.warning(
            "Topology query exceeded max edges, truncating",
            requested=len(edges),
            max_edges=max_edges,
        )
        # Sort by bytes (most significant edges first) and truncate
        edges = sorted(edges, key=lambda e: e.bytes_total or 0, reverse=True)[:max_edges]

    # Filter nodes to only include those with at least one edge
    connected_asset_ids = set()
    for edge in edges:
        connected_asset_ids.add(edge.source)
        connected_asset_ids.add(edge.target)

    # Only include nodes that have dependencies
    filtered_nodes = [node for node in nodes if node.id in connected_asset_ids]

    # Build result
    result = TopologyGraph(
        nodes=filtered_nodes,
        edges=edges,
        generated_at=datetime.now(timezone.utc),
    )

    # Cache the result
    if use_cache:
        cache.set(cache_key, result)
        logger.debug("Topology cache set", cache_key=cache_key, nodes=len(filtered_nodes), edges=len(edges))

    return result


@router.get("/downstream/{asset_id}", response_model=TraversalResult)
async def get_downstream_dependencies(
    asset_id: UUID,
    db: DbSession,
    _user: ViewerUser,
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
    _user: ViewerUser,
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
    _user: ViewerUser,
    source_id: UUID = Query(..., alias="sourceId"),
    target_id: UUID = Query(..., alias="targetId"),
    max_depth: int = Query(5, ge=1, le=10, alias="maxDepth"),
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
    # Search bidirectionally - treat dependencies as undirected edges for path finding
    # This finds paths regardless of which direction the traffic flows
    result = await db.execute(
        text("""
            WITH RECURSIVE
            -- Create bidirectional edges view
            edges AS (
                SELECT source_asset_id AS from_id, target_asset_id AS to_id
                FROM dependencies
                WHERE valid_to IS NULL
                UNION
                SELECT target_asset_id AS from_id, source_asset_id AS to_id
                FROM dependencies
                WHERE valid_to IS NULL
            ),
            path_search AS (
                SELECT
                    from_id,
                    to_id,
                    ARRAY[from_id, to_id] AS path,
                    1 AS depth,
                    (to_id = :target_id) AS found
                FROM edges
                WHERE from_id = :source_id

                UNION ALL

                SELECT
                    e.from_id,
                    e.to_id,
                    ps.path || e.to_id,
                    ps.depth + 1,
                    (e.to_id = :target_id) AS found
                FROM path_search ps
                JOIN edges e ON e.from_id = ps.to_id
                WHERE ps.depth < :max_depth
                  AND NOT e.to_id = ANY(ps.path)
                  AND NOT ps.found  -- Stop expanding paths that found target
            )
            SELECT path, depth
            FROM path_search
            WHERE to_id = :target_id
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

    # Get edges along the path (check both directions since path is bidirectional)
    # Note: There may be multiple dependencies between the same assets (different ports),
    # so we use .first() instead of .scalar_one_or_none()
    edges = []
    for i in range(len(path) - 1):
        # Try forward direction first
        edge_result = await db.execute(
            select(Dependency).where(
                Dependency.source_asset_id == path[i],
                Dependency.target_asset_id == path[i + 1],
                Dependency.valid_to.is_(None),
            ).limit(1)
        )
        dep = edge_result.scalar()

        # If not found, try reverse direction
        if not dep:
            edge_result = await db.execute(
                select(Dependency).where(
                    Dependency.source_asset_id == path[i + 1],
                    Dependency.target_asset_id == path[i],
                    Dependency.valid_to.is_(None),
                ).limit(1)
            )
            dep = edge_result.scalar()

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
    _user: ViewerUser,
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

    return await get_topology_graph(filters, db, _user)

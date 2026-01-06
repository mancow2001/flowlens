"""Topology API endpoints for graph queries."""

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select, text

from sqlalchemy.orm import selectinload

from flowlens.api.cache import get_topology_cache
from flowlens.api.dependencies import DbSession, ViewerUser
from flowlens.common.config import get_settings
from flowlens.common.logging import get_logger
from flowlens.models.asset import Application, ApplicationMember, Asset
from flowlens.models.dependency import Dependency
from flowlens.models.folder import Folder
from flowlens.models.topology_exclusion import TopologyExclusion
from flowlens.schemas.folder import (
    ApplicationDependencyList,
    ApplicationDependencySummary,
    ApplicationInFolder,
    ArcDependency,
    ArcTopologyData,
    EdgeDirection,
    ExclusionEntityType,
    FolderDependency,
    FolderTree,
    FolderTreeNode,
    TopologyExclusionCreate,
    TopologyExclusionList,
    TopologyExclusionResponse,
)
from flowlens.schemas.topology import (
    PathResult,
    SubgraphRequest,
    TopologyConfig,
    TopologyEdge,
    TopologyFilter,
    TopologyGraph,
    TopologyNode,
    TraversalNode,
    TraversalResult,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/topology", tags=["topology"])


@router.get("/config", response_model=TopologyConfig)
async def get_topology_config(
    _user: ViewerUser,
) -> TopologyConfig:
    """Get topology configuration settings.

    Returns configuration that affects how the topology should be displayed,
    including whether external flows are discarded. This helps the frontend
    know which UI elements to show or hide.
    """
    settings = get_settings()

    return TopologyConfig(
        discard_external_flows=settings.resolution.discard_external_flows,
    )


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


def build_folder_tree_node(
    folder: Folder,
    excluded_folder_ids: set[UUID] | None = None,
    excluded_app_ids: set[UUID] | None = None,
) -> FolderTreeNode:
    """Recursively build a folder tree node from a Folder model.

    Args:
        folder: The folder to build the tree node from.
        excluded_folder_ids: Set of folder IDs to exclude from children.
        excluded_app_ids: Set of application IDs to exclude from applications.
    """
    excluded_folder_ids = excluded_folder_ids or set()
    excluded_app_ids = excluded_app_ids or set()

    # Filter children and applications
    children = [
        build_folder_tree_node(child, excluded_folder_ids, excluded_app_ids)
        for child in folder.children
        if child.id not in excluded_folder_ids
    ]
    applications = [
        ApplicationInFolder.model_validate(app)
        for app in folder.applications
        if app.id not in excluded_app_ids
    ]

    return FolderTreeNode(
        id=folder.id,
        name=folder.name,
        display_name=folder.display_name,
        color=folder.color,
        icon=folder.icon,
        order=folder.order,
        parent_id=folder.parent_id,
        children=children,
        applications=applications,
    )


@router.get("/arc", response_model=ArcTopologyData)
async def get_arc_topology(
    db: DbSession,
    user: ViewerUser,
    apply_exclusions: bool = Query(
        True,
        description="Whether to apply user's exclusions to filter the topology",
    ),
) -> ArcTopologyData:
    """Get arc-based topology data with folder hierarchy and dependencies.

    Returns a hierarchical folder structure with applications, plus aggregated
    dependencies between applications for arc visualization.

    By default, entities excluded by the user are filtered out from both
    the hierarchy and dependency aggregations. Set apply_exclusions=false
    to see all entities.
    """
    from sqlalchemy import func

    # Get user's exclusions if applying them
    excluded_folder_ids: set[UUID] = set()
    excluded_app_ids: set[UUID] = set()

    if apply_exclusions:
        exclusions_query = select(TopologyExclusion).where(
            TopologyExclusion.user_id == user.id
        )
        exclusions_result = await db.execute(exclusions_query)
        exclusions = exclusions_result.scalars().all()

        for exc in exclusions:
            if exc.entity_type == ExclusionEntityType.FOLDER.value:
                excluded_folder_ids.add(exc.entity_id)
            elif exc.entity_type == ExclusionEntityType.APPLICATION.value:
                excluded_app_ids.add(exc.entity_id)

    # Get all root folders with their children and applications eagerly loaded
    folder_query = (
        select(Folder)
        .where(Folder.parent_id == None)  # noqa: E711
        .options(
            selectinload(Folder.children).selectinload(Folder.children),
            selectinload(Folder.children).selectinload(Folder.applications),
            selectinload(Folder.applications),
        )
        .order_by(Folder.order, Folder.name)
    )

    folder_result = await db.execute(folder_query)
    root_folders = folder_result.scalars().all()

    # Filter out excluded folders
    root_folders = [f for f in root_folders if f.id not in excluded_folder_ids]

    # Count totals
    folder_count_result = await db.execute(select(func.count(Folder.id)))
    total_folders = folder_count_result.scalar() or 0

    app_count_result = await db.execute(select(func.count(Application.id)))
    total_applications = app_count_result.scalar() or 0

    # Get all applications with their folder assignments
    apps_query = select(Application).options(selectinload(Application.members))
    apps_result = await db.execute(apps_query)
    all_apps = apps_result.scalars().all()

    # Filter out excluded applications and apps in excluded folders
    all_apps = [
        app for app in all_apps
        if app.id not in excluded_app_ids
        and (app.folder_id is None or app.folder_id not in excluded_folder_ids)
    ]

    # Find unassigned applications (not in any folder)
    unassigned_apps = [app for app in all_apps if app.folder_id is None]

    # Build folder tree roots (pass exclusions for recursive filtering)
    tree_roots = [
        build_folder_tree_node(f, excluded_folder_ids, excluded_app_ids)
        for f in root_folders
    ]

    # Add "Unassigned" virtual folder if there are unassigned apps
    if unassigned_apps:
        unassigned_folder = FolderTreeNode(
            id="unassigned",
            name="Unassigned",
            display_name="Unassigned Applications",
            color="#64748b",  # Slate color
            icon=None,
            order=9999,
            parent_id=None,
            children=[],
            applications=[
                ApplicationInFolder.model_validate(app) for app in unassigned_apps
            ],
        )
        tree_roots.append(unassigned_folder)

    # Build folder tree
    hierarchy = FolderTree(
        roots=tree_roots,
        total_folders=total_folders,
        total_applications=total_applications,
    )

    # Build app_id -> app mapping and app_id -> folder_id mapping
    app_map = {app.id: app for app in all_apps}
    app_folder_map = {app.id: app.folder_id for app in all_apps}

    # Get asset_id -> application_id mapping
    asset_to_app: dict[UUID, UUID] = {}
    for app in all_apps:
        for member in app.members:
            asset_to_app[member.asset_id] = app.id

    # Get all active dependencies between assets in applications
    deps_query = select(Dependency).where(Dependency.valid_to.is_(None))
    deps_result = await db.execute(deps_query)
    all_deps = deps_result.scalars().all()

    # Aggregate dependencies by application pair (directional)
    # Key: (source_app_id, target_app_id) -> aggregated data
    app_deps_directional: dict[tuple[UUID, UUID], dict] = {}
    for dep in all_deps:
        source_app_id = asset_to_app.get(dep.source_asset_id)
        target_app_id = asset_to_app.get(dep.target_asset_id)

        # Only include dependencies where both assets belong to applications
        if source_app_id and target_app_id and source_app_id != target_app_id:
            key = (source_app_id, target_app_id)
            if key not in app_deps_directional:
                app_deps_directional[key] = {
                    "connection_count": 0,
                    "bytes_total": 0,
                    "bytes_last_24h": 0,
                }
            app_deps_directional[key]["connection_count"] += 1
            app_deps_directional[key]["bytes_total"] += dep.bytes_total or 0
            app_deps_directional[key]["bytes_last_24h"] += dep.bytes_last_24h or 0

    # Merge bi-directional app dependencies into single edges
    # Key: frozenset({app_id1, app_id2}) -> merged data with direction
    app_deps_merged: dict[frozenset, dict] = {}
    for (source_app_id, target_app_id), agg in app_deps_directional.items():
        edge_key = frozenset({source_app_id, target_app_id})
        if edge_key in app_deps_merged:
            # This is the reverse direction - mark as bi-directional and merge
            existing = app_deps_merged[edge_key]
            existing["direction"] = EdgeDirection.BI
            existing["connection_count"] += agg["connection_count"]
            existing["bytes_total"] += agg["bytes_total"]
            existing["bytes_last_24h"] += agg["bytes_last_24h"]
        else:
            # First time seeing this edge pair
            app_deps_merged[edge_key] = {
                "source_app_id": source_app_id,
                "target_app_id": target_app_id,
                "direction": EdgeDirection.OUT,
                "connection_count": agg["connection_count"],
                "bytes_total": agg["bytes_total"],
                "bytes_last_24h": agg["bytes_last_24h"],
            }

    # Build dependency list
    dependencies = []
    for agg in app_deps_merged.values():
        source_app = app_map.get(agg["source_app_id"])
        target_app = app_map.get(agg["target_app_id"])
        if source_app and target_app:
            dependencies.append(
                ArcDependency(
                    source_folder_id=app_folder_map.get(agg["source_app_id"]),
                    source_app_id=agg["source_app_id"],
                    source_app_name=source_app.name,
                    target_folder_id=app_folder_map.get(agg["target_app_id"]),
                    target_app_id=agg["target_app_id"],
                    target_app_name=target_app.name,
                    connection_count=agg["connection_count"],
                    bytes_total=agg["bytes_total"],
                    bytes_last_24h=agg["bytes_last_24h"],
                    direction=agg["direction"],
                )
            )

    # Sort by bytes descending
    dependencies.sort(key=lambda d: d.bytes_total, reverse=True)

    # Build folder-to-folder dependencies (aggregated from app dependencies)
    # Map folder_id to folder name for lookup
    folder_name_map: dict[UUID | str, str] = {}
    for folder in root_folders:
        folder_name_map[folder.id] = folder.display_name or folder.name
    if unassigned_apps:
        folder_name_map["unassigned"] = "Unassigned"

    # Aggregate by folder pair (directional first)
    folder_deps_directional: dict[tuple, dict] = {}
    for dep in dependencies:
        source_folder_id = dep.source_folder_id or "unassigned"
        target_folder_id = dep.target_folder_id or "unassigned"

        # Skip same-folder dependencies
        if source_folder_id == target_folder_id:
            continue

        key = (source_folder_id, target_folder_id)
        if key not in folder_deps_directional:
            folder_deps_directional[key] = {
                "connection_count": 0,
                "bytes_total": 0,
                "bytes_last_24h": 0,
            }
        folder_deps_directional[key]["connection_count"] += dep.connection_count
        folder_deps_directional[key]["bytes_total"] += dep.bytes_total
        folder_deps_directional[key]["bytes_last_24h"] += dep.bytes_last_24h

    # Merge bi-directional folder dependencies
    folder_deps_merged: dict[frozenset, dict] = {}
    for (source_folder_id, target_folder_id), agg in folder_deps_directional.items():
        edge_key = frozenset({source_folder_id, target_folder_id})
        if edge_key in folder_deps_merged:
            # Reverse direction exists - mark as bi-directional
            existing = folder_deps_merged[edge_key]
            existing["direction"] = EdgeDirection.BI
            existing["connection_count"] += agg["connection_count"]
            existing["bytes_total"] += agg["bytes_total"]
            existing["bytes_last_24h"] += agg["bytes_last_24h"]
        else:
            folder_deps_merged[edge_key] = {
                "source_folder_id": source_folder_id,
                "target_folder_id": target_folder_id,
                "direction": EdgeDirection.OUT,
                "connection_count": agg["connection_count"],
                "bytes_total": agg["bytes_total"],
                "bytes_last_24h": agg["bytes_last_24h"],
            }

    # Build folder dependency list
    folder_dependencies = []
    for agg in folder_deps_merged.values():
        source_name = folder_name_map.get(agg["source_folder_id"], "Unknown")
        target_name = folder_name_map.get(agg["target_folder_id"], "Unknown")
        folder_dependencies.append(
            FolderDependency(
                source_folder_id=agg["source_folder_id"],
                source_folder_name=source_name,
                target_folder_id=agg["target_folder_id"],
                target_folder_name=target_name,
                direction=agg["direction"],
                connection_count=agg["connection_count"],
                bytes_total=agg["bytes_total"],
                bytes_last_24h=agg["bytes_last_24h"],
            )
        )

    # Sort folder dependencies by bytes descending
    folder_dependencies.sort(key=lambda d: d.bytes_total, reverse=True)

    return ArcTopologyData(
        hierarchy=hierarchy,
        dependencies=dependencies,
        folder_dependencies=folder_dependencies,
        statistics={
            "total_folders": total_folders,
            "total_applications": total_applications,
            "total_dependencies": len(dependencies),
            "total_folder_dependencies": len(folder_dependencies),
        },
    )


@router.get("/arc/app/{app_id}/dependencies", response_model=ApplicationDependencyList)
async def get_app_dependencies(
    app_id: UUID,
    db: DbSession,
    _user: ViewerUser,
    direction: str = Query(
        "both",
        description="Filter by direction: 'incoming', 'outgoing', or 'both'",
    ),
) -> ApplicationDependencyList:
    """Get dependency details for a specific application.

    Returns a list of counterparties (apps that this app communicates with)
    along with traffic statistics for each connection.
    """
    # Get the application
    app_result = await db.execute(
        select(Application).where(Application.id == app_id)
    )
    app = app_result.scalar_one_or_none()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")

    # Get all member asset IDs for this application
    members_result = await db.execute(
        select(ApplicationMember.asset_id).where(
            ApplicationMember.application_id == app_id
        )
    )
    member_asset_ids = [row[0] for row in members_result.fetchall()]

    if not member_asset_ids:
        return ApplicationDependencyList(
            app_id=app_id,
            app_name=app.name,
            direction_filter=direction,
            dependencies=[],
            total_connections=0,
            total_bytes=0,
            total_bytes_24h=0,
        )

    # Build application membership mapping for all apps
    all_members_result = await db.execute(
        select(ApplicationMember.asset_id, ApplicationMember.application_id)
    )
    asset_to_app: dict[UUID, UUID] = {}
    for asset_id, application_id in all_members_result.fetchall():
        asset_to_app[asset_id] = application_id

    # Get all applications for name lookup
    apps_result = await db.execute(
        select(Application.id, Application.name, Application.folder_id)
    )
    app_info: dict[UUID, tuple[str, UUID | None]] = {}
    for aid, aname, folder_id in apps_result.fetchall():
        app_info[aid] = (aname, folder_id)

    # Get folder names
    folders_result = await db.execute(select(Folder.id, Folder.name))
    folder_names: dict[UUID, str] = {fid: fname for fid, fname in folders_result.fetchall()}

    # Query dependencies
    deps_query = select(Dependency)

    if direction == "outgoing":
        deps_query = deps_query.where(Dependency.source_asset_id.in_(member_asset_ids))
    elif direction == "incoming":
        deps_query = deps_query.where(Dependency.target_asset_id.in_(member_asset_ids))
    else:  # both
        deps_query = deps_query.where(
            (Dependency.source_asset_id.in_(member_asset_ids))
            | (Dependency.target_asset_id.in_(member_asset_ids))
        )

    deps_result = await db.execute(deps_query)
    dependencies = deps_result.scalars().all()

    # Aggregate by counterparty application
    counterparty_agg: dict[UUID, dict] = {}

    for dep in dependencies:
        source_app_id = asset_to_app.get(dep.source_asset_id)
        target_app_id = asset_to_app.get(dep.target_asset_id)

        # Determine if this is incoming or outgoing from our app's perspective
        if dep.source_asset_id in member_asset_ids:
            # Outgoing: our app is the source
            counterparty_app_id = target_app_id
            dep_direction = EdgeDirection.OUT
        else:
            # Incoming: our app is the target
            counterparty_app_id = source_app_id
            dep_direction = EdgeDirection.IN

        # Skip if counterparty is the same app or not in an application
        if not counterparty_app_id or counterparty_app_id == app_id:
            continue

        key = counterparty_app_id
        if key not in counterparty_agg:
            cp_name, cp_folder_id = app_info.get(counterparty_app_id, ("Unknown", None))
            cp_folder_name = folder_names.get(cp_folder_id) if cp_folder_id else None
            counterparty_agg[key] = {
                "counterparty_id": counterparty_app_id,
                "counterparty_name": cp_name,
                "counterparty_folder_id": cp_folder_id,
                "counterparty_folder_name": cp_folder_name,
                "direction": dep_direction,
                "connection_count": 0,
                "bytes_total": 0,
                "bytes_last_24h": 0,
                "last_seen": None,
            }

        agg = counterparty_agg[key]
        agg["connection_count"] += 1
        agg["bytes_total"] += dep.bytes_total or 0
        agg["bytes_last_24h"] += dep.bytes_last_24h or 0

        # Track bi-directional
        if agg["direction"] != dep_direction and agg["direction"] != EdgeDirection.BI:
            agg["direction"] = EdgeDirection.BI

        # Track most recent last_seen
        if dep.last_seen:
            last_seen_str = dep.last_seen.isoformat()
            if agg["last_seen"] is None or last_seen_str > agg["last_seen"]:
                agg["last_seen"] = last_seen_str

    # Build response
    dep_summaries = [
        ApplicationDependencySummary(**agg) for agg in counterparty_agg.values()
    ]

    # Sort by bytes_total descending
    dep_summaries.sort(key=lambda d: d.bytes_total, reverse=True)

    total_connections = sum(d.connection_count for d in dep_summaries)
    total_bytes = sum(d.bytes_total for d in dep_summaries)
    total_bytes_24h = sum(d.bytes_last_24h for d in dep_summaries)

    return ApplicationDependencyList(
        app_id=app_id,
        app_name=app.name,
        direction_filter=direction,
        dependencies=dep_summaries,
        total_connections=total_connections,
        total_bytes=total_bytes,
        total_bytes_24h=total_bytes_24h,
    )


@router.get("/arc/app/{app_id}/dependencies/export")
async def export_app_dependencies(
    app_id: UUID,
    db: DbSession,
    _user: ViewerUser,
    direction: str = Query(
        "both",
        description="Filter by direction: 'incoming', 'outgoing', or 'both'",
    ),
):
    """Export application dependencies as CSV.

    Returns a downloadable CSV file with dependency details.
    """
    from fastapi.responses import StreamingResponse
    import io
    import csv

    # Get the dependency list using the existing endpoint logic
    dep_list = await get_app_dependencies(app_id, db, _user, direction)

    # Create CSV in memory
    output = io.StringIO()
    writer = csv.writer(output)

    # Write header
    writer.writerow([
        "Counterparty Name",
        "Counterparty Folder",
        "Direction",
        "Connections",
        "Total Bytes",
        "Bytes (24h)",
        "Last Seen",
    ])

    # Write data rows
    for dep in dep_list.dependencies:
        direction_label = "Bi-directional" if dep.direction == EdgeDirection.BI else (
            "Outgoing" if dep.direction == EdgeDirection.OUT else "Incoming"
        )
        writer.writerow([
            dep.counterparty_name,
            dep.counterparty_folder_name or "",
            direction_label,
            dep.connection_count,
            dep.bytes_total,
            dep.bytes_last_24h,
            dep.last_seen or "",
        ])

    # Reset stream position
    output.seek(0)

    # Generate filename
    filename = f"{dep_list.app_name.replace(' ', '_')}_dependencies_{direction}.csv"

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# =============================================================================
# Topology Exclusion Endpoints
# =============================================================================


@router.get("/exclusions", response_model=TopologyExclusionList)
async def list_exclusions(
    db: DbSession,
    user: ViewerUser,
) -> TopologyExclusionList:
    """List all topology exclusions for the current user.

    Returns the user's excluded folders and applications that are hidden
    from the arc topology view.
    """
    # Get exclusions for the current user
    query = select(TopologyExclusion).where(TopologyExclusion.user_id == user.id)
    result = await db.execute(query)
    exclusions = result.scalars().all()

    # Build response with entity names
    items = []
    for exc in exclusions:
        entity_name = None

        # Look up the entity name based on type
        if exc.entity_type == ExclusionEntityType.FOLDER.value:
            folder_result = await db.execute(
                select(Folder.name).where(Folder.id == exc.entity_id)
            )
            folder_name = folder_result.scalar()
            entity_name = folder_name
        elif exc.entity_type == ExclusionEntityType.APPLICATION.value:
            app_result = await db.execute(
                select(Application.name).where(Application.id == exc.entity_id)
            )
            app_name = app_result.scalar()
            entity_name = app_name

        items.append(
            TopologyExclusionResponse(
                id=exc.id,
                user_id=exc.user_id,
                entity_type=exc.entity_type,
                entity_id=exc.entity_id,
                entity_name=entity_name,
                reason=exc.reason,
                created_at=exc.created_at,
            )
        )

    return TopologyExclusionList(items=items, total=len(items))


@router.post("/exclusions", response_model=TopologyExclusionResponse, status_code=201)
async def create_exclusion(
    data: TopologyExclusionCreate,
    db: DbSession,
    user: ViewerUser,
) -> TopologyExclusionResponse:
    """Create a new topology exclusion.

    Excludes a folder or application from the user's arc topology view.
    The excluded entity will not be rendered and will not contribute
    to dependency aggregations.
    """
    # Verify the entity exists
    entity_name = None
    if data.entity_type == ExclusionEntityType.FOLDER:
        folder_result = await db.execute(
            select(Folder).where(Folder.id == data.entity_id)
        )
        folder = folder_result.scalar_one_or_none()
        if not folder:
            raise HTTPException(status_code=404, detail="Folder not found")
        entity_name = folder.name
    elif data.entity_type == ExclusionEntityType.APPLICATION:
        app_result = await db.execute(
            select(Application).where(Application.id == data.entity_id)
        )
        app = app_result.scalar_one_or_none()
        if not app:
            raise HTTPException(status_code=404, detail="Application not found")
        entity_name = app.name

    # Check if exclusion already exists
    existing_query = select(TopologyExclusion).where(
        TopologyExclusion.user_id == user.id,
        TopologyExclusion.entity_type == data.entity_type.value,
        TopologyExclusion.entity_id == data.entity_id,
    )
    existing_result = await db.execute(existing_query)
    if existing_result.scalar_one_or_none():
        raise HTTPException(
            status_code=400,
            detail="Exclusion already exists for this entity",
        )

    # Create the exclusion
    exclusion = TopologyExclusion(
        user_id=user.id,
        entity_type=data.entity_type.value,
        entity_id=data.entity_id,
        reason=data.reason,
    )
    db.add(exclusion)
    await db.commit()
    await db.refresh(exclusion)

    return TopologyExclusionResponse(
        id=exclusion.id,
        user_id=exclusion.user_id,
        entity_type=exclusion.entity_type,
        entity_id=exclusion.entity_id,
        entity_name=entity_name,
        reason=exclusion.reason,
        created_at=exclusion.created_at,
    )


@router.delete("/exclusions/{exclusion_id}", status_code=204)
async def delete_exclusion(
    exclusion_id: UUID,
    db: DbSession,
    user: ViewerUser,
) -> None:
    """Delete a topology exclusion.

    Removes an exclusion, making the entity visible again in the
    user's arc topology view.
    """
    # Get the exclusion (must belong to the current user)
    query = select(TopologyExclusion).where(
        TopologyExclusion.id == exclusion_id,
        TopologyExclusion.user_id == user.id,
    )
    result = await db.execute(query)
    exclusion = result.scalar_one_or_none()

    if not exclusion:
        raise HTTPException(status_code=404, detail="Exclusion not found")

    await db.delete(exclusion)
    await db.commit()

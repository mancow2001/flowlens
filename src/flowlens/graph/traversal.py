"""Graph traversal using recursive CTEs.

Provides upstream and downstream traversal of the dependency graph
using PostgreSQL recursive Common Table Expressions (CTEs).
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import and_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from flowlens.common.logging import get_logger
from flowlens.models.asset import Asset
from flowlens.models.dependency import Dependency

logger = get_logger(__name__)


@dataclass
class TraversalNode:
    """A node in the traversal result."""

    asset_id: UUID
    asset_name: str
    depth: int
    path: list[UUID]
    incoming_dependency_id: UUID | None = None
    bytes_total: int = 0
    last_seen: datetime | None = None


@dataclass
class TraversalResult:
    """Result of a graph traversal."""

    root_asset_id: UUID
    direction: str  # "upstream" or "downstream"
    nodes: list[TraversalNode]
    max_depth: int
    total_nodes: int


class GraphTraversal:
    """Performs graph traversals using recursive CTEs.

    Supports:
    - Upstream traversal (who depends on this asset)
    - Downstream traversal (what does this asset depend on)
    - Path finding between two assets
    """

    def __init__(self, max_depth: int = 10) -> None:
        """Initialize traversal.

        Args:
            max_depth: Maximum recursion depth.
        """
        self._max_depth = max_depth

    async def get_upstream(
        self,
        db: AsyncSession,
        asset_id: UUID,
        max_depth: int | None = None,
        as_of: datetime | None = None,
    ) -> TraversalResult:
        """Get all assets that depend on the given asset.

        Uses a recursive CTE to traverse the dependency graph
        from target back to sources.

        Args:
            db: Database session.
            asset_id: Starting asset ID.
            max_depth: Maximum traversal depth.
            as_of: Point-in-time for temporal query.

        Returns:
            Traversal result with upstream assets.
        """
        depth = max_depth or self._max_depth

        # Build temporal filter
        temporal_filter = "d.valid_to IS NULL"
        if as_of:
            temporal_filter = f"""
                d.valid_from <= '{as_of.isoformat()}'
                AND (d.valid_to IS NULL OR d.valid_to > '{as_of.isoformat()}')
            """

        query = text(f"""
            WITH RECURSIVE upstream AS (
                -- Base case: direct dependencies on this asset
                SELECT
                    d.source_asset_id AS asset_id,
                    d.id AS dependency_id,
                    d.bytes_total,
                    d.last_seen,
                    1 AS depth,
                    ARRAY[d.source_asset_id] AS path
                FROM dependencies d
                WHERE d.target_asset_id = :asset_id
                AND {temporal_filter}

                UNION ALL

                -- Recursive case: dependencies on those assets
                SELECT
                    d.source_asset_id,
                    d.id,
                    d.bytes_total,
                    d.last_seen,
                    u.depth + 1,
                    u.path || d.source_asset_id
                FROM dependencies d
                JOIN upstream u ON d.target_asset_id = u.asset_id
                WHERE u.depth < :max_depth
                AND NOT d.source_asset_id = ANY(u.path)  -- Cycle detection
                AND {temporal_filter}
            )
            SELECT
                u.asset_id,
                a.name AS asset_name,
                u.dependency_id,
                u.bytes_total,
                u.last_seen,
                u.depth,
                u.path
            FROM upstream u
            JOIN assets a ON a.id = u.asset_id
            WHERE a.deleted_at IS NULL
            ORDER BY u.depth, a.name
        """)

        result = await db.execute(
            query,
            {"asset_id": str(asset_id), "max_depth": depth},
        )

        nodes = []
        for row in result.fetchall():
            nodes.append(TraversalNode(
                asset_id=UUID(row.asset_id),
                asset_name=row.asset_name,
                depth=row.depth,
                path=[UUID(p) for p in row.path],
                incoming_dependency_id=UUID(row.dependency_id) if row.dependency_id else None,
                bytes_total=row.bytes_total or 0,
                last_seen=row.last_seen,
            ))

        return TraversalResult(
            root_asset_id=asset_id,
            direction="upstream",
            nodes=nodes,
            max_depth=max(n.depth for n in nodes) if nodes else 0,
            total_nodes=len(nodes),
        )

    async def get_downstream(
        self,
        db: AsyncSession,
        asset_id: UUID,
        max_depth: int | None = None,
        as_of: datetime | None = None,
    ) -> TraversalResult:
        """Get all assets that this asset depends on.

        Uses a recursive CTE to traverse the dependency graph
        from source to targets.

        Args:
            db: Database session.
            asset_id: Starting asset ID.
            max_depth: Maximum traversal depth.
            as_of: Point-in-time for temporal query.

        Returns:
            Traversal result with downstream assets.
        """
        depth = max_depth or self._max_depth

        temporal_filter = "d.valid_to IS NULL"
        if as_of:
            temporal_filter = f"""
                d.valid_from <= '{as_of.isoformat()}'
                AND (d.valid_to IS NULL OR d.valid_to > '{as_of.isoformat()}')
            """

        query = text(f"""
            WITH RECURSIVE downstream AS (
                -- Base case: direct dependencies from this asset
                SELECT
                    d.target_asset_id AS asset_id,
                    d.id AS dependency_id,
                    d.bytes_total,
                    d.last_seen,
                    1 AS depth,
                    ARRAY[d.target_asset_id] AS path
                FROM dependencies d
                WHERE d.source_asset_id = :asset_id
                AND {temporal_filter}

                UNION ALL

                -- Recursive case: dependencies from those assets
                SELECT
                    d.target_asset_id,
                    d.id,
                    d.bytes_total,
                    d.last_seen,
                    ds.depth + 1,
                    ds.path || d.target_asset_id
                FROM dependencies d
                JOIN downstream ds ON d.source_asset_id = ds.asset_id
                WHERE ds.depth < :max_depth
                AND NOT d.target_asset_id = ANY(ds.path)  -- Cycle detection
                AND {temporal_filter}
            )
            SELECT
                ds.asset_id,
                a.name AS asset_name,
                ds.dependency_id,
                ds.bytes_total,
                ds.last_seen,
                ds.depth,
                ds.path
            FROM downstream ds
            JOIN assets a ON a.id = ds.asset_id
            WHERE a.deleted_at IS NULL
            ORDER BY ds.depth, a.name
        """)

        result = await db.execute(
            query,
            {"asset_id": str(asset_id), "max_depth": depth},
        )

        nodes = []
        for row in result.fetchall():
            nodes.append(TraversalNode(
                asset_id=UUID(row.asset_id),
                asset_name=row.asset_name,
                depth=row.depth,
                path=[UUID(p) for p in row.path],
                incoming_dependency_id=UUID(row.dependency_id) if row.dependency_id else None,
                bytes_total=row.bytes_total or 0,
                last_seen=row.last_seen,
            ))

        return TraversalResult(
            root_asset_id=asset_id,
            direction="downstream",
            nodes=nodes,
            max_depth=max(n.depth for n in nodes) if nodes else 0,
            total_nodes=len(nodes),
        )

    async def find_path(
        self,
        db: AsyncSession,
        source_asset_id: UUID,
        target_asset_id: UUID,
        max_depth: int | None = None,
    ) -> list[list[UUID]] | None:
        """Find paths between two assets.

        Uses a recursive CTE to find all paths from source to target.

        Args:
            db: Database session.
            source_asset_id: Starting asset.
            target_asset_id: Ending asset.
            max_depth: Maximum path length.

        Returns:
            List of paths (each path is a list of asset IDs), or None if no path.
        """
        depth = max_depth or self._max_depth

        query = text("""
            WITH RECURSIVE paths AS (
                -- Base case: direct dependencies from source
                SELECT
                    d.target_asset_id AS current_id,
                    ARRAY[:source_id, d.target_asset_id::text] AS path,
                    1 AS depth
                FROM dependencies d
                WHERE d.source_asset_id = :source_id
                AND d.valid_to IS NULL

                UNION ALL

                -- Recursive case: extend paths
                SELECT
                    d.target_asset_id,
                    p.path || d.target_asset_id::text,
                    p.depth + 1
                FROM dependencies d
                JOIN paths p ON d.source_asset_id = p.current_id
                WHERE p.depth < :max_depth
                AND NOT d.target_asset_id::text = ANY(p.path)
                AND d.valid_to IS NULL
            )
            SELECT path
            FROM paths
            WHERE current_id = :target_id
            ORDER BY array_length(path, 1)
            LIMIT 10
        """)

        result = await db.execute(
            query,
            {
                "source_id": str(source_asset_id),
                "target_id": str(target_asset_id),
                "max_depth": depth,
            },
        )

        paths = []
        for row in result.fetchall():
            paths.append([UUID(p) for p in row.path])

        return paths if paths else None

    async def get_neighbors(
        self,
        db: AsyncSession,
        asset_id: UUID,
        direction: str = "both",
    ) -> dict[str, list[dict[str, Any]]]:
        """Get immediate neighbors of an asset.

        Args:
            db: Database session.
            asset_id: Asset to query.
            direction: "upstream", "downstream", or "both".

        Returns:
            Dictionary with "upstream" and/or "downstream" lists.
        """
        result = {"upstream": [], "downstream": []}

        if direction in ("upstream", "both"):
            # Assets that depend on this asset
            query = (
                select(
                    Asset.id,
                    Asset.name,
                    Dependency.id.label("dep_id"),
                    Dependency.target_port,
                    Dependency.protocol,
                    Dependency.bytes_total,
                    Dependency.last_seen,
                )
                .join(Dependency, Dependency.source_asset_id == Asset.id)
                .where(
                    Dependency.target_asset_id == asset_id,
                    Dependency.valid_to.is_(None),
                    Asset.deleted_at.is_(None),
                )
            )
            rows = await db.execute(query)
            for row in rows.fetchall():
                result["upstream"].append({
                    "asset_id": row.id,
                    "asset_name": row.name,
                    "dependency_id": row.dep_id,
                    "port": row.target_port,
                    "protocol": row.protocol,
                    "bytes_total": row.bytes_total,
                    "last_seen": row.last_seen,
                })

        if direction in ("downstream", "both"):
            # Assets this asset depends on
            query = (
                select(
                    Asset.id,
                    Asset.name,
                    Dependency.id.label("dep_id"),
                    Dependency.target_port,
                    Dependency.protocol,
                    Dependency.bytes_total,
                    Dependency.last_seen,
                )
                .join(Dependency, Dependency.target_asset_id == Asset.id)
                .where(
                    Dependency.source_asset_id == asset_id,
                    Dependency.valid_to.is_(None),
                    Asset.deleted_at.is_(None),
                )
            )
            rows = await db.execute(query)
            for row in rows.fetchall():
                result["downstream"].append({
                    "asset_id": row.id,
                    "asset_name": row.name,
                    "dependency_id": row.dep_id,
                    "port": row.target_port,
                    "protocol": row.protocol,
                    "bytes_total": row.bytes_total,
                    "last_seen": row.last_seen,
                })

        return result

    async def get_full_graph(
        self,
        db: AsyncSession,
        asset_ids: list[UUID] | None = None,
        limit: int = 1000,
    ) -> dict[str, Any]:
        """Get full dependency graph or subgraph.

        Args:
            db: Database session.
            asset_ids: Optional list of asset IDs to filter.
            limit: Maximum number of dependencies.

        Returns:
            Dictionary with "nodes" and "edges" lists.
        """
        # Get dependencies
        query = (
            select(Dependency)
            .where(Dependency.valid_to.is_(None))
            .limit(limit)
        )

        if asset_ids:
            query = query.where(
                (Dependency.source_asset_id.in_(asset_ids)) |
                (Dependency.target_asset_id.in_(asset_ids))
            )

        result = await db.execute(query)
        dependencies = result.scalars().all()

        # Collect unique asset IDs
        asset_id_set = set()
        for dep in dependencies:
            asset_id_set.add(dep.source_asset_id)
            asset_id_set.add(dep.target_asset_id)

        # Get asset details
        assets_result = await db.execute(
            select(Asset)
            .where(
                Asset.id.in_(list(asset_id_set)),
                Asset.deleted_at.is_(None),
            )
        )
        assets = {a.id: a for a in assets_result.scalars().all()}

        # Build response
        nodes = []
        for asset_id, asset in assets.items():
            nodes.append({
                "id": str(asset_id),
                "name": asset.name,
                "type": asset.asset_type.value if asset.asset_type else "unknown",
                "is_internal": asset.is_internal,
                "is_critical": asset.is_critical,
            })

        edges = []
        for dep in dependencies:
            if dep.source_asset_id in assets and dep.target_asset_id in assets:
                edges.append({
                    "id": str(dep.id),
                    "source": str(dep.source_asset_id),
                    "target": str(dep.target_asset_id),
                    "port": dep.target_port,
                    "protocol": dep.protocol,
                    "bytes_total": dep.bytes_total,
                    "last_seen": dep.last_seen.isoformat() if dep.last_seen else None,
                })

        return {
            "nodes": nodes,
            "edges": edges,
            "node_count": len(nodes),
            "edge_count": len(edges),
        }

"""Blast radius calculation for dependency graph.

Calculates the "blast radius" - the full extent of impact
from an asset failure, considering both directions of dependencies.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from flowlens.common.logging import get_logger
from flowlens.graph.traversal import GraphTraversal
from flowlens.models.asset import Asset

logger = get_logger(__name__)


@dataclass
class BlastRadiusNode:
    """A node in the blast radius."""

    asset_id: UUID
    asset_name: str
    direction: str  # "upstream" (depends on source) or "downstream" (source depends on)
    distance: int
    is_critical: bool = False
    bytes_total: int = 0


@dataclass
class BlastRadius:
    """Complete blast radius from an asset failure."""

    source_asset_id: UUID
    source_asset_name: str
    upstream_nodes: list[BlastRadiusNode]  # Assets that depend on source
    downstream_nodes: list[BlastRadiusNode]  # Assets source depends on
    total_nodes: int
    max_upstream_depth: int
    max_downstream_depth: int
    critical_nodes_count: int
    radius_score: int  # 0-100
    calculated_at: datetime = field(default_factory=datetime.utcnow)


class BlastRadiusCalculator:
    """Calculates blast radius for asset failures.

    The blast radius includes:
    - Upstream: All assets that depend on the failed asset
    - Downstream: All assets that the failed asset depends on
      (these may also fail if the source has critical dependencies)

    This gives a complete picture of failure propagation.
    """

    def __init__(
        self,
        traversal: GraphTraversal | None = None,
        max_depth: int = 10,
    ) -> None:
        """Initialize calculator.

        Args:
            traversal: Graph traversal instance.
            max_depth: Maximum traversal depth.
        """
        self._traversal = traversal or GraphTraversal(max_depth)
        self._max_depth = max_depth

    async def calculate(
        self,
        db: AsyncSession,
        asset_id: UUID,
        include_downstream: bool = True,
    ) -> BlastRadius:
        """Calculate blast radius for an asset.

        Args:
            db: Database session.
            asset_id: Asset to analyze.
            include_downstream: Include downstream dependencies.

        Returns:
            Blast radius result.
        """
        # Get asset details
        result = await db.execute(
            select(Asset).where(Asset.id == asset_id)
        )
        source_asset = result.scalar_one_or_none()

        if not source_asset:
            raise ValueError(f"Asset not found: {asset_id}")

        # Get critical asset IDs
        critical_result = await db.execute(
            select(Asset.id).where(
                Asset.is_critical == True,
                Asset.deleted_at.is_(None),
            )
        )
        critical_ids = {row[0] for row in critical_result.fetchall()}

        # Get upstream (who depends on this asset)
        upstream_result = await self._traversal.get_upstream(
            db, asset_id, max_depth=self._max_depth
        )

        upstream_nodes = []
        for node in upstream_result.nodes:
            upstream_nodes.append(BlastRadiusNode(
                asset_id=node.asset_id,
                asset_name=node.asset_name,
                direction="upstream",
                distance=node.depth,
                is_critical=node.asset_id in critical_ids,
                bytes_total=node.bytes_total,
            ))

        # Get downstream (what does this asset depend on)
        downstream_nodes = []
        max_downstream_depth = 0

        if include_downstream:
            downstream_result = await self._traversal.get_downstream(
                db, asset_id, max_depth=self._max_depth
            )

            for node in downstream_result.nodes:
                downstream_nodes.append(BlastRadiusNode(
                    asset_id=node.asset_id,
                    asset_name=node.asset_name,
                    direction="downstream",
                    distance=node.depth,
                    is_critical=node.asset_id in critical_ids,
                    bytes_total=node.bytes_total,
                ))

            max_downstream_depth = downstream_result.max_depth

        # Count critical nodes
        critical_count = sum(
            1 for n in upstream_nodes + downstream_nodes if n.is_critical
        )

        # Calculate radius score
        radius_score = self._calculate_radius_score(
            upstream_count=len(upstream_nodes),
            downstream_count=len(downstream_nodes),
            critical_count=critical_count,
            max_upstream_depth=upstream_result.max_depth,
            max_downstream_depth=max_downstream_depth,
            source_is_critical=source_asset.is_critical,
        )

        return BlastRadius(
            source_asset_id=asset_id,
            source_asset_name=source_asset.name,
            upstream_nodes=upstream_nodes,
            downstream_nodes=downstream_nodes,
            total_nodes=len(upstream_nodes) + len(downstream_nodes),
            max_upstream_depth=upstream_result.max_depth,
            max_downstream_depth=max_downstream_depth,
            critical_nodes_count=critical_count,
            radius_score=radius_score,
        )

    def _calculate_radius_score(
        self,
        upstream_count: int,
        downstream_count: int,
        critical_count: int,
        max_upstream_depth: int,
        max_downstream_depth: int,
        source_is_critical: bool,
    ) -> int:
        """Calculate blast radius score (0-100).

        Higher scores indicate larger blast radius.

        Args:
            upstream_count: Number of upstream nodes.
            downstream_count: Number of downstream nodes.
            critical_count: Number of critical nodes.
            max_upstream_depth: Max upstream traversal depth.
            max_downstream_depth: Max downstream traversal depth.
            source_is_critical: Whether source is critical.

        Returns:
            Radius score 0-100.
        """
        score = 0

        # Total node count factor (max 30)
        total_nodes = upstream_count + downstream_count
        score += min(30, total_nodes * 2)

        # Depth factor (max 20)
        max_depth = max(max_upstream_depth, max_downstream_depth)
        score += min(20, max_depth * 4)

        # Critical nodes factor (max 30)
        score += min(30, critical_count * 10)

        # Source criticality bonus
        if source_is_critical:
            score += 10

        # Spread factor (both directions) (max 10)
        if upstream_count > 0 and downstream_count > 0:
            score += 10

        return min(100, score)

    async def get_largest_blast_radii(
        self,
        db: AsyncSession,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Get assets with largest potential blast radii.

        Args:
            db: Database session.
            limit: Maximum number to return.

        Returns:
            List of assets with blast radius estimates.
        """
        # Query to find assets with most connections
        query = text("""
            WITH connection_counts AS (
                SELECT
                    a.id,
                    a.name,
                    a.is_critical,
                    COALESCE(upstream.cnt, 0) as upstream_count,
                    COALESCE(downstream.cnt, 0) as downstream_count,
                    COALESCE(upstream.bytes, 0) + COALESCE(downstream.bytes, 0) as total_bytes
                FROM assets a
                LEFT JOIN (
                    SELECT target_asset_id as asset_id, COUNT(*) as cnt, SUM(bytes_total) as bytes
                    FROM dependencies
                    WHERE valid_to IS NULL
                    GROUP BY target_asset_id
                ) upstream ON upstream.asset_id = a.id
                LEFT JOIN (
                    SELECT source_asset_id as asset_id, COUNT(*) as cnt, SUM(bytes_total) as bytes
                    FROM dependencies
                    WHERE valid_to IS NULL
                    GROUP BY source_asset_id
                ) downstream ON downstream.asset_id = a.id
                WHERE a.deleted_at IS NULL
            )
            SELECT *,
                (upstream_count + downstream_count) as total_connections
            FROM connection_counts
            WHERE upstream_count > 0 OR downstream_count > 0
            ORDER BY
                is_critical DESC,
                total_connections DESC,
                total_bytes DESC
            LIMIT :limit
        """)

        result = await db.execute(query, {"limit": limit})

        largest = []
        for row in result.fetchall():
            # Estimate blast radius score
            score = min(30, (row.upstream_count + row.downstream_count) * 2)
            if row.is_critical:
                score += 20
            if row.upstream_count > 0 and row.downstream_count > 0:
                score += 10

            largest.append({
                "asset_id": row.id,
                "asset_name": row.name,
                "is_critical": row.is_critical,
                "upstream_count": row.upstream_count,
                "downstream_count": row.downstream_count,
                "total_bytes": row.total_bytes,
                "estimated_radius_score": min(100, score),
            })

        return largest

    async def visualize_radius(
        self,
        db: AsyncSession,
        asset_id: UUID,
    ) -> dict[str, Any]:
        """Get blast radius data formatted for visualization.

        Args:
            db: Database session.
            asset_id: Asset to visualize.

        Returns:
            Visualization data with nodes and edges.
        """
        radius = await self.calculate(db, asset_id, include_downstream=True)

        # Build visualization data
        nodes = [{
            "id": str(radius.source_asset_id),
            "name": radius.source_asset_name,
            "type": "source",
            "level": 0,
        }]

        edges = []

        # Add upstream nodes (they connect TO the source)
        for node in radius.upstream_nodes:
            nodes.append({
                "id": str(node.asset_id),
                "name": node.asset_name,
                "type": "upstream",
                "level": -node.distance,
                "is_critical": node.is_critical,
            })

            # Edge from upstream to source (or its dependency)
            if node.distance == 1:
                edges.append({
                    "source": str(node.asset_id),
                    "target": str(radius.source_asset_id),
                    "bytes": node.bytes_total,
                })

        # Add downstream nodes (source connects TO them)
        for node in radius.downstream_nodes:
            nodes.append({
                "id": str(node.asset_id),
                "name": node.asset_name,
                "type": "downstream",
                "level": node.distance,
                "is_critical": node.is_critical,
            })

            # Edge from source to downstream (at distance 1)
            if node.distance == 1:
                edges.append({
                    "source": str(radius.source_asset_id),
                    "target": str(node.asset_id),
                    "bytes": node.bytes_total,
                })

        return {
            "source_asset_id": str(radius.source_asset_id),
            "source_asset_name": radius.source_asset_name,
            "radius_score": radius.radius_score,
            "nodes": nodes,
            "edges": edges,
            "summary": {
                "total_nodes": radius.total_nodes,
                "upstream_count": len(radius.upstream_nodes),
                "downstream_count": len(radius.downstream_nodes),
                "critical_count": radius.critical_nodes_count,
                "max_upstream_depth": radius.max_upstream_depth,
                "max_downstream_depth": radius.max_downstream_depth,
            },
        }

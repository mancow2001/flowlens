"""Impact analysis for dependency graph.

Calculates the potential impact of asset failures by analyzing
the dependency graph structure.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from flowlens.common.logging import get_logger
from flowlens.graph.traversal import GraphTraversal, TraversalResult
from flowlens.models.asset import Asset
from flowlens.models.dependency import Dependency

logger = get_logger(__name__)


@dataclass
class ImpactedAsset:
    """An asset impacted by a failure."""

    asset_id: UUID
    asset_name: str
    distance: int  # Hops from failed asset
    impact_type: str  # "direct", "indirect", "cascading"
    dependency_path: list[UUID]
    bytes_at_risk: int = 0


@dataclass
class ImpactAnalysis:
    """Result of impact analysis."""

    source_asset_id: UUID
    source_asset_name: str
    total_impacted: int
    direct_impacted: int
    indirect_impacted: int
    critical_impacted: int
    impacted_assets: list[ImpactedAsset]
    impact_score: int  # 0-100
    bytes_at_risk: int
    analyzed_at: datetime = field(default_factory=datetime.utcnow)


class ImpactAnalyzer:
    """Analyzes impact of asset failures.

    Determines which assets would be affected if a given asset
    becomes unavailable, considering the dependency graph structure.
    """

    def __init__(
        self,
        traversal: GraphTraversal | None = None,
        max_depth: int = 10,
    ) -> None:
        """Initialize analyzer.

        Args:
            traversal: Graph traversal instance.
            max_depth: Maximum analysis depth.
        """
        self._traversal = traversal or GraphTraversal(max_depth)
        self._max_depth = max_depth

    async def analyze(
        self,
        db: AsyncSession,
        asset_id: UUID,
        include_indirect: bool = True,
    ) -> ImpactAnalysis:
        """Analyze impact of asset failure.

        Finds all assets that depend on the given asset (upstream).
        These are the assets that would be impacted if the asset fails.

        Args:
            db: Database session.
            asset_id: Asset to analyze.
            include_indirect: Include indirect dependencies.

        Returns:
            Impact analysis result.
        """
        # Get asset details
        result = await db.execute(
            select(Asset).where(Asset.id == asset_id)
        )
        source_asset = result.scalar_one_or_none()

        if not source_asset:
            raise ValueError(f"Asset not found: {asset_id}")

        # Get upstream dependencies (assets that depend on this one)
        depth = self._max_depth if include_indirect else 1
        upstream = await self._traversal.get_upstream(db, asset_id, max_depth=depth)

        # Categorize impacted assets
        impacted_assets: list[ImpactedAsset] = []
        direct_count = 0
        indirect_count = 0
        critical_count = 0
        total_bytes_at_risk = 0

        # Get critical asset IDs for scoring
        critical_result = await db.execute(
            select(Asset.id).where(
                Asset.is_critical == True,
                Asset.deleted_at.is_(None),
            )
        )
        critical_ids = {row[0] for row in critical_result.fetchall()}

        for node in upstream.nodes:
            impact_type = "direct" if node.depth == 1 else "indirect"
            if node.depth > 2:
                impact_type = "cascading"

            is_critical = node.asset_id in critical_ids

            impacted_assets.append(ImpactedAsset(
                asset_id=node.asset_id,
                asset_name=node.asset_name,
                distance=node.depth,
                impact_type=impact_type,
                dependency_path=node.path,
                bytes_at_risk=node.bytes_total,
            ))

            total_bytes_at_risk += node.bytes_total

            if node.depth == 1:
                direct_count += 1
            else:
                indirect_count += 1

            if is_critical:
                critical_count += 1

        # Calculate impact score (0-100)
        impact_score = self._calculate_impact_score(
            direct_count=direct_count,
            indirect_count=indirect_count,
            critical_count=critical_count,
            total_impacted=len(impacted_assets),
            bytes_at_risk=total_bytes_at_risk,
            source_is_critical=source_asset.is_critical,
        )

        return ImpactAnalysis(
            source_asset_id=asset_id,
            source_asset_name=source_asset.name,
            total_impacted=len(impacted_assets),
            direct_impacted=direct_count,
            indirect_impacted=indirect_count,
            critical_impacted=critical_count,
            impacted_assets=impacted_assets,
            impact_score=impact_score,
            bytes_at_risk=total_bytes_at_risk,
        )

    def _calculate_impact_score(
        self,
        direct_count: int,
        indirect_count: int,
        critical_count: int,
        total_impacted: int,
        bytes_at_risk: int,
        source_is_critical: bool,
    ) -> int:
        """Calculate impact score (0-100).

        Higher scores indicate greater potential impact.

        Args:
            direct_count: Directly impacted assets.
            indirect_count: Indirectly impacted assets.
            critical_count: Critical assets impacted.
            total_impacted: Total impacted count.
            bytes_at_risk: Total bytes flowing through.
            source_is_critical: Whether source is critical.

        Returns:
            Impact score 0-100.
        """
        score = 0

        # Base score from direct dependencies (max 30)
        score += min(30, direct_count * 5)

        # Score from indirect dependencies (max 20)
        score += min(20, indirect_count * 2)

        # Critical assets have high impact (max 30)
        score += min(30, critical_count * 10)

        # Source criticality bonus
        if source_is_critical:
            score += 10

        # Traffic volume factor (max 10)
        if bytes_at_risk > 1_000_000_000:  # 1GB
            score += 10
        elif bytes_at_risk > 100_000_000:  # 100MB
            score += 5

        return min(100, score)

    async def get_high_impact_assets(
        self,
        db: AsyncSession,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Get assets with highest impact scores.

        Analyzes all assets and returns those with highest
        potential impact if they fail.

        Args:
            db: Database session.
            limit: Maximum number to return.

        Returns:
            List of assets with impact scores.
        """
        # Get assets that are targets of dependencies (have upstream)
        query = text("""
            SELECT
                a.id,
                a.name,
                a.is_critical,
                COUNT(DISTINCT d.source_asset_id) as upstream_count,
                SUM(d.bytes_total) as total_bytes
            FROM assets a
            JOIN dependencies d ON d.target_asset_id = a.id
            WHERE d.valid_to IS NULL
            AND a.deleted_at IS NULL
            GROUP BY a.id, a.name, a.is_critical
            ORDER BY
                a.is_critical DESC,
                upstream_count DESC,
                total_bytes DESC
            LIMIT :limit
        """)

        result = await db.execute(query, {"limit": limit})

        high_impact = []
        for row in result.fetchall():
            # Quick score estimation without full analysis
            score = min(30, row.upstream_count * 5)
            if row.is_critical:
                score += 20
            if row.total_bytes and row.total_bytes > 1_000_000_000:
                score += 10

            high_impact.append({
                "asset_id": row.id,
                "asset_name": row.name,
                "is_critical": row.is_critical,
                "upstream_count": row.upstream_count,
                "total_bytes": row.total_bytes,
                "estimated_impact_score": min(100, score),
            })

        return high_impact

    async def compare_scenarios(
        self,
        db: AsyncSession,
        asset_ids: list[UUID],
    ) -> dict[str, Any]:
        """Compare impact of multiple asset failures.

        Args:
            db: Database session.
            asset_ids: Assets to compare.

        Returns:
            Comparison results.
        """
        results = []

        for asset_id in asset_ids:
            try:
                analysis = await self.analyze(db, asset_id, include_indirect=True)
                results.append({
                    "asset_id": str(asset_id),
                    "asset_name": analysis.source_asset_name,
                    "impact_score": analysis.impact_score,
                    "total_impacted": analysis.total_impacted,
                    "critical_impacted": analysis.critical_impacted,
                    "bytes_at_risk": analysis.bytes_at_risk,
                })
            except ValueError:
                continue

        # Sort by impact score
        results.sort(key=lambda x: x["impact_score"], reverse=True)

        return {
            "scenarios": results,
            "highest_impact": results[0] if results else None,
            "total_scenarios": len(results),
        }

"""Single Point of Failure (SPOF) detection.

Identifies assets that are single points of failure in the
dependency graph - assets whose failure would isolate or
severely impact other assets.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from flowlens.common.logging import get_logger
from flowlens.graph.traversal import GraphTraversal
from flowlens.models.asset import Asset
from flowlens.models.dependency import Dependency

logger = get_logger(__name__)


@dataclass
class SPOFResult:
    """Single Point of Failure detection result."""

    asset_id: UUID
    asset_name: str
    spof_type: str  # "bridge", "sole_dependency", "critical_hub"
    severity: str  # "low", "medium", "high", "critical"
    affected_assets: list[UUID]
    affected_count: int
    description: str
    bytes_at_risk: int = 0


@dataclass
class SPOFAnalysis:
    """Complete SPOF analysis results."""

    total_spofs: int
    critical_spofs: int
    high_spofs: int
    medium_spofs: int
    low_spofs: int
    spofs: list[SPOFResult]
    recommendations: list[str]
    analyzed_at: datetime = field(default_factory=datetime.utcnow)


class SPOFDetector:
    """Detects single points of failure in the dependency graph.

    Identifies:
    1. Bridge nodes - assets that connect otherwise separate graph components
    2. Sole dependencies - assets that are the only dependency for others
    3. Critical hubs - highly connected assets where failure has wide impact
    """

    def __init__(
        self,
        traversal: GraphTraversal | None = None,
        max_depth: int = 10,
    ) -> None:
        """Initialize detector.

        Args:
            traversal: Graph traversal instance.
            max_depth: Maximum analysis depth.
        """
        self._traversal = traversal or GraphTraversal(max_depth)
        self._max_depth = max_depth

    async def detect_all(
        self,
        db: AsyncSession,
        min_severity: str = "medium",
    ) -> SPOFAnalysis:
        """Detect all single points of failure.

        Args:
            db: Database session.
            min_severity: Minimum severity to include.

        Returns:
            SPOF analysis results.
        """
        all_spofs: list[SPOFResult] = []

        # Detect sole dependencies
        sole_deps = await self._detect_sole_dependencies(db)
        all_spofs.extend(sole_deps)

        # Detect critical hubs
        hubs = await self._detect_critical_hubs(db)
        all_spofs.extend(hubs)

        # Detect bridge nodes
        bridges = await self._detect_bridges(db)
        all_spofs.extend(bridges)

        # Filter by severity
        severity_order = {"critical": 4, "high": 3, "medium": 2, "low": 1}
        min_level = severity_order.get(min_severity, 2)
        filtered = [
            s for s in all_spofs
            if severity_order.get(s.severity, 0) >= min_level
        ]

        # Deduplicate by asset ID (keep highest severity)
        seen: dict[UUID, SPOFResult] = {}
        for spof in filtered:
            existing = seen.get(spof.asset_id)
            if existing is None or severity_order.get(spof.severity, 0) > severity_order.get(existing.severity, 0):
                seen[spof.asset_id] = spof

        unique_spofs = list(seen.values())
        unique_spofs.sort(key=lambda s: (severity_order.get(s.severity, 0), s.affected_count), reverse=True)

        # Count by severity
        critical_count = sum(1 for s in unique_spofs if s.severity == "critical")
        high_count = sum(1 for s in unique_spofs if s.severity == "high")
        medium_count = sum(1 for s in unique_spofs if s.severity == "medium")
        low_count = sum(1 for s in unique_spofs if s.severity == "low")

        # Generate recommendations
        recommendations = self._generate_recommendations(unique_spofs)

        return SPOFAnalysis(
            total_spofs=len(unique_spofs),
            critical_spofs=critical_count,
            high_spofs=high_count,
            medium_spofs=medium_count,
            low_spofs=low_count,
            spofs=unique_spofs,
            recommendations=recommendations,
        )

    async def _detect_sole_dependencies(
        self,
        db: AsyncSession,
    ) -> list[SPOFResult]:
        """Detect assets that are the only dependency for other assets.

        An asset is a sole dependency if removing it would leave
        dependent assets with no connections to a required service.

        Args:
            db: Database session.

        Returns:
            List of SPOF results.
        """
        # Find assets that are the ONLY target for their dependents
        query = text("""
            WITH dependency_counts AS (
                SELECT
                    d1.source_asset_id,
                    d1.target_asset_id,
                    COUNT(*) OVER (PARTITION BY d1.source_asset_id) as total_deps
                FROM dependencies d1
                WHERE d1.valid_to IS NULL
            )
            SELECT
                t.id as target_id,
                t.name as target_name,
                t.is_critical,
                ARRAY_AGG(DISTINCT dc.source_asset_id) as dependent_ids,
                COUNT(DISTINCT dc.source_asset_id) as dependent_count,
                SUM(d.bytes_total) as bytes_total
            FROM dependency_counts dc
            JOIN assets t ON t.id = dc.target_asset_id
            JOIN dependencies d ON d.source_asset_id = dc.source_asset_id
                AND d.target_asset_id = dc.target_asset_id
                AND d.valid_to IS NULL
            WHERE dc.total_deps = 1
            AND t.deleted_at IS NULL
            GROUP BY t.id, t.name, t.is_critical
            HAVING COUNT(DISTINCT dc.source_asset_id) > 0
            ORDER BY dependent_count DESC
            LIMIT 50
        """)

        result = await db.execute(query)
        spofs = []

        for row in result.fetchall():
            # Determine severity
            if row.is_critical or row.dependent_count >= 10:
                severity = "critical"
            elif row.dependent_count >= 5:
                severity = "high"
            elif row.dependent_count >= 2:
                severity = "medium"
            else:
                severity = "low"

            spofs.append(SPOFResult(
                asset_id=row.target_id,
                asset_name=row.target_name,
                spof_type="sole_dependency",
                severity=severity,
                affected_assets=[UUID(aid) for aid in row.dependent_ids],
                affected_count=row.dependent_count,
                description=f"Sole dependency for {row.dependent_count} asset(s)",
                bytes_at_risk=row.bytes_total or 0,
            ))

        return spofs

    async def _detect_critical_hubs(
        self,
        db: AsyncSession,
        min_connections: int = 5,
    ) -> list[SPOFResult]:
        """Detect highly connected assets (critical hubs).

        Assets with many incoming connections are SPOFs because
        their failure impacts many dependents.

        Args:
            db: Database session.
            min_connections: Minimum connections to be a hub.

        Returns:
            List of SPOF results.
        """
        query = text("""
            SELECT
                a.id,
                a.name,
                a.is_critical,
                COUNT(DISTINCT d.source_asset_id) as upstream_count,
                ARRAY_AGG(DISTINCT d.source_asset_id) as upstream_ids,
                SUM(d.bytes_total) as bytes_total
            FROM assets a
            JOIN dependencies d ON d.target_asset_id = a.id
            WHERE d.valid_to IS NULL
            AND a.deleted_at IS NULL
            GROUP BY a.id, a.name, a.is_critical
            HAVING COUNT(DISTINCT d.source_asset_id) >= :min_connections
            ORDER BY upstream_count DESC
            LIMIT 50
        """)

        result = await db.execute(query, {"min_connections": min_connections})
        spofs = []

        for row in result.fetchall():
            # Determine severity based on connection count
            if row.is_critical or row.upstream_count >= 20:
                severity = "critical"
            elif row.upstream_count >= 10:
                severity = "high"
            elif row.upstream_count >= 5:
                severity = "medium"
            else:
                severity = "low"

            spofs.append(SPOFResult(
                asset_id=row.id,
                asset_name=row.name,
                spof_type="critical_hub",
                severity=severity,
                affected_assets=[UUID(aid) for aid in row.upstream_ids],
                affected_count=row.upstream_count,
                description=f"Critical hub with {row.upstream_count} dependent asset(s)",
                bytes_at_risk=row.bytes_total or 0,
            ))

        return spofs

    async def _detect_bridges(
        self,
        db: AsyncSession,
    ) -> list[SPOFResult]:
        """Detect bridge nodes connecting graph components.

        A bridge is an asset whose removal would disconnect
        parts of the graph.

        Args:
            db: Database session.

        Returns:
            List of SPOF results.
        """
        # Find assets that sit between internal and external zones
        # or between different network segments
        query = text("""
            WITH bidirectional AS (
                SELECT
                    a.id,
                    a.name,
                    a.is_critical,
                    a.is_internal,
                    COUNT(DISTINCT in_d.source_asset_id) as incoming,
                    COUNT(DISTINCT out_d.target_asset_id) as outgoing,
                    ARRAY_AGG(DISTINCT in_d.source_asset_id) FILTER (WHERE in_d.source_asset_id IS NOT NULL) as incoming_ids,
                    ARRAY_AGG(DISTINCT out_d.target_asset_id) FILTER (WHERE out_d.target_asset_id IS NOT NULL) as outgoing_ids
                FROM assets a
                LEFT JOIN dependencies in_d ON in_d.target_asset_id = a.id AND in_d.valid_to IS NULL
                LEFT JOIN dependencies out_d ON out_d.source_asset_id = a.id AND out_d.valid_to IS NULL
                WHERE a.deleted_at IS NULL
                GROUP BY a.id, a.name, a.is_critical, a.is_internal
                HAVING COUNT(DISTINCT in_d.source_asset_id) > 0
                AND COUNT(DISTINCT out_d.target_asset_id) > 0
            )
            SELECT *
            FROM bidirectional
            WHERE incoming >= 2 AND outgoing >= 2
            ORDER BY (incoming * outgoing) DESC
            LIMIT 50
        """)

        result = await db.execute(query)
        spofs = []

        for row in result.fetchall():
            total_affected = row.incoming + row.outgoing

            # Determine severity
            if row.is_critical or total_affected >= 20:
                severity = "critical"
            elif total_affected >= 10:
                severity = "high"
            elif total_affected >= 5:
                severity = "medium"
            else:
                severity = "low"

            # Combine affected IDs
            affected = []
            if row.incoming_ids:
                affected.extend([UUID(aid) for aid in row.incoming_ids if aid])
            if row.outgoing_ids:
                affected.extend([UUID(aid) for aid in row.outgoing_ids if aid])

            spofs.append(SPOFResult(
                asset_id=row.id,
                asset_name=row.name,
                spof_type="bridge",
                severity=severity,
                affected_assets=affected,
                affected_count=total_affected,
                description=f"Bridge connecting {row.incoming} upstream to {row.outgoing} downstream",
            ))

        return spofs

    def _generate_recommendations(
        self,
        spofs: list[SPOFResult],
    ) -> list[str]:
        """Generate remediation recommendations.

        Args:
            spofs: Detected SPOFs.

        Returns:
            List of recommendation strings.
        """
        recommendations = []

        # Count by type
        sole_deps = [s for s in spofs if s.spof_type == "sole_dependency"]
        hubs = [s for s in spofs if s.spof_type == "critical_hub"]
        bridges = [s for s in spofs if s.spof_type == "bridge"]

        critical_count = sum(1 for s in spofs if s.severity == "critical")

        if critical_count > 0:
            recommendations.append(
                f"URGENT: {critical_count} critical SPOF(s) detected. "
                "Prioritize adding redundancy for these assets."
            )

        if sole_deps:
            recommendations.append(
                f"Add redundant dependencies for {len(sole_deps)} asset(s) "
                "that are sole dependencies. Consider load balancing or failover."
            )

        if hubs:
            recommendations.append(
                f"Review {len(hubs)} critical hub(s) for high availability. "
                "Consider clustering or geographic distribution."
            )

        if bridges:
            recommendations.append(
                f"Evaluate {len(bridges)} bridge node(s). "
                "Consider adding alternate paths between network segments."
            )

        if not recommendations:
            recommendations.append(
                "No significant SPOFs detected. Continue monitoring."
            )

        return recommendations

    async def check_asset_spof(
        self,
        db: AsyncSession,
        asset_id: UUID,
    ) -> dict[str, Any]:
        """Check if a specific asset is a SPOF.

        Args:
            db: Database session.
            asset_id: Asset to check.

        Returns:
            SPOF status for the asset.
        """
        # Get asset details
        result = await db.execute(
            select(Asset).where(Asset.id == asset_id)
        )
        asset = result.scalar_one_or_none()

        if not asset:
            raise ValueError(f"Asset not found: {asset_id}")

        # Check sole dependency status
        sole_query = text("""
            WITH dependency_counts AS (
                SELECT
                    source_asset_id,
                    COUNT(DISTINCT target_asset_id) as total_deps
                FROM dependencies
                WHERE valid_to IS NULL
                GROUP BY source_asset_id
            )
            SELECT COUNT(DISTINCT d.source_asset_id) as sole_dependent_count
            FROM dependencies d
            JOIN dependency_counts dc ON dc.source_asset_id = d.source_asset_id
            WHERE d.target_asset_id = :asset_id
            AND d.valid_to IS NULL
            AND dc.total_deps = 1
        """)
        sole_result = await db.execute(sole_query, {"asset_id": str(asset_id)})
        sole_count = sole_result.scalar() or 0

        # Check hub status
        hub_query = text("""
            SELECT COUNT(DISTINCT source_asset_id) as upstream_count
            FROM dependencies
            WHERE target_asset_id = :asset_id
            AND valid_to IS NULL
        """)
        hub_result = await db.execute(hub_query, {"asset_id": str(asset_id)})
        upstream_count = hub_result.scalar() or 0

        # Check bridge status
        bridge_query = text("""
            SELECT
                COUNT(DISTINCT d_in.source_asset_id) as incoming,
                COUNT(DISTINCT d_out.target_asset_id) as outgoing
            FROM assets a
            LEFT JOIN dependencies d_in ON d_in.target_asset_id = a.id AND d_in.valid_to IS NULL
            LEFT JOIN dependencies d_out ON d_out.source_asset_id = a.id AND d_out.valid_to IS NULL
            WHERE a.id = :asset_id
            GROUP BY a.id
        """)
        bridge_result = await db.execute(bridge_query, {"asset_id": str(asset_id)})
        bridge_row = bridge_result.first()

        is_spof = False
        spof_types = []
        severity = "none"

        if sole_count > 0:
            is_spof = True
            spof_types.append("sole_dependency")
            if sole_count >= 5:
                severity = "critical" if severity != "critical" else severity
            elif sole_count >= 2:
                severity = "high" if severity in ("none", "low", "medium") else severity

        if upstream_count >= 5:
            is_spof = True
            spof_types.append("critical_hub")
            if upstream_count >= 10:
                severity = "critical"
            elif upstream_count >= 5:
                severity = "high" if severity in ("none", "low", "medium") else severity

        if bridge_row and bridge_row.incoming >= 2 and bridge_row.outgoing >= 2:
            is_spof = True
            spof_types.append("bridge")
            if bridge_row.incoming >= 5 and bridge_row.outgoing >= 5:
                severity = "high" if severity in ("none", "low", "medium") else severity
            else:
                severity = "medium" if severity in ("none", "low") else severity

        if asset.is_critical and is_spof:
            severity = "critical"

        return {
            "asset_id": str(asset_id),
            "asset_name": asset.name,
            "is_spof": is_spof,
            "spof_types": spof_types,
            "severity": severity,
            "sole_dependency_count": sole_count,
            "upstream_count": upstream_count,
            "is_bridge": len(spof_types) > 0 and "bridge" in spof_types,
        }

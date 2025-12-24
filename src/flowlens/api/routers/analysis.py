"""Analysis API endpoints - blast radius, impact, SPOF detection."""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select, text

from flowlens.api.dependencies import AuthenticatedUser, DbSession
from flowlens.models.asset import Asset
from flowlens.schemas.analysis import (
    BlastRadiusResult,
    ImpactAnalysisRequest,
    ImpactAnalysisResult,
    ImpactedAsset,
    SPOFAnalysisResult,
    SPOFCandidate,
)

router = APIRouter(prefix="/analysis", tags=["analysis"])


@router.get("/blast-radius/{asset_id}", response_model=BlastRadiusResult)
async def calculate_blast_radius(
    asset_id: UUID,
    db: DbSession,
    user: AuthenticatedUser,
    max_depth: int = Query(5, ge=1, le=10, alias="maxDepth"),
) -> BlastRadiusResult:
    """Calculate blast radius for an asset.

    Returns all assets that would be affected if this asset fails.
    """
    # Verify asset exists
    asset_result = await db.execute(
        select(Asset).where(Asset.id == asset_id, Asset.deleted_at.is_(None))
    )
    asset = asset_result.scalar_one_or_none()

    if not asset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Asset {asset_id} not found",
        )

    # Call the database function
    result = await db.execute(
        text("SELECT * FROM calculate_blast_radius(:asset_id, :max_depth)"),
        {"asset_id": asset_id, "max_depth": max_depth},
    )
    row = result.fetchone()

    affected_assets = []
    if row and row.affected_assets:
        affected_assets = row.affected_assets

    return BlastRadiusResult(
        asset_id=asset_id,
        asset_name=asset.name,
        total_affected=row.total_affected if row else 0,
        critical_affected=row.critical_affected if row else 0,
        affected_assets=affected_assets,
        max_depth=max_depth,
        calculated_at=datetime.utcnow(),
    )


@router.post("/impact", response_model=ImpactAnalysisResult)
async def analyze_impact(
    request: ImpactAnalysisRequest,
    db: DbSession,
    user: AuthenticatedUser,
) -> ImpactAnalysisResult:
    """Analyze impact of an asset failure.

    More detailed than blast radius - considers failure type and
    provides severity scoring.
    """
    # Verify asset exists
    asset_result = await db.execute(
        select(Asset).where(Asset.id == request.asset_id, Asset.deleted_at.is_(None))
    )
    asset = asset_result.scalar_one_or_none()

    if not asset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Asset {request.asset_id} not found",
        )

    # Get upstream dependencies (assets that depend on this one)
    result = await db.execute(
        text("SELECT * FROM get_upstream_dependencies(:asset_id, :max_depth)"),
        {"asset_id": request.asset_id, "max_depth": request.max_depth},
    )
    rows = result.fetchall()

    # Build impacted assets list
    impacted_assets = []
    critical_count = 0

    for row in rows:
        # Check if asset is critical
        asset_check = await db.execute(
            select(Asset.is_critical, Asset.ip_address).where(Asset.id == row.asset_id)
        )
        asset_info = asset_check.fetchone()
        is_critical = asset_info.is_critical if asset_info else False

        if is_critical:
            critical_count += 1

        impacted_assets.append(
            ImpactedAsset(
                id=row.asset_id,
                name=row.asset_name,
                ip_address=str(asset_info.ip_address) if asset_info else "",
                is_critical=is_critical,
                impact_level="direct" if row.depth == 1 else "indirect",
                depth=row.depth,
                dependency_path=list(row.path),
            )
        )

    # Calculate severity score
    # Factors: total impacted, critical impacted, max depth reached
    base_score = min(len(impacted_assets) * 2, 50)  # Up to 50 from count
    critical_score = min(critical_count * 10, 40)   # Up to 40 from critical
    asset_critical_bonus = 10 if asset.is_critical else 0  # 10 if source is critical

    severity_score = min(base_score + critical_score + asset_critical_bonus, 100)

    # Get impacted applications (would require additional query)
    impacted_applications: list[dict] = []

    return ImpactAnalysisResult(
        source_asset_id=request.asset_id,
        source_asset_name=asset.name,
        failure_type=request.failure_type,
        total_impacted=len(impacted_assets),
        critical_impacted=critical_count,
        impacted_assets=impacted_assets,
        impacted_applications=impacted_applications,
        severity_score=severity_score,
        calculated_at=datetime.utcnow(),
    )


@router.get("/spof", response_model=SPOFAnalysisResult)
async def detect_spof(
    db: DbSession,
    user: AuthenticatedUser,
    environment: str | None = None,
    min_dependents: int = Query(3, ge=1, alias="minDependents"),
    limit: int = Query(20, ge=1, le=100),
) -> SPOFAnalysisResult:
    """Detect Single Points of Failure.

    Identifies assets that many other assets depend on and would
    cause significant impact if they failed.
    """
    scope = "global"
    if environment:
        scope = f"environment:{environment}"

    # Query to find assets with high inbound dependency count
    # and calculate a risk score
    query = text("""
        WITH dependency_counts AS (
            SELECT
                d.target_asset_id,
                COUNT(DISTINCT d.source_asset_id) AS dependents_count,
                COUNT(DISTINCT CASE WHEN a.is_critical THEN d.source_asset_id END) AS critical_dependents
            FROM dependencies d
            JOIN assets a ON a.id = d.source_asset_id
            WHERE d.valid_to IS NULL
              AND a.deleted_at IS NULL
            GROUP BY d.target_asset_id
            HAVING COUNT(DISTINCT d.source_asset_id) >= :min_dependents
        )
        SELECT
            a.id AS asset_id,
            a.name AS asset_name,
            a.ip_address,
            a.is_critical,
            dc.dependents_count,
            dc.critical_dependents,
            -- Calculate risk score
            (dc.dependents_count * 3 +
             dc.critical_dependents * 10 +
             CASE WHEN a.is_critical THEN 20 ELSE 0 END) AS risk_score
        FROM dependency_counts dc
        JOIN assets a ON a.id = dc.target_asset_id
        WHERE a.deleted_at IS NULL
          AND (:environment IS NULL OR a.environment = :environment)
        ORDER BY risk_score DESC
        LIMIT :limit
    """)

    result = await db.execute(
        query,
        {
            "min_dependents": min_dependents,
            "environment": environment,
            "limit": limit,
        },
    )
    rows = result.fetchall()

    candidates = []
    high_risk_count = 0

    for row in rows:
        # Normalize risk score to 0-100
        normalized_score = min(row.risk_score, 100)

        # Determine risk level
        if normalized_score >= 70:
            risk_level = "critical"
            high_risk_count += 1
        elif normalized_score >= 50:
            risk_level = "high"
            high_risk_count += 1
        elif normalized_score >= 30:
            risk_level = "medium"
        else:
            risk_level = "low"

        candidates.append(
            SPOFCandidate(
                asset_id=row.asset_id,
                asset_name=row.asset_name,
                ip_address=str(row.ip_address),
                is_critical=row.is_critical,
                dependents_count=row.dependents_count,
                critical_dependents=row.critical_dependents,
                unique_path_count=row.dependents_count,  # Simplified
                centrality_score=row.dependents_count / 10.0,  # Simplified
                risk_score=normalized_score,
                risk_level=risk_level,
            )
        )

    # Get total analyzed count
    count_result = await db.execute(
        text("""
            SELECT COUNT(DISTINCT id) FROM assets
            WHERE deleted_at IS NULL
              AND (:environment IS NULL OR environment = :environment)
        """),
        {"environment": environment},
    )
    total_analyzed = count_result.scalar() or 0

    return SPOFAnalysisResult(
        scope=scope,
        candidates=candidates,
        total_analyzed=total_analyzed,
        high_risk_count=high_risk_count,
        calculated_at=datetime.utcnow(),
    )


@router.get("/critical-paths/{asset_id}")
async def get_critical_paths(
    asset_id: UUID,
    db: DbSession,
    user: AuthenticatedUser,
    direction: str = Query("both", pattern=r"^(upstream|downstream|both)$"),
) -> dict:
    """Get critical dependency paths for an asset.

    Identifies paths that involve critical assets.
    """
    # Verify asset exists
    asset_result = await db.execute(
        select(Asset).where(Asset.id == asset_id, Asset.deleted_at.is_(None))
    )
    asset = asset_result.scalar_one_or_none()

    if not asset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Asset {asset_id} not found",
        )

    critical_paths = []

    # Get paths that include critical assets
    if direction in ("downstream", "both"):
        result = await db.execute(
            text("""
                WITH RECURSIVE downstream AS (
                    SELECT
                        d.target_asset_id AS asset_id,
                        a.name AS asset_name,
                        a.is_critical,
                        1 AS depth,
                        ARRAY[d.source_asset_id, d.target_asset_id] AS path
                    FROM dependencies d
                    JOIN assets a ON a.id = d.target_asset_id
                    WHERE d.source_asset_id = :asset_id
                      AND d.valid_to IS NULL
                      AND a.deleted_at IS NULL

                    UNION ALL

                    SELECT
                        d.target_asset_id,
                        a.name,
                        a.is_critical,
                        ds.depth + 1,
                        ds.path || d.target_asset_id
                    FROM downstream ds
                    JOIN dependencies d ON d.source_asset_id = ds.asset_id
                    JOIN assets a ON a.id = d.target_asset_id
                    WHERE ds.depth < 5
                      AND d.valid_to IS NULL
                      AND a.deleted_at IS NULL
                      AND NOT d.target_asset_id = ANY(ds.path)
                )
                SELECT DISTINCT path
                FROM downstream
                WHERE is_critical = true
            """),
            {"asset_id": asset_id},
        )

        for row in result.fetchall():
            critical_paths.append({
                "direction": "downstream",
                "path": list(row.path),
            })

    if direction in ("upstream", "both"):
        result = await db.execute(
            text("""
                WITH RECURSIVE upstream AS (
                    SELECT
                        d.source_asset_id AS asset_id,
                        a.name AS asset_name,
                        a.is_critical,
                        1 AS depth,
                        ARRAY[d.target_asset_id, d.source_asset_id] AS path
                    FROM dependencies d
                    JOIN assets a ON a.id = d.source_asset_id
                    WHERE d.target_asset_id = :asset_id
                      AND d.valid_to IS NULL
                      AND a.deleted_at IS NULL

                    UNION ALL

                    SELECT
                        d.source_asset_id,
                        a.name,
                        a.is_critical,
                        us.depth + 1,
                        us.path || d.source_asset_id
                    FROM upstream us
                    JOIN dependencies d ON d.target_asset_id = us.asset_id
                    JOIN assets a ON a.id = d.source_asset_id
                    WHERE us.depth < 5
                      AND d.valid_to IS NULL
                      AND a.deleted_at IS NULL
                      AND NOT d.source_asset_id = ANY(us.path)
                )
                SELECT DISTINCT path
                FROM upstream
                WHERE is_critical = true
            """),
            {"asset_id": asset_id},
        )

        for row in result.fetchall():
            critical_paths.append({
                "direction": "upstream",
                "path": list(row.path),
            })

    return {
        "asset_id": asset_id,
        "asset_name": asset.name,
        "critical_paths": critical_paths,
        "total_critical_paths": len(critical_paths),
        "calculated_at": datetime.utcnow().isoformat(),
    }

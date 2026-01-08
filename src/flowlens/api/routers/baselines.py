"""Application Baselines API endpoints for point-in-time snapshots."""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Path, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from flowlens.api.dependencies import DbSession, ViewerUser, AnalystUser
from flowlens.models.asset import Application, ApplicationMember, Asset, EntryPoint
from flowlens.models.baseline import ApplicationBaseline
from flowlens.models.dependency import Dependency
from flowlens.models.layout import ApplicationLayout
from flowlens.schemas.baseline import (
    ApplicationBaselineCreate,
    ApplicationBaselineResponse,
    ApplicationBaselineWithSnapshot,
    BaselineComparisonRequest,
    BaselineComparisonResult,
    DependencyChange,
    EntryPointChange,
    MemberChange,
    TrafficDeviation,
)

router = APIRouter(prefix="/applications/{application_id}/baselines", tags=["baselines"])


async def get_application_or_404(db: DbSession, application_id: uuid.UUID) -> Application:
    """Get application by ID or raise 404."""
    result = await db.execute(
        select(Application).where(Application.id == application_id)
    )
    application = result.scalar_one_or_none()
    if not application:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Application {application_id} not found",
        )
    return application


async def get_baseline_or_404(
    db: DbSession, application_id: uuid.UUID, baseline_id: uuid.UUID
) -> ApplicationBaseline:
    """Get baseline by ID or raise 404."""
    result = await db.execute(
        select(ApplicationBaseline)
        .where(ApplicationBaseline.id == baseline_id)
        .where(ApplicationBaseline.application_id == application_id)
    )
    baseline = result.scalar_one_or_none()
    if not baseline:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Baseline {baseline_id} not found",
        )
    return baseline


async def capture_application_snapshot(
    db: DbSession,
    application_id: uuid.UUID,
    hop_depth: int,
    include_positions: bool,
) -> tuple[dict, int, int, int, int]:
    """Capture current state of an application as a snapshot.

    Returns:
        Tuple of (snapshot_dict, dependency_count, member_count, entry_point_count, total_traffic_bytes)
    """
    # Get application members
    members_result = await db.execute(
        select(ApplicationMember)
        .where(ApplicationMember.application_id == application_id)
        .options(selectinload(ApplicationMember.asset))
        .options(selectinload(ApplicationMember.entry_points))
    )
    members = members_result.scalars().all()
    member_asset_ids = [str(m.asset_id) for m in members]

    # Get dependencies for member assets
    if member_asset_ids:
        deps_result = await db.execute(
            select(Dependency)
            .where(
                (Dependency.source_asset_id.in_([m.asset_id for m in members]))
                | (Dependency.target_asset_id.in_([m.asset_id for m in members]))
            )
        )
        dependencies = deps_result.scalars().all()
    else:
        dependencies = []

    # Get entry points
    entry_points = []
    for member in members:
        for ep in member.entry_points:
            entry_points.append({
                "id": str(ep.id),
                "member_id": str(member.id),
                "asset_id": str(member.asset_id),
                "port": ep.port,
                "protocol": ep.protocol,
                "label": ep.label,
            })

    # Get saved positions if requested
    node_positions = {}
    if include_positions:
        layout_result = await db.execute(
            select(ApplicationLayout)
            .where(ApplicationLayout.application_id == application_id)
            .where(ApplicationLayout.hop_depth == hop_depth)
        )
        layout = layout_result.scalar_one_or_none()
        if layout and layout.positions:
            node_positions = layout.positions

    # Build dependencies snapshot
    deps_snapshot = []
    total_traffic = 0
    for dep in dependencies:
        deps_snapshot.append({
            "id": str(dep.id),
            "source_asset_id": str(dep.source_asset_id),
            "target_asset_id": str(dep.target_asset_id),
            "target_port": dep.target_port,
            "protocol": dep.protocol,
            "bytes_total": dep.bytes_total or 0,
            "bytes_last_24h": dep.bytes_last_24h or 0,
            "first_seen": dep.first_seen.isoformat() if dep.first_seen else None,
            "last_seen": dep.last_seen.isoformat() if dep.last_seen else None,
        })
        total_traffic += dep.bytes_total or 0

    snapshot = {
        "dependencies": deps_snapshot,
        "traffic_volumes": {},  # Could be calculated from dependencies
        "node_positions": node_positions,
        "entry_points": entry_points,
        "member_asset_ids": member_asset_ids,
        "hop_depth": hop_depth,
    }

    return (
        snapshot,
        len(dependencies),
        len(members),
        len(entry_points),
        total_traffic,
    )


@router.get("", response_model=list[ApplicationBaselineResponse])
async def list_baselines(
    application_id: uuid.UUID,
    active_only: bool = False,
    db: DbSession = None,
    _user: ViewerUser = None,
) -> list[ApplicationBaselineResponse]:
    """List all baselines for an application."""
    await get_application_or_404(db, application_id)

    query = select(ApplicationBaseline).where(
        ApplicationBaseline.application_id == application_id
    )
    if active_only:
        query = query.where(ApplicationBaseline.is_active == True)
    query = query.order_by(ApplicationBaseline.captured_at.desc())

    result = await db.execute(query)
    baselines = result.scalars().all()

    return [ApplicationBaselineResponse.model_validate(b) for b in baselines]


@router.post("", response_model=ApplicationBaselineResponse, status_code=status.HTTP_201_CREATED)
async def create_baseline(
    application_id: uuid.UUID,
    data: ApplicationBaselineCreate,
    db: DbSession = None,
    user: AnalystUser = None,
) -> ApplicationBaselineResponse:
    """Create a new baseline snapshot for an application."""
    await get_application_or_404(db, application_id)

    # Capture current state
    snapshot, dep_count, member_count, ep_count, total_traffic = await capture_application_snapshot(
        db,
        application_id,
        data.hop_depth,
        data.include_positions,
    )

    # Create baseline
    baseline = ApplicationBaseline(
        application_id=application_id,
        name=data.name,
        description=data.description,
        captured_at=datetime.now(timezone.utc),
        created_by=user.sub,
        snapshot=snapshot,
        dependency_count=dep_count,
        member_count=member_count,
        entry_point_count=ep_count,
        total_traffic_bytes=total_traffic,
        tags=data.tags,
    )
    db.add(baseline)
    await db.commit()
    await db.refresh(baseline)

    return ApplicationBaselineResponse.model_validate(baseline)


@router.get("/{baseline_id}", response_model=ApplicationBaselineResponse)
async def get_baseline(
    application_id: uuid.UUID,
    baseline_id: uuid.UUID,
    db: DbSession = None,
    _user: ViewerUser = None,
) -> ApplicationBaselineResponse:
    """Get a specific baseline by ID."""
    await get_application_or_404(db, application_id)
    baseline = await get_baseline_or_404(db, application_id, baseline_id)
    return ApplicationBaselineResponse.model_validate(baseline)


@router.get("/{baseline_id}/snapshot", response_model=ApplicationBaselineWithSnapshot)
async def get_baseline_snapshot(
    application_id: uuid.UUID,
    baseline_id: uuid.UUID,
    db: DbSession = None,
    _user: ViewerUser = None,
) -> ApplicationBaselineWithSnapshot:
    """Get a baseline with its full snapshot data."""
    await get_application_or_404(db, application_id)
    baseline = await get_baseline_or_404(db, application_id, baseline_id)
    return ApplicationBaselineWithSnapshot.model_validate(baseline)


@router.delete("/{baseline_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_baseline(
    application_id: uuid.UUID,
    baseline_id: uuid.UUID,
    db: DbSession = None,
    _user: AnalystUser = None,
) -> None:
    """Delete a baseline."""
    await get_application_or_404(db, application_id)
    baseline = await get_baseline_or_404(db, application_id, baseline_id)

    await db.delete(baseline)
    await db.commit()


@router.post("/{baseline_id}/compare", response_model=BaselineComparisonResult)
async def compare_baseline_to_current(
    application_id: uuid.UUID,
    baseline_id: uuid.UUID,
    data: BaselineComparisonRequest | None = None,
    db: DbSession = None,
    _user: ViewerUser = None,
) -> BaselineComparisonResult:
    """Compare a baseline to the current state of the application."""
    await get_application_or_404(db, application_id)
    baseline = await get_baseline_or_404(db, application_id, baseline_id)

    if data is None:
        data = BaselineComparisonRequest()

    # Get current state
    current_snapshot, _, _, _, _ = await capture_application_snapshot(
        db,
        application_id,
        data.hop_depth,
        data.include_positions,
    )

    # Compare dependencies
    baseline_deps = {d["id"]: d for d in baseline.snapshot.get("dependencies", [])}
    current_deps = {d["id"]: d for d in current_snapshot["dependencies"]}

    # Find changed dependencies and collect all asset IDs we need to look up
    added_dep_ids = set(current_deps.keys()) - set(baseline_deps.keys())
    removed_dep_ids = set(baseline_deps.keys()) - set(current_deps.keys())

    asset_ids_to_lookup: set[uuid.UUID] = set()
    for dep_id in added_dep_ids:
        dep = current_deps[dep_id]
        asset_ids_to_lookup.add(uuid.UUID(dep["source_asset_id"]))
        asset_ids_to_lookup.add(uuid.UUID(dep["target_asset_id"]))
    for dep_id in removed_dep_ids:
        dep = baseline_deps[dep_id]
        asset_ids_to_lookup.add(uuid.UUID(dep["source_asset_id"]))
        asset_ids_to_lookup.add(uuid.UUID(dep["target_asset_id"]))

    # Look up asset names and IPs
    asset_map: dict[str, dict[str, str | None]] = {}
    if asset_ids_to_lookup:
        assets_result = await db.execute(
            select(Asset).where(Asset.id.in_(asset_ids_to_lookup))
        )
        for asset in assets_result.scalars().all():
            asset_map[str(asset.id)] = {
                "name": asset.display_name or asset.name,
                "ip": asset.ip_address,
            }

    deps_added = []
    deps_removed = []

    for dep_id in added_dep_ids:
        dep = current_deps[dep_id]
        source_info = asset_map.get(dep["source_asset_id"], {})
        target_info = asset_map.get(dep["target_asset_id"], {})
        deps_added.append(DependencyChange(
            id=uuid.UUID(dep_id),
            source_asset_id=uuid.UUID(dep["source_asset_id"]),
            source_name=source_info.get("name"),
            source_ip=source_info.get("ip"),
            target_asset_id=uuid.UUID(dep["target_asset_id"]),
            target_name=target_info.get("name"),
            target_ip=target_info.get("ip"),
            target_port=dep["target_port"],
            protocol=dep["protocol"],
            change_type="added",
        ))

    for dep_id in removed_dep_ids:
        dep = baseline_deps[dep_id]
        source_info = asset_map.get(dep["source_asset_id"], {})
        target_info = asset_map.get(dep["target_asset_id"], {})
        deps_removed.append(DependencyChange(
            id=uuid.UUID(dep_id),
            source_asset_id=uuid.UUID(dep["source_asset_id"]),
            source_name=source_info.get("name"),
            source_ip=source_info.get("ip"),
            target_asset_id=uuid.UUID(dep["target_asset_id"]),
            target_name=target_info.get("name"),
            target_ip=target_info.get("ip"),
            target_port=dep["target_port"],
            protocol=dep["protocol"],
            change_type="removed",
        ))

    # Compare entry points
    baseline_eps = {f"{ep['asset_id']}:{ep['port']}:{ep['protocol']}": ep
                    for ep in baseline.snapshot.get("entry_points", [])}
    current_eps = {f"{ep['asset_id']}:{ep['port']}:{ep['protocol']}": ep
                   for ep in current_snapshot["entry_points"]}

    eps_added = []
    eps_removed = []

    for ep_key, ep in current_eps.items():
        if ep_key not in baseline_eps:
            eps_added.append(EntryPointChange(
                port=ep["port"],
                protocol=ep["protocol"],
                label=ep.get("label"),
                member_id=uuid.UUID(ep["member_id"]),
                asset_id=uuid.UUID(ep["asset_id"]),
                change_type="added",
            ))

    for ep_key, ep in baseline_eps.items():
        if ep_key not in current_eps:
            eps_removed.append(EntryPointChange(
                port=ep["port"],
                protocol=ep["protocol"],
                label=ep.get("label"),
                member_id=uuid.UUID(ep["member_id"]),
                asset_id=uuid.UUID(ep["asset_id"]),
                change_type="removed",
            ))

    # Compare members
    baseline_members = set(baseline.snapshot.get("member_asset_ids", []))
    current_members = set(current_snapshot["member_asset_ids"])

    members_added = [
        MemberChange(asset_id=uuid.UUID(m), change_type="added")
        for m in current_members - baseline_members
    ]
    members_removed = [
        MemberChange(asset_id=uuid.UUID(m), change_type="removed")
        for m in baseline_members - current_members
    ]

    # Build result
    result = BaselineComparisonResult(
        baseline_id=baseline.id,
        baseline_name=baseline.name,
        captured_at=baseline.captured_at,
        compared_at=datetime.now(timezone.utc),
        dependencies_added=deps_added,
        dependencies_removed=deps_removed,
        entry_points_added=eps_added,
        entry_points_removed=eps_removed,
        members_added=members_added,
        members_removed=members_removed,
    )
    result.calculate_severity()

    return result


@router.post("/{baseline_id_a}/compare/{baseline_id_b}", response_model=BaselineComparisonResult)
async def compare_two_baselines(
    application_id: uuid.UUID,
    baseline_id_a: uuid.UUID,
    baseline_id_b: uuid.UUID,
    db: DbSession = None,
    _user: ViewerUser = None,
) -> BaselineComparisonResult:
    """Compare two baselines to each other."""
    await get_application_or_404(db, application_id)
    baseline_a = await get_baseline_or_404(db, application_id, baseline_id_a)
    baseline_b = await get_baseline_or_404(db, application_id, baseline_id_b)

    # Compare dependencies (B vs A - what changed from A to B)
    baseline_a_deps = {d["id"]: d for d in baseline_a.snapshot.get("dependencies", [])}
    baseline_b_deps = {d["id"]: d for d in baseline_b.snapshot.get("dependencies", [])}

    # Find changed dependencies and collect all asset IDs we need to look up
    added_dep_ids = set(baseline_b_deps.keys()) - set(baseline_a_deps.keys())
    removed_dep_ids = set(baseline_a_deps.keys()) - set(baseline_b_deps.keys())

    asset_ids_to_lookup: set[uuid.UUID] = set()
    for dep_id in added_dep_ids:
        dep = baseline_b_deps[dep_id]
        asset_ids_to_lookup.add(uuid.UUID(dep["source_asset_id"]))
        asset_ids_to_lookup.add(uuid.UUID(dep["target_asset_id"]))
    for dep_id in removed_dep_ids:
        dep = baseline_a_deps[dep_id]
        asset_ids_to_lookup.add(uuid.UUID(dep["source_asset_id"]))
        asset_ids_to_lookup.add(uuid.UUID(dep["target_asset_id"]))

    # Look up asset names and IPs
    asset_map: dict[str, dict[str, str | None]] = {}
    if asset_ids_to_lookup:
        assets_result = await db.execute(
            select(Asset).where(Asset.id.in_(asset_ids_to_lookup))
        )
        for asset in assets_result.scalars().all():
            asset_map[str(asset.id)] = {
                "name": asset.display_name or asset.name,
                "ip": asset.ip_address,
            }

    deps_added = []
    deps_removed = []

    for dep_id in added_dep_ids:
        dep = baseline_b_deps[dep_id]
        source_info = asset_map.get(dep["source_asset_id"], {})
        target_info = asset_map.get(dep["target_asset_id"], {})
        deps_added.append(DependencyChange(
            id=uuid.UUID(dep_id),
            source_asset_id=uuid.UUID(dep["source_asset_id"]),
            source_name=source_info.get("name"),
            source_ip=source_info.get("ip"),
            target_asset_id=uuid.UUID(dep["target_asset_id"]),
            target_name=target_info.get("name"),
            target_ip=target_info.get("ip"),
            target_port=dep["target_port"],
            protocol=dep["protocol"],
            change_type="added",
        ))

    for dep_id in removed_dep_ids:
        dep = baseline_a_deps[dep_id]
        source_info = asset_map.get(dep["source_asset_id"], {})
        target_info = asset_map.get(dep["target_asset_id"], {})
        deps_removed.append(DependencyChange(
            id=uuid.UUID(dep_id),
            source_asset_id=uuid.UUID(dep["source_asset_id"]),
            source_name=source_info.get("name"),
            source_ip=source_info.get("ip"),
            target_asset_id=uuid.UUID(dep["target_asset_id"]),
            target_name=target_info.get("name"),
            target_ip=target_info.get("ip"),
            target_port=dep["target_port"],
            protocol=dep["protocol"],
            change_type="removed",
        ))

    # Compare entry points
    eps_a = {f"{ep['asset_id']}:{ep['port']}:{ep['protocol']}": ep
             for ep in baseline_a.snapshot.get("entry_points", [])}
    eps_b = {f"{ep['asset_id']}:{ep['port']}:{ep['protocol']}": ep
             for ep in baseline_b.snapshot.get("entry_points", [])}

    eps_added = []
    eps_removed = []

    for ep_key, ep in eps_b.items():
        if ep_key not in eps_a:
            eps_added.append(EntryPointChange(
                port=ep["port"],
                protocol=ep["protocol"],
                label=ep.get("label"),
                member_id=uuid.UUID(ep["member_id"]),
                asset_id=uuid.UUID(ep["asset_id"]),
                change_type="added",
            ))

    for ep_key, ep in eps_a.items():
        if ep_key not in eps_b:
            eps_removed.append(EntryPointChange(
                port=ep["port"],
                protocol=ep["protocol"],
                label=ep.get("label"),
                member_id=uuid.UUID(ep["member_id"]),
                asset_id=uuid.UUID(ep["asset_id"]),
                change_type="removed",
            ))

    # Compare members
    members_a = set(baseline_a.snapshot.get("member_asset_ids", []))
    members_b = set(baseline_b.snapshot.get("member_asset_ids", []))

    members_added = [
        MemberChange(asset_id=uuid.UUID(m), change_type="added")
        for m in members_b - members_a
    ]
    members_removed = [
        MemberChange(asset_id=uuid.UUID(m), change_type="removed")
        for m in members_a - members_b
    ]

    # Build result
    result = BaselineComparisonResult(
        baseline_id=baseline_b.id,
        baseline_name=f"{baseline_a.name} → {baseline_b.name}",
        captured_at=baseline_b.captured_at,
        compared_at=datetime.now(timezone.utc),
        dependencies_added=deps_added,
        dependencies_removed=deps_removed,
        entry_points_added=eps_added,
        entry_points_removed=eps_removed,
        members_added=members_added,
        members_removed=members_removed,
    )
    result.calculate_severity()

    return result

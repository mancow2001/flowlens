"""Application API endpoints."""

import json
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, UploadFile, File, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from flowlens.api.dependencies import AdminUser, AnalystUser, DbSession, Pagination, Sorting, ViewerUser
from flowlens.common.logging import get_logger
from flowlens.models.asset import Application, ApplicationMember, Asset, EntryPoint
from flowlens.models.folder import Folder
from flowlens.schemas.asset import (
    ApplicationCreate,
    ApplicationEntryPointExport,
    ApplicationExportRow,
    ApplicationImportPreview,
    ApplicationImportResult,
    ApplicationImportValidation,
    ApplicationList,
    ApplicationMemberCreate,
    ApplicationMemberExport,
    ApplicationMemberResponse,
    ApplicationMemberUpdate,
    ApplicationResponse,
    ApplicationUpdate,
    ApplicationWithMembers,
    AssetSummary,
    EntryPointCreate,
    EntryPointResponse,
    EntryPointUpdate,
)
from flowlens.schemas.folder import MoveApplicationRequest

logger = get_logger(__name__)

router = APIRouter(prefix="/applications", tags=["applications"])


def _build_member_response(member: ApplicationMember) -> ApplicationMemberResponse:
    """Build an ApplicationMemberResponse from a member with loaded asset and entry points."""
    return ApplicationMemberResponse(
        id=member.id,
        asset_id=member.asset_id,
        asset=AssetSummary(
            id=member.asset.id,
            name=member.asset.name,
            display_name=member.asset.display_name,
            asset_type=member.asset.asset_type,
            ip_address=str(member.asset.ip_address),
            hostname=member.asset.hostname,
            is_internal=member.asset.is_internal,
            is_critical=member.asset.is_critical,
            last_seen=member.asset.last_seen,
        ),
        role=member.role,
        entry_points=[
            EntryPointResponse(
                id=ep.id,
                member_id=ep.member_id,
                port=ep.port,
                protocol=ep.protocol,
                order=ep.order,
                label=ep.label,
                created_at=ep.created_at,
                updated_at=ep.updated_at,
            )
            for ep in sorted(member.entry_points, key=lambda e: e.order)
        ],
        created_at=member.created_at,
        updated_at=member.updated_at,
    )


@router.get("", response_model=ApplicationList)
async def list_applications(
    db: DbSession,
    _user: ViewerUser,
    pagination: Pagination,
    sorting: Sorting,
    search: str | None = None,
    environment: str | None = None,
    team: str | None = None,
    criticality: str | None = None,
) -> ApplicationList:
    """List applications with filtering and pagination."""
    query = select(Application)

    # Apply filters
    if search:
        search_filter = f"%{search}%"
        query = query.where(
            Application.name.ilike(search_filter)
            | Application.display_name.ilike(search_filter)
            | Application.description.ilike(search_filter)
        )
    if environment:
        query = query.where(Application.environment == environment)
    if team:
        query = query.where(Application.team == team)
    if criticality:
        query = query.where(Application.criticality == criticality)

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query) or 0

    # Apply sorting
    if sorting.sort_by:
        sort_column = getattr(Application, sorting.sort_by, Application.name)
        if sorting.ascending:
            query = query.order_by(sort_column.asc())
        else:
            query = query.order_by(sort_column.desc())
    else:
        query = query.order_by(Application.name.asc())

    # Apply pagination
    query = query.offset(pagination.offset).limit(pagination.page_size)

    result = await db.execute(query)
    applications = result.scalars().all()

    items = [
        ApplicationResponse(
            id=app.id,
            name=app.name,
            display_name=app.display_name,
            description=app.description,
            owner=app.owner,
            team=app.team,
            environment=app.environment,
            criticality=app.criticality,
            tags=app.tags,
            metadata=app.extra_data,
            created_at=app.created_at,
            updated_at=app.updated_at,
        )
        for app in applications
    ]

    return ApplicationList(
        items=items,
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
        pages=(total + pagination.page_size - 1) // pagination.page_size if total > 0 else 0,
    )


# =============================================================================
# Export/Import Endpoints (must be before /{application_id} routes)
# =============================================================================


@router.get("/export", response_class=StreamingResponse)
async def export_applications(
    db: DbSession,
    _user: ViewerUser,
    environment: str | None = None,
    team: str | None = None,
    criticality: str | None = None,
) -> StreamingResponse:
    """Export applications with their members to JSON format.

    Exported data includes application details, members (identified by IP address),
    and entry points. This data can be modified and re-imported.

    Note: Only JSON format is supported due to the nested structure of applications.
    """
    # Build query with optional filters
    query = (
        select(Application)
        .options(
            selectinload(Application.members).selectinload(ApplicationMember.asset),
            selectinload(Application.members).selectinload(ApplicationMember.entry_points),
        )
    )

    if environment:
        query = query.where(Application.environment == environment)
    if team:
        query = query.where(Application.team == team)
    if criticality:
        query = query.where(Application.criticality == criticality)

    query = query.order_by(Application.name.asc())

    result = await db.execute(query)
    applications = result.scalars().all()

    # Build export rows
    rows = []
    for app in applications:
        members_export = []
        for member in sorted(app.members, key=lambda m: m.asset.name):
            entry_points_export = [
                ApplicationEntryPointExport(
                    port=ep.port,
                    protocol=ep.protocol,
                    order=ep.order,
                    label=ep.label,
                )
                for ep in sorted(member.entry_points, key=lambda e: e.order)
            ]
            members_export.append(ApplicationMemberExport(
                asset_ip_address=str(member.asset.ip_address),
                role=member.role,
                entry_points=entry_points_export,
            ))

        rows.append(ApplicationExportRow(
            name=app.name,
            display_name=app.display_name,
            description=app.description,
            owner=app.owner,
            team=app.team,
            environment=app.environment,
            criticality=app.criticality,
            tags=app.tags,
            metadata=app.extra_data,
            members=members_export,
        ))

    content = json.dumps([r.model_dump() for r in rows], indent=2)
    return StreamingResponse(
        iter([content]),
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=applications-export.json"},
    )


@router.post("/import/preview", response_model=ApplicationImportPreview)
async def preview_application_import(
    db: DbSession,
    _user: AnalystUser,
    file: UploadFile = File(...),
) -> ApplicationImportPreview:
    """Preview what an application import will do before committing.

    Accepts JSON file. Matches applications by name and members by asset IP address.
    Returns a preview of creates, updates, and any errors.
    """
    content = await file.read()
    content_str = content.decode("utf-8")

    # Parse JSON
    try:
        rows = json.loads(content_str)
        if not isinstance(rows, list):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="JSON file must contain an array of application objects",
            )
    except json.JSONDecodeError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid JSON: {e}",
        )

    if not rows:
        return ApplicationImportPreview(
            total_rows=0,
            to_create=0,
            to_update=0,
            to_skip=0,
            errors=0,
            validations=[],
        )

    # Get existing applications by name for comparison
    names = [r.get("name", "") for r in rows if r.get("name")]
    existing_query = (
        select(Application)
        .where(Application.name.in_(names))
        .options(
            selectinload(Application.members).selectinload(ApplicationMember.asset),
            selectinload(Application.members).selectinload(ApplicationMember.entry_points),
        )
    )
    existing_result = await db.execute(existing_query)
    existing_apps = {a.name: a for a in existing_result.scalars().all()}

    # Get all referenced asset IPs to validate they exist
    all_ips = set()
    for row in rows:
        members = row.get("members", [])
        for m in members:
            if m.get("asset_ip_address"):
                all_ips.add(m["asset_ip_address"])

    # Fetch all assets by IP
    # Use func.host() to extract just the IP without CIDR notation (e.g., /32)
    # since PostgreSQL INET type adds CIDR notation when cast to string
    if all_ips:
        asset_query = select(Asset).where(
            Asset.deleted_at.is_(None),
            func.host(Asset.ip_address).in_(list(all_ips)),
        )
        asset_result = await db.execute(asset_query)
        # Strip CIDR notation from keys to match import file format
        ip_to_asset = {str(a.ip_address).split('/')[0]: a for a in asset_result.scalars().all()}
    else:
        ip_to_asset = {}

    # Validate each row
    validations = []
    to_create = 0
    to_update = 0
    to_skip = 0
    errors = 0

    for idx, row in enumerate(rows, start=1):
        name = row.get("name", "").strip() if row.get("name") else ""

        if not name:
            validations.append(ApplicationImportValidation(
                row_number=idx,
                name="",
                status="error",
                message="Missing name",
            ))
            errors += 1
            continue

        # Validate member IPs exist
        members = row.get("members", [])
        member_errors = []
        for m in members:
            ip = m.get("asset_ip_address", "")
            if ip and ip not in ip_to_asset:
                member_errors.append(f"Asset with IP {ip} not found")

        if member_errors:
            validations.append(ApplicationImportValidation(
                row_number=idx,
                name=name,
                status="error",
                message=f"Member errors: {'; '.join(member_errors)}",
            ))
            errors += 1
            continue

        existing = existing_apps.get(name)

        if existing:
            # Check for changes
            changes = {}
            for field in ["display_name", "description", "owner", "team", "environment", "criticality"]:
                new_val = row.get(field, "").strip() if row.get(field) else None
                old_val = getattr(existing, field)
                if new_val and new_val != old_val:
                    changes[field] = {"old": old_val, "new": new_val}

            # Check for tag changes
            if row.get("tags"):
                if row["tags"] != existing.tags:
                    changes["tags"] = {"old": existing.tags, "new": row["tags"]}

            # Check for metadata changes
            if row.get("metadata"):
                if row["metadata"] != existing.extra_data:
                    changes["metadata"] = {"old": existing.extra_data, "new": row["metadata"]}

            # Check member changes
            existing_member_ips = {str(m.asset.ip_address): m for m in existing.members}
            import_member_ips = {m["asset_ip_address"]: m for m in members}

            member_changes = []

            # Members to add
            for ip in import_member_ips:
                if ip not in existing_member_ips:
                    member_changes.append({
                        "action": "add",
                        "asset_ip": ip,
                        "role": import_member_ips[ip].get("role"),
                        "entry_points": len(import_member_ips[ip].get("entry_points", [])),
                    })

            # Members to remove
            for ip in existing_member_ips:
                if ip not in import_member_ips:
                    member_changes.append({
                        "action": "remove",
                        "asset_ip": ip,
                        "role": existing_member_ips[ip].role,
                    })

            # Members to update
            for ip in import_member_ips:
                if ip in existing_member_ips:
                    existing_m = existing_member_ips[ip]
                    import_m = import_member_ips[ip]

                    role_changed = import_m.get("role") != existing_m.role
                    existing_eps = {(ep.port, ep.protocol) for ep in existing_m.entry_points}
                    import_eps = {(ep["port"], ep.get("protocol", 6)) for ep in import_m.get("entry_points", [])}
                    eps_changed = existing_eps != import_eps

                    if role_changed or eps_changed:
                        member_changes.append({
                            "action": "update",
                            "asset_ip": ip,
                            "role_changed": role_changed,
                            "entry_points_changed": eps_changed,
                        })

            if changes or member_changes:
                validations.append(ApplicationImportValidation(
                    row_number=idx,
                    name=name,
                    status="update",
                    message=f"Will update {len(changes)} field(s), {len(member_changes)} member change(s)",
                    changes=changes if changes else None,
                    member_changes=member_changes if member_changes else None,
                ))
                to_update += 1
            else:
                validations.append(ApplicationImportValidation(
                    row_number=idx,
                    name=name,
                    status="skip",
                    message="No changes detected",
                ))
                to_skip += 1
        else:
            # New application
            validations.append(ApplicationImportValidation(
                row_number=idx,
                name=name,
                status="create",
                message=f"Will create new application with {len(members)} member(s)",
            ))
            to_create += 1

    return ApplicationImportPreview(
        total_rows=len(rows),
        to_create=to_create,
        to_update=to_update,
        to_skip=to_skip,
        errors=errors,
        validations=validations,
    )


@router.post("/import", response_model=ApplicationImportResult)
async def import_applications(
    db: DbSession,
    _user: AnalystUser,
    file: UploadFile = File(...),
    skip_errors: bool = Query(False, alias="skipErrors"),
    sync_members: bool = Query(True, alias="syncMembers", description="Remove members not in import file"),
) -> ApplicationImportResult:
    """Import applications from JSON file.

    Matches applications by name. Updates existing applications or creates new ones.
    Members are matched by asset IP address.

    Options:
    - skipErrors: Continue processing if errors occur (default: false)
    - syncMembers: Remove members not in import file (default: true)
    """
    content = await file.read()
    content_str = content.decode("utf-8")

    # Parse JSON
    try:
        rows = json.loads(content_str)
    except json.JSONDecodeError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid JSON: {e}",
        )

    if not rows:
        return ApplicationImportResult(
            created=0,
            updated=0,
            skipped=0,
            errors=0,
            members_added=0,
            members_updated=0,
            members_removed=0,
        )

    # Get existing applications
    names = [r.get("name", "") for r in rows if r.get("name")]
    existing_query = (
        select(Application)
        .where(Application.name.in_(names))
        .options(
            selectinload(Application.members).selectinload(ApplicationMember.asset),
            selectinload(Application.members).selectinload(ApplicationMember.entry_points),
        )
    )
    existing_result = await db.execute(existing_query)
    existing_apps = {a.name: a for a in existing_result.scalars().all()}

    # Get all referenced assets
    all_ips = set()
    for row in rows:
        members = row.get("members", [])
        for m in members:
            if m.get("asset_ip_address"):
                all_ips.add(m["asset_ip_address"])

    # Use func.host() to extract just the IP without CIDR notation (e.g., /32)
    # since PostgreSQL INET type adds CIDR notation when cast to string
    if all_ips:
        asset_query = select(Asset).where(
            Asset.deleted_at.is_(None),
            func.host(Asset.ip_address).in_(list(all_ips)),
        )
        asset_result = await db.execute(asset_query)
        # Strip CIDR notation from keys to match import file format
        ip_to_asset = {str(a.ip_address).split('/')[0]: a for a in asset_result.scalars().all()}
    else:
        ip_to_asset = {}

    created = 0
    updated = 0
    skipped = 0
    errors = 0
    error_details = []
    members_added = 0
    members_updated = 0
    members_removed = 0

    for idx, row in enumerate(rows, start=1):
        name = row.get("name", "").strip() if row.get("name") else ""

        if not name:
            if skip_errors:
                errors += 1
                error_details.append(f"Row {idx}: Missing name")
                continue
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Row {idx}: Missing name",
            )

        # Validate member IPs exist
        members = row.get("members", [])
        member_errors = []
        for m in members:
            ip = m.get("asset_ip_address", "")
            if ip and ip not in ip_to_asset:
                member_errors.append(f"Asset with IP {ip} not found")

        if member_errors:
            if skip_errors:
                errors += 1
                error_details.append(f"Row {idx}: {'; '.join(member_errors)}")
                continue
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Row {idx}: {'; '.join(member_errors)}",
            )

        existing = existing_apps.get(name)

        if existing:
            # Update existing application
            has_changes = False
            for field in ["display_name", "description", "owner", "team", "environment", "criticality"]:
                new_val = row.get(field, "").strip() if row.get(field) else None
                if new_val:
                    if new_val != getattr(existing, field):
                        setattr(existing, field, new_val)
                        has_changes = True

            if row.get("tags") and row["tags"] != existing.tags:
                existing.tags = row["tags"]
                has_changes = True

            if row.get("metadata") and row["metadata"] != existing.extra_data:
                existing.extra_data = row["metadata"]
                has_changes = True

            # Handle members
            existing_member_ips = {str(m.asset.ip_address): m for m in existing.members}
            import_member_ips = {m["asset_ip_address"]: m for m in members}

            # Add new members
            for ip, m_data in import_member_ips.items():
                if ip not in existing_member_ips:
                    asset = ip_to_asset[ip]
                    new_member = ApplicationMember(
                        application_id=existing.id,
                        asset_id=asset.id,
                        role=m_data.get("role"),
                    )
                    db.add(new_member)
                    await db.flush()

                    # Add entry points
                    for ep_data in m_data.get("entry_points", []):
                        entry_point = EntryPoint(
                            member_id=new_member.id,
                            port=ep_data["port"],
                            protocol=ep_data.get("protocol", 6),
                            order=ep_data.get("order", 0),
                            label=ep_data.get("label"),
                        )
                        db.add(entry_point)

                    members_added += 1
                    has_changes = True

            # Update existing members
            for ip, m_data in import_member_ips.items():
                if ip in existing_member_ips:
                    existing_m = existing_member_ips[ip]
                    member_changed = False

                    # Update role
                    if m_data.get("role") != existing_m.role:
                        existing_m.role = m_data.get("role")
                        member_changed = True

                    # Sync entry points
                    import_eps = {(ep["port"], ep.get("protocol", 6)): ep for ep in m_data.get("entry_points", [])}
                    existing_eps = {(ep.port, ep.protocol): ep for ep in existing_m.entry_points}

                    # Add new entry points
                    for key, ep_data in import_eps.items():
                        if key not in existing_eps:
                            entry_point = EntryPoint(
                                member_id=existing_m.id,
                                port=ep_data["port"],
                                protocol=ep_data.get("protocol", 6),
                                order=ep_data.get("order", 0),
                                label=ep_data.get("label"),
                            )
                            db.add(entry_point)
                            member_changed = True

                    # Update or remove existing entry points
                    for key, ep in existing_eps.items():
                        if key in import_eps:
                            ep_data = import_eps[key]
                            if ep.order != ep_data.get("order", 0) or ep.label != ep_data.get("label"):
                                ep.order = ep_data.get("order", 0)
                                ep.label = ep_data.get("label")
                                member_changed = True
                        else:
                            # Remove entry point not in import
                            await db.delete(ep)
                            member_changed = True

                    if member_changed:
                        members_updated += 1
                        has_changes = True

            # Remove members not in import
            if sync_members:
                for ip, existing_m in existing_member_ips.items():
                    if ip not in import_member_ips:
                        await db.delete(existing_m)
                        members_removed += 1
                        has_changes = True

            if has_changes:
                updated += 1
            else:
                skipped += 1
        else:
            # Create new application
            new_app = Application(
                name=name,
                display_name=row.get("display_name", "").strip() if row.get("display_name") else None,
                description=row.get("description", "").strip() if row.get("description") else None,
                owner=row.get("owner", "").strip() if row.get("owner") else None,
                team=row.get("team", "").strip() if row.get("team") else None,
                environment=row.get("environment", "").strip() if row.get("environment") else None,
                criticality=row.get("criticality", "").strip() if row.get("criticality") else None,
                tags=row.get("tags"),
                extra_data=row.get("metadata"),
            )
            db.add(new_app)
            await db.flush()

            # Add members
            for m_data in members:
                ip = m_data["asset_ip_address"]
                asset = ip_to_asset[ip]
                new_member = ApplicationMember(
                    application_id=new_app.id,
                    asset_id=asset.id,
                    role=m_data.get("role"),
                )
                db.add(new_member)
                await db.flush()

                # Add entry points
                for ep_data in m_data.get("entry_points", []):
                    entry_point = EntryPoint(
                        member_id=new_member.id,
                        port=ep_data["port"],
                        protocol=ep_data.get("protocol", 6),
                        order=ep_data.get("order", 0),
                        label=ep_data.get("label"),
                    )
                    db.add(entry_point)

                members_added += 1

            created += 1

    await db.flush()

    logger.info(
        "Application import completed",
        created=created,
        updated=updated,
        skipped=skipped,
        errors=errors,
        members_added=members_added,
        members_updated=members_updated,
        members_removed=members_removed,
    )

    return ApplicationImportResult(
        created=created,
        updated=updated,
        skipped=skipped,
        errors=errors,
        members_added=members_added,
        members_updated=members_updated,
        members_removed=members_removed,
        error_details=error_details if error_details else None,
    )


@router.get("/{application_id}", response_model=ApplicationWithMembers)
async def get_application(
    application_id: UUID,
    db: DbSession,
    _user: ViewerUser,
) -> ApplicationWithMembers:
    """Get application by ID with all members."""
    query = (
        select(Application)
        .where(Application.id == application_id)
        .options(
            selectinload(Application.members)
            .selectinload(ApplicationMember.asset),
            selectinload(Application.members)
            .selectinload(ApplicationMember.entry_points),
        )
    )
    result = await db.execute(query)
    application = result.scalar_one_or_none()

    if not application:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Application {application_id} not found",
        )

    # Build member list with entry points first (members with entry points come first)
    # For ordering, use the minimum entry point order if any, otherwise 9999
    def get_sort_key(m: ApplicationMember) -> tuple:
        has_entry_points = len(m.entry_points) > 0
        min_order = min((ep.order for ep in m.entry_points), default=9999)
        return (not has_entry_points, min_order, m.asset.name)

    members = sorted(application.members, key=get_sort_key)

    return ApplicationWithMembers(
        id=application.id,
        name=application.name,
        display_name=application.display_name,
        description=application.description,
        owner=application.owner,
        team=application.team,
        environment=application.environment,
        criticality=application.criticality,
        tags=application.tags,
        metadata=application.extra_data,
        created_at=application.created_at,
        updated_at=application.updated_at,
        members=[_build_member_response(m) for m in members],
    )


@router.post("", response_model=ApplicationWithMembers, status_code=status.HTTP_201_CREATED)
async def create_application(
    data: ApplicationCreate,
    db: DbSession,
    _user: AnalystUser,
) -> ApplicationWithMembers:
    """Create a new application."""
    # Check for duplicate name
    existing = await db.execute(
        select(Application).where(Application.name == data.name)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Application with name '{data.name}' already exists",
        )

    # Create application
    application = Application(
        name=data.name,
        display_name=data.display_name,
        description=data.description,
        owner=data.owner,
        team=data.team,
        environment=data.environment,
        criticality=data.criticality,
        tags=data.tags,
        extra_data=data.metadata,
    )
    db.add(application)
    await db.flush()

    # Add initial members if provided
    members = []
    if data.members:
        # Validate all asset IDs exist
        asset_ids = [m.asset_id for m in data.members]
        asset_result = await db.execute(
            select(Asset)
            .where(Asset.id.in_(asset_ids), Asset.deleted_at.is_(None))
        )
        assets_map = {a.id: a for a in asset_result.scalars().all()}

        for member_data in data.members:
            if member_data.asset_id not in assets_map:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Asset {member_data.asset_id} not found",
                )

            member = ApplicationMember(
                application_id=application.id,
                asset_id=member_data.asset_id,
                role=member_data.role,
            )
            db.add(member)
            await db.flush()  # Get member.id for entry points

            # Create entry points if provided
            if member_data.entry_points:
                for ep_data in member_data.entry_points:
                    entry_point = EntryPoint(
                        member_id=member.id,
                        port=ep_data.port,
                        protocol=ep_data.protocol,
                        order=ep_data.order,
                        label=ep_data.label,
                    )
                    db.add(entry_point)
                    member.entry_points.append(entry_point)

            members.append((member, assets_map[member_data.asset_id]))

        await db.flush()

    # Build response
    member_responses = []
    for member, asset in members:
        await db.refresh(member)
        member_responses.append(ApplicationMemberResponse(
            id=member.id,
            asset_id=member.asset_id,
            asset=AssetSummary(
                id=asset.id,
                name=asset.name,
                display_name=asset.display_name,
                asset_type=asset.asset_type,
                ip_address=str(asset.ip_address),
                hostname=asset.hostname,
                is_internal=asset.is_internal,
                is_critical=asset.is_critical,
                last_seen=asset.last_seen,
            ),
            role=member.role,
            entry_points=[
                EntryPointResponse(
                    id=ep.id,
                    member_id=ep.member_id,
                    port=ep.port,
                    protocol=ep.protocol,
                    order=ep.order,
                    label=ep.label,
                    created_at=ep.created_at,
                    updated_at=ep.updated_at,
                )
                for ep in sorted(member.entry_points, key=lambda e: e.order)
            ],
            created_at=member.created_at,
            updated_at=member.updated_at,
        ))

    return ApplicationWithMembers(
        id=application.id,
        name=application.name,
        display_name=application.display_name,
        description=application.description,
        owner=application.owner,
        team=application.team,
        environment=application.environment,
        criticality=application.criticality,
        tags=application.tags,
        metadata=application.extra_data,
        created_at=application.created_at,
        updated_at=application.updated_at,
        members=member_responses,
    )


@router.put("/{application_id}", response_model=ApplicationResponse)
async def update_application(
    application_id: UUID,
    data: ApplicationUpdate,
    db: DbSession,
    _user: AnalystUser,
) -> ApplicationResponse:
    """Update an application."""
    result = await db.execute(
        select(Application).where(Application.id == application_id)
    )
    application = result.scalar_one_or_none()

    if not application:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Application {application_id} not found",
        )

    # Check for duplicate name if name is being changed
    if data.name and data.name != application.name:
        existing = await db.execute(
            select(Application).where(
                Application.name == data.name,
                Application.id != application_id,
            )
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Application with name '{data.name}' already exists",
            )

    # Update fields
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if field == "metadata":
            setattr(application, "extra_data", value)
        else:
            setattr(application, field, value)

    await db.flush()
    await db.refresh(application)

    return ApplicationResponse(
        id=application.id,
        name=application.name,
        display_name=application.display_name,
        description=application.description,
        owner=application.owner,
        team=application.team,
        environment=application.environment,
        criticality=application.criticality,
        tags=application.tags,
        metadata=application.extra_data,
        created_at=application.created_at,
        updated_at=application.updated_at,
    )


@router.delete("/{application_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_application(
    application_id: UUID,
    db: DbSession,
    _user: AdminUser,
) -> None:
    """Delete an application."""
    result = await db.execute(
        select(Application).where(Application.id == application_id)
    )
    application = result.scalar_one_or_none()

    if not application:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Application {application_id} not found",
        )

    await db.delete(application)
    await db.flush()


@router.post("/{application_id}/move", response_model=ApplicationResponse)
async def move_application_to_folder(
    application_id: UUID,
    move_request: MoveApplicationRequest,
    db: DbSession,
    _user: AnalystUser,
) -> ApplicationResponse:
    """Move an application to a folder.

    Set folder_id to null to remove the application from its current folder.
    """
    result = await db.execute(
        select(Application).where(Application.id == application_id)
    )
    application = result.scalar_one_or_none()

    if not application:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Application {application_id} not found",
        )

    # Verify folder exists if specified
    if move_request.folder_id:
        folder_result = await db.execute(
            select(Folder).where(Folder.id == move_request.folder_id)
        )
        folder = folder_result.scalar_one_or_none()
        if not folder:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Folder {move_request.folder_id} not found",
            )

    application.folder_id = move_request.folder_id
    await db.flush()
    await db.refresh(application)

    return ApplicationResponse(
        id=application.id,
        name=application.name,
        display_name=application.display_name,
        description=application.description,
        owner=application.owner,
        team=application.team,
        environment=application.environment,
        criticality=application.criticality,
        tags=application.tags,
        metadata=application.extra_data,
        created_at=application.created_at,
        updated_at=application.updated_at,
    )


# =============================================================================
# Member Management Endpoints
# =============================================================================


@router.get("/{application_id}/members", response_model=list[ApplicationMemberResponse])
async def list_application_members(
    application_id: UUID,
    db: DbSession,
    _user: ViewerUser,
    entry_points_only: bool = Query(False, alias="entryPointsOnly"),
) -> list[ApplicationMemberResponse]:
    """List all members of an application."""
    # Verify application exists
    app_result = await db.execute(
        select(Application.id).where(Application.id == application_id)
    )
    if not app_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Application {application_id} not found",
        )

    # Get members with assets and entry points
    query = (
        select(ApplicationMember)
        .where(ApplicationMember.application_id == application_id)
        .options(
            selectinload(ApplicationMember.asset),
            selectinload(ApplicationMember.entry_points),
        )
    )

    result = await db.execute(query)
    members = list(result.scalars().all())

    # Filter to members with entry points if requested
    if entry_points_only:
        members = [m for m in members if len(m.entry_points) > 0]

    # Sort: members with entry points first, then by min entry point order, then by name
    def get_sort_key(m: ApplicationMember) -> tuple:
        has_entry_points = len(m.entry_points) > 0
        min_order = min((ep.order for ep in m.entry_points), default=9999)
        return (not has_entry_points, min_order, m.asset.name)

    members = sorted(members, key=get_sort_key)

    return [_build_member_response(m) for m in members]


@router.post(
    "/{application_id}/members",
    response_model=ApplicationMemberResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_application_member(
    application_id: UUID,
    data: ApplicationMemberCreate,
    db: DbSession,
    _user: AnalystUser,
) -> ApplicationMemberResponse:
    """Add an asset to an application."""
    # Verify application exists
    app_result = await db.execute(
        select(Application.id).where(Application.id == application_id)
    )
    if not app_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Application {application_id} not found",
        )

    # Verify asset exists
    asset_result = await db.execute(
        select(Asset).where(Asset.id == data.asset_id, Asset.deleted_at.is_(None))
    )
    asset = asset_result.scalar_one_or_none()
    if not asset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Asset {data.asset_id} not found",
        )

    # Check if asset is already a member
    existing = await db.execute(
        select(ApplicationMember).where(
            ApplicationMember.application_id == application_id,
            ApplicationMember.asset_id == data.asset_id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Asset {data.asset_id} is already a member of this application",
        )

    # Create member
    member = ApplicationMember(
        application_id=application_id,
        asset_id=data.asset_id,
        role=data.role,
    )
    db.add(member)
    await db.flush()

    # Create entry points if provided
    entry_points_list = []
    if data.entry_points:
        for ep_data in data.entry_points:
            entry_point = EntryPoint(
                member_id=member.id,
                port=ep_data.port,
                protocol=ep_data.protocol,
                order=ep_data.order,
                label=ep_data.label,
            )
            db.add(entry_point)
            entry_points_list.append(entry_point)
        await db.flush()

    await db.refresh(member)

    return ApplicationMemberResponse(
        id=member.id,
        asset_id=member.asset_id,
        asset=AssetSummary(
            id=asset.id,
            name=asset.name,
            display_name=asset.display_name,
            asset_type=asset.asset_type,
            ip_address=str(asset.ip_address),
            hostname=asset.hostname,
            is_internal=asset.is_internal,
            is_critical=asset.is_critical,
            last_seen=asset.last_seen,
        ),
        role=member.role,
        entry_points=[
            EntryPointResponse(
                id=ep.id,
                member_id=ep.member_id,
                port=ep.port,
                protocol=ep.protocol,
                order=ep.order,
                label=ep.label,
                created_at=ep.created_at,
                updated_at=ep.updated_at,
            )
            for ep in sorted(entry_points_list, key=lambda e: e.order)
        ],
        created_at=member.created_at,
        updated_at=member.updated_at,
    )


@router.patch(
    "/{application_id}/members/{asset_id}",
    response_model=ApplicationMemberResponse,
)
async def update_application_member(
    application_id: UUID,
    asset_id: UUID,
    data: ApplicationMemberUpdate,
    db: DbSession,
    _user: AnalystUser,
) -> ApplicationMemberResponse:
    """Update a member's role."""
    # Get member with asset and entry points
    result = await db.execute(
        select(ApplicationMember)
        .where(
            ApplicationMember.application_id == application_id,
            ApplicationMember.asset_id == asset_id,
        )
        .options(
            selectinload(ApplicationMember.asset),
            selectinload(ApplicationMember.entry_points),
        )
    )
    member = result.scalar_one_or_none()

    if not member:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Member with asset {asset_id} not found in application {application_id}",
        )

    # Update fields
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(member, field, value)

    await db.flush()
    await db.refresh(member)

    return _build_member_response(member)


@router.delete(
    "/{application_id}/members/{asset_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_application_member(
    application_id: UUID,
    asset_id: UUID,
    db: DbSession,
    _user: AnalystUser,
) -> None:
    """Remove an asset from an application."""
    result = await db.execute(
        select(ApplicationMember).where(
            ApplicationMember.application_id == application_id,
            ApplicationMember.asset_id == asset_id,
        )
    )
    member = result.scalar_one_or_none()

    if not member:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Member with asset {asset_id} not found in application {application_id}",
        )

    await db.delete(member)
    await db.flush()


# =============================================================================
# Entry Point CRUD Endpoints
# =============================================================================


@router.get(
    "/{application_id}/members/{asset_id}/entry-points",
    response_model=list[EntryPointResponse],
)
async def list_entry_points(
    application_id: UUID,
    asset_id: UUID,
    db: DbSession,
    _user: ViewerUser,
) -> list[EntryPointResponse]:
    """List all entry points for a specific member."""
    result = await db.execute(
        select(ApplicationMember)
        .where(
            ApplicationMember.application_id == application_id,
            ApplicationMember.asset_id == asset_id,
        )
        .options(selectinload(ApplicationMember.entry_points))
    )
    member = result.scalar_one_or_none()

    if not member:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Member with asset {asset_id} not found in application {application_id}",
        )

    return [
        EntryPointResponse(
            id=ep.id,
            member_id=ep.member_id,
            port=ep.port,
            protocol=ep.protocol,
            order=ep.order,
            label=ep.label,
            created_at=ep.created_at,
            updated_at=ep.updated_at,
        )
        for ep in sorted(member.entry_points, key=lambda e: e.order)
    ]


@router.post(
    "/{application_id}/members/{asset_id}/entry-points",
    response_model=EntryPointResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_entry_point(
    application_id: UUID,
    asset_id: UUID,
    data: EntryPointCreate,
    db: DbSession,
    _user: AnalystUser,
) -> EntryPointResponse:
    """Add an entry point to a member."""
    result = await db.execute(
        select(ApplicationMember)
        .where(
            ApplicationMember.application_id == application_id,
            ApplicationMember.asset_id == asset_id,
        )
        .options(selectinload(ApplicationMember.entry_points))
    )
    member = result.scalar_one_or_none()

    if not member:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Member with asset {asset_id} not found in application {application_id}",
        )

    # Check for duplicate port/protocol
    for existing_ep in member.entry_points:
        if existing_ep.port == data.port and existing_ep.protocol == data.protocol:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Entry point with port {data.port}/{data.protocol} already exists",
            )

    entry_point = EntryPoint(
        member_id=member.id,
        port=data.port,
        protocol=data.protocol,
        order=data.order,
        label=data.label,
    )
    db.add(entry_point)
    await db.flush()
    await db.refresh(entry_point)

    return EntryPointResponse(
        id=entry_point.id,
        member_id=entry_point.member_id,
        port=entry_point.port,
        protocol=entry_point.protocol,
        order=entry_point.order,
        label=entry_point.label,
        created_at=entry_point.created_at,
        updated_at=entry_point.updated_at,
    )


@router.patch(
    "/{application_id}/members/{asset_id}/entry-points/{entry_point_id}",
    response_model=EntryPointResponse,
)
async def update_entry_point(
    application_id: UUID,
    asset_id: UUID,
    entry_point_id: UUID,
    data: EntryPointUpdate,
    db: DbSession,
    _user: AnalystUser,
) -> EntryPointResponse:
    """Update an entry point."""
    # First verify the member exists for this application
    member_result = await db.execute(
        select(ApplicationMember.id)
        .where(
            ApplicationMember.application_id == application_id,
            ApplicationMember.asset_id == asset_id,
        )
    )
    member_id = member_result.scalar_one_or_none()

    if not member_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Member with asset {asset_id} not found in application {application_id}",
        )

    # Get the entry point
    result = await db.execute(
        select(EntryPoint)
        .where(
            EntryPoint.id == entry_point_id,
            EntryPoint.member_id == member_id,
        )
    )
    entry_point = result.scalar_one_or_none()

    if not entry_point:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Entry point {entry_point_id} not found",
        )

    # Check for duplicate port/protocol if changing port or protocol
    if data.port is not None or data.protocol is not None:
        new_port = data.port if data.port is not None else entry_point.port
        new_protocol = data.protocol if data.protocol is not None else entry_point.protocol

        existing = await db.execute(
            select(EntryPoint)
            .where(
                EntryPoint.member_id == member_id,
                EntryPoint.port == new_port,
                EntryPoint.protocol == new_protocol,
                EntryPoint.id != entry_point_id,
            )
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Entry point with port {new_port}/{new_protocol} already exists",
            )

    # Update fields
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(entry_point, field, value)

    await db.flush()
    await db.refresh(entry_point)

    return EntryPointResponse(
        id=entry_point.id,
        member_id=entry_point.member_id,
        port=entry_point.port,
        protocol=entry_point.protocol,
        order=entry_point.order,
        label=entry_point.label,
        created_at=entry_point.created_at,
        updated_at=entry_point.updated_at,
    )


@router.delete(
    "/{application_id}/members/{asset_id}/entry-points/{entry_point_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_entry_point(
    application_id: UUID,
    asset_id: UUID,
    entry_point_id: UUID,
    db: DbSession,
    _user: AnalystUser,
) -> None:
    """Delete an entry point."""
    # First verify the member exists for this application
    member_result = await db.execute(
        select(ApplicationMember.id)
        .where(
            ApplicationMember.application_id == application_id,
            ApplicationMember.asset_id == asset_id,
        )
    )
    member_id = member_result.scalar_one_or_none()

    if not member_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Member with asset {asset_id} not found in application {application_id}",
        )

    # Get and delete the entry point
    result = await db.execute(
        select(EntryPoint)
        .where(
            EntryPoint.id == entry_point_id,
            EntryPoint.member_id == member_id,
        )
    )
    entry_point = result.scalar_one_or_none()

    if not entry_point:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Entry point {entry_point_id} not found",
        )

    await db.delete(entry_point)
    await db.flush()


# =============================================================================
# Application Topology Endpoint
# =============================================================================


@router.get("/{application_id}/topology")
async def get_application_topology(
    application_id: UUID,
    db: DbSession,
    _user: ViewerUser,
    max_depth: int = Query(default=3, ge=1, le=5, description="Maximum hop depth for downstream traversal"),
) -> dict:
    """Get topology data for an application with entry point flow visualization.

    Returns a hierarchical view organized by hop distance:
    - Left: Aggregated inbound client counts for each entry point
    - Center: Entry point nodes (hop 0)
    - Right: Downstream dependencies organized by hop distance (1, 2, 3...)

    The topology shows:
    1. External clients connecting TO entry points (aggregated by entry point port)
    2. Connections FROM entry points traversed up to max_depth hops
    3. All downstream assets with their hop distance from entry points
    """
    from sqlalchemy import func as sql_func
    from flowlens.models.dependency import Dependency
    from flowlens.graph.traversal import GraphTraversal

    # Get application with members and entry points
    query = (
        select(Application)
        .where(Application.id == application_id)
        .options(
            selectinload(Application.members).selectinload(ApplicationMember.asset),
            selectinload(Application.members).selectinload(ApplicationMember.entry_points),
        )
    )
    result = await db.execute(query)
    application = result.scalar_one_or_none()

    if not application:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Application {application_id} not found",
        )

    # Get asset IDs of all members
    member_asset_ids = {m.asset_id for m in application.members}
    member_map = {m.asset_id: m for m in application.members}

    if not member_asset_ids:
        return {
            "application": {
                "id": str(application.id),
                "name": application.name,
                "display_name": application.display_name,
            },
            "nodes": [],
            "edges": [],
            "entry_points": [],
            "inbound_summary": [],
        }

    # Identify entry point members (members with at least one entry point)
    entry_point_members = [m for m in application.members if len(m.entry_points) > 0]
    entry_point_asset_ids = {m.asset_id for m in entry_point_members}

    # Query 1: Get inbound connections TO entry points from OUTSIDE the application
    # For each entry point definition (port/protocol)
    inbound_summary = []
    for ep_member in entry_point_members:
        for ep in ep_member.entry_points:
            # Count unique external sources connecting to this entry point
            inbound_query = (
                select(
                    sql_func.count(sql_func.distinct(Dependency.source_asset_id)).label("client_count"),
                    sql_func.sum(Dependency.bytes_last_24h).label("total_bytes"),
                )
                .where(
                    Dependency.target_asset_id == ep_member.asset_id,
                    Dependency.target_port == ep.port,
                    Dependency.protocol == ep.protocol,
                    Dependency.source_asset_id.notin_(member_asset_ids),  # External sources only
                )
            )

            inbound_result = await db.execute(inbound_query)
            row = inbound_result.one()

            inbound_summary.append({
                "entry_point_id": str(ep.id),
                "entry_point_asset_id": str(ep_member.asset_id),
                "entry_point_name": ep_member.asset.name,
                "port": ep.port,
                "protocol": ep.protocol,
                "label": ep.label,
                "client_count": row.client_count or 0,
                "total_bytes_24h": row.total_bytes or 0,
            })

    # Use GraphTraversal to get downstream dependencies from each entry point
    traversal = GraphTraversal(max_depth=max_depth)

    # Track downstream assets with their minimum hop distance from any entry point
    # Key: asset_id, Value: {min_hop_distance, paths_from_entry_points}
    downstream_assets: dict[UUID, dict] = {}

    # Traverse downstream from each entry point
    for ep_member in entry_point_members:
        result = await traversal.get_downstream(db, ep_member.asset_id, max_depth=max_depth)

        for node in result.nodes:
            if node.asset_id in downstream_assets:
                # Update if this path is shorter
                if node.depth < downstream_assets[node.asset_id]["hop_distance"]:
                    downstream_assets[node.asset_id]["hop_distance"] = node.depth
                # Track all entry points that reach this asset
                downstream_assets[node.asset_id]["from_entry_points"].append({
                    "entry_point_id": str(ep_member.asset_id),
                    "distance": node.depth,
                })
            else:
                downstream_assets[node.asset_id] = {
                    "hop_distance": node.depth,
                    "from_entry_points": [{
                        "entry_point_id": str(ep_member.asset_id),
                        "distance": node.depth,
                    }],
                    "bytes_total": node.bytes_total,
                    "last_seen": node.last_seen,
                }

    # Get full asset details for all downstream assets
    downstream_asset_ids = set(downstream_assets.keys())
    downstream_asset_details = {}
    if downstream_asset_ids:
        assets_query = (
            select(Asset)
            .where(
                Asset.id.in_(list(downstream_asset_ids)),
                Asset.deleted_at.is_(None),
            )
        )
        result = await db.execute(assets_query)
        for asset in result.scalars().all():
            downstream_asset_details[asset.id] = asset

    # Build node data - entry points first (hop 0), then downstream by hop distance
    nodes = []

    # Add entry point nodes (hop 0)
    # For each member with entry points, include all their entry point definitions
    for member in entry_point_members:
        asset = member.asset
        # Get minimum order from all entry points for this member
        min_order = min((ep.order for ep in member.entry_points), default=0)
        nodes.append({
            "id": str(asset.id),
            "name": asset.name,
            "display_name": asset.display_name,
            "ip_address": str(asset.ip_address),
            "asset_type": asset.asset_type,
            "is_entry_point": True,
            "entry_points": [
                {
                    "id": str(ep.id),
                    "port": ep.port,
                    "protocol": ep.protocol,
                    "order": ep.order,
                    "label": ep.label,
                }
                for ep in sorted(member.entry_points, key=lambda e: e.order)
            ],
            "entry_point_order": min_order,
            "role": member.role,
            "is_critical": asset.is_critical,
            "is_external": False,
            "hop_distance": 0,
        })

    # Add downstream nodes with hop distance
    for asset_id, info in sorted(downstream_assets.items(), key=lambda x: x[1]["hop_distance"]):
        asset = downstream_asset_details.get(asset_id)
        if not asset:
            continue

        # Check if this is an application member
        member = member_map.get(asset_id)
        is_app_member = member is not None

        # Skip entry points (already added)
        if asset_id in entry_point_asset_ids:
            continue

        nodes.append({
            "id": str(asset.id),
            "name": asset.name,
            "display_name": asset.display_name,
            "ip_address": str(asset.ip_address),
            "asset_type": asset.asset_type,
            "is_entry_point": False,
            "entry_points": [],
            "entry_point_order": None,
            "role": member.role if member else None,
            "is_critical": asset.is_critical,
            "is_external": not is_app_member,
            "is_internal_asset": asset.is_internal,
            "hop_distance": info["hop_distance"],
            "from_entry_points": info["from_entry_points"],
        })

    # Build edge data - get all dependencies between nodes in our graph
    node_ids = {UUID(n["id"]) for n in nodes}
    edges = []

    if node_ids:
        # Get all dependencies where both source and target are in our node set
        deps_query = (
            select(Dependency)
            .where(
                Dependency.source_asset_id.in_(list(node_ids)),
                Dependency.target_asset_id.in_(list(node_ids)),
                Dependency.valid_to.is_(None),
            )
        )
        result = await db.execute(deps_query)

        for conn in result.scalars().all():
            # Calculate hop distance for the edge (based on target's hop distance)
            target_hop = downstream_assets.get(conn.target_asset_id, {}).get("hop_distance", 0)

            edges.append({
                "id": str(conn.id),
                "source": str(conn.source_asset_id),
                "target": str(conn.target_asset_id),
                "target_port": conn.target_port,
                "protocol": conn.protocol,
                "dependency_type": conn.dependency_type,
                "bytes_last_24h": conn.bytes_last_24h,
                "last_seen": conn.last_seen.isoformat() if conn.last_seen else None,
                "is_from_entry_point": conn.source_asset_id in entry_point_asset_ids,
                "hop_distance": target_hop,
            })

    # Build entry points list with port/protocol info
    # Flatten entry points from all members, with asset info
    entry_points = []
    for m in entry_point_members:
        for ep in sorted(m.entry_points, key=lambda e: e.order):
            entry_points.append({
                "id": str(ep.id),
                "asset_id": str(m.asset_id),
                "asset_name": m.asset.name,
                "port": ep.port,
                "protocol": ep.protocol,
                "order": ep.order,
                "label": ep.label,
            })
    # Sort by order
    entry_points.sort(key=lambda e: e["order"])

    return {
        "application": {
            "id": str(application.id),
            "name": application.name,
            "display_name": application.display_name,
        },
        "nodes": nodes,
        "edges": edges,
        "entry_points": entry_points,
        "inbound_summary": inbound_summary,
        "max_depth": max_depth,
    }

"""Application API endpoints."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from flowlens.api.dependencies import AuthenticatedUser, DbSession, Pagination, Sorting
from flowlens.models.asset import Application, ApplicationMember, Asset
from flowlens.schemas.asset import (
    ApplicationCreate,
    ApplicationList,
    ApplicationMemberCreate,
    ApplicationMemberResponse,
    ApplicationMemberUpdate,
    ApplicationResponse,
    ApplicationUpdate,
    ApplicationWithMembers,
    AssetSummary,
)

router = APIRouter(prefix="/applications", tags=["applications"])


def _build_member_response(member: ApplicationMember) -> ApplicationMemberResponse:
    """Build an ApplicationMemberResponse from a member with loaded asset."""
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
        is_entry_point=member.is_entry_point,
        entry_point_order=member.entry_point_order,
        created_at=member.created_at,
        updated_at=member.updated_at,
    )


@router.get("", response_model=ApplicationList)
async def list_applications(
    db: DbSession,
    user: AuthenticatedUser,
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


@router.get("/{application_id}", response_model=ApplicationWithMembers)
async def get_application(
    application_id: UUID,
    db: DbSession,
    user: AuthenticatedUser,
) -> ApplicationWithMembers:
    """Get application by ID with all members."""
    query = (
        select(Application)
        .where(Application.id == application_id)
        .options(
            selectinload(Application.members).selectinload(ApplicationMember.asset)
        )
    )
    result = await db.execute(query)
    application = result.scalar_one_or_none()

    if not application:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Application {application_id} not found",
        )

    # Build member list with entry points first
    members = sorted(
        application.members,
        key=lambda m: (not m.is_entry_point, m.entry_point_order or 9999, m.asset.name),
    )

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
    user: AuthenticatedUser,
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
                is_entry_point=member_data.is_entry_point,
                entry_point_order=member_data.entry_point_order,
            )
            db.add(member)
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
            is_entry_point=member.is_entry_point,
            entry_point_order=member.entry_point_order,
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
    user: AuthenticatedUser,
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
    user: AuthenticatedUser,
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


# =============================================================================
# Member Management Endpoints
# =============================================================================


@router.get("/{application_id}/members", response_model=list[ApplicationMemberResponse])
async def list_application_members(
    application_id: UUID,
    db: DbSession,
    user: AuthenticatedUser,
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

    # Get members with assets
    query = (
        select(ApplicationMember)
        .where(ApplicationMember.application_id == application_id)
        .options(selectinload(ApplicationMember.asset))
    )

    if entry_points_only:
        query = query.where(ApplicationMember.is_entry_point == True)

    result = await db.execute(query)
    members = result.scalars().all()

    # Sort: entry points first, then by order, then by name
    members = sorted(
        members,
        key=lambda m: (not m.is_entry_point, m.entry_point_order or 9999, m.asset.name),
    )

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
    user: AuthenticatedUser,
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
        is_entry_point=data.is_entry_point,
        entry_point_order=data.entry_point_order,
    )
    db.add(member)
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
        is_entry_point=member.is_entry_point,
        entry_point_order=member.entry_point_order,
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
    user: AuthenticatedUser,
) -> ApplicationMemberResponse:
    """Update a member's role or entry point status."""
    # Get member with asset
    result = await db.execute(
        select(ApplicationMember)
        .where(
            ApplicationMember.application_id == application_id,
            ApplicationMember.asset_id == asset_id,
        )
        .options(selectinload(ApplicationMember.asset))
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
    user: AuthenticatedUser,
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
# Entry Point Convenience Endpoints
# =============================================================================


@router.post(
    "/{application_id}/entry-points/{asset_id}",
    response_model=ApplicationMemberResponse,
)
async def set_entry_point(
    application_id: UUID,
    asset_id: UUID,
    db: DbSession,
    user: AuthenticatedUser,
    order: int | None = Query(None, description="Entry point order (lower = first)"),
) -> ApplicationMemberResponse:
    """Mark an existing member as an entry point."""
    result = await db.execute(
        select(ApplicationMember)
        .where(
            ApplicationMember.application_id == application_id,
            ApplicationMember.asset_id == asset_id,
        )
        .options(selectinload(ApplicationMember.asset))
    )
    member = result.scalar_one_or_none()

    if not member:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Member with asset {asset_id} not found in application {application_id}",
        )

    member.is_entry_point = True
    member.entry_point_order = order

    await db.flush()
    await db.refresh(member)

    return _build_member_response(member)


@router.delete(
    "/{application_id}/entry-points/{asset_id}",
    response_model=ApplicationMemberResponse,
)
async def unset_entry_point(
    application_id: UUID,
    asset_id: UUID,
    db: DbSession,
    user: AuthenticatedUser,
) -> ApplicationMemberResponse:
    """Remove entry point status from a member."""
    result = await db.execute(
        select(ApplicationMember)
        .where(
            ApplicationMember.application_id == application_id,
            ApplicationMember.asset_id == asset_id,
        )
        .options(selectinload(ApplicationMember.asset))
    )
    member = result.scalar_one_or_none()

    if not member:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Member with asset {asset_id} not found in application {application_id}",
        )

    member.is_entry_point = False
    member.entry_point_order = None

    await db.flush()
    await db.refresh(member)

    return _build_member_response(member)

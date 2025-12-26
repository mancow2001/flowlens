"""Classification Rules API endpoints."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select, text

from flowlens.api.dependencies import AuthenticatedUser, DbSession, Pagination
from flowlens.models.classification import ClassificationRule
from flowlens.schemas.classification import (
    ClassificationRuleCreate,
    ClassificationRuleList,
    ClassificationRuleResponse,
    ClassificationRuleSummary,
    ClassificationRuleUpdate,
    IPClassificationDebug,
    IPClassificationMatch,
    IPClassificationResult,
)

router = APIRouter(prefix="/classification-rules", tags=["classification"])


@router.get("", response_model=ClassificationRuleList)
async def list_classification_rules(
    db: DbSession,
    user: AuthenticatedUser,
    pagination: Pagination,
    is_active: bool | None = Query(None, alias="isActive"),
    environment: str | None = None,
    datacenter: str | None = None,
) -> ClassificationRuleList:
    """List classification rules with filtering and pagination."""
    query = select(ClassificationRule)

    if is_active is not None:
        query = query.where(ClassificationRule.is_active == is_active)
    if environment:
        query = query.where(ClassificationRule.environment == environment)
    if datacenter:
        query = query.where(ClassificationRule.datacenter == datacenter)

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query) or 0

    # Order by priority, then name
    query = query.order_by(ClassificationRule.priority.asc(), ClassificationRule.name.asc())

    # Apply pagination
    query = query.offset(pagination.offset).limit(pagination.page_size)

    result = await db.execute(query)
    rules = result.scalars().all()

    items = [
        ClassificationRuleSummary(
            id=r.id,
            name=r.name,
            cidr=str(r.cidr),
            environment=r.environment,
            datacenter=r.datacenter,
            location=r.location,
            is_active=r.is_active,
        )
        for r in rules
    ]

    return ClassificationRuleList(
        items=items,
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
    )


@router.get("/classify/{ip_address}", response_model=IPClassificationResult)
async def classify_ip(
    ip_address: str,
    db: DbSession,
    user: AuthenticatedUser,
) -> IPClassificationResult:
    """Get classification for a specific IP address.

    Returns the winning classification rule's attributes for the IP.
    """
    # Validate IP address format
    try:
        import ipaddress
        ipaddress.ip_address(ip_address)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid IP address: {ip_address}",
        )

    # Call the database function
    result = await db.execute(
        text("SELECT * FROM get_ip_classification(:ip_addr::inet)"),
        {"ip_addr": ip_address},
    )
    row = result.fetchone()

    if not row or row.rule_id is None:
        return IPClassificationResult(
            ip_address=ip_address,
            matched=False,
        )

    return IPClassificationResult(
        ip_address=ip_address,
        matched=True,
        rule_id=row.rule_id,
        rule_name=row.rule_name,
        environment=row.environment,
        datacenter=row.datacenter,
        location=row.location,
        asset_type=row.asset_type,
        is_internal=row.is_internal,
        default_owner=row.default_owner,
        default_team=row.default_team,
    )


@router.get("/classify/{ip_address}/debug", response_model=IPClassificationDebug)
async def classify_ip_debug(
    ip_address: str,
    db: DbSession,
    user: AuthenticatedUser,
) -> IPClassificationDebug:
    """Debug view showing all matching rules for an IP.

    Useful for understanding why a particular rule won.
    """
    # Validate IP address format
    try:
        import ipaddress
        ipaddress.ip_address(ip_address)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid IP address: {ip_address}",
        )

    # Call the database function
    result = await db.execute(
        text("SELECT * FROM get_all_ip_classifications(:ip_addr::inet)"),
        {"ip_addr": ip_address},
    )
    rows = result.fetchall()

    matches = [
        IPClassificationMatch(
            rule_id=row.rule_id,
            rule_name=row.rule_name,
            cidr=str(row.cidr),
            prefix_length=row.prefix_length,
            priority=row.priority,
            environment=row.environment,
            datacenter=row.datacenter,
            location=row.location,
            is_winning=row.is_winning,
        )
        for row in rows
    ]

    winning_id = next((m.rule_id for m in matches if m.is_winning), None)

    return IPClassificationDebug(
        ip_address=ip_address,
        matches=matches,
        winning_rule_id=winning_id,
    )


@router.get("/{rule_id}", response_model=ClassificationRuleResponse)
async def get_classification_rule(
    rule_id: UUID,
    db: DbSession,
    user: AuthenticatedUser,
) -> ClassificationRuleResponse:
    """Get classification rule by ID."""
    result = await db.execute(
        select(ClassificationRule).where(ClassificationRule.id == rule_id)
    )
    rule = result.scalar_one_or_none()

    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Classification rule {rule_id} not found",
        )

    return ClassificationRuleResponse(
        id=rule.id,
        name=rule.name,
        description=rule.description,
        cidr=str(rule.cidr),
        priority=rule.priority,
        environment=rule.environment,
        datacenter=rule.datacenter,
        location=rule.location,
        asset_type=rule.asset_type,
        is_internal=rule.is_internal,
        default_owner=rule.default_owner,
        default_team=rule.default_team,
        is_active=rule.is_active,
        created_at=rule.created_at,
        updated_at=rule.updated_at,
    )


@router.post("", response_model=ClassificationRuleResponse, status_code=status.HTTP_201_CREATED)
async def create_classification_rule(
    data: ClassificationRuleCreate,
    db: DbSession,
    user: AuthenticatedUser,
) -> ClassificationRuleResponse:
    """Create a new classification rule."""
    # Check for duplicate name
    existing = await db.execute(
        select(ClassificationRule).where(ClassificationRule.name == data.name)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Classification rule with name '{data.name}' already exists",
        )

    rule = ClassificationRule(
        name=data.name,
        description=data.description,
        cidr=data.cidr,
        priority=data.priority,
        environment=data.environment,
        datacenter=data.datacenter,
        location=data.location,
        asset_type=data.asset_type,
        is_internal=data.is_internal,
        default_owner=data.default_owner,
        default_team=data.default_team,
        is_active=data.is_active,
    )

    db.add(rule)
    await db.flush()
    await db.refresh(rule)

    return ClassificationRuleResponse(
        id=rule.id,
        name=rule.name,
        description=rule.description,
        cidr=str(rule.cidr),
        priority=rule.priority,
        environment=rule.environment,
        datacenter=rule.datacenter,
        location=rule.location,
        asset_type=rule.asset_type,
        is_internal=rule.is_internal,
        default_owner=rule.default_owner,
        default_team=rule.default_team,
        is_active=rule.is_active,
        created_at=rule.created_at,
        updated_at=rule.updated_at,
    )


@router.patch("/{rule_id}", response_model=ClassificationRuleResponse)
async def update_classification_rule(
    rule_id: UUID,
    data: ClassificationRuleUpdate,
    db: DbSession,
    user: AuthenticatedUser,
) -> ClassificationRuleResponse:
    """Update a classification rule."""
    result = await db.execute(
        select(ClassificationRule).where(ClassificationRule.id == rule_id)
    )
    rule = result.scalar_one_or_none()

    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Classification rule {rule_id} not found",
        )

    # Check for duplicate name if name is being changed
    if data.name and data.name != rule.name:
        existing = await db.execute(
            select(ClassificationRule).where(ClassificationRule.name == data.name)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Classification rule with name '{data.name}' already exists",
            )

    # Update fields
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(rule, field, value)

    await db.flush()
    await db.refresh(rule)

    return ClassificationRuleResponse(
        id=rule.id,
        name=rule.name,
        description=rule.description,
        cidr=str(rule.cidr),
        priority=rule.priority,
        environment=rule.environment,
        datacenter=rule.datacenter,
        location=rule.location,
        asset_type=rule.asset_type,
        is_internal=rule.is_internal,
        default_owner=rule.default_owner,
        default_team=rule.default_team,
        is_active=rule.is_active,
        created_at=rule.created_at,
        updated_at=rule.updated_at,
    )


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_classification_rule(
    rule_id: UUID,
    db: DbSession,
    user: AuthenticatedUser,
) -> None:
    """Delete a classification rule."""
    result = await db.execute(
        select(ClassificationRule).where(ClassificationRule.id == rule_id)
    )
    rule = result.scalar_one_or_none()

    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Classification rule {rule_id} not found",
        )

    await db.delete(rule)
    await db.flush()


@router.get("/environments/list", response_model=list[str])
async def list_environments(
    db: DbSession,
    user: AuthenticatedUser,
) -> list[str]:
    """List all unique environments from classification rules."""
    result = await db.execute(
        select(ClassificationRule.environment)
        .where(
            ClassificationRule.is_active == True,
            ClassificationRule.environment.isnot(None),
        )
        .distinct()
        .order_by(ClassificationRule.environment)
    )
    return [row[0] for row in result.fetchall()]


@router.get("/datacenters/list", response_model=list[str])
async def list_datacenters(
    db: DbSession,
    user: AuthenticatedUser,
) -> list[str]:
    """List all unique datacenters from classification rules."""
    result = await db.execute(
        select(ClassificationRule.datacenter)
        .where(
            ClassificationRule.is_active == True,
            ClassificationRule.datacenter.isnot(None),
        )
        .distinct()
        .order_by(ClassificationRule.datacenter)
    )
    return [row[0] for row in result.fetchall()]


@router.get("/locations/list", response_model=list[str])
async def list_locations(
    db: DbSession,
    user: AuthenticatedUser,
) -> list[str]:
    """List all unique locations from classification rules."""
    result = await db.execute(
        select(ClassificationRule.location)
        .where(
            ClassificationRule.is_active == True,
            ClassificationRule.location.isnot(None),
        )
        .distinct()
        .order_by(ClassificationRule.location)
    )
    return [row[0] for row in result.fetchall()]

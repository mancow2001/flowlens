"""Alert Rules API endpoints for configurable alert generation."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select

from flowlens.api.dependencies import AdminUser, AnalystUser, DbSession, Pagination
from flowlens.models.alert_rule import AlertRule
from flowlens.models.change import ChangeType
from flowlens.schemas.alert_rule import (
    AlertRuleCreate,
    AlertRuleList,
    AlertRuleResponse,
    AlertRuleSummary,
    AlertRuleTestRequest,
    AlertRuleTestResult,
    AlertRuleUpdate,
    ChangeTypeInfo,
)

router = APIRouter(prefix="/alert-rules", tags=["alert-rules"])


@router.get("", response_model=AlertRuleList)
async def list_alert_rules(
    db: DbSession,
    _user: AnalystUser,
    pagination: Pagination,
    is_active: bool | None = Query(None, alias="isActive"),
    severity: str | None = None,
    change_type: str | None = Query(None, alias="changeType"),
) -> AlertRuleList:
    """List alert rules with filtering and pagination."""
    query = select(AlertRule)

    if is_active is not None:
        query = query.where(AlertRule.is_active == is_active)
    if severity:
        query = query.where(AlertRule.severity == severity)
    if change_type:
        # Check if change_type is in the array
        query = query.where(AlertRule.change_types.any(change_type))

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query) or 0

    # Order by priority, then name
    query = query.order_by(AlertRule.priority.asc(), AlertRule.name.asc())

    # Apply pagination
    query = query.offset(pagination.offset).limit(pagination.page_size)

    result = await db.execute(query)
    rules = result.scalars().all()

    items = [
        AlertRuleSummary(
            id=r.id,
            name=r.name,
            is_active=r.is_active,
            change_types=r.change_types,
            severity=r.severity.value if hasattr(r.severity, 'value') else r.severity,
            cooldown_minutes=r.cooldown_minutes,
            priority=r.priority,
            trigger_count=r.trigger_count,
            last_triggered_at=r.last_triggered_at,
        )
        for r in rules
    ]

    return AlertRuleList(
        items=items,
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
    )


@router.get("/change-types", response_model=list[ChangeTypeInfo])
async def list_change_types(
    _user: AnalystUser,
) -> list[ChangeTypeInfo]:
    """List all available change types for rule configuration."""
    change_type_info = {
        # Dependency changes
        "dependency_created": ("Dependency Created", "dependency"),
        "dependency_removed": ("Dependency Removed", "dependency"),
        "dependency_stale": ("Dependency Stale", "dependency"),
        "dependency_traffic_spike": ("Traffic Spike", "dependency"),
        "dependency_traffic_drop": ("Traffic Drop", "dependency"),
        # Asset changes
        "asset_discovered": ("Asset Discovered", "asset"),
        "asset_removed": ("Asset Removed", "asset"),
        "asset_offline": ("Asset Offline", "asset"),
        "asset_online": ("Asset Online", "asset"),
        # Service changes
        "service_discovered": ("Service Discovered", "service"),
        "service_removed": ("Service Removed", "service"),
        # Topology changes
        "new_external_connection": ("New External Connection", "topology"),
        "critical_path_change": ("Critical Path Change", "topology"),
    }

    return [
        ChangeTypeInfo(
            value=ct.value,
            label=change_type_info.get(ct.value, (ct.value.replace("_", " ").title(), "other"))[0],
            category=change_type_info.get(ct.value, (ct.value, "other"))[1],
        )
        for ct in ChangeType
    ]


@router.get("/{rule_id}", response_model=AlertRuleResponse)
async def get_alert_rule(
    rule_id: UUID,
    db: DbSession,
    _user: AnalystUser,
) -> AlertRuleResponse:
    """Get alert rule by ID."""
    result = await db.execute(
        select(AlertRule).where(AlertRule.id == rule_id)
    )
    rule = result.scalar_one_or_none()

    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Alert rule {rule_id} not found",
        )

    return AlertRuleResponse(
        id=rule.id,
        name=rule.name,
        description=rule.description,
        is_active=rule.is_active,
        change_types=rule.change_types,
        asset_filter=rule.asset_filter,
        severity=rule.severity.value if hasattr(rule.severity, 'value') else rule.severity,
        title_template=rule.title_template,
        description_template=rule.description_template,
        notify_channels=rule.notify_channels,
        cooldown_minutes=rule.cooldown_minutes,
        priority=rule.priority,
        schedule=rule.schedule,
        tags=rule.tags,
        last_triggered_at=rule.last_triggered_at,
        trigger_count=rule.trigger_count,
        created_at=rule.created_at,
        updated_at=rule.updated_at,
    )


@router.post("", response_model=AlertRuleResponse, status_code=status.HTTP_201_CREATED)
async def create_alert_rule(
    data: AlertRuleCreate,
    db: DbSession,
    _user: AnalystUser,
) -> AlertRuleResponse:
    """Create a new alert rule."""
    # Check for duplicate name
    existing = await db.execute(
        select(AlertRule).where(AlertRule.name == data.name)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Alert rule with name '{data.name}' already exists",
        )

    # Validate change types
    valid_types = {ct.value for ct in ChangeType}
    invalid_types = set(data.change_types) - valid_types
    if invalid_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid change types: {', '.join(invalid_types)}",
        )

    rule = AlertRule(
        name=data.name,
        description=data.description,
        is_active=data.is_active,
        change_types=data.change_types,
        asset_filter=data.asset_filter,
        severity=data.severity,
        title_template=data.title_template,
        description_template=data.description_template,
        notify_channels=data.notify_channels,
        cooldown_minutes=data.cooldown_minutes,
        priority=data.priority,
        schedule=data.schedule,
        tags=data.tags,
    )

    db.add(rule)
    await db.flush()
    await db.refresh(rule)

    return AlertRuleResponse(
        id=rule.id,
        name=rule.name,
        description=rule.description,
        is_active=rule.is_active,
        change_types=rule.change_types,
        asset_filter=rule.asset_filter,
        severity=rule.severity.value if hasattr(rule.severity, 'value') else rule.severity,
        title_template=rule.title_template,
        description_template=rule.description_template,
        notify_channels=rule.notify_channels,
        cooldown_minutes=rule.cooldown_minutes,
        priority=rule.priority,
        schedule=rule.schedule,
        tags=rule.tags,
        last_triggered_at=rule.last_triggered_at,
        trigger_count=rule.trigger_count,
        created_at=rule.created_at,
        updated_at=rule.updated_at,
    )


@router.patch("/{rule_id}", response_model=AlertRuleResponse)
async def update_alert_rule(
    rule_id: UUID,
    data: AlertRuleUpdate,
    db: DbSession,
    _user: AnalystUser,
) -> AlertRuleResponse:
    """Update an alert rule."""
    result = await db.execute(
        select(AlertRule).where(AlertRule.id == rule_id)
    )
    rule = result.scalar_one_or_none()

    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Alert rule {rule_id} not found",
        )

    # Check for duplicate name if name is being changed
    if data.name and data.name != rule.name:
        existing = await db.execute(
            select(AlertRule).where(AlertRule.name == data.name)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Alert rule with name '{data.name}' already exists",
            )

    # Validate change types if provided
    if data.change_types:
        valid_types = {ct.value for ct in ChangeType}
        invalid_types = set(data.change_types) - valid_types
        if invalid_types:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid change types: {', '.join(invalid_types)}",
            )

    # Update fields
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(rule, field, value)

    await db.flush()
    await db.refresh(rule)

    return AlertRuleResponse(
        id=rule.id,
        name=rule.name,
        description=rule.description,
        is_active=rule.is_active,
        change_types=rule.change_types,
        asset_filter=rule.asset_filter,
        severity=rule.severity.value if hasattr(rule.severity, 'value') else rule.severity,
        title_template=rule.title_template,
        description_template=rule.description_template,
        notify_channels=rule.notify_channels,
        cooldown_minutes=rule.cooldown_minutes,
        priority=rule.priority,
        schedule=rule.schedule,
        tags=rule.tags,
        last_triggered_at=rule.last_triggered_at,
        trigger_count=rule.trigger_count,
        created_at=rule.created_at,
        updated_at=rule.updated_at,
    )


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_alert_rule(
    rule_id: UUID,
    db: DbSession,
    _user: AdminUser,
) -> None:
    """Delete an alert rule."""
    result = await db.execute(
        select(AlertRule).where(AlertRule.id == rule_id)
    )
    rule = result.scalar_one_or_none()

    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Alert rule {rule_id} not found",
        )

    await db.delete(rule)
    await db.flush()


@router.post("/{rule_id}/test", response_model=AlertRuleTestResult)
async def test_alert_rule(
    rule_id: UUID,
    request: AlertRuleTestRequest,
    db: DbSession,
    _user: AnalystUser,
) -> AlertRuleTestResult:
    """Test an alert rule against a sample change event.

    This endpoint allows testing whether a rule would trigger
    for a given change type and asset data.
    """
    result = await db.execute(
        select(AlertRule).where(AlertRule.id == rule_id)
    )
    rule = result.scalar_one_or_none()

    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Alert rule {rule_id} not found",
        )

    # Check if rule is active
    if not rule.is_active:
        return AlertRuleTestResult(
            would_trigger=False,
            reason="Rule is not active",
        )

    # Check if change type matches
    if not rule.matches_change_type(request.change_type):
        return AlertRuleTestResult(
            would_trigger=False,
            reason=f"Change type '{request.change_type}' does not match rule's change types: {rule.change_types}",
        )

    # Check asset filter
    if request.asset_data and not rule.matches_asset_filter(request.asset_data):
        return AlertRuleTestResult(
            would_trigger=False,
            reason=f"Asset data does not match rule's filter: {rule.asset_filter}",
        )

    # Check cooldown
    if rule.is_on_cooldown():
        return AlertRuleTestResult(
            would_trigger=False,
            reason=f"Rule is on cooldown (last triggered at {rule.last_triggered_at})",
        )

    # Build context for template rendering
    context = {
        "change_type": request.change_type.replace("_", " ").title(),
        "summary": f"Test {request.change_type} event",
        "asset_name": request.asset_data.get("name", "Unknown") if request.asset_data else "Unknown",
        "asset_ip": request.asset_data.get("ip_address", "") if request.asset_data else "",
    }

    return AlertRuleTestResult(
        would_trigger=True,
        reason="Rule would trigger for this event",
        rendered_title=rule.render_title(context),
        rendered_description=rule.render_description(context),
    )


@router.post("/{rule_id}/toggle", response_model=AlertRuleResponse)
async def toggle_alert_rule(
    rule_id: UUID,
    db: DbSession,
    _user: AnalystUser,
) -> AlertRuleResponse:
    """Toggle an alert rule's active status."""
    result = await db.execute(
        select(AlertRule).where(AlertRule.id == rule_id)
    )
    rule = result.scalar_one_or_none()

    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Alert rule {rule_id} not found",
        )

    rule.is_active = not rule.is_active
    await db.flush()
    await db.refresh(rule)

    return AlertRuleResponse(
        id=rule.id,
        name=rule.name,
        description=rule.description,
        is_active=rule.is_active,
        change_types=rule.change_types,
        asset_filter=rule.asset_filter,
        severity=rule.severity.value if hasattr(rule.severity, 'value') else rule.severity,
        title_template=rule.title_template,
        description_template=rule.description_template,
        notify_channels=rule.notify_channels,
        cooldown_minutes=rule.cooldown_minutes,
        priority=rule.priority,
        schedule=rule.schedule,
        tags=rule.tags,
        last_triggered_at=rule.last_triggered_at,
        trigger_count=rule.trigger_count,
        created_at=rule.created_at,
        updated_at=rule.updated_at,
    )

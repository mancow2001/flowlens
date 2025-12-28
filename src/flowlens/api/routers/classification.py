"""Classification Rules API endpoints."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import String, cast, func, select, text

from flowlens.api.dependencies import AuthenticatedUser, DbSession, Pagination
from flowlens.common.logging import get_logger
from flowlens.models.asset import Asset
from flowlens.models.classification import ClassificationRule
from flowlens.models.task import TaskType
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
from flowlens.tasks.executor import TaskExecutor, run_task_in_background, run_classification_task_with_new_session

logger = get_logger(__name__)

router = APIRouter(prefix="/classification-rules", tags=["classification"])


async def _trigger_classification_task(
    db: DbSession,
    rule_id: UUID,
    rule_name: str,
    action: str,
) -> UUID | None:
    """Trigger a background task to apply classification rules.

    Args:
        db: Database session.
        rule_id: The rule that was changed.
        rule_name: Name of the rule.
        action: What happened (created, updated).

    Returns:
        Task ID if created, None if skipped.
    """
    try:
        executor = TaskExecutor(db)

        # Create the task
        task = await executor.create_task(
            task_type=TaskType.APPLY_CLASSIFICATION_RULES.value,
            name=f"Apply Classification Rules ({action}: {rule_name})",
            description=f"Automatically triggered after rule '{rule_name}' was {action}",
            parameters={"rule_id": str(rule_id), "force": False},
            triggered_by="rule_change",
            related_entity_type="classification_rule",
            related_entity_id=rule_id,
        )

        await db.commit()

        # Run task in background with its own session
        run_task_in_background(
            task.id,
            run_classification_task_with_new_session(task.id, force=False, rule_id=rule_id),
        )

        logger.info(
            "Auto-triggered classification task",
            task_id=str(task.id),
            rule_id=str(rule_id),
            action=action,
        )

        return task.id

    except Exception as e:
        logger.error(
            "Failed to trigger classification task",
            rule_id=str(rule_id),
            error=str(e),
        )
        return None


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
        text("SELECT * FROM get_ip_classification(CAST(:ip_addr AS inet))"),
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
        text("SELECT * FROM get_all_ip_classifications(CAST(:ip_addr AS inet))"),
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
    auto_apply: bool = Query(True, alias="autoApply", description="Automatically apply rule to matching assets"),
) -> ClassificationRuleResponse:
    """Create a new classification rule.

    By default, automatically triggers a background task to apply
    the new rule to matching assets. Set autoApply=false to skip.
    """
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

    # Auto-trigger classification task if rule is active
    if auto_apply and rule.is_active:
        await _trigger_classification_task(db, rule.id, rule.name, "created")

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
    auto_apply: bool = Query(True, alias="autoApply", description="Automatically apply rule to matching assets"),
) -> ClassificationRuleResponse:
    """Update a classification rule.

    By default, automatically triggers a background task to apply
    the updated rule to matching assets. Set autoApply=false to skip.
    """
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

    # Auto-trigger classification task if rule is active
    if auto_apply and rule.is_active:
        await _trigger_classification_task(db, rule.id, rule.name, "updated")

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


# =============================================================================
# Apply Classification Rules to Assets
# =============================================================================


class ApplyRulesResult(BaseModel):
    """Result of applying classification rules to assets."""

    total_assets: int
    matched: int
    updated: int
    skipped: int
    details: list[dict] | None = None


@router.post("/apply", response_model=ApplyRulesResult)
async def apply_classification_rules(
    db: DbSession,
    user: AuthenticatedUser,
    dry_run: bool = Query(False, alias="dryRun", description="Preview changes without applying"),
    force: bool = Query(False, description="Update even if asset has manually set values"),
) -> ApplyRulesResult:
    """Apply all active classification rules to matching assets.

    This endpoint matches assets against CIDR classification rules and updates
    their is_internal, environment, datacenter, location, owner, and team fields.

    By default, only updates assets that don't already have these fields set
    (to avoid overwriting manual configurations). Use force=true to override.

    Use dryRun=true to preview what would be changed without making updates.
    """
    # Get all active assets
    assets_result = await db.execute(
        select(Asset).where(Asset.deleted_at.is_(None))
    )
    assets = assets_result.scalars().all()

    total_assets = len(assets)
    matched = 0
    updated = 0
    skipped = 0
    details = []

    for asset in assets:
        ip_address = str(asset.ip_address)

        # Get classification for this IP
        class_result = await db.execute(
            text("SELECT * FROM get_ip_classification(CAST(:ip_addr AS inet))"),
            {"ip_addr": ip_address},
        )
        row = class_result.fetchone()

        if not row or row.rule_id is None:
            # No matching rule
            continue

        matched += 1

        # Determine what needs to be updated
        changes = {}

        # is_internal - always apply from rules if specified
        if row.is_internal is not None and (force or asset.is_internal != row.is_internal):
            changes["is_internal"] = {"old": asset.is_internal, "new": row.is_internal}

        # environment - only update if force or currently empty
        if row.environment and (force or not asset.environment):
            if asset.environment != row.environment:
                changes["environment"] = {"old": asset.environment, "new": row.environment}

        # datacenter - only update if force or currently empty
        if row.datacenter and (force or not asset.datacenter):
            if asset.datacenter != row.datacenter:
                changes["datacenter"] = {"old": asset.datacenter, "new": row.datacenter}

        # location (maps to city field on asset)
        if row.location and (force or not asset.city):
            if asset.city != row.location:
                changes["city"] = {"old": asset.city, "new": row.location}

        # owner - only update if force or currently empty
        if row.default_owner and (force or not asset.owner):
            if asset.owner != row.default_owner:
                changes["owner"] = {"old": asset.owner, "new": row.default_owner}

        # team - only update if force or currently empty
        if row.default_team and (force or not asset.team):
            if asset.team != row.default_team:
                changes["team"] = {"old": asset.team, "new": row.default_team}

        if not changes:
            skipped += 1
            continue

        # Apply changes (unless dry run)
        if not dry_run:
            if "is_internal" in changes:
                asset.is_internal = changes["is_internal"]["new"]
            if "environment" in changes:
                asset.environment = changes["environment"]["new"]
            if "datacenter" in changes:
                asset.datacenter = changes["datacenter"]["new"]
            if "city" in changes:
                asset.city = changes["city"]["new"]
            if "owner" in changes:
                asset.owner = changes["owner"]["new"]
            if "team" in changes:
                asset.team = changes["team"]["new"]

        updated += 1

        # Track details for first 100 updates
        if len(details) < 100:
            details.append({
                "asset_id": str(asset.id),
                "asset_name": asset.name,
                "ip_address": ip_address,
                "rule_name": row.rule_name,
                "changes": changes,
            })

    if not dry_run:
        await db.flush()
        logger.info(
            "Applied classification rules",
            total_assets=total_assets,
            matched=matched,
            updated=updated,
            skipped=skipped,
        )

    return ApplyRulesResult(
        total_assets=total_assets,
        matched=matched,
        updated=updated,
        skipped=skipped,
        details=details if details else None,
    )

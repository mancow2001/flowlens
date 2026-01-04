"""Classification Rules API endpoints."""

import csv
import io
import ipaddress
import json
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, UploadFile, File, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import String, cast, func, select, text

from flowlens.api.dependencies import AdminUser, AnalystUser, DbSession, Pagination, ViewerUser
from flowlens.common.logging import get_logger
from flowlens.models.asset import Asset
from flowlens.models.classification import ClassificationRule
from flowlens.models.task import TaskType
from flowlens.schemas.classification import (
    ClassificationRuleCreate,
    ClassificationRuleExportRow,
    ClassificationRuleImportPreview,
    ClassificationRuleImportResult,
    ClassificationRuleImportValidation,
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


def _parse_is_internal(value: str | None) -> bool | None:
    """Parse is_internal value from import data.

    Handles three states:
    - True (Internal): "true", "1", "yes", "internal"
    - False (External): "false", "0", "no", "external"
    - None (Not Specified): "", None, "null", "none", or missing

    Args:
        value: The string value from import file.

    Returns:
        True, False, or None based on the input value.
    """
    if value is None or value == "":
        return None

    lower_val = str(value).lower().strip()

    if lower_val in ("true", "1", "yes", "internal"):
        return True
    elif lower_val in ("false", "0", "no", "external"):
        return False
    elif lower_val in ("null", "none", "not specified", ""):
        return None

    # Default to None for unrecognized values
    return None


def _export_is_internal(value: bool | None) -> str:
    """Convert is_internal value for export.

    Args:
        value: The boolean or None value.

    Returns:
        "true", "false", or "" (empty string for Not Specified).
    """
    if value is True:
        return "true"
    elif value is False:
        return "false"
    else:
        return ""


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
    # When a rule is updated, we want to force-apply the new values
    # to all assets matching that rule, since the user explicitly changed it.
    # For new rules, we don't force (only fill empty fields).
    force = action == "updated"

    try:
        executor = TaskExecutor(db)

        # Create the task
        task = await executor.create_task(
            task_type=TaskType.APPLY_CLASSIFICATION_RULES.value,
            name=f"Apply Classification Rules ({action}: {rule_name})",
            description=f"Automatically triggered after rule '{rule_name}' was {action}",
            parameters={"rule_id": str(rule_id), "force": force},
            triggered_by="rule_change",
            related_entity_type="classification_rule",
            related_entity_id=rule_id,
        )

        await db.commit()

        # Run task in background with its own session
        run_task_in_background(
            task.id,
            run_classification_task_with_new_session(task.id, force=force, rule_id=rule_id),
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
    _user: AnalystUser,
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


# =============================================================================
# Export/Import Endpoints (must be before /{rule_id} routes)
# =============================================================================


@router.get("/export", response_class=StreamingResponse)
async def export_classification_rules(
    db: DbSession,
    _user: ViewerUser,
    format: Literal["csv", "json"] = Query("json"),
    is_active: bool | None = Query(None, alias="isActive"),
    environment: str | None = None,
    datacenter: str | None = None,
) -> StreamingResponse:
    """Export classification rules to CSV or JSON format.

    Exported data can be modified and re-imported to update or create rules.
    """
    # Build query with optional filters
    query = select(ClassificationRule)

    if is_active is not None:
        query = query.where(ClassificationRule.is_active == is_active)
    if environment:
        query = query.where(ClassificationRule.environment == environment)
    if datacenter:
        query = query.where(ClassificationRule.datacenter == datacenter)

    # Order by priority then name for consistent exports
    query = query.order_by(ClassificationRule.priority.asc(), ClassificationRule.name.asc())

    result = await db.execute(query)
    rules = result.scalars().all()

    # Build export rows
    rows = []
    for r in rules:
        rows.append(ClassificationRuleExportRow(
            name=r.name,
            description=r.description,
            cidr=str(r.cidr),
            priority=r.priority,
            environment=r.environment,
            datacenter=r.datacenter,
            location=r.location,
            asset_type=r.asset_type,
            is_internal=r.is_internal,
            default_owner=r.default_owner,
            default_team=r.default_team,
            is_active=r.is_active,
        ))

    if format == "json":
        content = json.dumps([r.model_dump() for r in rows], indent=2)
        return StreamingResponse(
            iter([content]),
            media_type="application/json",
            headers={"Content-Disposition": "attachment; filename=classification-rules-export.json"},
        )
    else:
        # CSV export
        output = io.StringIO()
        fieldnames = [
            "name", "description", "cidr", "priority", "environment", "datacenter",
            "location", "asset_type", "is_internal", "default_owner", "default_team", "is_active"
        ]
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            row_dict = row.model_dump()
            # Convert is_internal to proper export format (empty string for None/Not Specified)
            row_dict["is_internal"] = _export_is_internal(row_dict["is_internal"])
            # Convert is_active to lowercase for consistency with import
            row_dict["is_active"] = "true" if row_dict["is_active"] else "false"
            writer.writerow(row_dict)

        output.seek(0)
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=classification-rules-export.csv"},
        )


@router.post("/import/preview", response_model=ClassificationRuleImportPreview)
async def preview_classification_rule_import(
    db: DbSession,
    _user: AnalystUser,
    file: UploadFile = File(...),
) -> ClassificationRuleImportPreview:
    """Preview what a classification rule import will do before committing.

    Accepts CSV or JSON file. Matches rules by name.
    Returns a preview of creates, updates, and any errors.
    """
    content = await file.read()
    content_str = content.decode("utf-8")

    # Parse file based on content type or extension
    rows: list[dict] = []
    filename = file.filename or ""

    if filename.endswith(".json") or file.content_type == "application/json":
        try:
            rows = json.loads(content_str)
            if not isinstance(rows, list):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="JSON file must contain an array of objects",
                )
        except json.JSONDecodeError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid JSON: {e}",
            )
    else:
        # Assume CSV
        try:
            reader = csv.DictReader(io.StringIO(content_str))
            rows = list(reader)
        except csv.Error as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid CSV: {e}",
            )

    if not rows:
        return ClassificationRuleImportPreview(
            total_rows=0,
            to_create=0,
            to_update=0,
            to_skip=0,
            errors=0,
            validations=[],
        )

    # Get existing rules by name for comparison
    names = [r.get("name", "") for r in rows if r.get("name")]
    existing_query = select(ClassificationRule).where(ClassificationRule.name.in_(names))
    existing_result = await db.execute(existing_query)
    existing_rules = {r.name: r for r in existing_result.scalars().all()}

    # Validate each row
    validations = []
    to_create = 0
    to_update = 0
    to_skip = 0
    errors = 0

    for idx, row in enumerate(rows, start=1):
        name = row.get("name", "").strip() if row.get("name") else ""

        if not name:
            validations.append(ClassificationRuleImportValidation(
                row_number=idx,
                name="",
                status="error",
                message="Missing name",
            ))
            errors += 1
            continue

        # Validate CIDR
        cidr = row.get("cidr", "").strip() if row.get("cidr") else ""
        if not cidr:
            validations.append(ClassificationRuleImportValidation(
                row_number=idx,
                name=name,
                status="error",
                message="Missing CIDR",
            ))
            errors += 1
            continue

        try:
            ipaddress.ip_network(cidr, strict=False)
        except ValueError as e:
            validations.append(ClassificationRuleImportValidation(
                row_number=idx,
                name=name,
                status="error",
                message=f"Invalid CIDR: {e}",
            ))
            errors += 1
            continue

        existing = existing_rules.get(name)

        if existing:
            # Check for changes
            changes = {}
            for field in ["description", "cidr", "environment", "datacenter", "location",
                         "asset_type", "default_owner", "default_team"]:
                new_val = row.get(field, "").strip() if row.get(field) else None
                old_val = getattr(existing, field)
                if field == "cidr":
                    old_val = str(old_val) if old_val else None
                if new_val and new_val != old_val:
                    changes[field] = {"old": old_val, "new": new_val}

            # Handle priority (int)
            if "priority" in row and row["priority"] != "":
                try:
                    new_priority = int(row["priority"])
                    if new_priority != existing.priority:
                        changes["priority"] = {"old": existing.priority, "new": new_priority}
                except ValueError:
                    validations.append(ClassificationRuleImportValidation(
                        row_number=idx,
                        name=name,
                        status="error",
                        message=f"Invalid priority value: {row['priority']}",
                    ))
                    errors += 1
                    continue

            # Handle is_internal (bool or None)
            if "is_internal" in row and row["is_internal"] != "":
                new_internal = _parse_is_internal(row["is_internal"])
                if new_internal != existing.is_internal:
                    changes["is_internal"] = {"old": existing.is_internal, "new": new_internal}

            # Handle is_active (bool)
            if "is_active" in row and row["is_active"] != "":
                new_active = str(row["is_active"]).lower() in ("true", "1", "yes")
                if new_active != existing.is_active:
                    changes["is_active"] = {"old": existing.is_active, "new": new_active}

            if changes:
                validations.append(ClassificationRuleImportValidation(
                    row_number=idx,
                    name=name,
                    status="update",
                    message=f"Will update {len(changes)} field(s)",
                    changes=changes,
                ))
                to_update += 1
            else:
                validations.append(ClassificationRuleImportValidation(
                    row_number=idx,
                    name=name,
                    status="skip",
                    message="No changes detected",
                ))
                to_skip += 1
        else:
            # New rule
            validations.append(ClassificationRuleImportValidation(
                row_number=idx,
                name=name,
                status="create",
                message=f"Will create new rule: {name}",
            ))
            to_create += 1

    return ClassificationRuleImportPreview(
        total_rows=len(rows),
        to_create=to_create,
        to_update=to_update,
        to_skip=to_skip,
        errors=errors,
        validations=validations,
    )


@router.post("/import", response_model=ClassificationRuleImportResult)
async def import_classification_rules(
    db: DbSession,
    _user: AnalystUser,
    file: UploadFile = File(...),
    skip_errors: bool = Query(False, alias="skipErrors"),
    auto_apply: bool = Query(True, alias="autoApply", description="Automatically apply rules to matching assets after import"),
) -> ClassificationRuleImportResult:
    """Import classification rules from CSV or JSON file.

    Matches rules by name. Updates existing rules or creates new ones.
    Blank values in the import file are ignored (won't overwrite existing data).
    """
    content = await file.read()
    content_str = content.decode("utf-8")

    # Parse file
    rows: list[dict] = []
    filename = file.filename or ""

    if filename.endswith(".json") or file.content_type == "application/json":
        try:
            rows = json.loads(content_str)
        except json.JSONDecodeError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid JSON: {e}",
            )
    else:
        try:
            reader = csv.DictReader(io.StringIO(content_str))
            rows = list(reader)
        except csv.Error as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid CSV: {e}",
            )

    if not rows:
        return ClassificationRuleImportResult(
            created=0,
            updated=0,
            skipped=0,
            errors=0,
        )

    # Get existing rules
    names = [r.get("name", "") for r in rows if r.get("name")]
    existing_query = select(ClassificationRule).where(ClassificationRule.name.in_(names))
    existing_result = await db.execute(existing_query)
    existing_rules = {r.name: r for r in existing_result.scalars().all()}

    created = 0
    updated = 0
    skipped = 0
    errors = 0
    error_details = []
    created_rule_ids = []
    updated_rule_ids = []

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

        # Validate CIDR
        cidr = row.get("cidr", "").strip() if row.get("cidr") else ""
        if not cidr:
            if skip_errors:
                errors += 1
                error_details.append(f"Row {idx}: Missing CIDR")
                continue
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Row {idx}: Missing CIDR",
            )

        try:
            ipaddress.ip_network(cidr, strict=False)
        except ValueError as e:
            if skip_errors:
                errors += 1
                error_details.append(f"Row {idx}: Invalid CIDR: {e}")
                continue
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Row {idx}: Invalid CIDR: {e}",
            )

        existing = existing_rules.get(name)

        if existing:
            # Update existing rule
            has_changes = False
            for field in ["description", "cidr", "environment", "datacenter", "location",
                         "asset_type", "default_owner", "default_team"]:
                new_val = row.get(field, "").strip() if row.get(field) else None
                if new_val:  # Only update if value provided
                    current_val = getattr(existing, field)
                    if field == "cidr":
                        current_val = str(current_val) if current_val else None
                    if new_val != current_val:
                        setattr(existing, field, new_val)
                        has_changes = True

            # Handle priority
            if "priority" in row and row["priority"] != "":
                try:
                    new_priority = int(row["priority"])
                    if new_priority != existing.priority:
                        existing.priority = new_priority
                        has_changes = True
                except ValueError:
                    if skip_errors:
                        errors += 1
                        error_details.append(f"Row {idx}: Invalid priority: {row['priority']}")
                        continue
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Row {idx}: Invalid priority: {row['priority']}",
                    )

            # Handle is_internal (bool or None)
            if "is_internal" in row and row["is_internal"] != "":
                new_internal = _parse_is_internal(row["is_internal"])
                if new_internal != existing.is_internal:
                    existing.is_internal = new_internal
                    has_changes = True

            # Handle is_active
            if "is_active" in row and row["is_active"] != "":
                new_active = str(row["is_active"]).lower() in ("true", "1", "yes")
                if new_active != existing.is_active:
                    existing.is_active = new_active
                    has_changes = True

            if has_changes:
                updated += 1
                updated_rule_ids.append(existing.id)
            else:
                skipped += 1
        else:
            # Create new rule
            priority = 100
            if "priority" in row and row["priority"] != "":
                try:
                    priority = int(row["priority"])
                except ValueError:
                    priority = 100

            # Parse is_internal using the helper (handles True, False, or None)
            is_internal = _parse_is_internal(row.get("is_internal"))

            is_active = True
            if "is_active" in row and row["is_active"] != "":
                is_active = str(row["is_active"]).lower() in ("true", "1", "yes")

            new_rule = ClassificationRule(
                name=name,
                description=row.get("description", "").strip() if row.get("description") else None,
                cidr=cidr,
                priority=priority,
                environment=row.get("environment", "").strip() if row.get("environment") else None,
                datacenter=row.get("datacenter", "").strip() if row.get("datacenter") else None,
                location=row.get("location", "").strip() if row.get("location") else None,
                asset_type=row.get("asset_type", "").strip() if row.get("asset_type") else None,
                is_internal=is_internal,
                default_owner=row.get("default_owner", "").strip() if row.get("default_owner") else None,
                default_team=row.get("default_team", "").strip() if row.get("default_team") else None,
                is_active=is_active,
            )
            db.add(new_rule)
            await db.flush()
            created += 1
            created_rule_ids.append(new_rule.id)

    await db.flush()

    # Trigger classification task if auto_apply and we made changes
    if auto_apply and (created_rule_ids or updated_rule_ids):
        try:
            executor = TaskExecutor(db)
            task = await executor.create_task(
                task_type=TaskType.APPLY_CLASSIFICATION_RULES.value,
                name="Apply Classification Rules (bulk import)",
                description=f"Automatically triggered after importing {created} new and {updated} updated rules",
                parameters={"force": updated > 0},  # Force update if we updated existing rules
                triggered_by="import",
                related_entity_type="classification_rule",
            )
            await db.commit()

            run_task_in_background(
                task.id,
                run_classification_task_with_new_session(task.id, force=updated > 0, rule_id=None),
            )

            logger.info(
                "Auto-triggered classification task after import",
                task_id=str(task.id),
                created=created,
                updated=updated,
            )
        except Exception as e:
            logger.error("Failed to trigger classification task after import", error=str(e))

    return ClassificationRuleImportResult(
        created=created,
        updated=updated,
        skipped=skipped,
        errors=errors,
        error_details=error_details if error_details else None,
    )


@router.get("/classify/{ip_address}", response_model=IPClassificationResult)
async def classify_ip(
    ip_address: str,
    db: DbSession,
    _user: AnalystUser,
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
    _user: AnalystUser,
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
    _user: AnalystUser,
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
    _user: AnalystUser,
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
    _user: AnalystUser,
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
    _user: AdminUser,
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
    _user: AnalystUser,
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
    _user: AnalystUser,
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
    _user: AnalystUser,
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
    _user: AnalystUser,
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

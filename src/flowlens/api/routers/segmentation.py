"""Segmentation Policy API endpoints."""

import csv
import io
import json
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from flowlens.api.dependencies import AdminUser, AnalystUser, DbSession, Pagination, ViewerUser
from flowlens.common.logging import get_logger
from flowlens.models.asset import Application
from flowlens.models.segmentation import (
    PolicyStance,
    PolicyStatus,
    SegmentationPolicy,
    SegmentationPolicyRule,
    SegmentationPolicyVersion,
)
from flowlens.schemas.segmentation import (
    FirewallRuleExport,
    PolicyApprovalResponse,
    PolicyComparisonResponse,
    PolicyCreate,
    PolicyExportFormat,
    PolicyGenerateRequest,
    PolicyList,
    PolicyResponse,
    PolicyRuleCreate,
    PolicyRuleResponse,
    PolicyRuleUpdate,
    PolicySummary,
    PolicyUpdate,
    PolicyVersionResponse,
    PolicyWithRules,
    PublishVersionRequest,
    RuleDiff,
)
from flowlens.services.policy_generator import PolicyGenerator, compare_rules

logger = get_logger(__name__)

router = APIRouter(prefix="/segmentation-policies", tags=["segmentation"])


# =============================================================================
# Policy CRUD Endpoints
# =============================================================================


@router.get("", response_model=PolicyList)
async def list_policies(
    db: DbSession,
    _user: ViewerUser,
    pagination: Pagination,
    application_id: UUID | None = Query(None, alias="applicationId"),
    status_filter: str | None = Query(None, alias="status"),
    stance: str | None = Query(None),
    is_active: bool | None = Query(None, alias="isActive"),
) -> PolicyList:
    """List segmentation policies with filtering."""
    query = select(SegmentationPolicy)

    # Apply filters
    if application_id:
        query = query.where(SegmentationPolicy.application_id == application_id)
    if status_filter:
        query = query.where(SegmentationPolicy.status == status_filter)
    if stance:
        query = query.where(SegmentationPolicy.stance == stance)
    if is_active is not None:
        query = query.where(SegmentationPolicy.is_active == is_active)

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    count_result = await db.execute(count_query)
    total = count_result.scalar() or 0

    # Apply pagination and ordering
    query = query.order_by(SegmentationPolicy.created_at.desc())
    query = query.offset(pagination.offset).limit(pagination.limit)

    result = await db.execute(query)
    policies = result.scalars().all()

    return PolicyList(
        items=[PolicySummary.model_validate(p) for p in policies],
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
    )


@router.post("", response_model=PolicyResponse, status_code=status.HTTP_201_CREATED)
async def create_policy(
    data: PolicyCreate,
    db: DbSession,
    _user: AnalystUser,
) -> PolicyResponse:
    """Create a new segmentation policy."""
    # Verify application exists
    app_query = select(Application).where(Application.id == data.application_id)
    app_result = await db.execute(app_query)
    application = app_result.scalar_one_or_none()

    if not application:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Application {data.application_id} not found",
        )

    policy = SegmentationPolicy(
        application_id=data.application_id,
        name=data.name,
        description=data.description,
        stance=data.stance,
        status=PolicyStatus.DRAFT.value,
    )

    db.add(policy)
    await db.commit()
    await db.refresh(policy)

    return PolicyResponse.model_validate(policy)


@router.get("/{policy_id}", response_model=PolicyWithRules)
async def get_policy(
    policy_id: UUID,
    db: DbSession,
    _user: ViewerUser,
) -> PolicyWithRules:
    """Get policy with all rules."""
    query = (
        select(SegmentationPolicy)
        .where(SegmentationPolicy.id == policy_id)
        .options(selectinload(SegmentationPolicy.rules))
    )
    result = await db.execute(query)
    policy = result.scalar_one_or_none()

    if not policy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Policy {policy_id} not found",
        )

    return PolicyWithRules.model_validate(policy)


@router.patch("/{policy_id}", response_model=PolicyResponse)
async def update_policy(
    policy_id: UUID,
    data: PolicyUpdate,
    db: DbSession,
    _user: AnalystUser,
) -> PolicyResponse:
    """Update a policy."""
    query = select(SegmentationPolicy).where(SegmentationPolicy.id == policy_id)
    result = await db.execute(query)
    policy = result.scalar_one_or_none()

    if not policy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Policy {policy_id} not found",
        )

    # Update fields
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(policy, field, value)

    await db.commit()
    await db.refresh(policy)

    return PolicyResponse.model_validate(policy)


@router.delete("/{policy_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_policy(
    policy_id: UUID,
    db: DbSession,
    _user: AdminUser,
) -> None:
    """Delete a policy."""
    query = select(SegmentationPolicy).where(SegmentationPolicy.id == policy_id)
    result = await db.execute(query)
    policy = result.scalar_one_or_none()

    if not policy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Policy {policy_id} not found",
        )

    await db.delete(policy)
    await db.commit()


# =============================================================================
# Policy Generation
# =============================================================================


@router.post("/generate", response_model=PolicyWithRules, status_code=status.HTTP_201_CREATED)
async def generate_policy_from_topology(
    data: PolicyGenerateRequest,
    db: DbSession,
    _user: AnalystUser,
) -> PolicyWithRules:
    """Generate a new policy from application topology.

    Analyzes the application's entry points, internal dependencies,
    and downstream connections to create comprehensive segmentation rules.
    """
    generator = PolicyGenerator(db)

    try:
        policy = await generator.generate_policy(
            application_id=data.application_id,
            stance=PolicyStance(data.stance),
            include_external_inbound=data.include_external_inbound,
            include_internal_communication=data.include_internal_communication,
            include_downstream_dependencies=data.include_downstream_dependencies,
            max_downstream_depth=data.max_downstream_depth,
            min_bytes_threshold=data.min_bytes_threshold,
            generated_by=_user.email,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )

    await db.commit()

    # Reload with rules
    query = (
        select(SegmentationPolicy)
        .where(SegmentationPolicy.id == policy.id)
        .options(selectinload(SegmentationPolicy.rules))
    )
    result = await db.execute(query)
    policy = result.scalar_one()

    return PolicyWithRules.model_validate(policy)


@router.post("/{policy_id}/regenerate", response_model=PolicyWithRules)
async def regenerate_policy(
    policy_id: UUID,
    db: DbSession,
    _user: AnalystUser,
) -> PolicyWithRules:
    """Regenerate rules for an existing policy from current topology.

    Deletes existing auto-generated rules and creates new ones.
    Manual rules are preserved.
    """
    generator = PolicyGenerator(db)

    try:
        policy = await generator.regenerate_policy(
            policy_id=policy_id,
            generated_by=_user.email,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )

    await db.commit()

    # Reload with rules
    query = (
        select(SegmentationPolicy)
        .where(SegmentationPolicy.id == policy.id)
        .options(selectinload(SegmentationPolicy.rules))
    )
    result = await db.execute(query)
    policy = result.scalar_one()

    return PolicyWithRules.model_validate(policy)


# =============================================================================
# Rule CRUD Endpoints
# =============================================================================


@router.post("/{policy_id}/rules", response_model=PolicyRuleResponse, status_code=status.HTTP_201_CREATED)
async def add_rule(
    policy_id: UUID,
    data: PolicyRuleCreate,
    db: DbSession,
    _user: AnalystUser,
) -> PolicyRuleResponse:
    """Add a rule to a policy."""
    # Verify policy exists
    policy_query = select(SegmentationPolicy).where(SegmentationPolicy.id == policy_id)
    policy_result = await db.execute(policy_query)
    policy = policy_result.scalar_one_or_none()

    if not policy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Policy {policy_id} not found",
        )

    # Get max order
    max_order_query = select(func.max(SegmentationPolicyRule.rule_order)).where(
        SegmentationPolicyRule.policy_id == policy_id
    )
    max_order_result = await db.execute(max_order_query)
    max_order = max_order_result.scalar() or 0

    rule = SegmentationPolicyRule(
        policy_id=policy_id,
        rule_order=max_order + 1,
        is_auto_generated=False,  # Manual rules
        **data.model_dump(),
    )

    db.add(rule)

    # Update policy rule counts
    policy.rule_count += 1
    if rule.rule_type == "inbound":
        policy.inbound_rule_count += 1
    elif rule.rule_type == "outbound":
        policy.outbound_rule_count += 1
    elif rule.rule_type == "internal":
        policy.internal_rule_count += 1

    await db.commit()
    await db.refresh(rule)

    return PolicyRuleResponse.model_validate(rule)


@router.patch("/{policy_id}/rules/{rule_id}", response_model=PolicyRuleResponse)
async def update_rule(
    policy_id: UUID,
    rule_id: UUID,
    data: PolicyRuleUpdate,
    db: DbSession,
    _user: AnalystUser,
) -> PolicyRuleResponse:
    """Update a rule."""
    query = select(SegmentationPolicyRule).where(
        SegmentationPolicyRule.id == rule_id,
        SegmentationPolicyRule.policy_id == policy_id,
    )
    result = await db.execute(query)
    rule = result.scalar_one_or_none()

    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Rule {rule_id} not found in policy {policy_id}",
        )

    # Update fields
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(rule, field, value)

    await db.commit()
    await db.refresh(rule)

    return PolicyRuleResponse.model_validate(rule)


@router.delete("/{policy_id}/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rule(
    policy_id: UUID,
    rule_id: UUID,
    db: DbSession,
    _user: AnalystUser,
) -> None:
    """Delete a rule."""
    query = select(SegmentationPolicyRule).where(
        SegmentationPolicyRule.id == rule_id,
        SegmentationPolicyRule.policy_id == policy_id,
    )
    result = await db.execute(query)
    rule = result.scalar_one_or_none()

    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Rule {rule_id} not found in policy {policy_id}",
        )

    # Update policy rule counts
    policy_query = select(SegmentationPolicy).where(SegmentationPolicy.id == policy_id)
    policy_result = await db.execute(policy_query)
    policy = policy_result.scalar_one()

    policy.rule_count -= 1
    if rule.rule_type == "inbound":
        policy.inbound_rule_count -= 1
    elif rule.rule_type == "outbound":
        policy.outbound_rule_count -= 1
    elif rule.rule_type == "internal":
        policy.internal_rule_count -= 1

    await db.delete(rule)
    await db.commit()


# =============================================================================
# Version Management
# =============================================================================


@router.post("/{policy_id}/publish", response_model=PolicyVersionResponse)
async def publish_policy_version(
    policy_id: UUID,
    db: DbSession,
    _user: AnalystUser,
    data: PublishVersionRequest | None = None,
) -> PolicyVersionResponse:
    """Publish current policy state as a new version."""
    # Load policy with rules
    query = (
        select(SegmentationPolicy)
        .where(SegmentationPolicy.id == policy_id)
        .options(selectinload(SegmentationPolicy.rules))
    )
    result = await db.execute(query)
    policy = result.scalar_one_or_none()

    if not policy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Policy {policy_id} not found",
        )

    # Get previous version for diff calculation
    prev_version_query = (
        select(SegmentationPolicyVersion)
        .where(SegmentationPolicyVersion.policy_id == policy_id)
        .order_by(SegmentationPolicyVersion.version_number.desc())
        .limit(1)
    )
    prev_version_result = await db.execute(prev_version_query)
    prev_version = prev_version_result.scalar_one_or_none()

    # Create rules snapshot
    rules_snapshot = [rule.to_dict() for rule in policy.rules]

    # Calculate diff if there's a previous version
    rules_added = 0
    rules_removed = 0
    rules_modified = 0

    if prev_version:
        comparison = compare_rules(prev_version.rules_snapshot, rules_snapshot)
        rules_added = comparison["summary"]["rules_added"]
        rules_removed = comparison["summary"]["rules_removed"]
        rules_modified = comparison["summary"]["rules_modified"]

    # Create new version
    version = SegmentationPolicyVersion(
        policy_id=policy_id,
        version_number=policy.version,
        version_label=data.version_label if data else None,
        stance=policy.stance,
        status=policy.status,
        rules_snapshot=rules_snapshot,
        rules_added=rules_added,
        rules_removed=rules_removed,
        rules_modified=rules_modified,
        created_by=_user.email,
        change_reason=data.change_reason if data else None,
    )

    db.add(version)

    # Increment policy version
    policy.version += 1

    await db.commit()
    await db.refresh(version)

    return PolicyVersionResponse.model_validate(version)


@router.get("/{policy_id}/versions", response_model=list[PolicyVersionResponse])
async def list_versions(
    policy_id: UUID,
    db: DbSession,
    _user: ViewerUser,
) -> list[PolicyVersionResponse]:
    """List all versions of a policy."""
    # Verify policy exists
    policy_query = select(SegmentationPolicy).where(SegmentationPolicy.id == policy_id)
    policy_result = await db.execute(policy_query)
    policy = policy_result.scalar_one_or_none()

    if not policy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Policy {policy_id} not found",
        )

    query = (
        select(SegmentationPolicyVersion)
        .where(SegmentationPolicyVersion.policy_id == policy_id)
        .order_by(SegmentationPolicyVersion.version_number.desc())
    )
    result = await db.execute(query)
    versions = result.scalars().all()

    return [PolicyVersionResponse.model_validate(v) for v in versions]


@router.get("/{policy_id}/versions/{version_number}", response_model=PolicyVersionResponse)
async def get_version(
    policy_id: UUID,
    version_number: int,
    db: DbSession,
    _user: ViewerUser,
) -> PolicyVersionResponse:
    """Get a specific version."""
    query = select(SegmentationPolicyVersion).where(
        SegmentationPolicyVersion.policy_id == policy_id,
        SegmentationPolicyVersion.version_number == version_number,
    )
    result = await db.execute(query)
    version = result.scalar_one_or_none()

    if not version:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Version {version_number} not found for policy {policy_id}",
        )

    return PolicyVersionResponse.model_validate(version)


# =============================================================================
# Comparison Endpoints
# =============================================================================


@router.get("/{policy_id}/compare", response_model=PolicyComparisonResponse)
async def compare_versions(
    policy_id: UUID,
    db: DbSession,
    _user: ViewerUser,
    version_a: int = Query(..., alias="versionA"),
    version_b: int = Query(..., alias="versionB"),
) -> PolicyComparisonResponse:
    """Compare two versions of a policy."""
    # Get both versions
    query_a = select(SegmentationPolicyVersion).where(
        SegmentationPolicyVersion.policy_id == policy_id,
        SegmentationPolicyVersion.version_number == version_a,
    )
    query_b = select(SegmentationPolicyVersion).where(
        SegmentationPolicyVersion.policy_id == policy_id,
        SegmentationPolicyVersion.version_number == version_b,
    )

    result_a = await db.execute(query_a)
    result_b = await db.execute(query_b)

    ver_a = result_a.scalar_one_or_none()
    ver_b = result_b.scalar_one_or_none()

    if not ver_a:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Version {version_a} not found",
        )
    if not ver_b:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Version {version_b} not found",
        )

    # Compare rules
    comparison = compare_rules(ver_a.rules_snapshot, ver_b.rules_snapshot)

    return PolicyComparisonResponse(
        policy_id=policy_id,
        version_a=version_a,
        version_b=version_b,
        stance_changed=ver_a.stance != ver_b.stance,
        rules_added=[RuleDiff(**r) for r in comparison["added"]],
        rules_removed=[RuleDiff(**r) for r in comparison["removed"]],
        rules_modified=[RuleDiff(**r) for r in comparison["modified"]],
        rules_unchanged=[RuleDiff(**r) for r in comparison["unchanged"]],
        summary=f"Version {version_a} -> {version_b}: {comparison['summary']['rules_added']} added, {comparison['summary']['rules_removed']} removed, {comparison['summary']['rules_modified']} modified",
    )


# =============================================================================
# Export Endpoints
# =============================================================================


@router.get("/{policy_id}/export")
async def export_policy(
    policy_id: UUID,
    db: DbSession,
    _user: ViewerUser,
    format: Literal["json", "csv"] = "json",
) -> StreamingResponse:
    """Export policy to generic firewall rule format."""
    # Load policy with rules and application
    query = (
        select(SegmentationPolicy)
        .where(SegmentationPolicy.id == policy_id)
        .options(
            selectinload(SegmentationPolicy.rules),
            selectinload(SegmentationPolicy.application),
        )
    )
    result = await db.execute(query)
    policy = result.scalar_one_or_none()

    if not policy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Policy {policy_id} not found",
        )

    # Convert rules to export format
    export_rules = []
    for rule in policy.rules:
        # Format port
        if rule.port is None:
            port_str = "any"
        elif rule.port_range_end and rule.port_range_end != rule.port:
            port_str = f"{rule.port}-{rule.port_range_end}"
        else:
            port_str = str(rule.port)

        # Format protocol
        protocol_str = "tcp" if rule.protocol == 6 else "udp" if rule.protocol == 17 else "any"

        export_rules.append(FirewallRuleExport(
            rule_id=str(rule.id),
            priority=rule.priority,
            action=rule.action,
            source_cidr=rule.source_cidr or "any",
            dest_cidr=rule.dest_cidr or "any",
            port=port_str,
            protocol=protocol_str,
            description=rule.description or "",
            application_name=policy.application.name,
            rule_type=rule.rule_type,
            is_enabled=rule.is_enabled,
        ))

    if format == "json":
        export_data = PolicyExportFormat(
            policy_name=policy.name,
            application_name=policy.application.name,
            stance=policy.stance,
            version=policy.version,
            exported_at=datetime.now(timezone.utc),
            rule_count=len(export_rules),
            rules=export_rules,
        )

        content = json.dumps(export_data.model_dump(), indent=2, default=str)
        return StreamingResponse(
            io.StringIO(content),
            media_type="application/json",
            headers={
                "Content-Disposition": f'attachment; filename="{policy.name.replace(" ", "_")}_policy.json"'
            },
        )
    else:
        # CSV export
        output = io.StringIO()
        writer = csv.writer(output)

        # Header
        writer.writerow([
            "rule_id", "priority", "action", "source_cidr", "dest_cidr",
            "port", "protocol", "description", "application_name",
            "rule_type", "is_enabled"
        ])

        # Rows
        for rule in export_rules:
            writer.writerow([
                rule.rule_id, rule.priority, rule.action, rule.source_cidr,
                rule.dest_cidr, rule.port, rule.protocol, rule.description,
                rule.application_name, rule.rule_type, rule.is_enabled
            ])

        output.seek(0)
        return StreamingResponse(
            output,
            media_type="text/csv",
            headers={
                "Content-Disposition": f'attachment; filename="{policy.name.replace(" ", "_")}_policy.csv"'
            },
        )


# =============================================================================
# Workflow Endpoints
# =============================================================================


@router.post("/{policy_id}/submit-for-review", response_model=PolicyResponse)
async def submit_for_review(
    policy_id: UUID,
    db: DbSession,
    _user: AnalystUser,
) -> PolicyResponse:
    """Submit policy for approval review."""
    query = select(SegmentationPolicy).where(SegmentationPolicy.id == policy_id)
    result = await db.execute(query)
    policy = result.scalar_one_or_none()

    if not policy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Policy {policy_id} not found",
        )

    if policy.status != PolicyStatus.DRAFT.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Policy must be in draft status to submit for review (current: {policy.status})",
        )

    policy.status = PolicyStatus.PENDING_REVIEW.value

    await db.commit()
    await db.refresh(policy)

    return PolicyResponse.model_validate(policy)


@router.post("/{policy_id}/approve", response_model=PolicyApprovalResponse)
async def approve_policy(
    policy_id: UUID,
    db: DbSession,
    _user: AdminUser,
) -> PolicyApprovalResponse:
    """Approve a policy."""
    query = select(SegmentationPolicy).where(SegmentationPolicy.id == policy_id)
    result = await db.execute(query)
    policy = result.scalar_one_or_none()

    if not policy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Policy {policy_id} not found",
        )

    if policy.status != PolicyStatus.PENDING_REVIEW.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Policy must be pending review to approve (current: {policy.status})",
        )

    policy.status = PolicyStatus.APPROVED.value
    policy.approved_by = _user.email
    policy.approved_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(policy)

    return PolicyApprovalResponse(
        policy_id=policy.id,
        status=policy.status,
        approved_by=policy.approved_by,
        approved_at=policy.approved_at,
        message="Policy approved successfully",
    )


@router.post("/{policy_id}/activate", response_model=PolicyResponse)
async def activate_policy(
    policy_id: UUID,
    db: DbSession,
    _user: AdminUser,
) -> PolicyResponse:
    """Activate a policy (deactivates any other active policy for the app)."""
    query = select(SegmentationPolicy).where(SegmentationPolicy.id == policy_id)
    result = await db.execute(query)
    policy = result.scalar_one_or_none()

    if not policy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Policy {policy_id} not found",
        )

    if policy.status not in (PolicyStatus.APPROVED.value, PolicyStatus.ACTIVE.value):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Policy must be approved to activate (current: {policy.status})",
        )

    # Deactivate any other active policies for this application
    deactivate_query = (
        select(SegmentationPolicy)
        .where(
            SegmentationPolicy.application_id == policy.application_id,
            SegmentationPolicy.is_active == True,
            SegmentationPolicy.id != policy_id,
        )
    )
    deactivate_result = await db.execute(deactivate_query)
    for other_policy in deactivate_result.scalars().all():
        other_policy.is_active = False
        other_policy.status = PolicyStatus.ARCHIVED.value

    # Activate this policy
    policy.is_active = True
    policy.status = PolicyStatus.ACTIVE.value

    await db.commit()
    await db.refresh(policy)

    return PolicyResponse.model_validate(policy)


@router.post("/{policy_id}/archive", response_model=PolicyResponse)
async def archive_policy(
    policy_id: UUID,
    db: DbSession,
    _user: AdminUser,
) -> PolicyResponse:
    """Archive a policy."""
    query = select(SegmentationPolicy).where(SegmentationPolicy.id == policy_id)
    result = await db.execute(query)
    policy = result.scalar_one_or_none()

    if not policy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Policy {policy_id} not found",
        )

    policy.status = PolicyStatus.ARCHIVED.value
    policy.is_active = False

    await db.commit()
    await db.refresh(policy)

    return PolicyResponse.model_validate(policy)

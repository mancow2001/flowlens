"""Policy generation service for micro-segmentation.

Generates segmentation policies from application topology by analyzing
entry points, internal dependencies, and downstream connections.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from flowlens.models.asset import Application, ApplicationMember, Asset, EntryPoint
from flowlens.models.dependency import Dependency
from flowlens.models.segmentation import (
    PolicyStance,
    PolicyStatus,
    RuleAction,
    RuleType,
    SegmentationPolicy,
    SegmentationPolicyRule,
    SegmentationPolicyVersion,
)
from flowlens.enrichment.resolvers.protocol import ProtocolResolver


@dataclass
class RuleSpec:
    """Specification for a generated rule."""

    rule_type: str
    source_type: str
    source_asset_id: UUID | None
    source_cidr: str | None
    source_label: str | None
    dest_type: str
    dest_asset_id: UUID | None
    dest_cidr: str | None
    dest_label: str | None
    port: int | None
    protocol: int
    service_label: str | None
    action: str
    description: str
    generated_from_dependency_id: UUID | None = None
    generated_from_entry_point_id: UUID | None = None
    bytes_observed: int | None = None
    last_seen_at: datetime | None = None


class PolicyGenerator:
    """Generates segmentation policies from application topology.

    Analyzes an application's entry points, internal member-to-member
    dependencies, and downstream external dependencies to create
    comprehensive segmentation rules.
    """

    def __init__(self, db: AsyncSession):
        """Initialize policy generator.

        Args:
            db: Async database session.
        """
        self.db = db
        self._protocol_resolver = ProtocolResolver()

    async def generate_policy(
        self,
        application_id: UUID,
        stance: PolicyStance = PolicyStance.ALLOW_LIST,
        include_external_inbound: bool = True,
        include_internal_communication: bool = True,
        include_downstream_dependencies: bool = True,
        max_downstream_depth: int = 3,
        min_bytes_threshold: int = 0,
        generated_by: str | None = None,
    ) -> SegmentationPolicy:
        """Generate a complete segmentation policy for an application.

        Args:
            application_id: The application to generate policy for.
            stance: Policy stance (allow_list or deny_list).
            include_external_inbound: Include rules for external -> entry point.
            include_internal_communication: Include rules for app member -> app member.
            include_downstream_dependencies: Include rules for app -> downstream deps.
            max_downstream_depth: How many hops to include for downstream.
            min_bytes_threshold: Minimum bytes observed to include a rule.
            generated_by: User who triggered generation.

        Returns:
            Generated SegmentationPolicy with rules.

        Raises:
            ValueError: If application not found.
        """
        # Load application with members and entry points
        app = await self._load_application(application_id)
        if not app:
            raise ValueError(f"Application {application_id} not found")

        rules: list[RuleSpec] = []

        # 1. Generate inbound rules (external -> entry points)
        if include_external_inbound:
            inbound_rules = await self._generate_inbound_rules(app, min_bytes_threshold)
            rules.extend(inbound_rules)

        # 2. Generate internal communication rules
        if include_internal_communication:
            internal_rules = await self._generate_internal_rules(app, min_bytes_threshold)
            rules.extend(internal_rules)

        # 3. Generate downstream dependency rules
        if include_downstream_dependencies:
            downstream_rules = await self._generate_downstream_rules(
                app, max_downstream_depth, min_bytes_threshold
            )
            rules.extend(downstream_rules)

        # Create policy
        policy = SegmentationPolicy(
            application_id=application_id,
            name=f"{app.display_name or app.name} Segmentation Policy",
            description=f"Auto-generated policy for {app.display_name or app.name}",
            stance=stance.value,
            status=PolicyStatus.DRAFT.value,
            generated_from_topology_at=datetime.now(timezone.utc),
            generated_by=generated_by,
            rule_count=len(rules),
            inbound_rule_count=sum(1 for r in rules if r.rule_type == RuleType.INBOUND.value),
            outbound_rule_count=sum(1 for r in rules if r.rule_type == RuleType.OUTBOUND.value),
            internal_rule_count=sum(1 for r in rules if r.rule_type == RuleType.INTERNAL.value),
        )

        self.db.add(policy)
        await self.db.flush()

        # Create rules
        for order, spec in enumerate(rules):
            rule = SegmentationPolicyRule(
                policy_id=policy.id,
                rule_order=order,
                rule_type=spec.rule_type,
                source_type=spec.source_type,
                source_asset_id=spec.source_asset_id,
                source_cidr=spec.source_cidr,
                source_label=spec.source_label,
                dest_type=spec.dest_type,
                dest_asset_id=spec.dest_asset_id,
                dest_cidr=spec.dest_cidr,
                dest_label=spec.dest_label,
                port=spec.port,
                protocol=spec.protocol,
                service_label=spec.service_label,
                action=spec.action,
                description=spec.description,
                generated_from_dependency_id=spec.generated_from_dependency_id,
                generated_from_entry_point_id=spec.generated_from_entry_point_id,
                bytes_observed=spec.bytes_observed,
                last_seen_at=spec.last_seen_at,
            )
            self.db.add(rule)

        await self.db.flush()

        # Reload with relationships
        await self.db.refresh(policy, attribute_names=["rules"])
        return policy

    async def _load_application(self, app_id: UUID) -> Application | None:
        """Load application with members and entry points."""
        query = (
            select(Application)
            .where(Application.id == app_id)
            .options(
                selectinload(Application.members).selectinload(ApplicationMember.asset),
                selectinload(Application.members).selectinload(ApplicationMember.entry_points),
            )
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def _generate_inbound_rules(
        self, app: Application, min_bytes: int
    ) -> list[RuleSpec]:
        """Generate rules for external traffic to entry points.

        Creates an allow rule for each defined entry point port/protocol
        combination.

        Args:
            app: Application with loaded members and entry points.
            min_bytes: Minimum bytes threshold (not used for entry points).

        Returns:
            List of inbound rule specifications.
        """
        rules = []

        for member in app.members:
            if not member.entry_points:
                continue

            asset = member.asset
            for ep in member.entry_points:
                # Get service name for the port
                service_info = self._protocol_resolver.resolve(ep.port, ep.protocol)
                service_label = ep.label or (service_info.name if service_info else None)

                rules.append(RuleSpec(
                    rule_type=RuleType.INBOUND.value,
                    source_type="any",
                    source_asset_id=None,
                    source_cidr="0.0.0.0/0",  # Any external
                    source_label="External Clients",
                    dest_type="app_member",
                    dest_asset_id=member.asset_id,
                    dest_cidr=f"{asset.ip_address}/32" if asset.ip_address else None,
                    dest_label=asset.display_name or asset.name,
                    port=ep.port,
                    protocol=ep.protocol,
                    service_label=service_label,
                    action=RuleAction.ALLOW.value,
                    description=f"Allow external access to {service_label or f'port {ep.port}'} on {asset.name}",
                    generated_from_entry_point_id=ep.id,
                ))

        return rules

    async def _generate_internal_rules(
        self, app: Application, min_bytes: int
    ) -> list[RuleSpec]:
        """Generate rules for communication between app members.

        Creates allow rules for each observed dependency between
        application members.

        Args:
            app: Application with loaded members.
            min_bytes: Minimum bytes observed to include a rule.

        Returns:
            List of internal rule specifications.
        """
        rules = []
        member_asset_ids = {m.asset_id for m in app.members}
        member_map = {m.asset_id: m for m in app.members}

        if len(member_asset_ids) < 2:
            return rules

        # Query dependencies between app members
        deps_query = (
            select(Dependency)
            .where(
                Dependency.source_asset_id.in_(member_asset_ids),
                Dependency.target_asset_id.in_(member_asset_ids),
                Dependency.valid_to.is_(None),
                Dependency.bytes_total >= min_bytes,
            )
        )
        result = await self.db.execute(deps_query)

        for dep in result.scalars().all():
            source_member = member_map.get(dep.source_asset_id)
            target_member = member_map.get(dep.target_asset_id)

            if not source_member or not target_member:
                continue

            source_asset = source_member.asset
            target_asset = target_member.asset

            # Get service name for the port
            service_info = self._protocol_resolver.resolve(dep.target_port, dep.protocol)
            service_label = dep.dependency_type or (service_info.name if service_info else None)

            rules.append(RuleSpec(
                rule_type=RuleType.INTERNAL.value,
                source_type="app_member",
                source_asset_id=dep.source_asset_id,
                source_cidr=f"{source_asset.ip_address}/32" if source_asset.ip_address else None,
                source_label=source_asset.display_name or source_asset.name,
                dest_type="app_member",
                dest_asset_id=dep.target_asset_id,
                dest_cidr=f"{target_asset.ip_address}/32" if target_asset.ip_address else None,
                dest_label=target_asset.display_name or target_asset.name,
                port=dep.target_port,
                protocol=dep.protocol,
                service_label=service_label,
                action=RuleAction.ALLOW.value,
                description=f"Internal: {source_asset.name} -> {target_asset.name}:{dep.target_port}",
                generated_from_dependency_id=dep.id,
                bytes_observed=dep.bytes_total,
                last_seen_at=dep.last_seen,
            ))

        return rules

    async def _generate_downstream_rules(
        self, app: Application, max_depth: int, min_bytes: int
    ) -> list[RuleSpec]:
        """Generate rules for app members connecting to external dependencies.

        Creates allow rules for each outbound dependency from an
        application member to an asset outside the application.

        Args:
            app: Application with loaded members.
            max_depth: Maximum downstream depth (for future multi-hop support).
            min_bytes: Minimum bytes observed to include a rule.

        Returns:
            List of outbound rule specifications.
        """
        rules = []
        member_asset_ids = {m.asset_id for m in app.members}
        member_map = {m.asset_id: m for m in app.members}

        if not member_asset_ids:
            return rules

        # Query outbound dependencies from app members to non-members
        deps_query = (
            select(Dependency)
            .where(
                Dependency.source_asset_id.in_(member_asset_ids),
                ~Dependency.target_asset_id.in_(member_asset_ids),
                Dependency.valid_to.is_(None),
                Dependency.bytes_total >= min_bytes,
            )
        )
        result = await self.db.execute(deps_query)
        dependencies = list(result.scalars().all())

        if not dependencies:
            return rules

        # Get target asset details
        target_ids = {d.target_asset_id for d in dependencies}
        assets_result = await self.db.execute(
            select(Asset).where(Asset.id.in_(target_ids))
        )
        target_assets = {a.id: a for a in assets_result.scalars().all()}

        for dep in dependencies:
            source_member = member_map.get(dep.source_asset_id)
            target_asset = target_assets.get(dep.target_asset_id)

            if not source_member or not target_asset:
                continue

            source_asset = source_member.asset

            # Get service name for the port
            service_info = self._protocol_resolver.resolve(dep.target_port, dep.protocol)
            service_label = dep.dependency_type or (service_info.name if service_info else None)

            rules.append(RuleSpec(
                rule_type=RuleType.OUTBOUND.value,
                source_type="app_member",
                source_asset_id=dep.source_asset_id,
                source_cidr=f"{source_asset.ip_address}/32" if source_asset.ip_address else None,
                source_label=source_asset.display_name or source_asset.name,
                dest_type="asset",
                dest_asset_id=dep.target_asset_id,
                dest_cidr=f"{target_asset.ip_address}/32" if target_asset.ip_address else None,
                dest_label=target_asset.display_name or target_asset.name,
                port=dep.target_port,
                protocol=dep.protocol,
                service_label=service_label,
                action=RuleAction.ALLOW.value,
                description=f"Outbound: {source_asset.name} -> {target_asset.name}:{dep.target_port}",
                generated_from_dependency_id=dep.id,
                bytes_observed=dep.bytes_total,
                last_seen_at=dep.last_seen,
            ))

        return rules

    async def regenerate_policy(
        self,
        policy_id: UUID,
        generated_by: str | None = None,
    ) -> SegmentationPolicy:
        """Regenerate rules for an existing policy.

        Deletes existing auto-generated rules and creates new ones
        based on current topology. Manual rules are preserved.

        Args:
            policy_id: Policy to regenerate.
            generated_by: User who triggered regeneration.

        Returns:
            Updated policy with new rules.

        Raises:
            ValueError: If policy not found.
        """
        # Load existing policy
        query = (
            select(SegmentationPolicy)
            .where(SegmentationPolicy.id == policy_id)
            .options(selectinload(SegmentationPolicy.rules))
        )
        result = await self.db.execute(query)
        policy = result.scalar_one_or_none()

        if not policy:
            raise ValueError(f"Policy {policy_id} not found")

        # Delete auto-generated rules (keep manual ones)
        for rule in list(policy.rules):
            if rule.is_auto_generated:
                await self.db.delete(rule)

        await self.db.flush()

        # Generate new rules
        app = await self._load_application(policy.application_id)
        if not app:
            raise ValueError(f"Application {policy.application_id} not found")

        stance = PolicyStance(policy.stance)
        rules: list[RuleSpec] = []

        # Generate all rule types
        rules.extend(await self._generate_inbound_rules(app, 0))
        rules.extend(await self._generate_internal_rules(app, 0))
        rules.extend(await self._generate_downstream_rules(app, 3, 0))

        # Get current max order for manual rules
        max_order = max((r.rule_order for r in policy.rules if not r.is_auto_generated), default=-1)

        # Create new rules
        for i, spec in enumerate(rules):
            rule = SegmentationPolicyRule(
                policy_id=policy.id,
                rule_order=max_order + 1 + i,
                rule_type=spec.rule_type,
                source_type=spec.source_type,
                source_asset_id=spec.source_asset_id,
                source_cidr=spec.source_cidr,
                source_label=spec.source_label,
                dest_type=spec.dest_type,
                dest_asset_id=spec.dest_asset_id,
                dest_cidr=spec.dest_cidr,
                dest_label=spec.dest_label,
                port=spec.port,
                protocol=spec.protocol,
                service_label=spec.service_label,
                action=spec.action,
                description=spec.description,
                generated_from_dependency_id=spec.generated_from_dependency_id,
                generated_from_entry_point_id=spec.generated_from_entry_point_id,
                bytes_observed=spec.bytes_observed,
                last_seen_at=spec.last_seen_at,
            )
            self.db.add(rule)

        # Update policy metadata
        policy.generated_from_topology_at = datetime.now(timezone.utc)
        policy.generated_by = generated_by
        policy.version += 1

        await self.db.flush()
        await self.db.refresh(policy, attribute_names=["rules"])

        # Update counts
        policy.update_rule_counts()

        return policy


def compare_rules(
    rules_a: list[dict[str, Any]],
    rules_b: list[dict[str, Any]],
) -> dict[str, Any]:
    """Compare two sets of rules and identify differences.

    Args:
        rules_a: First set of rules (e.g., current version).
        rules_b: Second set of rules (e.g., proposed or new version).

    Returns:
        Dictionary containing:
        - added: Rules in B but not in A
        - removed: Rules in A but not in B
        - modified: Rules that exist in both but have changes
        - unchanged: Rules that are identical
    """
    def rule_key(rule: dict) -> tuple:
        """Generate a unique key for rule comparison."""
        return (
            rule.get("rule_type"),
            rule.get("source_cidr"),
            rule.get("dest_cidr"),
            rule.get("port"),
            rule.get("protocol"),
            rule.get("action"),
        )

    def rules_equal(r1: dict, r2: dict) -> bool:
        """Check if two rules are semantically equal."""
        compare_fields = [
            "rule_type", "source_type", "source_cidr", "source_label",
            "dest_type", "dest_cidr", "dest_label", "port", "protocol",
            "service_label", "action", "description", "is_enabled",
        ]
        return all(r1.get(f) == r2.get(f) for f in compare_fields)

    # Index rules by key
    rules_a_by_key = {rule_key(r): r for r in rules_a}
    rules_b_by_key = {rule_key(r): r for r in rules_b}

    keys_a = set(rules_a_by_key.keys())
    keys_b = set(rules_b_by_key.keys())

    added = []
    removed = []
    modified = []
    unchanged = []

    # Rules only in B (added)
    for key in keys_b - keys_a:
        added.append({
            "rule_data": rules_b_by_key[key],
            "change_type": "added",
        })

    # Rules only in A (removed)
    for key in keys_a - keys_b:
        removed.append({
            "rule_data": rules_a_by_key[key],
            "change_type": "removed",
        })

    # Rules in both (check for modifications)
    for key in keys_a & keys_b:
        rule_a = rules_a_by_key[key]
        rule_b = rules_b_by_key[key]

        if rules_equal(rule_a, rule_b):
            unchanged.append({
                "rule_data": rule_a,
                "change_type": "unchanged",
            })
        else:
            # Find changed fields
            compare_fields = [
                "rule_type", "source_type", "source_cidr", "source_label",
                "dest_type", "dest_cidr", "dest_label", "port", "protocol",
                "service_label", "action", "description", "is_enabled",
            ]
            changed_fields = [
                f for f in compare_fields
                if rule_a.get(f) != rule_b.get(f)
            ]
            modified.append({
                "rule_data": rule_b,
                "previous_data": rule_a,
                "change_type": "modified",
                "changed_fields": changed_fields,
            })

    return {
        "added": added,
        "removed": removed,
        "modified": modified,
        "unchanged": unchanged,
        "summary": {
            "rules_added": len(added),
            "rules_removed": len(removed),
            "rules_modified": len(modified),
            "rules_unchanged": len(unchanged),
        },
    }

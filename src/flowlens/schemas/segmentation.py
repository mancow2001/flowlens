"""Pydantic schemas for segmentation policy API endpoints."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# =============================================================================
# Policy Rule Schemas
# =============================================================================


class PolicyRuleBase(BaseModel):
    """Base schema for policy rules."""

    rule_type: str = Field(..., pattern="^(inbound|outbound|internal)$")
    source_type: str = Field(..., description="Source type: 'any', 'app_member', 'cidr', 'asset'")
    source_asset_id: UUID | None = None
    source_cidr: str | None = None
    source_app_id: UUID | None = None
    source_label: str | None = None
    dest_type: str = Field(..., description="Destination type: 'app_member', 'cidr', 'asset'")
    dest_asset_id: UUID | None = None
    dest_cidr: str | None = None
    dest_app_id: UUID | None = None
    dest_label: str | None = None
    port: int | None = Field(None, ge=0, le=65535)
    port_range_end: int | None = Field(None, ge=0, le=65535)
    protocol: int = Field(6, ge=0, le=255, description="IP protocol: 6=TCP, 17=UDP")
    service_label: str | None = Field(None, max_length=50)
    action: str = Field("allow", pattern="^(allow|deny)$")
    description: str | None = None
    is_enabled: bool = True
    priority: int = Field(100, ge=0, le=10000)


class PolicyRuleCreate(PolicyRuleBase):
    """Schema for creating a rule."""

    pass


class PolicyRuleUpdate(BaseModel):
    """Schema for updating a rule."""

    priority: int | None = Field(None, ge=0, le=10000)
    is_enabled: bool | None = None
    description: str | None = None
    action: str | None = Field(None, pattern="^(allow|deny)$")
    source_label: str | None = None
    dest_label: str | None = None
    service_label: str | None = None


class PolicyRuleResponse(PolicyRuleBase):
    """Schema for rule response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    policy_id: UUID
    rule_order: int
    is_auto_generated: bool
    generated_from_dependency_id: UUID | None = None
    generated_from_entry_point_id: UUID | None = None
    bytes_observed: int | None = None
    last_seen_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class PolicyRuleSummary(BaseModel):
    """Minimal rule info for list views."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    rule_type: str
    source_label: str | None
    dest_label: str | None
    port: int | None
    protocol: int
    service_label: str | None
    action: str
    is_enabled: bool
    is_auto_generated: bool


# =============================================================================
# Policy Schemas
# =============================================================================


class PolicyBase(BaseModel):
    """Base schema for policies."""

    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    stance: str = Field("allow_list", pattern="^(allow_list|deny_list)$")


class PolicyCreate(PolicyBase):
    """Schema for creating a policy."""

    application_id: UUID


class PolicyUpdate(BaseModel):
    """Schema for updating a policy."""

    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    stance: str | None = Field(None, pattern="^(allow_list|deny_list)$")


class PolicyGenerateRequest(BaseModel):
    """Request to generate a policy from topology."""

    application_id: UUID
    stance: str = Field("allow_list", pattern="^(allow_list|deny_list)$")
    include_external_inbound: bool = True
    include_internal_communication: bool = True
    include_downstream_dependencies: bool = True
    max_downstream_depth: int = Field(3, ge=1, le=10)
    min_bytes_threshold: int = Field(0, ge=0)


class PolicyResponse(PolicyBase):
    """Schema for policy response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    application_id: UUID
    status: str
    version: int
    is_active: bool
    rule_count: int
    inbound_rule_count: int
    outbound_rule_count: int
    internal_rule_count: int
    generated_from_topology_at: datetime | None = None
    generated_by: str | None = None
    approved_by: str | None = None
    approved_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class PolicySummary(BaseModel):
    """Minimal policy info for list views."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    application_id: UUID
    name: str
    stance: str
    status: str
    version: int
    is_active: bool
    rule_count: int
    created_at: datetime


class PolicyWithRules(PolicyResponse):
    """Policy with full rule list."""

    rules: list[PolicyRuleResponse]


class PolicyList(BaseModel):
    """Paginated list of policies."""

    items: list[PolicySummary]
    total: int
    page: int
    page_size: int


# =============================================================================
# Version Schemas
# =============================================================================


class PolicyVersionResponse(BaseModel):
    """Schema for version response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    policy_id: UUID
    version_number: int
    version_label: str | None = None
    stance: str
    status: str
    rules_snapshot: list[dict[str, Any]]
    rules_added: int
    rules_removed: int
    rules_modified: int
    created_by: str | None = None
    change_reason: str | None = None
    approved_by: str | None = None
    approved_at: datetime | None = None
    created_at: datetime


class PublishVersionRequest(BaseModel):
    """Request to publish a new version."""

    version_label: str | None = Field(None, max_length=100)
    change_reason: str | None = None


# =============================================================================
# Comparison Schemas
# =============================================================================


class RuleDiff(BaseModel):
    """Difference for a single rule."""

    rule_id: UUID | None = None
    change_type: str  # 'added', 'removed', 'modified', 'unchanged'
    rule_data: dict[str, Any]
    previous_data: dict[str, Any] | None = None
    changed_fields: list[str] | None = None


class PolicyComparisonResponse(BaseModel):
    """Comparison between two policy states."""

    policy_id: UUID
    version_a: int | None = None
    version_b: int | None = None
    stance_changed: bool = False
    rules_added: list[RuleDiff]
    rules_removed: list[RuleDiff]
    rules_modified: list[RuleDiff]
    rules_unchanged: list[RuleDiff] | None = None
    summary: str


# =============================================================================
# Export Schemas
# =============================================================================


class FirewallRuleExport(BaseModel):
    """Generic firewall rule export format."""

    rule_id: str
    priority: int
    action: str
    source_cidr: str
    dest_cidr: str
    port: str  # "any" or "80" or "80-443"
    protocol: str  # "tcp", "udp", "any"
    description: str
    application_name: str
    rule_type: str
    is_enabled: bool


class PolicyExportFormat(BaseModel):
    """Complete policy export."""

    policy_name: str
    application_name: str
    stance: str
    version: int
    exported_at: datetime
    rule_count: int
    rules: list[FirewallRuleExport]


# =============================================================================
# Workflow Schemas
# =============================================================================


class PolicyStatusUpdate(BaseModel):
    """Request to update policy status."""

    status: str = Field(..., pattern="^(draft|pending_review|approved|active|archived)$")
    reason: str | None = None


class PolicyApprovalResponse(BaseModel):
    """Response after approval action."""

    policy_id: UUID
    status: str
    approved_by: str | None = None
    approved_at: datetime | None = None
    message: str

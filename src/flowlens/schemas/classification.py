"""Pydantic schemas for CIDR classification rules API endpoints."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator
import ipaddress

from flowlens.models.asset import Environment


class ClassificationRuleBase(BaseModel):
    """Base schema for classification rule data."""

    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    cidr: str = Field(..., description="CIDR notation (e.g., 10.0.0.0/8)")
    priority: int = Field(100, ge=0, le=1000, description="Lower priority wins for equal prefix lengths")
    environment: Environment | None = None
    datacenter: str | None = Field(None, max_length=100)
    location: str | None = Field(None, max_length=100)
    asset_type: str | None = Field(None, max_length=50)
    is_internal: bool | None = None
    default_owner: str | None = Field(None, max_length=255)
    default_team: str | None = Field(None, max_length=100)
    is_active: bool = True

    @field_validator("cidr")
    @classmethod
    def validate_cidr(cls, v: str) -> str:
        """Validate CIDR notation."""
        try:
            ipaddress.ip_network(v, strict=False)
        except ValueError as e:
            raise ValueError(f"Invalid CIDR notation: {e}")
        return v


class ClassificationRuleCreate(ClassificationRuleBase):
    """Schema for creating a classification rule."""

    pass


class ClassificationRuleUpdate(BaseModel):
    """Schema for updating a classification rule (all fields optional)."""

    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    cidr: str | None = None
    priority: int | None = Field(None, ge=0, le=1000)
    environment: Environment | None = None
    datacenter: str | None = Field(None, max_length=100)
    location: str | None = Field(None, max_length=100)
    asset_type: str | None = Field(None, max_length=50)
    is_internal: bool | None = None
    default_owner: str | None = Field(None, max_length=255)
    default_team: str | None = Field(None, max_length=100)
    is_active: bool | None = None

    @field_validator("cidr")
    @classmethod
    def validate_cidr(cls, v: str | None) -> str | None:
        """Validate CIDR notation if provided."""
        if v is None:
            return v
        try:
            ipaddress.ip_network(v, strict=False)
        except ValueError as e:
            raise ValueError(f"Invalid CIDR notation: {e}")
        return v


class ClassificationRuleResponse(BaseModel):
    """Schema for classification rule response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    description: str | None = None
    cidr: str
    priority: int
    environment: str | None = None
    datacenter: str | None = None
    location: str | None = None
    asset_type: str | None = None
    is_internal: bool | None = None
    default_owner: str | None = None
    default_team: str | None = None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    @field_validator("cidr", mode="before")
    @classmethod
    def convert_cidr_to_string(cls, v) -> str:
        """Convert CIDR type to string."""
        return str(v) if v else v


class ClassificationRuleSummary(BaseModel):
    """Minimal classification rule info for list views."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    cidr: str
    priority: int
    environment: str | None
    datacenter: str | None
    location: str | None
    is_active: bool

    @field_validator("cidr", mode="before")
    @classmethod
    def convert_cidr_to_string(cls, v) -> str:
        """Convert CIDR type to string."""
        return str(v) if v else v


class ClassificationRuleList(BaseModel):
    """Paginated list of classification rules."""

    items: list[ClassificationRuleSummary]
    total: int
    page: int
    page_size: int


class IPClassificationResult(BaseModel):
    """Result of classifying an IP address."""

    ip_address: str
    matched: bool
    rule_id: UUID | None = None
    rule_name: str | None = None
    environment: str | None = None
    datacenter: str | None = None
    location: str | None = None
    asset_type: str | None = None
    is_internal: bool | None = None
    default_owner: str | None = None
    default_team: str | None = None


class IPClassificationMatch(BaseModel):
    """A single matching rule for an IP (used in debug view)."""

    rule_id: UUID
    rule_name: str
    cidr: str
    prefix_length: int
    priority: int
    environment: str | None = None
    datacenter: str | None = None
    location: str | None = None
    is_winning: bool


class IPClassificationDebug(BaseModel):
    """Debug view showing all matching rules for an IP."""

    ip_address: str
    matches: list[IPClassificationMatch]
    winning_rule_id: UUID | None = None


# =============================================================================
# Import/Export Schemas
# =============================================================================


class ClassificationRuleExportRow(BaseModel):
    """Single row in classification rule export (CSV/JSON)."""

    name: str
    description: str | None = None
    cidr: str
    priority: int = 100
    environment: str | None = None
    datacenter: str | None = None
    location: str | None = None
    asset_type: str | None = None
    is_internal: bool | None = None
    default_owner: str | None = None
    default_team: str | None = None
    is_active: bool = True


class ClassificationRuleImportValidation(BaseModel):
    """Validation result for a single import row."""

    row_number: int
    name: str
    status: str  # "create", "update", "skip", "error"
    message: str | None = None
    changes: dict[str, dict[str, Any]] | None = None  # field -> {old, new}


class ClassificationRuleImportPreview(BaseModel):
    """Preview of what an import will do before committing."""

    total_rows: int
    to_create: int
    to_update: int
    to_skip: int
    errors: int
    validations: list[ClassificationRuleImportValidation]


class ClassificationRuleImportResult(BaseModel):
    """Result of committing a classification rule import."""

    created: int
    updated: int
    skipped: int
    errors: int
    error_details: list[str] | None = None

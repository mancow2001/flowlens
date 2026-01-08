"""Pydantic schemas for Application Layout API endpoints."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class NodePosition(BaseModel):
    """Position of a node on the canvas."""

    x: float
    y: float


class Viewport(BaseModel):
    """Viewport state (zoom and pan)."""

    scale: float = Field(0.85, ge=0.1, le=4.0)
    x: float = 30
    y: float = 30


class AssetGroupCreate(BaseModel):
    """Schema for creating an asset group."""

    name: str = Field(..., min_length=1, max_length=255)
    color: str = Field(default="#3b82f6", pattern=r"^#[0-9A-Fa-f]{6}$")
    asset_ids: list[UUID]
    position_x: float = 0
    position_y: float = 0


class AssetGroupUpdate(BaseModel):
    """Schema for updating an asset group (all fields optional)."""

    name: str | None = Field(None, min_length=1, max_length=255)
    color: str | None = Field(None, pattern=r"^#[0-9A-Fa-f]{6}$")
    asset_ids: list[UUID] | None = None
    position_x: float | None = None
    position_y: float | None = None
    width: float | None = None
    height: float | None = None
    is_collapsed: bool | None = None


class AssetGroupResponse(BaseModel):
    """Schema for asset group response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    layout_id: UUID
    name: str
    color: str
    asset_ids: list[UUID]
    position_x: float
    position_y: float
    width: float | None = None
    height: float | None = None
    is_collapsed: bool = False
    created_at: datetime
    updated_at: datetime


class LayoutPositionsUpdate(BaseModel):
    """Batch update of node positions."""

    positions: dict[str, NodePosition]


class LayoutUpdate(BaseModel):
    """Full layout update."""

    positions: dict[str, NodePosition] | None = None
    viewport: Viewport | None = None


class ApplicationLayoutResponse(BaseModel):
    """Schema for application layout response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID | None = None  # None when returning inherited groups without a real layout
    application_id: UUID
    hop_depth: int
    positions: dict[str, dict[str, float]] = {}  # {asset_id: {x, y}}
    viewport: dict | None = None  # {scale, x, y}
    modified_by: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    groups: list[AssetGroupResponse] = []

    @classmethod
    def from_model(cls, layout, groups: list | None = None):
        """Create response from model with groups."""
        return cls(
            id=layout.id,
            application_id=layout.application_id,
            hop_depth=layout.hop_depth,
            positions=layout.positions or {},
            viewport=layout.viewport,
            modified_by=layout.modified_by,
            created_at=layout.created_at,
            updated_at=layout.updated_at,
            groups=[AssetGroupResponse.model_validate(g) for g in (groups or layout.asset_groups)],
        )

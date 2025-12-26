"""Pydantic schemas for Saved View API endpoints."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class ViewFilters(BaseModel):
    """Topology filter settings for a saved view."""

    asset_types: list[str] | None = None
    environments: list[str] | None = None
    datacenters: list[str] | None = None
    include_external: bool = True
    min_bytes_24h: int = 0
    as_of: datetime | None = None  # For historical views


class ViewZoom(BaseModel):
    """Zoom and pan settings for a saved view."""

    scale: float = 1.0
    x: float = 0
    y: float = 0


class ViewConfig(BaseModel):
    """Complete configuration for a saved view."""

    filters: ViewFilters = Field(default_factory=ViewFilters)
    grouping: str = "none"  # none, location, environment, datacenter, type
    zoom: ViewZoom = Field(default_factory=ViewZoom)
    selected_asset_ids: list[UUID] = Field(default_factory=list)
    layout_positions: dict[str, dict[str, float]] = Field(default_factory=dict)


class SavedViewCreate(BaseModel):
    """Schema for creating a new saved view."""

    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    is_public: bool = False
    is_default: bool = False
    config: ViewConfig


class SavedViewUpdate(BaseModel):
    """Schema for updating an existing saved view."""

    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    is_public: bool | None = None
    is_default: bool | None = None
    config: ViewConfig | None = None


class SavedViewResponse(BaseModel):
    """Schema for saved view response."""

    id: UUID
    name: str
    description: str | None
    created_by: str | None
    is_public: bool
    is_default: bool
    config: dict[str, Any]
    last_accessed_at: datetime | None
    access_count: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class SavedViewSummary(BaseModel):
    """Summary of a saved view for list responses."""

    id: UUID
    name: str
    description: str | None
    is_public: bool
    is_default: bool
    access_count: int
    created_at: datetime

    class Config:
        from_attributes = True

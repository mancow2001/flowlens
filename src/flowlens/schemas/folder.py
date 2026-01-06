"""Pydantic schemas for Folder API endpoints and arc topology view."""

from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class EdgeDirection(str, Enum):
    """Direction of a dependency edge."""

    IN = "in"
    OUT = "out"
    BI = "bi"


class FolderBase(BaseModel):
    """Base schema for folder data."""

    name: str = Field(..., min_length=1, max_length=255)
    display_name: str | None = Field(None, max_length=255)
    description: str | None = None
    parent_id: UUID | None = None
    color: str | None = Field(None, pattern=r"^#[0-9A-Fa-f]{6}$")
    icon: str | None = Field(None, max_length=50)
    order: int = Field(0, ge=0)
    owner: str | None = Field(None, max_length=255)
    team: str | None = Field(None, max_length=100)
    tags: dict | None = None
    metadata: dict | None = None


class FolderCreate(FolderBase):
    """Schema for creating a folder."""

    pass


class FolderUpdate(BaseModel):
    """Schema for updating a folder (all fields optional)."""

    name: str | None = Field(None, min_length=1, max_length=255)
    display_name: str | None = Field(None, max_length=255)
    description: str | None = None
    color: str | None = Field(None, pattern=r"^#[0-9A-Fa-f]{6}$")
    icon: str | None = Field(None, max_length=50)
    order: int | None = Field(None, ge=0)
    owner: str | None = Field(None, max_length=255)
    team: str | None = Field(None, max_length=100)
    tags: dict | None = None
    metadata: dict | None = None


class FolderResponse(BaseModel):
    """Schema for folder response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    display_name: str | None = None
    description: str | None = None
    parent_id: UUID | None = None
    color: str | None = None
    icon: str | None = None
    order: int = 0
    owner: str | None = None
    team: str | None = None
    tags: dict | None = None
    extra_data: dict | None = Field(None, alias="metadata")
    created_at: datetime
    updated_at: datetime


class FolderSummary(BaseModel):
    """Minimal folder info for list views."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    display_name: str | None = None
    color: str | None = None
    icon: str | None = None
    parent_id: UUID | None = None


class FolderList(BaseModel):
    """Paginated list of folders."""

    items: list[FolderSummary]
    total: int


class MoveFolderRequest(BaseModel):
    """Request to move a folder to a new parent."""

    new_parent_id: UUID | None = None  # None = move to root


class FolderPath(BaseModel):
    """Path from root to a folder."""

    path: list[FolderSummary]


# =============================================================================
# Application summary for folder contents
# =============================================================================


class ApplicationInFolder(BaseModel):
    """Minimal application info for folder contents."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    display_name: str | None = None
    environment: str | None = None
    criticality: str | None = None
    team: str | None = None


# =============================================================================
# Tree structures for hierarchy display
# =============================================================================


class FolderTreeNode(BaseModel):
    """Recursive folder tree node with children and applications."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID | str  # Allow string for virtual folders like "unassigned"
    name: str
    display_name: str | None = None
    color: str | None = None
    icon: str | None = None
    order: int = 0
    parent_id: UUID | None = None
    team: str | None = None
    children: list["FolderTreeNode"] = Field(default_factory=list)
    applications: list[ApplicationInFolder] = Field(default_factory=list)


class FolderTree(BaseModel):
    """Full folder hierarchy with nested children."""

    roots: list[FolderTreeNode]
    total_folders: int
    total_applications: int


# =============================================================================
# Arc Topology View schemas
# =============================================================================


class ArcDependency(BaseModel):
    """Aggregated dependency between applications for arc view."""

    source_folder_id: UUID | str | None = None
    source_app_id: UUID
    source_app_name: str
    target_folder_id: UUID | str | None = None
    target_app_id: UUID
    target_app_name: str
    connection_count: int
    bytes_total: int
    bytes_last_24h: int = 0
    direction: EdgeDirection = EdgeDirection.OUT


class FolderDependency(BaseModel):
    """Aggregated dependency between folders for arc view (folder-level edges)."""

    source_folder_id: UUID | str
    source_folder_name: str
    target_folder_id: UUID | str
    target_folder_name: str
    direction: EdgeDirection
    connection_count: int
    bytes_total: int
    bytes_last_24h: int


class ArcTopologyData(BaseModel):
    """Complete data for arc-based topology visualization."""

    hierarchy: FolderTree
    dependencies: list[ArcDependency]
    folder_dependencies: list[FolderDependency] = Field(default_factory=list)
    statistics: dict


class MoveApplicationRequest(BaseModel):
    """Request to move an application to a folder."""

    folder_id: UUID | None = None  # None = remove from folder


# =============================================================================
# Application Dependency Details (for details pane)
# =============================================================================


class ApplicationDependencySummary(BaseModel):
    """Summary of a single dependency counterparty for the details pane."""

    counterparty_id: UUID
    counterparty_name: str
    counterparty_folder_id: UUID | str | None = None
    counterparty_folder_name: str | None = None
    direction: EdgeDirection
    connection_count: int
    bytes_total: int
    bytes_last_24h: int
    last_seen: str | None = None


class ApplicationDependencyList(BaseModel):
    """List of dependencies for an application."""

    app_id: UUID
    app_name: str
    direction_filter: str  # "incoming", "outgoing", or "both"
    dependencies: list[ApplicationDependencySummary]
    total_connections: int
    total_bytes: int
    total_bytes_24h: int


# =============================================================================
# Topology Exclusions (for hiding entities from arc view)
# =============================================================================


class ExclusionEntityType(str, Enum):
    """Type of entity being excluded."""

    FOLDER = "folder"
    APPLICATION = "application"


class TopologyExclusionCreate(BaseModel):
    """Schema for creating a topology exclusion."""

    entity_type: ExclusionEntityType
    entity_id: UUID
    reason: str | None = Field(None, max_length=500)


class TopologyExclusionResponse(BaseModel):
    """Schema for topology exclusion response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    entity_type: str
    entity_id: UUID
    entity_name: str | None = None  # Populated from folder/application name
    reason: str | None = None
    created_at: datetime


class TopologyExclusionList(BaseModel):
    """List of topology exclusions."""

    items: list[TopologyExclusionResponse]
    total: int


# Rebuild model for forward reference
FolderTreeNode.model_rebuild()

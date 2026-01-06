"""Pydantic schemas for Folder API endpoints and arc topology view."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


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

    id: UUID
    name: str
    display_name: str | None = None
    color: str | None = None
    icon: str | None = None
    order: int = 0
    parent_id: UUID | None = None
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

    source_folder_id: UUID | None = None
    source_app_id: UUID
    source_app_name: str
    target_folder_id: UUID | None = None
    target_app_id: UUID
    target_app_name: str
    connection_count: int
    bytes_total: int


class ArcTopologyData(BaseModel):
    """Complete data for arc-based topology visualization."""

    hierarchy: FolderTree
    dependencies: list[ArcDependency]
    statistics: dict


class MoveApplicationRequest(BaseModel):
    """Request to move an application to a folder."""

    folder_id: UUID | None = None  # None = remove from folder


# Rebuild model for forward reference
FolderTreeNode.model_rebuild()

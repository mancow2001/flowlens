"""Backup and restore API schemas."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class BackupType(str, Enum):
    """Backup type enumeration."""

    CONFIGURATION = "configuration"
    FULL = "full"


class BackupMetadata(BaseModel):
    """Backup file metadata."""

    version: str = "1.0"
    app_version: str
    backup_type: BackupType
    created_at: datetime
    table_counts: dict[str, int] = Field(default_factory=dict)


class RestorePreview(BaseModel):
    """Preview of what restore will do."""

    backup_type: BackupType
    backup_created_at: datetime
    app_version_backup: str
    app_version_current: str
    table_counts: dict[str, int]
    warnings: list[str] = Field(default_factory=list)
    is_compatible: bool


class RestoreResponse(BaseModel):
    """Response after restore operation."""

    success: bool
    message: str
    tables_restored: list[str] = Field(default_factory=list)
    rows_restored: dict[str, int] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)

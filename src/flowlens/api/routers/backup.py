"""Backup and restore API endpoints.

Provides endpoints for creating database backups and restoring from backup files.
Requires admin role for all operations.
"""

import gzip
import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, File, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select, text

from flowlens.api.dependencies import AdminUser, DbSession
from flowlens.common.config import get_settings
from flowlens.common.logging import get_logger
from flowlens.models import (
    Alert,
    AlertRule,
    Application,
    ApplicationBaseline,
    ApplicationLayout,
    ApplicationMember,
    Asset,
    AssetGateway,
    AssetGroup,
    AuthAuditLog,
    ChangeEvent,
    ClassificationRule,
    Dependency,
    EntryPoint,
    FlowAggregate,
    FlowRecord,
    Folder,
    MaintenanceWindow,
    SAMLProvider,
    SavedView,
    SegmentationPolicy,
    SegmentationPolicyRule,
    SegmentationPolicyVersion,
    Service,
    TopologyExclusion,
    User,
)
from flowlens.models.discovery import DiscoveryProvider
from flowlens.schemas.backup import (
    BackupMetadata,
    BackupType,
    RestorePreview,
    RestoreResponse,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/admin/backup", tags=["backup"])

# Configuration tables (always backed up)
CONFIG_TABLES: list[tuple[str, type]] = [
    ("alert_rules", AlertRule),
    ("segmentation_policies", SegmentationPolicy),
    ("segmentation_policy_rules", SegmentationPolicyRule),
    ("segmentation_policy_versions", SegmentationPolicyVersion),
    ("classification_rules", ClassificationRule),
    ("topology_exclusions", TopologyExclusion),
    ("saved_views", SavedView),
    ("maintenance_windows", MaintenanceWindow),
    ("folders", Folder),
    ("discovery_providers", DiscoveryProvider),
    ("saml_providers", SAMLProvider),
    ("layouts", ApplicationLayout),
    ("asset_groups", AssetGroup),
    ("baselines", ApplicationBaseline),
]

# Asset/dependency tables (always backed up)
ASSET_TABLES: list[tuple[str, type]] = [
    ("assets", Asset),
    ("services", Service),
    ("dependencies", Dependency),
    ("applications", Application),
    ("application_members", ApplicationMember),
    ("entry_points", EntryPoint),
    ("asset_gateways", AssetGateway),
    ("changes", ChangeEvent),
    ("alerts", Alert),
]

# User tables (always backed up)
USER_TABLES: list[tuple[str, type]] = [
    ("users", User),
    ("auth_audit_logs", AuthAuditLog),
]

# Flow tables (only for full backup)
FLOW_TABLES: list[tuple[str, type]] = [
    ("flow_records", FlowRecord),
    ("flow_aggregates", FlowAggregate),
]


def serialize_value(value: Any) -> Any:
    """Serialize a value for JSON export."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if hasattr(value, "value"):  # Enum
        return value.value
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def serialize_model(obj: Any) -> dict[str, Any]:
    """Serialize SQLAlchemy model to dictionary."""
    result = {}
    for column in obj.__table__.columns:
        value = getattr(obj, column.name)
        result[column.name] = serialize_value(value)
    return result


@router.get("/download", response_class=StreamingResponse)
async def download_backup(
    db: DbSession,
    admin: AdminUser,
    backup_type: BackupType = Query(BackupType.CONFIGURATION),
) -> StreamingResponse:
    """Download a backup of the database.

    Args:
        backup_type: "configuration" for config+assets, "full" for everything including flows

    Returns:
        Gzip-compressed JSON backup file.
    """
    settings = get_settings()
    logger.info("Starting backup", backup_type=backup_type.value, user=admin.sub)

    # Build table list based on backup type
    tables_to_backup = CONFIG_TABLES + ASSET_TABLES + USER_TABLES
    if backup_type == BackupType.FULL:
        tables_to_backup = tables_to_backup + FLOW_TABLES

    # Collect data
    data: dict[str, list[dict[str, Any]]] = {}
    table_counts: dict[str, int] = {}

    for table_name, model_class in tables_to_backup:
        try:
            result = await db.execute(select(model_class))  # type: ignore[var-annotated]
            records = result.scalars().all()
            data[table_name] = [serialize_model(r) for r in records]
            table_counts[table_name] = len(data[table_name])
        except Exception as e:
            logger.warning(f"Error backing up table {table_name}", error=str(e))
            data[table_name] = []
            table_counts[table_name] = 0

    # Build metadata
    metadata = BackupMetadata(
        version="1.0",
        app_version=settings.app_version,
        backup_type=backup_type,
        created_at=datetime.now(UTC),
        table_counts=table_counts,
    )

    # Build backup structure
    backup = {
        "metadata": metadata.model_dump(mode="json"),
        "data": data,
    }

    # Compress
    json_bytes = json.dumps(backup, default=str).encode("utf-8")
    compressed = gzip.compress(json_bytes)

    # Generate filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"flowlens_backup_{backup_type.value}_{timestamp}.json.gz"

    total_rows = sum(table_counts.values())
    logger.info(
        "Backup completed",
        backup_type=backup_type.value,
        tables=len(tables_to_backup),
        rows=total_rows,
        size_bytes=len(compressed),
        user=admin.sub,
    )

    return StreamingResponse(
        iter([compressed]),
        media_type="application/gzip",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.post("/restore/preview", response_model=RestorePreview)
async def preview_restore(
    _db: DbSession,
    _admin: AdminUser,
    file: UploadFile = File(...),
) -> RestorePreview:
    """Preview what a restore operation will do.

    Upload a backup file to see its contents and compatibility before restoring.
    """
    settings = get_settings()

    # Read and decompress
    content = await file.read()
    try:
        decompressed = gzip.decompress(content)
        backup = json.loads(decompressed.decode("utf-8"))
    except gzip.BadGzipFile:
        # Try reading as plain JSON
        try:
            backup = json.loads(content.decode("utf-8"))
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid backup file format: {e}",
            )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid backup file: {e}",
        )

    metadata = backup.get("metadata", {})
    if not metadata:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid backup file: missing metadata",
        )

    backup_type_str = metadata.get("backup_type", "configuration")
    try:
        backup_type = BackupType(backup_type_str)
    except ValueError:
        backup_type = BackupType.CONFIGURATION

    backup_version = metadata.get("app_version", "unknown")
    created_at_str = metadata.get("created_at")

    try:
        backup_created_at = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        backup_created_at = datetime.now(UTC)

    # Version compatibility check
    warnings: list[str] = []
    is_compatible = True

    if backup_version != settings.app_version:
        warnings.append(
            f"Backup was created with app version {backup_version}, "
            f"current version is {settings.app_version}. "
            "Some data may not restore correctly."
        )

    # Check backup format version
    backup_format_version = metadata.get("version", "1.0")
    if backup_format_version != "1.0":
        warnings.append(f"Backup format version {backup_format_version} may not be fully compatible.")
        is_compatible = False

    return RestorePreview(
        backup_type=backup_type,
        backup_created_at=backup_created_at,
        app_version_backup=backup_version,
        app_version_current=settings.app_version,
        table_counts=metadata.get("table_counts", {}),
        warnings=warnings,
        is_compatible=is_compatible,
    )


# Table restore order (respects foreign key dependencies)
RESTORE_ORDER: list[str] = [
    # Users first (no dependencies)
    "users",
    # Config tables with no FK dependencies
    "folders",
    "saml_providers",
    "discovery_providers",
    "classification_rules",
    "topology_exclusions",
    "saved_views",
    "maintenance_windows",
    # Assets and services
    "assets",
    "services",
    # Applications depend on assets
    "applications",
    "application_members",
    "entry_points",
    # Dependencies depend on assets
    "dependencies",
    "asset_gateways",
    # Policies may depend on assets
    "segmentation_policies",
    "segmentation_policy_rules",
    "segmentation_policy_versions",
    # Alert rules
    "alert_rules",
    # Layouts depend on applications
    "layouts",
    "asset_groups",
    "baselines",
    # Events depend on assets
    "changes",
    "alerts",
    "auth_audit_logs",
    # Flow data last
    "flow_records",
    "flow_aggregates",
]


@router.post("/restore", response_model=RestoreResponse)
async def restore_backup(
    db: DbSession,
    admin: AdminUser,
    file: UploadFile = File(...),
    confirm_destructive: bool = Query(
        False,
        alias="confirm_destructive",
        description="Must be true to confirm destructive operation",
    ),
) -> RestoreResponse:
    """Restore database from backup file.

    WARNING: This is a destructive operation that will replace ALL existing data.
    You must set confirm_destructive=true to proceed.
    """
    if not confirm_destructive:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Must set confirm_destructive=true to proceed with restore. "
            "This operation will delete all existing data.",
        )

    logger.warning("Starting database restore", user=admin.sub)

    # Read and decompress
    content = await file.read()
    try:
        decompressed = gzip.decompress(content)
        backup = json.loads(decompressed.decode("utf-8"))
    except gzip.BadGzipFile:
        try:
            backup = json.loads(content.decode("utf-8"))
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid backup file format: {e}",
            )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid backup file: {e}",
        )

    data = backup.get("data", {})
    if not data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid backup file: no data section found",
        )

    # Build model mapping from all table lists
    all_tables = CONFIG_TABLES + ASSET_TABLES + USER_TABLES + FLOW_TABLES
    model_map: dict[str, type[Any]] = dict(all_tables)

    tables_restored: list[str] = []
    rows_restored: dict[str, int] = {}
    errors: list[str] = []

    try:
        # Clear existing data in reverse restore order (CASCADE handles FKs)
        for table_name in reversed(RESTORE_ORDER):
            if table_name in model_map and table_name in data:
                model = model_map[table_name]
                tablename = getattr(model, "__tablename__", table_name)
                await db.execute(text(f"TRUNCATE TABLE {tablename} CASCADE"))

        # Restore data in dependency order
        for table_name in RESTORE_ORDER:
            if table_name not in data or table_name not in model_map:
                continue

            model = model_map[table_name]
            records = data[table_name]

            if not records:
                continue

            restored_count = 0
            for record in records:
                try:
                    # Convert UUID strings back to UUID objects
                    processed_record: dict[str, Any] = {}
                    for key, value in record.items():
                        # Check if it's a UUID string
                        if isinstance(value, str) and len(value) == 36 and value.count("-") == 4:
                            try:
                                processed_record[key] = UUID(value)
                            except ValueError:
                                processed_record[key] = value
                        # Handle datetime strings
                        elif isinstance(value, str) and "T" in value and (":" in value or "Z" in value):
                            try:
                                processed_record[key] = datetime.fromisoformat(
                                    value.replace("Z", "+00:00")
                                )
                            except ValueError:
                                processed_record[key] = value
                        else:
                            processed_record[key] = value

                    obj = model(**processed_record)
                    db.add(obj)
                    restored_count += 1
                except Exception as e:
                    errors.append(f"Error restoring {table_name} record: {e}")

            if restored_count > 0:
                tables_restored.append(table_name)
                rows_restored[table_name] = restored_count

        await db.commit()

        total_rows = sum(rows_restored.values())
        logger.info(
            "Database restore completed",
            tables=len(tables_restored),
            rows=total_rows,
            errors=len(errors),
            user=admin.sub,
        )

        return RestoreResponse(
            success=True,
            message=f"Successfully restored {len(tables_restored)} tables with {total_rows} rows",
            tables_restored=tables_restored,
            rows_restored=rows_restored,
            errors=errors[:10],  # Limit errors to first 10
        )

    except Exception as e:
        await db.rollback()
        logger.error("Database restore failed", error=str(e), user=admin.sub)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Restore failed: {e}. Database has been rolled back.",
        )

"""Asset API endpoints."""

import csv
import io
import json
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, UploadFile, File, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.orm import selectinload

from flowlens.api.dependencies import AuthenticatedUser, DbSession, Pagination, Sorting
from flowlens.models.asset import Asset, AssetType, Service
from flowlens.models.dependency import Dependency
from flowlens.schemas.asset import (
    AssetCreate,
    AssetExportRow,
    AssetImportPreview,
    AssetImportResult,
    AssetImportRow,
    AssetImportValidation,
    AssetList,
    AssetResponse,
    AssetSummary,
    AssetUpdate,
    AssetWithServices,
    ServiceResponse,
)
from flowlens.schemas.dependency import AssetInfo, DependencyWithAssets

router = APIRouter(prefix="/assets", tags=["assets"])


@router.get("", response_model=AssetList)
async def list_assets(
    db: DbSession,
    user: AuthenticatedUser,
    pagination: Pagination,
    sorting: Sorting,
    asset_type: AssetType | None = Query(None, alias="assetType"),
    environment: str | None = None,
    datacenter: str | None = None,
    team: str | None = None,
    is_internal: bool | None = Query(None, alias="isInternal"),
    is_critical: bool | None = Query(None, alias="isCritical"),
    search: str | None = None,
) -> AssetList:
    """List assets with filtering and pagination."""
    # Build query
    query = select(Asset).where(Asset.deleted_at.is_(None))

    # Apply filters
    if asset_type:
        query = query.where(Asset.asset_type == asset_type)
    if environment:
        query = query.where(Asset.environment == environment)
    if datacenter:
        query = query.where(Asset.datacenter == datacenter)
    if team:
        query = query.where(Asset.team == team)
    if is_internal is not None:
        query = query.where(Asset.is_internal == is_internal)
    if is_critical is not None:
        query = query.where(Asset.is_critical == is_critical)
    if search:
        search_filter = f"%{search}%"
        query = query.where(
            Asset.name.ilike(search_filter)
            | Asset.hostname.ilike(search_filter)
            | cast(Asset.ip_address, String).ilike(search_filter)
        )

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query) or 0

    # Apply sorting
    if sorting.sort_by:
        sort_column = getattr(Asset, sorting.sort_by, Asset.last_seen)
        if sorting.ascending:
            query = query.order_by(sort_column.asc())
        else:
            query = query.order_by(sort_column.desc())
    else:
        query = query.order_by(Asset.last_seen.desc())

    # Apply pagination
    query = query.offset(pagination.offset).limit(pagination.page_size)

    # Execute query
    result = await db.execute(query)
    assets = result.scalars().all()

    # Build response
    items = [
        AssetSummary(
            id=a.id,
            name=a.name,
            display_name=a.display_name,
            asset_type=a.asset_type,
            ip_address=str(a.ip_address),
            hostname=a.hostname,
            is_internal=a.is_internal,
            is_critical=a.is_critical,
            last_seen=a.last_seen,
        )
        for a in assets
    ]

    return AssetList(
        items=items,
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
        pages=(total + pagination.page_size - 1) // pagination.page_size,
    )


# =============================================================================
# Bulk Export/Import Endpoints (must be before /{asset_id} routes)
# =============================================================================


@router.get("/export", response_class=StreamingResponse)
async def export_assets(
    db: DbSession,
    user: AuthenticatedUser,
    format: Literal["csv", "json"] = Query("csv"),
    asset_type: AssetType | None = Query(None, alias="assetType"),
    environment: str | None = None,
    datacenter: str | None = None,
    is_internal: bool | None = Query(None, alias="isInternal"),
) -> StreamingResponse:
    """Export all assets to CSV or JSON format.

    Exported data includes editable fields that can be modified and re-imported.
    Fields like environment and datacenter from static asset data are included
    (CIDR-based classifications are not included in export as they're dynamic).
    """
    # Build query with optional filters
    query = select(Asset).where(Asset.deleted_at.is_(None))

    if asset_type:
        query = query.where(Asset.asset_type == asset_type)
    if environment:
        query = query.where(Asset.environment == environment)
    if datacenter:
        query = query.where(Asset.datacenter == datacenter)
    if is_internal is not None:
        query = query.where(Asset.is_internal == is_internal)

    query = query.order_by(Asset.ip_address)

    result = await db.execute(query)
    assets = result.scalars().all()

    # Build export rows
    rows = []
    for a in assets:
        rows.append(AssetExportRow(
            ip_address=str(a.ip_address),
            name=a.name,
            hostname=a.hostname,
            asset_type=a.asset_type.value if hasattr(a.asset_type, 'value') else str(a.asset_type),
            owner=a.owner,
            team=a.team,
            description=a.description,
            is_critical=a.is_critical,
            environment=a.environment,
            datacenter=a.datacenter,
            tags=json.dumps(a.tags) if a.tags else None,
        ))

    if format == "json":
        # JSON export
        content = json.dumps([r.model_dump() for r in rows], indent=2)
        return StreamingResponse(
            iter([content]),
            media_type="application/json",
            headers={"Content-Disposition": "attachment; filename=assets-export.json"},
        )
    else:
        # CSV export
        output = io.StringIO()
        fieldnames = [
            "ip_address", "name", "hostname", "asset_type", "owner", "team",
            "description", "is_critical", "environment", "datacenter", "tags"
        ]
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row.model_dump())

        output.seek(0)
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=assets-export.csv"},
        )


@router.post("/import/preview", response_model=AssetImportPreview)
async def preview_asset_import(
    db: DbSession,
    user: AuthenticatedUser,
    file: UploadFile = File(...),
) -> AssetImportPreview:
    """Preview what an asset import will do before committing.

    Accepts CSV or JSON file. Matches assets by IP address.
    Returns a preview of creates, updates, and any errors.
    """
    content = await file.read()
    content_str = content.decode("utf-8")

    # Parse file based on content type or extension
    rows: list[dict] = []
    filename = file.filename or ""

    if filename.endswith(".json") or file.content_type == "application/json":
        try:
            rows = json.loads(content_str)
            if not isinstance(rows, list):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="JSON file must contain an array of objects",
                )
        except json.JSONDecodeError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid JSON: {e}",
            )
    else:
        # Assume CSV
        try:
            reader = csv.DictReader(io.StringIO(content_str))
            rows = list(reader)
        except csv.Error as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid CSV: {e}",
            )

    if not rows:
        return AssetImportPreview(
            total_rows=0,
            to_create=0,
            to_update=0,
            to_skip=0,
            errors=0,
            validations=[],
        )

    # Get existing assets by IP for comparison
    ip_addresses = [r.get("ip_address", "") for r in rows if r.get("ip_address")]
    existing_query = select(Asset).where(
        Asset.deleted_at.is_(None),
        cast(Asset.ip_address, String).in_(ip_addresses),
    )
    existing_result = await db.execute(existing_query)
    existing_assets = {str(a.ip_address): a for a in existing_result.scalars().all()}

    # Validate each row
    validations = []
    to_create = 0
    to_update = 0
    to_skip = 0
    errors = 0

    for idx, row in enumerate(rows, start=1):
        ip = row.get("ip_address", "").strip()

        if not ip:
            validations.append(AssetImportValidation(
                row_number=idx,
                ip_address="",
                status="error",
                message="Missing ip_address",
            ))
            errors += 1
            continue

        # Validate IP format
        try:
            import ipaddress
            ipaddress.ip_address(ip)
        except ValueError:
            validations.append(AssetImportValidation(
                row_number=idx,
                ip_address=ip,
                status="error",
                message=f"Invalid IP address format: {ip}",
            ))
            errors += 1
            continue

        existing = existing_assets.get(ip)

        if existing:
            # Check for changes
            changes = {}
            for field in ["name", "hostname", "owner", "team", "description"]:
                new_val = row.get(field, "").strip() if row.get(field) else None
                old_val = getattr(existing, field)
                if new_val and new_val != old_val:
                    changes[field] = {"old": old_val, "new": new_val}

            # Handle is_critical (bool)
            if "is_critical" in row and row["is_critical"] != "":
                new_critical = str(row["is_critical"]).lower() in ("true", "1", "yes")
                if new_critical != existing.is_critical:
                    changes["is_critical"] = {"old": existing.is_critical, "new": new_critical}

            # Handle asset_type
            if row.get("asset_type"):
                new_type = row["asset_type"].strip()
                old_type = existing.asset_type.value if hasattr(existing.asset_type, 'value') else str(existing.asset_type)
                if new_type and new_type != old_type:
                    # Validate asset type
                    valid_types = [t.value for t in AssetType]
                    if new_type not in valid_types:
                        validations.append(AssetImportValidation(
                            row_number=idx,
                            ip_address=ip,
                            status="error",
                            message=f"Invalid asset_type: {new_type}. Valid types: {', '.join(valid_types)}",
                        ))
                        errors += 1
                        continue
                    changes["asset_type"] = {"old": old_type, "new": new_type}

            if changes:
                validations.append(AssetImportValidation(
                    row_number=idx,
                    ip_address=ip,
                    status="update",
                    message=f"Will update {len(changes)} field(s)",
                    changes=changes,
                ))
                to_update += 1
            else:
                validations.append(AssetImportValidation(
                    row_number=idx,
                    ip_address=ip,
                    status="skip",
                    message="No changes detected",
                ))
                to_skip += 1
        else:
            # New asset - requires name
            name = row.get("name", "").strip() if row.get("name") else None
            if not name:
                validations.append(AssetImportValidation(
                    row_number=idx,
                    ip_address=ip,
                    status="error",
                    message="New asset requires a name",
                ))
                errors += 1
                continue

            validations.append(AssetImportValidation(
                row_number=idx,
                ip_address=ip,
                status="create",
                message=f"Will create new asset: {name}",
            ))
            to_create += 1

    return AssetImportPreview(
        total_rows=len(rows),
        to_create=to_create,
        to_update=to_update,
        to_skip=to_skip,
        errors=errors,
        validations=validations,
    )


@router.post("/import", response_model=AssetImportResult)
async def import_assets(
    db: DbSession,
    user: AuthenticatedUser,
    file: UploadFile = File(...),
    skip_errors: bool = Query(False, alias="skipErrors"),
) -> AssetImportResult:
    """Import assets from CSV or JSON file.

    Matches assets by IP address. Updates existing assets or creates new ones.
    Blank values in the import file are ignored (won't overwrite existing data).
    """
    content = await file.read()
    content_str = content.decode("utf-8")

    # Parse file
    rows: list[dict] = []
    filename = file.filename or ""

    if filename.endswith(".json") or file.content_type == "application/json":
        try:
            rows = json.loads(content_str)
        except json.JSONDecodeError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid JSON: {e}",
            )
    else:
        try:
            reader = csv.DictReader(io.StringIO(content_str))
            rows = list(reader)
        except csv.Error as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid CSV: {e}",
            )

    if not rows:
        return AssetImportResult(
            created=0,
            updated=0,
            skipped=0,
            errors=0,
        )

    # Get existing assets
    ip_addresses = [r.get("ip_address", "") for r in rows if r.get("ip_address")]
    existing_query = select(Asset).where(
        Asset.deleted_at.is_(None),
        cast(Asset.ip_address, String).in_(ip_addresses),
    )
    existing_result = await db.execute(existing_query)
    existing_assets = {str(a.ip_address): a for a in existing_result.scalars().all()}

    created = 0
    updated = 0
    skipped = 0
    errors = 0
    error_details = []

    for idx, row in enumerate(rows, start=1):
        ip = row.get("ip_address", "").strip()

        if not ip:
            if skip_errors:
                errors += 1
                error_details.append(f"Row {idx}: Missing ip_address")
                continue
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Row {idx}: Missing ip_address",
            )

        # Validate IP
        try:
            import ipaddress
            ipaddress.ip_address(ip)
        except ValueError:
            if skip_errors:
                errors += 1
                error_details.append(f"Row {idx}: Invalid IP address: {ip}")
                continue
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Row {idx}: Invalid IP address: {ip}",
            )

        existing = existing_assets.get(ip)

        if existing:
            # Update existing asset
            has_changes = False
            for field in ["name", "hostname", "owner", "team", "description"]:
                new_val = row.get(field, "").strip() if row.get(field) else None
                if new_val:  # Only update if value provided
                    if new_val != getattr(existing, field):
                        setattr(existing, field, new_val)
                        has_changes = True

            # Handle is_critical
            if "is_critical" in row and row["is_critical"] != "":
                new_critical = str(row["is_critical"]).lower() in ("true", "1", "yes")
                if new_critical != existing.is_critical:
                    existing.is_critical = new_critical
                    has_changes = True

            # Handle asset_type
            if row.get("asset_type"):
                new_type = row["asset_type"].strip()
                if new_type:
                    try:
                        existing.asset_type = AssetType(new_type)
                        has_changes = True
                    except ValueError:
                        if skip_errors:
                            errors += 1
                            error_details.append(f"Row {idx}: Invalid asset_type: {new_type}")
                            continue
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"Row {idx}: Invalid asset_type: {new_type}",
                        )

            # Handle tags (JSON string)
            if row.get("tags"):
                try:
                    new_tags = json.loads(row["tags"])
                    if new_tags != existing.tags:
                        existing.tags = new_tags
                        has_changes = True
                except json.JSONDecodeError:
                    if skip_errors:
                        errors += 1
                        error_details.append(f"Row {idx}: Invalid tags JSON")
                        continue
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Row {idx}: Invalid tags JSON",
                    )

            if has_changes:
                updated += 1
            else:
                skipped += 1
        else:
            # Create new asset
            name = row.get("name", "").strip() if row.get("name") else None
            if not name:
                if skip_errors:
                    errors += 1
                    error_details.append(f"Row {idx}: New asset requires a name")
                    continue
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Row {idx}: New asset requires a name",
                )

            asset_type_str = row.get("asset_type", "").strip() if row.get("asset_type") else "unknown"
            try:
                asset_type_val = AssetType(asset_type_str)
            except ValueError:
                asset_type_val = AssetType.UNKNOWN

            is_critical = False
            if "is_critical" in row and row["is_critical"] != "":
                is_critical = str(row["is_critical"]).lower() in ("true", "1", "yes")

            tags = None
            if row.get("tags"):
                try:
                    tags = json.loads(row["tags"])
                except json.JSONDecodeError:
                    pass

            new_asset = Asset(
                ip_address=ip,
                name=name,
                hostname=row.get("hostname", "").strip() if row.get("hostname") else None,
                asset_type=asset_type_val,
                owner=row.get("owner", "").strip() if row.get("owner") else None,
                team=row.get("team", "").strip() if row.get("team") else None,
                description=row.get("description", "").strip() if row.get("description") else None,
                is_critical=is_critical,
                environment=row.get("environment", "").strip() if row.get("environment") else None,
                datacenter=row.get("datacenter", "").strip() if row.get("datacenter") else None,
                tags=tags,
            )
            db.add(new_asset)
            created += 1

    await db.flush()

    return AssetImportResult(
        created=created,
        updated=updated,
        skipped=skipped,
        errors=errors,
        error_details=error_details if error_details else None,
    )


# =============================================================================
# Bulk Update Endpoint (must be before /{asset_id} routes)
# =============================================================================


class BulkAssetUpdate(BaseModel):
    """Request body for bulk asset updates."""
    ids: list[UUID]
    updates: dict[str, str | bool | None]


class BulkUpdateResult(BaseModel):
    """Result of bulk update operation."""
    updated: int
    skipped: int
    errors: int
    error_details: list[str] | None = None


@router.patch("/bulk", response_model=BulkUpdateResult)
async def bulk_update_assets(
    data: BulkAssetUpdate,
    db: DbSession,
    user: AuthenticatedUser,
) -> BulkUpdateResult:
    """Update multiple assets at once.

    Supports updating: environment, datacenter, is_critical, owner, team.
    """
    allowed_fields = {"environment", "datacenter", "is_critical", "owner", "team"}
    update_fields = {k: v for k, v in data.updates.items() if k in allowed_fields}

    if not update_fields:
        return BulkUpdateResult(updated=0, skipped=len(data.ids), errors=0)

    # Get assets to update
    result = await db.execute(
        select(Asset).where(
            Asset.id.in_(data.ids),
            Asset.deleted_at.is_(None),
        )
    )
    assets = result.scalars().all()

    found_ids = {a.id for a in assets}
    missing_ids = set(data.ids) - found_ids

    updated = 0
    errors = 0
    error_details = []

    for asset in assets:
        try:
            for field, value in update_fields.items():
                setattr(asset, field, value)
            updated += 1
        except Exception as e:
            errors += 1
            error_details.append(f"Asset {asset.id}: {str(e)}")

    await db.flush()

    return BulkUpdateResult(
        updated=updated,
        skipped=len(missing_ids),
        errors=errors,
        error_details=error_details if error_details else None,
    )


@router.delete("/bulk", response_model=dict)
async def bulk_delete_assets(
    ids: list[UUID],
    db: DbSession,
    user: AuthenticatedUser,
) -> dict:
    """Soft delete multiple assets at once."""
    result = await db.execute(
        select(Asset).where(
            Asset.id.in_(ids),
            Asset.deleted_at.is_(None),
        )
    )
    assets = result.scalars().all()

    deleted = 0
    for asset in assets:
        asset.soft_delete()
        deleted += 1

    await db.flush()

    return {"deleted": deleted, "not_found": len(ids) - deleted}


# =============================================================================
# Individual Asset Endpoints (must be after static routes)
# =============================================================================


@router.get("/{asset_id}", response_model=AssetWithServices)
async def get_asset(
    asset_id: UUID,
    db: DbSession,
    user: AuthenticatedUser,
) -> AssetWithServices:
    """Get asset by ID with services."""
    query = (
        select(Asset)
        .where(Asset.id == asset_id, Asset.deleted_at.is_(None))
        .options(selectinload(Asset.services))
    )
    result = await db.execute(query)
    asset = result.scalar_one_or_none()

    if not asset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Asset {asset_id} not found",
        )

    # Build services list
    services = [
        ServiceResponse(
            id=s.id,
            asset_id=s.asset_id,
            port=s.port,
            protocol=s.protocol,
            name=s.name,
            service_type=s.service_type,
            version=s.version,
            first_seen=s.first_seen,
            last_seen=s.last_seen,
            bytes_total=s.bytes_total,
            connections_total=s.connections_total,
        )
        for s in asset.services
    ]

    return AssetWithServices(
        id=asset.id,
        name=asset.name,
        display_name=asset.display_name,
        asset_type=asset.asset_type,
        ip_address=str(asset.ip_address),
        hostname=asset.hostname,
        fqdn=asset.fqdn,
        mac_address=asset.mac_address,
        subnet=str(asset.subnet) if asset.subnet else None,
        vlan_id=asset.vlan_id,
        datacenter=asset.datacenter,
        environment=asset.environment,
        country_code=asset.country_code,
        city=asset.city,
        is_internal=asset.is_internal,
        is_critical=asset.is_critical,
        criticality_score=asset.criticality_score,
        owner=asset.owner,
        team=asset.team,
        external_id=asset.external_id,
        description=asset.description,
        tags=asset.tags,
        metadata=asset.extra_data,
        first_seen=asset.first_seen,
        last_seen=asset.last_seen,
        bytes_in_total=asset.bytes_in_total,
        bytes_out_total=asset.bytes_out_total,
        connections_in=asset.connections_in,
        connections_out=asset.connections_out,
        created_at=asset.created_at,
        updated_at=asset.updated_at,
        services=services,
    )


@router.post("", response_model=AssetResponse, status_code=status.HTTP_201_CREATED)
async def create_asset(
    data: AssetCreate,
    db: DbSession,
    user: AuthenticatedUser,
) -> AssetResponse:
    """Create a new asset."""
    # Check for duplicate IP
    existing = await db.execute(
        select(Asset).where(
            Asset.ip_address == str(data.ip_address),
            Asset.deleted_at.is_(None),
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Asset with IP {data.ip_address} already exists",
        )

    # Create asset
    asset = Asset(
        name=data.name,
        display_name=data.display_name,
        asset_type=data.asset_type,
        ip_address=str(data.ip_address),
        hostname=data.hostname,
        fqdn=data.fqdn,
        mac_address=data.mac_address,
        subnet=data.subnet,
        vlan_id=data.vlan_id,
        datacenter=data.datacenter,
        environment=data.environment,
        is_internal=data.is_internal,
        is_critical=data.is_critical,
        criticality_score=data.criticality_score,
        owner=data.owner,
        team=data.team,
        external_id=data.external_id,
        description=data.description,
        tags=data.tags,
        extra_data=data.metadata,
    )

    db.add(asset)
    await db.flush()
    await db.refresh(asset)

    return AssetResponse(
        id=asset.id,
        name=asset.name,
        display_name=asset.display_name,
        asset_type=asset.asset_type,
        ip_address=str(asset.ip_address),
        hostname=asset.hostname,
        fqdn=asset.fqdn,
        mac_address=asset.mac_address,
        subnet=str(asset.subnet) if asset.subnet else None,
        vlan_id=asset.vlan_id,
        datacenter=asset.datacenter,
        environment=asset.environment,
        country_code=asset.country_code,
        city=asset.city,
        is_internal=asset.is_internal,
        is_critical=asset.is_critical,
        criticality_score=asset.criticality_score,
        owner=asset.owner,
        team=asset.team,
        external_id=asset.external_id,
        description=asset.description,
        tags=asset.tags,
        metadata=asset.extra_data,
        first_seen=asset.first_seen,
        last_seen=asset.last_seen,
        bytes_in_total=asset.bytes_in_total,
        bytes_out_total=asset.bytes_out_total,
        connections_in=asset.connections_in,
        connections_out=asset.connections_out,
        created_at=asset.created_at,
        updated_at=asset.updated_at,
    )


@router.put("/{asset_id}", response_model=AssetResponse)
async def update_asset(
    asset_id: UUID,
    data: AssetUpdate,
    db: DbSession,
    user: AuthenticatedUser,
) -> AssetResponse:
    """Update an asset (full replacement)."""
    result = await db.execute(
        select(Asset).where(Asset.id == asset_id, Asset.deleted_at.is_(None))
    )
    asset = result.scalar_one_or_none()

    if not asset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Asset {asset_id} not found",
        )

    # Update fields
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        # Map 'metadata' field to 'extra_data' on the model
        if field == "metadata":
            setattr(asset, "extra_data", value)
        else:
            setattr(asset, field, value)

    await db.flush()
    await db.refresh(asset)

    return AssetResponse(
        id=asset.id,
        name=asset.name,
        display_name=asset.display_name,
        asset_type=asset.asset_type,
        ip_address=str(asset.ip_address),
        hostname=asset.hostname,
        fqdn=asset.fqdn,
        mac_address=asset.mac_address,
        subnet=str(asset.subnet) if asset.subnet else None,
        vlan_id=asset.vlan_id,
        datacenter=asset.datacenter,
        environment=asset.environment,
        country_code=asset.country_code,
        city=asset.city,
        is_internal=asset.is_internal,
        is_critical=asset.is_critical,
        criticality_score=asset.criticality_score,
        owner=asset.owner,
        team=asset.team,
        external_id=asset.external_id,
        description=asset.description,
        tags=asset.tags,
        metadata=asset.extra_data,
        first_seen=asset.first_seen,
        last_seen=asset.last_seen,
        bytes_in_total=asset.bytes_in_total,
        bytes_out_total=asset.bytes_out_total,
        connections_in=asset.connections_in,
        connections_out=asset.connections_out,
        created_at=asset.created_at,
        updated_at=asset.updated_at,
    )


@router.patch("/{asset_id}", response_model=AssetResponse)
async def patch_asset(
    asset_id: UUID,
    data: AssetUpdate,
    db: DbSession,
    user: AuthenticatedUser,
) -> AssetResponse:
    """Partially update an asset."""
    result = await db.execute(
        select(Asset).where(Asset.id == asset_id, Asset.deleted_at.is_(None))
    )
    asset = result.scalar_one_or_none()

    if not asset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Asset {asset_id} not found",
        )

    # Update only provided fields
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        # Map 'metadata' field to 'extra_data' on the model
        if field == "metadata":
            setattr(asset, "extra_data", value)
        else:
            setattr(asset, field, value)

    await db.flush()
    await db.refresh(asset)

    return AssetResponse(
        id=asset.id,
        name=asset.name,
        display_name=asset.display_name,
        asset_type=asset.asset_type,
        ip_address=str(asset.ip_address),
        hostname=asset.hostname,
        fqdn=asset.fqdn,
        mac_address=asset.mac_address,
        subnet=str(asset.subnet) if asset.subnet else None,
        vlan_id=asset.vlan_id,
        datacenter=asset.datacenter,
        environment=asset.environment,
        country_code=asset.country_code,
        city=asset.city,
        is_internal=asset.is_internal,
        is_critical=asset.is_critical,
        criticality_score=asset.criticality_score,
        owner=asset.owner,
        team=asset.team,
        external_id=asset.external_id,
        description=asset.description,
        tags=asset.tags,
        metadata=asset.extra_data,
        first_seen=asset.first_seen,
        last_seen=asset.last_seen,
        bytes_in_total=asset.bytes_in_total,
        bytes_out_total=asset.bytes_out_total,
        connections_in=asset.connections_in,
        connections_out=asset.connections_out,
        created_at=asset.created_at,
        updated_at=asset.updated_at,
    )


@router.delete("/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_asset(
    asset_id: UUID,
    db: DbSession,
    user: AuthenticatedUser,
) -> None:
    """Soft delete an asset."""
    result = await db.execute(
        select(Asset).where(Asset.id == asset_id, Asset.deleted_at.is_(None))
    )
    asset = result.scalar_one_or_none()

    if not asset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Asset {asset_id} not found",
        )

    asset.soft_delete()
    await db.flush()


@router.get("/{asset_id}/services", response_model=list[ServiceResponse])
async def get_asset_services(
    asset_id: UUID,
    db: DbSession,
    user: AuthenticatedUser,
) -> list[ServiceResponse]:
    """Get services running on an asset."""
    # Verify asset exists
    asset_result = await db.execute(
        select(Asset.id).where(Asset.id == asset_id, Asset.deleted_at.is_(None))
    )
    if not asset_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Asset {asset_id} not found",
        )

    # Get services
    result = await db.execute(
        select(Service)
        .where(Service.asset_id == asset_id)
        .order_by(Service.port)
    )
    services = result.scalars().all()

    return [ServiceResponse.model_validate(s) for s in services]


@router.get("/{asset_id}/dependencies", response_model=list[DependencyWithAssets])
async def get_asset_dependencies(
    asset_id: UUID,
    db: DbSession,
    user: AuthenticatedUser,
    direction: Literal["upstream", "downstream", "both"] = Query("both"),
) -> list[DependencyWithAssets]:
    """Get dependencies for an asset.

    Args:
        asset_id: The asset ID.
        direction: Filter by direction - upstream (assets that connect TO this asset),
                   downstream (assets this asset connects TO), or both.
    """
    # Verify asset exists
    asset_result = await db.execute(
        select(Asset.id).where(Asset.id == asset_id, Asset.deleted_at.is_(None))
    )
    if not asset_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Asset {asset_id} not found",
        )

    # Build query based on direction
    if direction == "upstream":
        # Dependencies where this asset is the target (others connect TO it)
        query = select(Dependency).where(
            Dependency.target_asset_id == asset_id,
            Dependency.valid_to.is_(None),
        )
    elif direction == "downstream":
        # Dependencies where this asset is the source (it connects TO others)
        query = select(Dependency).where(
            Dependency.source_asset_id == asset_id,
            Dependency.valid_to.is_(None),
        )
    else:
        # Both directions
        query = select(Dependency).where(
            or_(
                Dependency.source_asset_id == asset_id,
                Dependency.target_asset_id == asset_id,
            ),
            Dependency.valid_to.is_(None),
        )

    # Load related assets
    query = query.options(
        selectinload(Dependency.source_asset),
        selectinload(Dependency.target_asset),
    ).order_by(Dependency.last_seen.desc())

    result = await db.execute(query)
    dependencies = result.scalars().all()

    # Build response
    response = []
    for dep in dependencies:
        source_info = AssetInfo(
            id=dep.source_asset.id,
            name=dep.source_asset.name,
            ip_address=str(dep.source_asset.ip_address),
            hostname=dep.source_asset.hostname,
            is_critical=dep.source_asset.is_critical,
        )
        target_info = AssetInfo(
            id=dep.target_asset.id,
            name=dep.target_asset.name,
            ip_address=str(dep.target_asset.ip_address),
            hostname=dep.target_asset.hostname,
            is_critical=dep.target_asset.is_critical,
        )

        response.append(DependencyWithAssets(
            id=dep.id,
            source_asset_id=dep.source_asset_id,
            target_asset_id=dep.target_asset_id,
            target_port=dep.target_port,
            protocol=dep.protocol,
            dependency_type=dep.dependency_type,
            is_critical=dep.is_critical,
            is_confirmed=dep.is_confirmed,
            is_ignored=dep.is_ignored,
            description=dep.description,
            tags=dep.tags,
            metadata=dep.extra_data,
            bytes_total=dep.bytes_total,
            packets_total=dep.packets_total,
            flows_total=dep.flows_total,
            bytes_last_24h=dep.bytes_last_24h,
            bytes_last_7d=dep.bytes_last_7d,
            first_seen=dep.first_seen,
            last_seen=dep.last_seen,
            valid_from=dep.valid_from,
            valid_to=dep.valid_to,
            avg_latency_ms=dep.avg_latency_ms,
            p95_latency_ms=dep.p95_latency_ms,
            discovered_by=dep.discovered_by,
            created_at=dep.created_at,
            updated_at=dep.updated_at,
            source_asset=source_info,
            target_asset=target_info,
        ))

    return response

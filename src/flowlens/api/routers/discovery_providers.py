"""Discovery provider management API endpoints.

Admin-only endpoints for configuring discovery providers
(Kubernetes, vCenter, Nutanix).
"""

import math
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from flowlens.api.dependencies import AdminUser, DbSession, Pagination
from flowlens.common.logging import get_logger
from flowlens.common.settings_service import (
    test_kubernetes_connection,
    test_nutanix_connection,
    test_vcenter_connection,
)
from flowlens.common.database import get_session
from flowlens.models.discovery import DiscoveryProvider, DiscoveryProviderType
from flowlens.schemas.discovery_providers import (
    ConnectionTestResponse,
    DiscoveryProviderCreate,
    DiscoveryProviderListResponse,
    DiscoveryProviderResponse,
    DiscoveryProviderSummary,
    DiscoveryProviderUpdate,
    SyncTriggerResponse,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/discovery-providers", tags=["Discovery Providers"])


async def _run_provider_sync(provider_id: uuid.UUID) -> None:
    """Run discovery sync for a provider in background.

    This function is designed to run as a background task, so it gets
    its own database session and handles all errors internally.
    """
    try:
        async with get_session() as db:
            # Re-fetch the provider in this session
            result = await db.execute(
                select(DiscoveryProvider).where(DiscoveryProvider.id == provider_id)
            )
            provider = result.scalar_one_or_none()

            if provider is None:
                logger.error("Provider not found for sync", provider_id=str(provider_id))
                return

            if not provider.is_enabled:
                logger.warning("Provider disabled, skipping sync", provider_id=str(provider_id))
                return

            logger.info(
                "Starting provider sync",
                provider_id=str(provider.id),
                name=provider.name,
                provider_type=provider.provider_type,
            )

            # Run the appropriate sync based on provider type
            if provider.provider_type == DiscoveryProviderType.VCENTER.value:
                from flowlens.discovery.vcenter import VCenterProviderDiscoveryService

                service = VCenterProviderDiscoveryService(provider)
                await service.sync(db)

            elif provider.provider_type == DiscoveryProviderType.KUBERNETES.value:
                from flowlens.discovery.kubernetes import KubernetesProviderDiscoveryService

                service = KubernetesProviderDiscoveryService(provider)
                await service.sync(db)

            elif provider.provider_type == DiscoveryProviderType.NUTANIX.value:
                from flowlens.discovery.nutanix import NutanixProviderDiscoveryService

                service = NutanixProviderDiscoveryService(provider)
                await service.sync(db)

            else:
                logger.error(
                    "Unknown provider type",
                    provider_id=str(provider.id),
                    provider_type=provider.provider_type,
                )
                provider.status = "failed"
                provider.last_error = f"Unknown provider type: {provider.provider_type}"
                provider.last_completed_at = datetime.now(timezone.utc)

            await db.commit()

    except Exception as exc:
        logger.exception(
            "Provider sync failed with unexpected error",
            provider_id=str(provider_id),
            error=str(exc),
        )
        # Try to update status to failed
        try:
            async with get_session() as db:
                result = await db.execute(
                    select(DiscoveryProvider).where(DiscoveryProvider.id == provider_id)
                )
                provider = result.scalar_one_or_none()
                if provider:
                    provider.status = "failed"
                    provider.last_error = str(exc)[:500]
                    provider.last_completed_at = datetime.now(timezone.utc)
                    await db.commit()
        except Exception:
            logger.exception("Failed to update provider status after error")


def _mask_sensitive_config(config: dict | None, provider_type: str) -> dict | None:
    """Mask sensitive fields in type-specific config."""
    if config is None:
        return None

    masked = config.copy()

    # Mask token for Kubernetes
    if provider_type == DiscoveryProviderType.KUBERNETES.value:
        if "token_encrypted" in masked:
            masked["token_encrypted"] = "****" if masked["token_encrypted"] else None
        if "token" in masked:
            masked["token"] = "****" if masked["token"] else None

    return masked


def _provider_to_response(provider: DiscoveryProvider) -> DiscoveryProviderResponse:
    """Convert database model to response schema with masked secrets."""
    return DiscoveryProviderResponse(
        id=provider.id,
        name=provider.name,
        display_name=provider.display_name,
        provider_type=provider.provider_type,
        api_url=provider.api_url,
        username=provider.username,
        has_password=provider.has_password,
        verify_ssl=provider.verify_ssl,
        timeout_seconds=provider.timeout_seconds,
        is_enabled=provider.is_enabled,
        priority=provider.priority,
        sync_interval_minutes=provider.sync_interval_minutes,
        kubernetes_config=_mask_sensitive_config(provider.k8s_config, provider.provider_type),
        vcenter_config=provider.vcenter_config,
        nutanix_config=provider.nutanix_config,
        status=provider.status,
        last_started_at=provider.last_started_at,
        last_completed_at=provider.last_completed_at,
        last_success_at=provider.last_success_at,
        last_error=provider.last_error,
        assets_discovered=provider.assets_discovered,
        applications_discovered=provider.applications_discovered,
        created_at=provider.created_at,
        updated_at=provider.updated_at,
    )


@router.get("", response_model=DiscoveryProviderListResponse)
async def list_discovery_providers(
    _user: AdminUser,
    db: DbSession,
    pagination: Pagination,
    provider_type: str | None = Query(default=None, description="Filter by provider type"),
    is_enabled: bool | None = Query(default=None, description="Filter by enabled status"),
) -> DiscoveryProviderListResponse:
    """List all discovery providers.

    Admin only.
    """
    query = select(DiscoveryProvider)

    # Apply filters
    if provider_type:
        query = query.where(DiscoveryProvider.provider_type == provider_type)
    if is_enabled is not None:
        query = query.where(DiscoveryProvider.is_enabled == is_enabled)

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query) or 0

    # Apply pagination and ordering
    query = (
        query.order_by(DiscoveryProvider.priority.asc(), DiscoveryProvider.created_at.desc())
        .offset(pagination.offset)
        .limit(pagination.page_size)
    )

    result = await db.execute(query)
    providers = list(result.scalars().all())

    return DiscoveryProviderListResponse(
        items=[
            DiscoveryProviderSummary(
                id=p.id,
                name=p.name,
                display_name=p.display_name,
                provider_type=p.provider_type,
                api_url=p.api_url,
                is_enabled=p.is_enabled,
                status=p.status,
                last_success_at=p.last_success_at,
                assets_discovered=p.assets_discovered,
            )
            for p in providers
        ],
        total=total,
    )


@router.post("", response_model=DiscoveryProviderResponse, status_code=status.HTTP_201_CREATED)
async def create_discovery_provider(
    body: DiscoveryProviderCreate,
    _admin: AdminUser,
    db: DbSession,
) -> DiscoveryProviderResponse:
    """Create a new discovery provider.

    Admin only.
    """
    # Check if name already exists
    existing = await db.execute(
        select(DiscoveryProvider).where(DiscoveryProvider.name == body.name)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A provider with this name already exists",
        )

    # Build type-specific config
    k8s_config = None
    vcenter_config = None
    nutanix_config = None

    if body.provider_type == DiscoveryProviderType.KUBERNETES:
        if body.kubernetes_config:
            k8s_config = {
                "cluster_name": body.kubernetes_config.cluster_name,
                "namespace": body.kubernetes_config.namespace,
                "ca_cert": body.kubernetes_config.ca_cert,
            }
            # Store token encrypted (placeholder - implement actual encryption)
            if body.kubernetes_config.token:
                k8s_config["token_encrypted"] = body.kubernetes_config.token  # TODO: encrypt
    elif body.provider_type == DiscoveryProviderType.VCENTER:
        if body.vcenter_config:
            vcenter_config = {
                "include_tags": body.vcenter_config.include_tags,
            }
    elif body.provider_type == DiscoveryProviderType.NUTANIX:
        if body.nutanix_config:
            nutanix_config = {}

    # Create provider
    provider = DiscoveryProvider(
        name=body.name,
        display_name=body.display_name,
        provider_type=body.provider_type.value,
        api_url=body.api_url,
        username=body.username,
        password_encrypted=body.password if body.password else None,  # TODO: encrypt
        verify_ssl=body.verify_ssl,
        timeout_seconds=body.timeout_seconds,
        is_enabled=body.is_enabled,
        priority=body.priority,
        sync_interval_minutes=body.sync_interval_minutes,
        k8s_config=k8s_config,
        vcenter_config=vcenter_config,
        nutanix_config=nutanix_config,
    )

    db.add(provider)
    await db.commit()
    await db.refresh(provider)

    logger.info(
        "Discovery provider created",
        provider_id=str(provider.id),
        provider_type=provider.provider_type,
        name=provider.name,
    )

    return _provider_to_response(provider)


@router.get("/{provider_id}", response_model=DiscoveryProviderResponse)
async def get_discovery_provider(
    provider_id: uuid.UUID,
    _admin: AdminUser,
    db: DbSession,
) -> DiscoveryProviderResponse:
    """Get a discovery provider by ID.

    Admin only.
    """
    result = await db.execute(
        select(DiscoveryProvider).where(DiscoveryProvider.id == provider_id)
    )
    provider = result.scalar_one_or_none()

    if provider is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Discovery provider not found",
        )

    return _provider_to_response(provider)


@router.patch("/{provider_id}", response_model=DiscoveryProviderResponse)
async def update_discovery_provider(
    provider_id: uuid.UUID,
    body: DiscoveryProviderUpdate,
    _admin: AdminUser,
    db: DbSession,
) -> DiscoveryProviderResponse:
    """Update a discovery provider.

    Admin only.
    """
    result = await db.execute(
        select(DiscoveryProvider).where(DiscoveryProvider.id == provider_id)
    )
    provider = result.scalar_one_or_none()

    if provider is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Discovery provider not found",
        )

    # Update fields if provided
    if body.name is not None:
        # Check if new name is already in use
        if body.name != provider.name:
            existing = await db.execute(
                select(DiscoveryProvider).where(
                    DiscoveryProvider.name == body.name,
                    DiscoveryProvider.id != provider_id,
                )
            )
            if existing.scalar_one_or_none():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="A provider with this name already exists",
                )
        provider.name = body.name

    if body.display_name is not None:
        provider.display_name = body.display_name if body.display_name else None

    if body.api_url is not None:
        provider.api_url = body.api_url

    if body.username is not None:
        provider.username = body.username if body.username else None

    if body.password is not None and body.password != "":
        provider.password_encrypted = body.password  # TODO: encrypt

    if body.verify_ssl is not None:
        provider.verify_ssl = body.verify_ssl

    if body.timeout_seconds is not None:
        provider.timeout_seconds = body.timeout_seconds

    if body.is_enabled is not None:
        provider.is_enabled = body.is_enabled

    if body.priority is not None:
        provider.priority = body.priority

    if body.sync_interval_minutes is not None:
        provider.sync_interval_minutes = body.sync_interval_minutes

    # Update type-specific configs
    if body.kubernetes_config is not None and provider.is_kubernetes:
        k8s_config = provider.k8s_config or {}
        k8s_config["cluster_name"] = body.kubernetes_config.cluster_name
        k8s_config["namespace"] = body.kubernetes_config.namespace
        k8s_config["ca_cert"] = body.kubernetes_config.ca_cert
        if body.kubernetes_config.token:
            k8s_config["token_encrypted"] = body.kubernetes_config.token  # TODO: encrypt
        provider.k8s_config = k8s_config

    if body.vcenter_config is not None and provider.is_vcenter:
        provider.vcenter_config = {
            "include_tags": body.vcenter_config.include_tags,
        }

    if body.nutanix_config is not None and provider.is_nutanix:
        provider.nutanix_config = {}

    await db.commit()
    await db.refresh(provider)

    logger.info(
        "Discovery provider updated",
        provider_id=str(provider.id),
        name=provider.name,
    )

    return _provider_to_response(provider)


@router.delete("/{provider_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_discovery_provider(
    provider_id: uuid.UUID,
    _admin: AdminUser,
    db: DbSession,
) -> None:
    """Delete a discovery provider.

    Admin only.
    """
    result = await db.execute(
        select(DiscoveryProvider).where(DiscoveryProvider.id == provider_id)
    )
    provider = result.scalar_one_or_none()

    if provider is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Discovery provider not found",
        )

    logger.info(
        "Discovery provider deleted",
        provider_id=str(provider.id),
        name=provider.name,
    )

    await db.delete(provider)
    await db.commit()


@router.post("/{provider_id}/enable", response_model=DiscoveryProviderResponse)
async def enable_discovery_provider(
    provider_id: uuid.UUID,
    _admin: AdminUser,
    db: DbSession,
) -> DiscoveryProviderResponse:
    """Enable a discovery provider.

    Admin only.
    """
    result = await db.execute(
        select(DiscoveryProvider).where(DiscoveryProvider.id == provider_id)
    )
    provider = result.scalar_one_or_none()

    if provider is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Discovery provider not found",
        )

    provider.is_enabled = True

    await db.commit()
    await db.refresh(provider)

    logger.info(
        "Discovery provider enabled",
        provider_id=str(provider.id),
        name=provider.name,
    )

    return _provider_to_response(provider)


@router.post("/{provider_id}/disable", response_model=DiscoveryProviderResponse)
async def disable_discovery_provider(
    provider_id: uuid.UUID,
    _admin: AdminUser,
    db: DbSession,
) -> DiscoveryProviderResponse:
    """Disable a discovery provider.

    Admin only.
    """
    result = await db.execute(
        select(DiscoveryProvider).where(DiscoveryProvider.id == provider_id)
    )
    provider = result.scalar_one_or_none()

    if provider is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Discovery provider not found",
        )

    provider.is_enabled = False

    await db.commit()
    await db.refresh(provider)

    logger.info(
        "Discovery provider disabled",
        provider_id=str(provider.id),
        name=provider.name,
    )

    return _provider_to_response(provider)


@router.post("/{provider_id}/test", response_model=ConnectionTestResponse)
async def test_discovery_provider(
    provider_id: uuid.UUID,
    _admin: AdminUser,
    db: DbSession,
) -> ConnectionTestResponse:
    """Test connection to a discovery provider.

    Admin only.
    """
    result = await db.execute(
        select(DiscoveryProvider).where(DiscoveryProvider.id == provider_id)
    )
    provider = result.scalar_one_or_none()

    if provider is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Discovery provider not found",
        )

    # Build test values from provider config
    test_values = {
        "api_url": provider.api_url,
        "api_server": provider.api_url,  # K8s uses api_server
        "username": provider.username,
        "password": provider.password_encrypted,  # TODO: decrypt
        "verify_ssl": provider.verify_ssl,
        "timeout_seconds": provider.timeout_seconds,
    }

    # Add type-specific values
    if provider.is_kubernetes and provider.k8s_config:
        test_values["token"] = provider.k8s_config.get("token_encrypted")  # TODO: decrypt

    # Run test based on provider type
    if provider.provider_type == DiscoveryProviderType.KUBERNETES.value:
        success, message, details = await test_kubernetes_connection(test_values)
    elif provider.provider_type == DiscoveryProviderType.VCENTER.value:
        success, message, details = await test_vcenter_connection(test_values)
    elif provider.provider_type == DiscoveryProviderType.NUTANIX.value:
        success, message, details = await test_nutanix_connection(test_values)
    else:
        success, message, details = False, f"Unknown provider type: {provider.provider_type}", None

    logger.info(
        "Discovery provider connection test",
        provider_id=str(provider.id),
        name=provider.name,
        success=success,
    )

    return ConnectionTestResponse(
        success=success,
        message=message,
        details=details,
    )


@router.post("/{provider_id}/sync", response_model=SyncTriggerResponse)
async def trigger_discovery_sync(
    provider_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    _admin: AdminUser,
    db: DbSession,
) -> SyncTriggerResponse:
    """Trigger a manual discovery sync for a provider.

    Admin only. This queues a sync job to run immediately in the background.
    """
    result = await db.execute(
        select(DiscoveryProvider).where(DiscoveryProvider.id == provider_id)
    )
    provider = result.scalar_one_or_none()

    if provider is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Discovery provider not found",
        )

    if not provider.is_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot sync disabled provider",
        )

    if provider.status == "running":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Sync already in progress",
        )

    # Update status to indicate sync is starting
    provider.status = "running"
    provider.last_started_at = datetime.now(timezone.utc)
    provider.last_error = None

    await db.commit()

    # Queue the sync to run in background
    background_tasks.add_task(_run_provider_sync, provider_id)

    logger.info(
        "Discovery sync triggered",
        provider_id=str(provider.id),
        name=provider.name,
    )

    return SyncTriggerResponse(
        success=True,
        message=f"Sync triggered for {provider.name}",
        provider_id=provider.id,
    )

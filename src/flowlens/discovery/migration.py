"""Auto-migration of discovery provider settings from environment variables to database.

On startup, checks for enabled discovery providers in environment variables and
creates corresponding database entries if they don't already exist. This provides
backward compatibility with the original single-instance configuration approach.
"""

from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from flowlens.common.config import (
    KubernetesSettings,
    NutanixSettings,
    Settings,
    VCenterSettings,
    get_settings,
)
from flowlens.common.database import get_session
from flowlens.common.logging import get_logger
from flowlens.models.discovery import DiscoveryProvider

logger = get_logger(__name__)

# Default names for auto-migrated providers
K8S_DEFAULT_NAME = "kubernetes-env"
VCENTER_DEFAULT_NAME = "vcenter-env"
NUTANIX_DEFAULT_NAME = "nutanix-env"


async def _provider_exists(db: AsyncSession, name: str) -> bool:
    """Check if a provider with the given name already exists."""
    result = await db.execute(
        select(DiscoveryProvider).where(DiscoveryProvider.name == name)
    )
    return result.scalar_one_or_none() is not None


async def _migrate_kubernetes(db: AsyncSession, settings: KubernetesSettings) -> UUID | None:
    """Migrate Kubernetes settings to database provider."""
    if not settings.enabled:
        return None

    name = K8S_DEFAULT_NAME
    if await _provider_exists(db, name):
        logger.debug("Kubernetes provider already exists, skipping migration", name=name)
        return None

    # Read token from file if not provided directly
    token = settings.token
    if not token and settings.token_file and settings.token_file.exists():
        try:
            token = settings.token_file.read_text().strip()
        except Exception as e:
            logger.warning("Failed to read Kubernetes token file", error=str(e))

    # Read CA cert if path provided
    ca_cert = None
    if settings.ca_cert_path and settings.ca_cert_path.exists():
        try:
            ca_cert = settings.ca_cert_path.read_text()
        except Exception as e:
            logger.warning("Failed to read Kubernetes CA cert", error=str(e))

    # Build K8s config
    k8s_config = {
        "cluster_name": settings.cluster_name,
        "namespace": settings.namespace,
        "token_encrypted": token,  # TODO: encrypt
        "ca_cert": ca_cert,
    }

    provider = DiscoveryProvider(
        name=name,
        display_name=f"Kubernetes ({settings.cluster_name})",
        provider_type="kubernetes",
        api_url=settings.api_server,
        verify_ssl=settings.verify_ssl,
        timeout_seconds=settings.timeout_seconds,
        k8s_config=k8s_config,
        is_enabled=True,
        priority=100,
        sync_interval_minutes=15,
    )

    db.add(provider)
    await db.flush()

    logger.info(
        "Migrated Kubernetes settings to database provider",
        provider_id=str(provider.id),
        name=name,
        cluster_name=settings.cluster_name,
    )

    return provider.id


async def _migrate_vcenter(db: AsyncSession, settings: VCenterSettings) -> UUID | None:
    """Migrate vCenter settings to database provider."""
    if not settings.enabled:
        return None

    name = VCENTER_DEFAULT_NAME
    if await _provider_exists(db, name):
        logger.debug("vCenter provider already exists, skipping migration", name=name)
        return None

    # Get password from SecretStr
    password = settings.password.get_secret_value() if settings.password else None

    # Build vCenter config
    vcenter_config = {
        "include_tags": settings.include_tags,
    }

    provider = DiscoveryProvider(
        name=name,
        display_name=f"vCenter ({settings.api_url})",
        provider_type="vcenter",
        api_url=settings.api_url,
        username=settings.username,
        password_encrypted=password,  # TODO: encrypt
        verify_ssl=settings.verify_ssl,
        timeout_seconds=settings.timeout_seconds,
        vcenter_config=vcenter_config,
        is_enabled=True,
        priority=100,
        sync_interval_minutes=15,
    )

    db.add(provider)
    await db.flush()

    logger.info(
        "Migrated vCenter settings to database provider",
        provider_id=str(provider.id),
        name=name,
        api_url=settings.api_url,
    )

    return provider.id


async def _migrate_nutanix(db: AsyncSession, settings: NutanixSettings) -> UUID | None:
    """Migrate Nutanix settings to database provider."""
    if not settings.enabled:
        return None

    name = NUTANIX_DEFAULT_NAME
    if await _provider_exists(db, name):
        logger.debug("Nutanix provider already exists, skipping migration", name=name)
        return None

    # Get password from SecretStr
    password = settings.password.get_secret_value() if settings.password else None

    provider = DiscoveryProvider(
        name=name,
        display_name=f"Nutanix ({settings.api_url})",
        provider_type="nutanix",
        api_url=settings.api_url,
        username=settings.username,
        password_encrypted=password,  # TODO: encrypt
        verify_ssl=settings.verify_ssl,
        timeout_seconds=settings.timeout_seconds,
        nutanix_config={},  # No special config for Nutanix yet
        is_enabled=True,
        priority=100,
        sync_interval_minutes=15,
    )

    db.add(provider)
    await db.flush()

    logger.info(
        "Migrated Nutanix settings to database provider",
        provider_id=str(provider.id),
        name=name,
        api_url=settings.api_url,
    )

    return provider.id


async def migrate_env_providers(db: AsyncSession | None = None) -> dict[str, UUID | None]:
    """Migrate all enabled discovery providers from environment variables to database.

    This function checks for enabled discovery providers in environment variables
    and creates corresponding database entries if they don't already exist.

    Args:
        db: Optional database session. If not provided, creates a new session.

    Returns:
        Dictionary mapping provider type to the created provider ID (or None if skipped).
    """
    settings = get_settings()
    results: dict[str, UUID | None] = {
        "kubernetes": None,
        "vcenter": None,
        "nutanix": None,
    }

    # Use provided session or create new one
    if db is not None:
        # Migrate each provider type
        results["kubernetes"] = await _migrate_kubernetes(db, settings.kubernetes)
        results["vcenter"] = await _migrate_vcenter(db, settings.vcenter)
        results["nutanix"] = await _migrate_nutanix(db, settings.nutanix)
        await db.commit()
    else:
        async with get_session() as session:
            results["kubernetes"] = await _migrate_kubernetes(session, settings.kubernetes)
            results["vcenter"] = await _migrate_vcenter(session, settings.vcenter)
            results["nutanix"] = await _migrate_nutanix(session, settings.nutanix)
            await session.commit()

    migrated = [k for k, v in results.items() if v is not None]
    if migrated:
        logger.info(
            "Completed discovery provider migration",
            migrated_providers=migrated,
        )
    else:
        logger.debug("No discovery providers to migrate from environment variables")

    return results

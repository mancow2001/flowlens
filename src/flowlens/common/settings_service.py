"""Settings management service.

Handles reading, updating, and persisting application settings.

In Docker deployments, settings are stored in the database since .env files
are not writable. For local development, settings can be written to .env.
"""

import json
import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from flowlens.common.config import Settings, get_settings
from flowlens.common.logging import get_logger
from flowlens.schemas.settings import (
    FieldType,
    SettingsSectionData,
    SettingsSectionInfo,
    SettingsValue,
    get_all_sections,
    get_section_by_key,
)

logger = get_logger(__name__)

# Path to .env file (may not be writable in Docker)
ENV_FILE_PATH = Path(__file__).parent.parent.parent.parent / ".env"

# Track if restart is required
_restart_required = False

# In-memory override store for Docker environments
# These overrides are applied when get_settings() is called
_settings_overrides: dict[str, str] = {}


def _get_nested_attr(obj: Any, path: str) -> Any:
    """Get a nested attribute using dot notation.

    Args:
        obj: Object to get attribute from.
        path: Dot-separated path (e.g., "database.host").

    Returns:
        The attribute value.
    """
    parts = path.split(".")
    for part in parts:
        obj = getattr(obj, part, None)
        if obj is None:
            return None
    return obj


def _get_section_object(settings: Settings, section_key: str) -> Any:
    """Get the settings object for a section.

    Args:
        settings: Main settings object.
        section_key: Section key.

    Returns:
        The section settings object.
    """
    mapping = {
        "application": settings,
        "database": settings.database,
        "redis": settings.redis,
        "kafka": settings.kafka,
        "ingestion": settings.ingestion,
        "enrichment": settings.enrichment,
        "resolution": settings.resolution,
        "classification": settings.classification,
        "api": settings.api,
        "auth": settings.auth,
        "logging": settings.logging,
        "email": settings.notifications.email,
        "webhook": settings.notifications.webhook,
        "slack": settings.notifications.slack,
        "teams": settings.notifications.teams,
        "pagerduty": settings.notifications.pagerduty,
    }
    return mapping.get(section_key)


def _mask_secret(value: Any) -> str:
    """Mask a secret value for display.

    Args:
        value: The secret value.

    Returns:
        Masked string.
    """
    if value is None:
        return ""
    if isinstance(value, SecretStr):
        secret = value.get_secret_value()
        if not secret:
            return ""
        return "****" + secret[-4:] if len(secret) > 4 else "****"
    return "****"


def get_current_value(section_key: str, field_name: str) -> tuple[Any, bool]:
    """Get the current value of a setting.

    Args:
        section_key: Section key.
        field_name: Field name.

    Returns:
        Tuple of (value, is_default).
    """
    settings = get_settings()
    section_obj = _get_section_object(settings, section_key)

    if section_obj is None:
        return None, True

    value = getattr(section_obj, field_name, None)

    # Handle special types
    if isinstance(value, SecretStr):
        # Check if it's still the default
        section_info = get_section_by_key(section_key)
        if section_info:
            for field in section_info.fields:
                if field.name == field_name:
                    default = field.default
                    if default and isinstance(value, SecretStr):
                        is_default = value.get_secret_value() == str(default)
                    else:
                        is_default = value is None
                    return _mask_secret(value), is_default

    if isinstance(value, Path):
        value = str(value) if value else None

    if hasattr(value, "__str__") and not isinstance(value, (str, int, float, bool, list)):
        value = str(value)

    # Convert lists to comma-separated strings for display
    if isinstance(value, list):
        value = ",".join(str(v) for v in value)

    # Get default from section info
    section_info = get_section_by_key(section_key)
    if section_info:
        for field in section_info.fields:
            if field.name == field_name:
                is_default = value == field.default
                return value, is_default

    return value, False


def get_section_data(section_key: str) -> SettingsSectionData | None:
    """Get current values for a settings section.

    Args:
        section_key: Section key.

    Returns:
        Section data with current values, or None if section not found.
    """
    section_info = get_section_by_key(section_key)
    if not section_info:
        return None

    values = []
    for field in section_info.fields:
        value, is_default = get_current_value(section_key, field.name)
        values.append(SettingsValue(
            name=field.name,
            value=value,
            is_default=is_default,
        ))

    return SettingsSectionData(key=section_key, values=values)


def get_all_section_data() -> list[SettingsSectionData]:
    """Get current values for all settings sections.

    Returns:
        List of section data with current values.
    """
    sections = []
    for section_info in get_all_sections():
        section_data = get_section_data(section_info.key)
        if section_data:
            sections.append(section_data)
    return sections


def read_env_file() -> dict[str, str]:
    """Read the .env file and parse key-value pairs.

    Returns:
        Dictionary of environment variable names to values.
    """
    env_vars = {}

    if not ENV_FILE_PATH.exists():
        logger.warning("No .env file found", path=str(ENV_FILE_PATH))
        return env_vars

    with open(ENV_FILE_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            # Skip comments and empty lines
            if not line or line.startswith("#"):
                continue
            # Parse key=value
            if "=" in line:
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip()
                # Remove quotes if present
                if value.startswith('"') and value.endswith('"'):
                    value = value[1:-1]
                elif value.startswith("'") and value.endswith("'"):
                    value = value[1:-1]
                env_vars[key] = value

    return env_vars


def write_env_file(updates: dict[str, str]) -> None:
    """Update the .env file with new values.

    Args:
        updates: Dictionary of env var names to new values.
    """
    # Read existing content
    lines = []
    if ENV_FILE_PATH.exists():
        with open(ENV_FILE_PATH, "r", encoding="utf-8") as f:
            lines = f.readlines()

    # Track which keys we've updated
    updated_keys = set()

    # Update existing lines
    new_lines = []
    for line in lines:
        stripped = line.strip()

        # Keep comments and empty lines
        if not stripped or stripped.startswith("#"):
            new_lines.append(line)
            continue

        # Check if this line has a key we're updating
        if "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key in updates:
                # Replace the value
                value = updates[key]
                # Quote values with spaces or special characters
                if " " in str(value) or "," in str(value):
                    new_lines.append(f'{key}="{value}"\n')
                else:
                    new_lines.append(f"{key}={value}\n")
                updated_keys.add(key)
                continue

        new_lines.append(line)

    # Add new keys that weren't in the file
    for key, value in updates.items():
        if key not in updated_keys:
            if " " in str(value) or "," in str(value):
                new_lines.append(f'{key}="{value}"\n')
            else:
                new_lines.append(f"{key}={value}\n")

    # Write back
    with open(ENV_FILE_PATH, "w", encoding="utf-8") as f:
        f.writelines(new_lines)

    logger.info("Updated .env file", updated_keys=list(updates.keys()))


def update_section_settings(
    section_key: str,
    values: dict[str, Any],
    user_id: str | None = None,
) -> tuple[bool, list[str], bool, bool]:
    """Update settings for a section.

    Args:
        section_key: Section key.
        values: Dictionary of field names to new values.
        user_id: ID of user making the change (for audit).

    Returns:
        Tuple of (success, updated_fields, restart_required, docker_mode).
    """
    global _restart_required

    section_info = get_section_by_key(section_key)
    if not section_info:
        return False, [], False, False

    # Build env var updates
    env_updates = {}
    updated_fields = []

    for field in section_info.fields:
        if field.name not in values:
            continue

        new_value = values[field.name]

        # Skip empty values for secret fields (keep existing)
        if field.is_secret and (new_value is None or new_value == "" or new_value == "****"):
            continue

        # Convert value to string for .env file
        if isinstance(new_value, bool):
            env_value = "true" if new_value else "false"
        elif isinstance(new_value, list):
            env_value = ",".join(str(v) for v in new_value)
        elif new_value is None:
            env_value = ""
        else:
            env_value = str(new_value)

        env_updates[field.env_var] = env_value
        updated_fields.append(field.name)

    if not env_updates:
        return True, [], False, False

    # Try to write to .env file first
    env_file_written = False
    try:
        write_env_file(env_updates)
        env_file_written = True
        logger.info("Settings written to .env file")
    except PermissionError:
        # Docker environment - .env file not writable
        # Store in memory and apply to environment
        logger.info(
            "Cannot write to .env file (Docker environment), "
            "storing settings in memory. Changes require container restart."
        )
        for key, value in env_updates.items():
            _settings_overrides[key] = value
            # Also set in current process environment
            os.environ[key] = value
    except Exception as e:
        logger.error("Failed to write .env file", error=str(e))
        # Still try to apply to environment
        for key, value in env_updates.items():
            _settings_overrides[key] = value
            os.environ[key] = value

    # Clear the settings cache so new values are picked up
    get_settings.cache_clear()

    # Check if restart is required
    # In Docker, settings changes always require container restart to persist
    needs_restart = section_info.restart_required and len(updated_fields) > 0
    if not env_file_written:
        # Docker mode - restart always required for persistence
        needs_restart = True

    if needs_restart:
        _restart_required = True

    docker_mode = not env_file_written

    logger.info(
        "Updated settings",
        section=section_key,
        fields=updated_fields,
        restart_required=needs_restart,
        docker_mode=docker_mode,
        user=user_id,
    )

    return True, updated_fields, needs_restart, docker_mode


def get_pending_overrides() -> dict[str, str]:
    """Get all pending settings overrides (for Docker mode).

    Returns:
        Dictionary of env var names to values.
    """
    return _settings_overrides.copy()


def generate_docker_compose_yaml() -> str:
    """Generate a docker-compose.yml with current settings.

    Reads the current settings (including any pending overrides) and
    generates a complete docker-compose.yml file with YAML anchors
    for shared environment variables.

    Returns:
        YAML string of the docker-compose configuration.
    """
    settings = get_settings()

    # Helper to escape special characters for docker-compose
    # $ must be escaped as $$ to prevent variable interpolation
    def esc(value: str | None) -> str:
        if value is None:
            return ""
        return str(value).replace("$", "$$")

    # Apply any pending overrides (with escaping for docker-compose)
    def get_val(env_key: str, default: str) -> str:
        return esc(_settings_overrides.get(env_key, default))

    # Get current values (with overrides applied)
    # All string values are escaped to handle $ and other special chars in passwords
    postgres_host = "postgres"
    postgres_port = get_val("POSTGRES_PORT", str(settings.database.port))
    postgres_user = get_val("POSTGRES_USER", settings.database.user)
    postgres_password = esc(
        _settings_overrides.get("POSTGRES_PASSWORD", settings.database.password.get_secret_value())
    )
    postgres_db = get_val("POSTGRES_DATABASE", settings.database.database)

    log_level = get_val("LOG_LEVEL", settings.logging.level)
    log_format = get_val("LOG_FORMAT", settings.logging.format)

    environment = get_val("ENVIRONMENT", settings.environment)
    debug = get_val("DEBUG", str(settings.debug).lower())

    # Classification settings
    class_worker_count = get_val("CLASSIFICATION_WORKER_COUNT", str(settings.classification.worker_count))
    class_poll_interval = get_val("CLASSIFICATION_POLL_INTERVAL_MS", str(settings.classification.poll_interval_ms))
    class_auto_confidence = get_val("CLASSIFICATION_AUTO_UPDATE_CONFIDENCE_THRESHOLD", str(settings.classification.auto_update_confidence_threshold))
    class_min_hours = get_val("CLASSIFICATION_MIN_OBSERVATION_HOURS", str(settings.classification.min_observation_hours))
    class_min_flows = get_val("CLASSIFICATION_MIN_FLOWS_REQUIRED", str(settings.classification.min_flows_required))
    class_batch_size = get_val("CLASSIFICATION_BATCH_SIZE", str(settings.classification.batch_size))
    class_high_confidence = get_val("CLASSIFICATION_HIGH_CONFIDENCE_THRESHOLD", str(settings.classification.high_confidence_threshold))
    class_reclassify_hours = get_val("CLASSIFICATION_RECLASSIFY_INTERVAL_HOURS", str(settings.classification.reclassify_interval_hours))

    # API settings
    api_host = get_val("API_HOST", settings.api.host)
    api_port = get_val("API_PORT", str(settings.api.port))
    api_workers = get_val("API_WORKERS", str(settings.api.workers))
    auth_enabled = get_val("AUTH_ENABLED", str(settings.auth.enabled).lower())

    # API additional settings
    api_cors_origins = get_val("API_CORS_ORIGINS", settings.api.cors_origins_str)

    # Auth settings
    auth_secret_key = esc(
        _settings_overrides.get("AUTH_SECRET_KEY", settings.auth.secret_key.get_secret_value())
    )

    # Ingestion settings
    ingestion_bind = get_val("INGESTION_BIND_ADDRESS", str(settings.ingestion.bind_address))
    ingestion_netflow_port = get_val("INGESTION_NETFLOW_PORT", str(settings.ingestion.netflow_port))
    ingestion_sflow_port = get_val("INGESTION_SFLOW_PORT", str(settings.ingestion.sflow_port))
    ingestion_batch_size = get_val("INGESTION_BATCH_SIZE", str(settings.ingestion.batch_size))
    ingestion_batch_timeout = get_val("INGESTION_BATCH_TIMEOUT_MS", str(settings.ingestion.batch_timeout_ms))
    ingestion_queue_max = get_val("INGESTION_QUEUE_MAX_SIZE", str(settings.ingestion.queue_max_size))
    ingestion_sample_threshold = get_val("INGESTION_SAMPLE_THRESHOLD", str(settings.ingestion.sample_threshold))
    ingestion_drop_threshold = get_val("INGESTION_DROP_THRESHOLD", str(settings.ingestion.drop_threshold))
    ingestion_sample_rate = get_val("INGESTION_SAMPLE_RATE", str(settings.ingestion.sample_rate))

    # Enrichment settings
    enrichment_worker_count = get_val("ENRICHMENT_WORKER_COUNT", str(settings.enrichment.worker_count))
    enrichment_batch_size = get_val("ENRICHMENT_BATCH_SIZE", str(settings.enrichment.batch_size))
    enrichment_poll_interval = get_val("ENRICHMENT_POLL_INTERVAL_MS", str(settings.enrichment.poll_interval_ms))
    enrichment_dns_timeout = get_val("ENRICHMENT_DNS_TIMEOUT", str(settings.enrichment.dns_timeout))
    enrichment_dns_cache_ttl = get_val("ENRICHMENT_DNS_CACHE_TTL", str(settings.enrichment.dns_cache_ttl))
    enrichment_dns_cache_size = get_val("ENRICHMENT_DNS_CACHE_SIZE", str(settings.enrichment.dns_cache_size))

    # Resolution settings
    resolution_worker_count = get_val("RESOLUTION_WORKER_COUNT", str(settings.resolution.worker_count))
    resolution_window_minutes = get_val("RESOLUTION_WINDOW_SIZE_MINUTES", str(settings.resolution.window_size_minutes))
    resolution_batch_size = get_val("RESOLUTION_BATCH_SIZE", str(settings.resolution.batch_size))
    resolution_poll_interval = get_val("RESOLUTION_POLL_INTERVAL_MS", str(settings.resolution.poll_interval_ms))
    resolution_stale_threshold = get_val("RESOLUTION_STALE_THRESHOLD_HOURS", str(settings.resolution.stale_threshold_hours))
    resolution_exclude_external_ips = get_val(
        "RESOLUTION_EXCLUDE_EXTERNAL_IPS", str(settings.resolution.exclude_external_ips).lower()
    )
    resolution_exclude_external_sources = get_val(
        "RESOLUTION_EXCLUDE_EXTERNAL_SOURCES", str(settings.resolution.exclude_external_sources).lower()
    )
    resolution_exclude_external_targets = get_val(
        "RESOLUTION_EXCLUDE_EXTERNAL_TARGETS", str(settings.resolution.exclude_external_targets).lower()
    )

    # Redis settings
    redis_enabled = get_val("REDIS_ENABLED", str(settings.redis.enabled).lower()) == "true"
    redis_port = get_val("REDIS_PORT", str(settings.redis.port))

    # Build the YAML manually to use anchors properly
    lines = [
        "# FlowLens Docker Compose - Minimal Configuration",
        "# PostgreSQL only, suitable for <10k flows/sec",
        f"# Generated from System Settings on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "# Shared environment variable definitions",
        "x-db-env: &db-env",
        f"  POSTGRES_HOST: {postgres_host}",
        f"  POSTGRES_PORT: {postgres_port}",
        f"  POSTGRES_USER: {postgres_user}",
        f"  POSTGRES_PASSWORD: {postgres_password}",
        f"  POSTGRES_DATABASE: {postgres_db}",
        "",
        "x-logging-env: &logging-env",
        f"  LOG_LEVEL: {log_level}",
        f"  LOG_FORMAT: {log_format}",
        "",
        "x-classification-env: &classification-env",
        f'  CLASSIFICATION_WORKER_COUNT: "{class_worker_count}"',
        f'  CLASSIFICATION_POLL_INTERVAL_MS: "{class_poll_interval}"',
        f'  CLASSIFICATION_AUTO_UPDATE_CONFIDENCE_THRESHOLD: "{class_auto_confidence}"',
        f'  CLASSIFICATION_MIN_OBSERVATION_HOURS: "{class_min_hours}"',
        f'  CLASSIFICATION_MIN_FLOWS_REQUIRED: "{class_min_flows}"',
        f'  CLASSIFICATION_BATCH_SIZE: "{class_batch_size}"',
        f'  CLASSIFICATION_HIGH_CONFIDENCE_THRESHOLD: "{class_high_confidence}"',
        f'  CLASSIFICATION_RECLASSIFY_INTERVAL_HOURS: "{class_reclassify_hours}"',
        "",
        "# Combined environments for services that need multiple anchors",
        "x-db-logging-env: &db-logging-env",
        f"  POSTGRES_HOST: {postgres_host}",
        f"  POSTGRES_PORT: {postgres_port}",
        f"  POSTGRES_USER: {postgres_user}",
        f"  POSTGRES_PASSWORD: {postgres_password}",
        f"  POSTGRES_DATABASE: {postgres_db}",
        f"  LOG_LEVEL: {log_level}",
        f"  LOG_FORMAT: {log_format}",
        "",
        "x-classification-full-env: &classification-full-env",
        f"  POSTGRES_HOST: {postgres_host}",
        f"  POSTGRES_PORT: {postgres_port}",
        f"  POSTGRES_USER: {postgres_user}",
        f"  POSTGRES_PASSWORD: {postgres_password}",
        f"  POSTGRES_DATABASE: {postgres_db}",
        f'  CLASSIFICATION_WORKER_COUNT: "{class_worker_count}"',
        f'  CLASSIFICATION_POLL_INTERVAL_MS: "{class_poll_interval}"',
        f'  CLASSIFICATION_AUTO_UPDATE_CONFIDENCE_THRESHOLD: "{class_auto_confidence}"',
        f'  CLASSIFICATION_MIN_OBSERVATION_HOURS: "{class_min_hours}"',
        f'  CLASSIFICATION_MIN_FLOWS_REQUIRED: "{class_min_flows}"',
        f'  CLASSIFICATION_BATCH_SIZE: "{class_batch_size}"',
        f'  CLASSIFICATION_HIGH_CONFIDENCE_THRESHOLD: "{class_high_confidence}"',
        f'  CLASSIFICATION_RECLASSIFY_INTERVAL_HOURS: "{class_reclassify_hours}"',
        f"  LOG_LEVEL: {log_level}",
        f"  LOG_FORMAT: {log_format}",
        "",
        "services:",
        "  # PostgreSQL Database",
        "  postgres:",
        "    image: postgres:15-alpine",
        "    container_name: flowlens-postgres",
        "    environment:",
        f"      POSTGRES_USER: {postgres_user}",
        f"      POSTGRES_PASSWORD: {postgres_password}",
        f"      POSTGRES_DB: {postgres_db}",
        "    volumes:",
        "      - postgres_data:/var/lib/postgresql/data",
        "    ports:",
        f'      - "{postgres_port}:5432"',
        "    healthcheck:",
        f'      test: ["CMD-SHELL", "pg_isready -U {postgres_user}"]',
        "      interval: 10s",
        "      timeout: 5s",
        "      retries: 5",
        "    restart: unless-stopped",
        "",
        "  # Database migrations",
        "  migrations:",
        "    build:",
        "      context: .",
        "      target: production",
        "    container_name: flowlens-migrations",
        '    command: ["alembic", "upgrade", "head"]',
        "    environment:",
        "      <<: *db-env",
        "    depends_on:",
        "      postgres:",
        "        condition: service_healthy",
        "",
        "  # API Service",
        "  api:",
        "    build:",
        "      context: .",
        "      target: production",
        "    container_name: flowlens-api",
        '    command: ["python", "-m", "flowlens.api.main"]',
        "    environment:",
        f"      ENVIRONMENT: {environment}",
        f'      DEBUG: "{debug}"',
        "      <<: *db-env",
        f'      API_HOST: "{api_host}"',
        f'      API_PORT: "{api_port}"',
        f'      API_WORKERS: "{api_workers}"',
        f'      API_CORS_ORIGINS: "{api_cors_origins}"',
        f'      AUTH_ENABLED: "{auth_enabled}"',
        f'      AUTH_SECRET_KEY: "{auth_secret_key}"',
        f'      CLASSIFICATION_MIN_OBSERVATION_HOURS: "{class_min_hours}"',
        f'      CLASSIFICATION_MIN_FLOWS_REQUIRED: "{class_min_flows}"',
        f"      LOG_LEVEL: {log_level}",
        f"      LOG_FORMAT: {log_format}",
        "    ports:",
        f'      - "{api_port}:8000"',
        "    depends_on:",
        "      migrations:",
        "        condition: service_completed_successfully",
        "    healthcheck:",
        '      test: ["CMD", "python", "-c", "import httpx; httpx.get(\'http://localhost:8000/admin/health/live\')"]',
        "      interval: 30s",
        "      timeout: 10s",
        "      retries: 3",
        "    restart: unless-stopped",
        "",
        "  # Flow Ingestion Service",
        "  ingestion:",
        "    build:",
        "      context: .",
        "      target: production",
        "    container_name: flowlens-ingestion",
        '    command: ["python", "-m", "flowlens.ingestion.main"]',
        "    environment:",
        f"      ENVIRONMENT: {environment}",
        "      <<: *db-env",
        f'      INGESTION_BIND_ADDRESS: "{ingestion_bind}"',
        f'      INGESTION_NETFLOW_PORT: "{ingestion_netflow_port}"',
        f'      INGESTION_SFLOW_PORT: "{ingestion_sflow_port}"',
        f'      INGESTION_BATCH_SIZE: "{ingestion_batch_size}"',
        f'      INGESTION_BATCH_TIMEOUT_MS: "{ingestion_batch_timeout}"',
        f'      INGESTION_QUEUE_MAX_SIZE: "{ingestion_queue_max}"',
        f'      INGESTION_SAMPLE_THRESHOLD: "{ingestion_sample_threshold}"',
        f'      INGESTION_DROP_THRESHOLD: "{ingestion_drop_threshold}"',
        f'      INGESTION_SAMPLE_RATE: "{ingestion_sample_rate}"',
        f"      LOG_LEVEL: {log_level}",
        f"      LOG_FORMAT: {log_format}",
        "    ports:",
        f'      - "{ingestion_netflow_port}:{ingestion_netflow_port}/udp"',
        f'      - "{ingestion_sflow_port}:{ingestion_sflow_port}/udp"',
        "    depends_on:",
        "      migrations:",
        "        condition: service_completed_successfully",
        "    healthcheck:",
        '      test: ["CMD", "pgrep", "-f", "flowlens.ingestion.main"]',
        "      interval: 30s",
        "      timeout: 10s",
        "      retries: 3",
        "    restart: unless-stopped",
        "",
        "  # Enrichment Service (enriches flow records with DNS, GeoIP, etc.)",
        "  enrichment:",
        "    build:",
        "      context: .",
        "      target: production",
        "    container_name: flowlens-enrichment",
        '    command: ["python", "-m", "flowlens.enrichment.main"]',
        "    environment:",
        f"      ENVIRONMENT: {environment}",
        "      <<: *db-logging-env",
        f'      ENRICHMENT_WORKER_COUNT: "{enrichment_worker_count}"',
        f'      ENRICHMENT_BATCH_SIZE: "{enrichment_batch_size}"',
        f'      ENRICHMENT_POLL_INTERVAL_MS: "{enrichment_poll_interval}"',
        f'      ENRICHMENT_DNS_TIMEOUT: "{enrichment_dns_timeout}"',
        f'      ENRICHMENT_DNS_CACHE_TTL: "{enrichment_dns_cache_ttl}"',
        f'      ENRICHMENT_DNS_CACHE_SIZE: "{enrichment_dns_cache_size}"',
        "    depends_on:",
        "      migrations:",
        "        condition: service_completed_successfully",
        "    healthcheck:",
        '      test: ["CMD", "pgrep", "-f", "flowlens.enrichment.main"]',
        "      interval: 30s",
        "      timeout: 10s",
        "      retries: 3",
        "    restart: unless-stopped",
        "",
        "  # Resolution Service (builds assets and dependencies from flows)",
        "  resolution:",
        "    build:",
        "      context: .",
        "      target: production",
        "    container_name: flowlens-resolution",
        '    command: ["python", "-m", "flowlens.resolution.main"]',
        "    env_file:",
        "      - .env",
        "    environment:",
        f"      ENVIRONMENT: {environment}",
        "      <<: *db-logging-env",
        f'      RESOLUTION_WORKER_COUNT: "{resolution_worker_count}"',
        f'      RESOLUTION_WINDOW_SIZE_MINUTES: "{resolution_window_minutes}"',
        f'      RESOLUTION_BATCH_SIZE: "{resolution_batch_size}"',
        f'      RESOLUTION_POLL_INTERVAL_MS: "{resolution_poll_interval}"',
        f'      RESOLUTION_STALE_THRESHOLD_HOURS: "{resolution_stale_threshold}"',
        f'      RESOLUTION_EXCLUDE_EXTERNAL_IPS: "{resolution_exclude_external_ips}"',
        f'      RESOLUTION_EXCLUDE_EXTERNAL_SOURCES: "{resolution_exclude_external_sources}"',
        f'      RESOLUTION_EXCLUDE_EXTERNAL_TARGETS: "{resolution_exclude_external_targets}"',
        "    depends_on:",
        "      migrations:",
        "        condition: service_completed_successfully",
        "    healthcheck:",
        '      test: ["CMD", "pgrep", "-f", "flowlens.resolution.main"]',
        "      interval: 30s",
        "      timeout: 10s",
        "      retries: 3",
        "    restart: unless-stopped",
        "",
        "  # Classification Service (auto-classifies assets based on behavioral features)",
        "  classification:",
        "    build:",
        "      context: .",
        "      target: production",
        "    container_name: flowlens-classification",
        '    command: ["python", "-m", "flowlens.classification.main"]',
        "    environment:",
        f"      ENVIRONMENT: {environment}",
        "      <<: *classification-full-env",
        "    depends_on:",
        "      migrations:",
        "        condition: service_completed_successfully",
        "    healthcheck:",
        '      test: ["CMD", "pgrep", "-f", "flowlens.classification.main"]',
        "      interval: 30s",
        "      timeout: 10s",
        "      retries: 3",
        "    restart: unless-stopped",
        "",
        "  # Frontend UI",
        "  frontend:",
        "    build:",
        "      context: ./frontend",
        "      target: production",
        "    container_name: flowlens-frontend",
        "    ports:",
        '      - "3000:80"',
        "    depends_on:",
        "      - api",
        "    healthcheck:",
        '      test: ["CMD", "curl", "-f", "http://localhost/"]',
        "      interval: 30s",
        "      timeout: 10s",
        "      retries: 3",
        "    restart: unless-stopped",
        "",
    ]

    # Add Redis if enabled
    if redis_enabled:
        redis_lines = [
            "  # Redis Cache",
            "  redis:",
            "    image: redis:7-alpine",
            "    container_name: flowlens-redis",
            "    ports:",
            f'      - "{redis_port}:6379"',
            "    healthcheck:",
            '      test: ["CMD", "redis-cli", "ping"]',
            "      interval: 10s",
            "      timeout: 5s",
            "      retries: 5",
            "    restart: unless-stopped",
            "",
        ]
        # Insert Redis service before frontend
        frontend_idx = next(i for i, line in enumerate(lines) if "# Frontend UI" in line)
        lines = lines[:frontend_idx] + redis_lines + lines[frontend_idx:]

    # Add volumes and networks
    lines.extend([
        "volumes:",
        "  postgres_data:",
        "",
        "networks:",
        "  default:",
        "    name: flowlens-network",
    ])

    return "\n".join(lines)


def is_restart_required() -> bool:
    """Check if a restart is required due to settings changes.

    Returns:
        True if restart is required.
    """
    return _restart_required


def clear_restart_required() -> None:
    """Clear the restart required flag (after restart)."""
    global _restart_required
    _restart_required = False


def trigger_restart() -> tuple[bool, str, str | None]:
    """Trigger a service restart.

    Attempts Docker restart first, falls back to instructions.

    Returns:
        Tuple of (success, message, method).
    """
    # Try Docker compose restart
    try:
        result = subprocess.run(
            ["docker", "compose", "restart", "api", "ingestion", "enrichment", "resolution"],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=str(ENV_FILE_PATH.parent),
        )

        if result.returncode == 0:
            clear_restart_required()
            logger.info("Services restarted via Docker Compose")
            return True, "Services restarted successfully via Docker Compose", "docker"

        logger.warning(
            "Docker Compose restart failed",
            returncode=result.returncode,
            stderr=result.stderr,
        )

    except FileNotFoundError:
        logger.info("Docker not available, providing manual instructions")
    except subprocess.TimeoutExpired:
        logger.warning("Docker Compose restart timed out")
    except Exception as e:
        logger.warning("Docker Compose restart error", error=str(e))

    # Fall back to manual instructions
    instructions = (
        "Please restart the FlowLens services manually:\n"
        "1. If using Docker: docker compose restart\n"
        "2. If using systemd: systemctl restart flowlens-*\n"
        "3. If running directly: Stop and restart the Python processes"
    )

    return False, instructions, "manual"


async def test_database_connection(test_values: dict[str, Any] | None = None) -> tuple[bool, str, dict | None]:
    """Test database connection.

    Args:
        test_values: Optional override values to test.

    Returns:
        Tuple of (success, message, details).
    """
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    settings = get_settings()
    db = settings.database

    # Use test values if provided
    host = test_values.get("host", db.host) if test_values else db.host
    port = test_values.get("port", db.port) if test_values else db.port
    user = test_values.get("user", db.user) if test_values else db.user
    password = test_values.get("password") if test_values and test_values.get("password") else db.password.get_secret_value()
    database = test_values.get("database", db.database) if test_values else db.database

    url = f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{database}"

    try:
        engine = create_async_engine(url, pool_pre_ping=True)
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT version()"))
            version = result.scalar()

        await engine.dispose()

        return True, "Connection successful", {"version": version}

    except Exception as e:
        return False, f"Connection failed: {str(e)}", None


async def test_redis_connection(test_values: dict[str, Any] | None = None) -> tuple[bool, str, dict | None]:
    """Test Redis connection.

    Args:
        test_values: Optional override values to test.

    Returns:
        Tuple of (success, message, details).
    """
    try:
        import redis.asyncio as redis
    except ImportError:
        return False, "Redis client not installed", None

    settings = get_settings()
    r = settings.redis

    # Use test values if provided
    host = test_values.get("host", r.host) if test_values else r.host
    port = test_values.get("port", r.port) if test_values else r.port
    password = test_values.get("password") if test_values and test_values.get("password") else (r.password.get_secret_value() if r.password else None)
    database = test_values.get("database", r.database) if test_values else r.database
    ssl = test_values.get("ssl", r.ssl) if test_values else r.ssl

    try:
        client = redis.Redis(
            host=host,
            port=port,
            password=password,
            db=database,
            ssl=ssl,
            socket_timeout=5.0,
        )

        info = await client.info("server")
        await client.close()

        return True, "Connection successful", {
            "version": info.get("redis_version"),
            "mode": info.get("redis_mode"),
        }

    except Exception as e:
        return False, f"Connection failed: {str(e)}", None


async def test_notification_channel(channel: str, test_values: dict[str, Any] | None = None) -> tuple[bool, str, dict | None]:
    """Test a notification channel.

    Args:
        channel: Channel name (email, webhook, slack, teams, pagerduty).
        test_values: Optional override values to test.

    Returns:
        Tuple of (success, message, details).
    """
    settings = get_settings()

    if channel == "slack":
        from flowlens.notifications.slack import SlackChannel, SlackSettings

        slack_settings = settings.notifications.slack
        webhook_url = test_values.get("webhook_url") if test_values else slack_settings.webhook_url

        if not webhook_url:
            return False, "Webhook URL not configured", None

        try:
            channel_obj = SlackChannel(SlackSettings(
                enabled=True,
                webhook_url=webhook_url,
                username=test_values.get("username", slack_settings.username) if test_values else slack_settings.username,
                icon_emoji=test_values.get("icon_emoji", slack_settings.icon_emoji) if test_values else slack_settings.icon_emoji,
            ))
            success = await channel_obj.test_connection()
            return success, "Test message sent" if success else "Failed to send test message", None
        except Exception as e:
            return False, f"Test failed: {str(e)}", None

    elif channel == "pagerduty":
        from flowlens.notifications.pagerduty import PagerDutyChannel, PagerDutySettings

        pd_settings = settings.notifications.pagerduty
        routing_key = test_values.get("routing_key") if test_values else pd_settings.routing_key

        if not routing_key:
            return False, "Routing key not configured", None

        try:
            channel_obj = PagerDutyChannel(PagerDutySettings(
                routing_key=routing_key,
                service_name=test_values.get("service_name", pd_settings.service_name) if test_values else pd_settings.service_name,
            ))
            success = await channel_obj.test_connection()
            return success, "Test event sent and resolved" if success else "Failed to send test event", None
        except Exception as e:
            return False, f"Test failed: {str(e)}", None

    # TODO: Add email, webhook, teams testing

    return False, f"Unknown channel: {channel}", None

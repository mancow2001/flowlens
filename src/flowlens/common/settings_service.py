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
    generates a complete docker-compose.yml file.

    Returns:
        YAML string of the docker-compose configuration.
    """
    import yaml

    settings = get_settings()

    # Build environment variables for each service
    # Common database settings
    db_env = {
        "POSTGRES_HOST": "postgres",
        "POSTGRES_PORT": "5432",
        "POSTGRES_USER": settings.database.user,
        "POSTGRES_PASSWORD": settings.database.password.get_secret_value(),
        "POSTGRES_DATABASE": settings.database.database,
    }

    # API service environment
    api_env = {
        **db_env,
        "ENVIRONMENT": settings.environment,
        "DEBUG": str(settings.debug).lower(),
        "API_HOST": settings.api.host,
        "API_PORT": str(settings.api.port),
        "API_WORKERS": str(settings.api.workers),
        "API_CORS_ORIGINS": settings.api.cors_origins_str,
        "API_RATE_LIMIT_REQUESTS": str(settings.api.rate_limit_requests),
        "API_RATE_LIMIT_WINDOW_SECONDS": str(settings.api.rate_limit_window_seconds),
        "API_DEFAULT_PAGE_SIZE": str(settings.api.default_page_size),
        "API_MAX_PAGE_SIZE": str(settings.api.max_page_size),
        "AUTH_ENABLED": str(settings.auth.enabled).lower(),
        "AUTH_SECRET_KEY": settings.auth.secret_key.get_secret_value(),
        "AUTH_ALGORITHM": settings.auth.algorithm,
        "AUTH_ACCESS_TOKEN_EXPIRE_MINUTES": str(settings.auth.access_token_expire_minutes),
        "AUTH_REFRESH_TOKEN_EXPIRE_DAYS": str(settings.auth.refresh_token_expire_days),
        "LOG_LEVEL": settings.logging.level,
        "LOG_FORMAT": settings.logging.format,
    }

    # Ingestion service environment
    ingestion_env = {
        **db_env,
        "ENVIRONMENT": settings.environment,
        "INGESTION_BIND_ADDRESS": str(settings.ingestion.bind_address),
        "INGESTION_NETFLOW_PORT": str(settings.ingestion.netflow_port),
        "INGESTION_SFLOW_PORT": str(settings.ingestion.sflow_port),
        "INGESTION_BATCH_SIZE": str(settings.ingestion.batch_size),
        "INGESTION_BATCH_TIMEOUT_MS": str(settings.ingestion.batch_timeout_ms),
        "INGESTION_QUEUE_MAX_SIZE": str(settings.ingestion.queue_max_size),
        "INGESTION_SAMPLE_THRESHOLD": str(settings.ingestion.sample_threshold),
        "INGESTION_DROP_THRESHOLD": str(settings.ingestion.drop_threshold),
        "INGESTION_SAMPLE_RATE": str(settings.ingestion.sample_rate),
        "LOG_LEVEL": settings.logging.level,
        "LOG_FORMAT": settings.logging.format,
    }

    # Enrichment service environment
    enrichment_env = {
        **db_env,
        "ENVIRONMENT": settings.environment,
        "ENRICHMENT_BATCH_SIZE": str(settings.enrichment.batch_size),
        "ENRICHMENT_POLL_INTERVAL_MS": str(settings.enrichment.poll_interval_ms),
        "ENRICHMENT_WORKER_COUNT": str(settings.enrichment.worker_count),
        "ENRICHMENT_DNS_TIMEOUT": str(settings.enrichment.dns_timeout),
        "ENRICHMENT_DNS_CACHE_TTL": str(settings.enrichment.dns_cache_ttl),
        "ENRICHMENT_DNS_CACHE_SIZE": str(settings.enrichment.dns_cache_size),
        "LOG_LEVEL": settings.logging.level,
        "LOG_FORMAT": settings.logging.format,
    }
    if settings.enrichment.dns_servers:
        enrichment_env["ENRICHMENT_DNS_SERVERS"] = ",".join(settings.enrichment.dns_servers)
    if settings.enrichment.geoip_database_path:
        enrichment_env["ENRICHMENT_GEOIP_DATABASE_PATH"] = str(settings.enrichment.geoip_database_path)

    # Resolution service environment
    resolution_env = {
        **db_env,
        "ENVIRONMENT": settings.environment,
        "RESOLUTION_WINDOW_SIZE_MINUTES": str(settings.resolution.window_size_minutes),
        "RESOLUTION_WORKER_COUNT": str(settings.resolution.worker_count),
        "RESOLUTION_BATCH_SIZE": str(settings.resolution.batch_size),
        "RESOLUTION_POLL_INTERVAL_MS": str(settings.resolution.poll_interval_ms),
        "RESOLUTION_DETECTION_INTERVAL_MINUTES": str(settings.resolution.detection_interval_minutes),
        "RESOLUTION_STALE_THRESHOLD_HOURS": str(settings.resolution.stale_threshold_hours),
        "RESOLUTION_NEW_DEPENDENCY_LOOKBACK_MINUTES": str(settings.resolution.new_dependency_lookback_minutes),
        "RESOLUTION_EXCLUDE_EXTERNAL_IPS": str(settings.resolution.exclude_external_ips).lower(),
        "RESOLUTION_EXCLUDE_EXTERNAL_SOURCES": str(settings.resolution.exclude_external_sources).lower(),
        "RESOLUTION_EXCLUDE_EXTERNAL_TARGETS": str(settings.resolution.exclude_external_targets).lower(),
        "LOG_LEVEL": settings.logging.level,
        "LOG_FORMAT": settings.logging.format,
    }

    # Add notification settings to API env
    notif = settings.notifications
    if notif.email.enabled:
        api_env.update({
            "EMAIL_ENABLED": "true",
            "EMAIL_HOST": notif.email.host,
            "EMAIL_PORT": str(notif.email.port),
            "EMAIL_USE_TLS": str(notif.email.use_tls).lower(),
            "EMAIL_START_TLS": str(notif.email.start_tls).lower(),
            "EMAIL_FROM_ADDRESS": notif.email.from_address,
            "EMAIL_FROM_NAME": notif.email.from_name,
        })
        if notif.email.username:
            api_env["EMAIL_USERNAME"] = notif.email.username
        if notif.email.password:
            api_env["EMAIL_PASSWORD"] = notif.email.password.get_secret_value()
        if notif.email.alert_recipients:
            api_env["EMAIL_ALERT_RECIPIENTS"] = ",".join(notif.email.alert_recipients)

    if notif.slack.enabled and notif.slack.webhook_url:
        api_env.update({
            "SLACK_ENABLED": "true",
            "SLACK_WEBHOOK_URL": notif.slack.webhook_url,
            "SLACK_USERNAME": notif.slack.username,
            "SLACK_ICON_EMOJI": notif.slack.icon_emoji,
        })
        if notif.slack.default_channel:
            api_env["SLACK_DEFAULT_CHANNEL"] = notif.slack.default_channel

    if notif.pagerduty.enabled and notif.pagerduty.routing_key:
        api_env.update({
            "PAGERDUTY_ENABLED": "true",
            "PAGERDUTY_ROUTING_KEY": notif.pagerduty.routing_key,
            "PAGERDUTY_SERVICE_NAME": notif.pagerduty.service_name,
        })

    if notif.webhook.enabled and notif.webhook.url:
        api_env.update({
            "WEBHOOK_ENABLED": "true",
            "WEBHOOK_URL": notif.webhook.url,
            "WEBHOOK_TIMEOUT": str(notif.webhook.timeout),
            "WEBHOOK_RETRY_COUNT": str(notif.webhook.retry_count),
        })
        if notif.webhook.secret:
            api_env["WEBHOOK_SECRET"] = notif.webhook.secret.get_secret_value()

    if notif.teams.enabled and notif.teams.webhook_url:
        api_env.update({
            "TEAMS_ENABLED": "true",
            "TEAMS_WEBHOOK_URL": notif.teams.webhook_url,
        })

    # Apply any pending overrides from Docker mode
    # These are settings changed via the UI that couldn't be written to .env
    if _settings_overrides:
        logger.info(
            "Applying settings overrides to docker-compose",
            override_keys=list(_settings_overrides.keys()),
        )
        # Apply overrides to all environment dictionaries
        for env_dict in [db_env, api_env, ingestion_env, enrichment_env, resolution_env]:
            for key, value in _settings_overrides.items():
                # Only apply if this env dict contains this key or a related key
                if key in env_dict:
                    env_dict[key] = value
                # Also check if we should add it based on key prefix matching
                elif any(key.startswith(prefix) for prefix in ["POSTGRES_", "REDIS_", "KAFKA_"]):
                    # Database/Redis/Kafka settings go in db_env which is spread to others
                    if env_dict is db_env:
                        env_dict[key] = value
                elif key.startswith("API_") or key.startswith("AUTH_"):
                    if env_dict is api_env:
                        env_dict[key] = value
                elif key.startswith("INGESTION_"):
                    if env_dict is ingestion_env:
                        env_dict[key] = value
                elif key.startswith("ENRICHMENT_"):
                    if env_dict is enrichment_env:
                        env_dict[key] = value
                elif key.startswith("RESOLUTION_"):
                    if env_dict is resolution_env:
                        env_dict[key] = value
                elif key.startswith("LOG_"):
                    # Logging settings apply to all services
                    env_dict[key] = value
                elif key in ["ENVIRONMENT", "DEBUG"]:
                    # Root settings apply to all services
                    env_dict[key] = value
                elif key.startswith(("EMAIL_", "SLACK_", "WEBHOOK_", "TEAMS_", "PAGERDUTY_")):
                    # Notification settings go in api_env
                    if env_dict is api_env:
                        env_dict[key] = value

    # Get values for ports and other compose-level settings
    # These need to use overrides if available
    postgres_user = _settings_overrides.get("POSTGRES_USER", settings.database.user)
    postgres_password = _settings_overrides.get(
        "POSTGRES_PASSWORD",
        settings.database.password.get_secret_value()
    )
    postgres_db = _settings_overrides.get("POSTGRES_DATABASE", settings.database.database)
    postgres_port = _settings_overrides.get("POSTGRES_PORT", str(settings.database.port))
    api_port = _settings_overrides.get("API_PORT", str(settings.api.port))
    netflow_port = _settings_overrides.get(
        "INGESTION_NETFLOW_PORT",
        str(settings.ingestion.netflow_port)
    )
    sflow_port = _settings_overrides.get(
        "INGESTION_SFLOW_PORT",
        str(settings.ingestion.sflow_port)
    )
    redis_port = _settings_overrides.get("REDIS_PORT", str(settings.redis.port))
    redis_enabled = _settings_overrides.get(
        "REDIS_ENABLED",
        str(settings.redis.enabled).lower()
    ) == "true"

    # Build the compose structure
    compose = {
        "version": "3.8",
        "services": {
            "postgres": {
                "image": "postgres:15-alpine",
                "container_name": "flowlens-postgres",
                "environment": {
                    "POSTGRES_USER": postgres_user,
                    "POSTGRES_PASSWORD": postgres_password,
                    "POSTGRES_DB": postgres_db,
                },
                "volumes": ["postgres_data:/var/lib/postgresql/data"],
                "ports": [f"{postgres_port}:5432"],
                "healthcheck": {
                    "test": ["CMD-SHELL", f"pg_isready -U {postgres_user}"],
                    "interval": "10s",
                    "timeout": "5s",
                    "retries": 5,
                },
                "restart": "unless-stopped",
            },
            "migrations": {
                "build": {"context": ".", "target": "production"},
                "container_name": "flowlens-migrations",
                "command": ["alembic", "upgrade", "head"],
                "environment": db_env,
                "depends_on": {"postgres": {"condition": "service_healthy"}},
            },
            "api": {
                "build": {"context": ".", "target": "production"},
                "container_name": "flowlens-api",
                "command": ["python", "-m", "flowlens.api.main"],
                "environment": api_env,
                "ports": [f"{api_port}:8000"],
                "depends_on": {"migrations": {"condition": "service_completed_successfully"}},
                "healthcheck": {
                    "test": ["CMD", "python", "-c", "import httpx; httpx.get('http://localhost:8000/admin/health/live')"],
                    "interval": "30s",
                    "timeout": "10s",
                    "retries": 3,
                },
                "restart": "unless-stopped",
            },
            "ingestion": {
                "build": {"context": ".", "target": "production"},
                "container_name": "flowlens-ingestion",
                "command": ["python", "-m", "flowlens.ingestion.main"],
                "environment": ingestion_env,
                "ports": [
                    f"{netflow_port}:{netflow_port}/udp",
                    f"{sflow_port}:{sflow_port}/udp",
                ],
                "depends_on": {"migrations": {"condition": "service_completed_successfully"}},
                "healthcheck": {
                    "test": ["CMD", "pgrep", "-f", "flowlens.ingestion.main"],
                    "interval": "30s",
                    "timeout": "10s",
                    "retries": 3,
                },
                "restart": "unless-stopped",
            },
            "enrichment": {
                "build": {"context": ".", "target": "production"},
                "container_name": "flowlens-enrichment",
                "command": ["python", "-m", "flowlens.enrichment.main"],
                "environment": enrichment_env,
                "depends_on": {"migrations": {"condition": "service_completed_successfully"}},
                "healthcheck": {
                    "test": ["CMD", "pgrep", "-f", "flowlens.enrichment.main"],
                    "interval": "30s",
                    "timeout": "10s",
                    "retries": 3,
                },
                "restart": "unless-stopped",
            },
            "resolution": {
                "build": {"context": ".", "target": "production"},
                "container_name": "flowlens-resolution",
                "command": ["python", "-m", "flowlens.resolution.main"],
                "environment": resolution_env,
                "depends_on": {"migrations": {"condition": "service_completed_successfully"}},
                "healthcheck": {
                    "test": ["CMD", "pgrep", "-f", "flowlens.resolution.main"],
                    "interval": "30s",
                    "timeout": "10s",
                    "retries": 3,
                },
                "restart": "unless-stopped",
            },
            "frontend": {
                "build": {"context": "./frontend", "target": "production"},
                "container_name": "flowlens-frontend",
                "ports": ["3000:80"],
                "depends_on": ["api"],
                "healthcheck": {
                    "test": ["CMD", "curl", "-f", "http://localhost/"],
                    "interval": "30s",
                    "timeout": "10s",
                    "retries": 3,
                },
                "restart": "unless-stopped",
            },
        },
        "volumes": {"postgres_data": None},
        "networks": {"default": {"name": "flowlens-network"}},
    }

    # Add Redis if enabled
    if redis_enabled:
        compose["services"]["redis"] = {
            "image": "redis:7-alpine",
            "container_name": "flowlens-redis",
            "ports": [f"{redis_port}:6379"],
            "healthcheck": {
                "test": ["CMD", "redis-cli", "ping"],
                "interval": "10s",
                "timeout": "5s",
                "retries": 5,
            },
            "restart": "unless-stopped",
        }
        redis_env = {
            "REDIS_ENABLED": "true",
            "REDIS_HOST": "redis",
            "REDIS_PORT": "6379",
        }
        redis_password = _settings_overrides.get("REDIS_PASSWORD")
        if redis_password:
            redis_env["REDIS_PASSWORD"] = redis_password
        elif settings.redis.password:
            redis_env["REDIS_PASSWORD"] = settings.redis.password.get_secret_value()
        # Add to all services
        for svc in ["api", "ingestion", "enrichment", "resolution"]:
            compose["services"][svc]["environment"].update(redis_env)
            if "depends_on" not in compose["services"][svc]:
                compose["services"][svc]["depends_on"] = {}
            if isinstance(compose["services"][svc]["depends_on"], list):
                compose["services"][svc]["depends_on"].append("redis")
            else:
                compose["services"][svc]["depends_on"]["redis"] = {"condition": "service_healthy"}

    # Generate YAML with nice formatting
    # Custom representer to handle None values
    def represent_none(dumper, _):
        return dumper.represent_scalar('tag:yaml.org,2002:null', '')

    yaml.add_representer(type(None), represent_none)

    # Add header comment
    header = """# FlowLens Docker Compose Configuration
# Generated from System Settings on {date}
#
# To use: docker compose up -d
#
""".format(date=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    return header + yaml.dump(compose, default_flow_style=False, sort_keys=False, allow_unicode=True)


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

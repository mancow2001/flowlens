"""Settings management service.

Handles reading, updating, and persisting application settings.
"""

import os
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import SecretStr

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

# Path to .env file
ENV_FILE_PATH = Path(__file__).parent.parent.parent.parent / ".env"

# Track if restart is required
_restart_required = False


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
) -> tuple[bool, list[str], bool]:
    """Update settings for a section.

    Args:
        section_key: Section key.
        values: Dictionary of field names to new values.
        user_id: ID of user making the change (for audit).

    Returns:
        Tuple of (success, updated_fields, restart_required).
    """
    global _restart_required

    section_info = get_section_by_key(section_key)
    if not section_info:
        return False, [], False

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
        return True, [], False

    # Write to .env file
    try:
        write_env_file(env_updates)
    except Exception as e:
        logger.error("Failed to write .env file", error=str(e))
        return False, [], False

    # Clear the settings cache so new values are picked up
    get_settings.cache_clear()

    # Check if restart is required
    needs_restart = section_info.restart_required and len(updated_fields) > 0

    if needs_restart:
        _restart_required = True

    logger.info(
        "Updated settings",
        section=section_key,
        fields=updated_fields,
        restart_required=needs_restart,
        user=user_id,
    )

    return True, updated_fields, needs_restart


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

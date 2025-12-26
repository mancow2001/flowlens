"""System settings API endpoints.

Provides endpoints for viewing and managing application configuration.
Requires admin role for all operations.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from flowlens.api.auth.jwt import TokenPayload
from flowlens.api.dependencies import AuthenticatedUser
from flowlens.common.config import get_settings
from flowlens.common.logging import get_logger
from flowlens.common.settings_service import (
    clear_restart_required,
    get_all_section_data,
    get_section_data,
    is_restart_required,
    test_database_connection,
    test_notification_channel,
    test_redis_connection,
    trigger_restart,
    update_section_settings,
)
from flowlens.schemas.settings import (
    ConnectionTestRequest,
    ConnectionTestResponse,
    RestartResponse,
    SettingsResponse,
    SettingsSectionResponse,
    SettingsUpdateRequest,
    SettingsUpdateResponse,
    get_all_sections,
    get_section_by_key,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/settings", tags=["settings"])


async def require_admin(user: AuthenticatedUser) -> TokenPayload:
    """Require admin role for access.

    Args:
        user: Authenticated user.

    Returns:
        User if admin.

    Raises:
        HTTPException: If not admin.
    """
    settings = get_settings()

    # If auth is disabled, allow all access
    if not settings.auth.enabled:
        return user

    # Check for admin role
    if "admin" not in user.roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )

    return user


AdminUser = Annotated[TokenPayload, Depends(require_admin)]


@router.get("", response_model=SettingsResponse)
async def get_all_settings(admin: AdminUser) -> SettingsResponse:
    """Get all settings sections with metadata.

    Returns section definitions with field metadata for form generation.
    Does not include current values (use GET /settings/{section} for that).
    """
    sections = get_all_sections()
    restart_required = is_restart_required()

    return SettingsResponse(
        sections=sections,
        restart_required=restart_required,
    )


@router.get("/restart-required")
async def check_restart_required(admin: AdminUser) -> dict:
    """Check if a service restart is required.

    Returns:
        Object with restart_required boolean.
    """
    return {"restart_required": is_restart_required()}


@router.post("/restart", response_model=RestartResponse)
async def restart_services(admin: AdminUser) -> RestartResponse:
    """Trigger a service restart.

    Attempts Docker Compose restart first, falls back to manual instructions.
    """
    logger.info("Restart requested", user=admin.sub)

    success, message, method = trigger_restart()

    return RestartResponse(
        success=success,
        message=message,
        method=method,
    )


@router.get("/{section_key}", response_model=SettingsSectionResponse)
async def get_section_settings(
    section_key: str,
    admin: AdminUser,
) -> SettingsSectionResponse:
    """Get settings for a specific section.

    Returns section metadata and current values (with secrets masked).
    """
    section_info = get_section_by_key(section_key)
    if not section_info:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Settings section '{section_key}' not found",
        )

    section_data = get_section_data(section_key)
    if not section_data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to load section data",
        )

    return SettingsSectionResponse(
        section=section_info,
        data=section_data,
        restart_required=is_restart_required(),
    )


@router.put("/{section_key}", response_model=SettingsUpdateResponse)
async def update_section(
    section_key: str,
    request: SettingsUpdateRequest,
    admin: AdminUser,
) -> SettingsUpdateResponse:
    """Update settings for a section.

    Updates are written to the .env file. Some settings require a
    service restart to take effect.
    """
    section_info = get_section_by_key(section_key)
    if not section_info:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Settings section '{section_key}' not found",
        )

    logger.info(
        "Updating settings",
        section=section_key,
        user=admin.sub,
        fields=list(request.values.keys()),
    )

    success, updated_fields, restart_required = update_section_settings(
        section_key,
        request.values,
        user_id=admin.sub,
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update settings",
        )

    message = f"Updated {len(updated_fields)} setting(s)"
    if restart_required:
        message += ". Restart required for changes to take effect."

    return SettingsUpdateResponse(
        success=True,
        message=message,
        restart_required=restart_required,
        updated_fields=updated_fields,
    )


@router.post("/test-connection/{service}", response_model=ConnectionTestResponse)
async def test_connection(
    service: str,
    request: ConnectionTestRequest | None = None,
    admin: AdminUser = None,
) -> ConnectionTestResponse:
    """Test connection to a service.

    Supported services: database, redis, kafka, email, webhook, slack, teams, pagerduty

    Args:
        service: Service to test.
        request: Optional override values to test before saving.
    """
    test_values = request.test_values if request else None

    if service == "database":
        success, message, details = await test_database_connection(test_values)
    elif service == "redis":
        success, message, details = await test_redis_connection(test_values)
    elif service in ("slack", "pagerduty", "email", "webhook", "teams"):
        success, message, details = await test_notification_channel(service, test_values)
    elif service == "kafka":
        # TODO: Implement Kafka connection test
        success, message, details = False, "Kafka connection test not implemented", None
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown service: {service}",
        )

    logger.info(
        "Connection test",
        service=service,
        success=success,
        user=admin.sub if admin else "anonymous",
    )

    return ConnectionTestResponse(
        success=success,
        message=message,
        details=details,
    )


@router.post("/clear-restart-flag")
async def clear_restart_flag(admin: AdminUser) -> dict:
    """Clear the restart required flag.

    Used after manual restart to acknowledge the restart was performed.
    """
    clear_restart_required()
    logger.info("Restart flag cleared", user=admin.sub)
    return {"message": "Restart flag cleared"}

"""Alerts API router.

Endpoints for managing alerts and notifications.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select, update

from flowlens.api.dependencies import DbSession, Pagination, get_current_user
from flowlens.common.config import get_settings
from flowlens.common.logging import get_logger
from flowlens.models.change import Alert, AlertSeverity
from flowlens.notifications.base import Notification, NotificationManager, NotificationPriority
from flowlens.notifications.email import EmailChannel, EmailSettings, create_alert_notification
from flowlens.schemas.alert import (
    AlertAcknowledge,
    AlertCreate,
    AlertListResponse,
    AlertResolve,
    AlertResponse,
    AlertSummary,
    AlertUpdate,
    NotificationTestRequest,
    NotificationTestResponse,
)

logger = get_logger(__name__)
router = APIRouter(prefix="/alerts", tags=["alerts"])


# Initialize notification manager
_notification_manager: NotificationManager | None = None


def get_notification_manager() -> NotificationManager:
    """Get or create notification manager singleton."""
    global _notification_manager

    if _notification_manager is None:
        _notification_manager = NotificationManager()

        # Register email channel if enabled
        settings = get_settings()
        if settings.notifications.email.enabled:
            email_settings = EmailSettings(
                host=settings.notifications.email.host,
                port=settings.notifications.email.port,
                username=settings.notifications.email.username,
                password=settings.notifications.email.password.get_secret_value() if settings.notifications.email.password else None,
                use_tls=settings.notifications.email.use_tls,
                start_tls=settings.notifications.email.start_tls,
                from_address=settings.notifications.email.from_address,
                from_name=settings.notifications.email.from_name,
                timeout=settings.notifications.email.timeout,
                validate_certs=settings.notifications.email.validate_certs,
            )
            _notification_manager.register_channel(EmailChannel(email_settings))

    return _notification_manager


@router.get("", response_model=AlertListResponse)
async def list_alerts(
    db: DbSession,
    pagination: Pagination,
    severity: str | None = Query(None, pattern="^(info|warning|error|critical)$"),
    is_acknowledged: bool | None = None,
    is_resolved: bool | None = None,
    asset_id: UUID | None = None,
    since: datetime | None = None,
) -> AlertListResponse:
    """List alerts with filtering and pagination.

    Args:
        db: Database session.
        pagination: Pagination parameters.
        severity: Filter by severity.
        is_acknowledged: Filter by acknowledgment status.
        is_resolved: Filter by resolution status.
        asset_id: Filter by related asset.
        since: Filter by creation time.

    Returns:
        Paginated list of alerts.
    """
    # Build query
    query = select(Alert).order_by(Alert.created_at.desc())

    if severity:
        query = query.where(Alert.severity == severity)
    if is_acknowledged is not None:
        query = query.where(Alert.is_acknowledged == is_acknowledged)
    if is_resolved is not None:
        query = query.where(Alert.is_resolved == is_resolved)
    if asset_id:
        query = query.where(Alert.asset_id == asset_id)
    if since:
        query = query.where(Alert.created_at >= since)

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query) or 0

    # Apply pagination
    query = query.offset(pagination.offset).limit(pagination.limit)

    # Execute query
    result = await db.execute(query)
    alerts = result.scalars().all()

    # Get summary counts
    summary = await _get_alert_summary(db)

    return AlertListResponse(
        items=[AlertResponse.model_validate(a) for a in alerts],
        total=total,
        page=pagination.page,
        page_size=pagination.limit,
        summary=summary,
    )


@router.get("/summary", response_model=AlertSummary)
async def get_alert_summary(
    db: DbSession,
) -> AlertSummary:
    """Get summary of alert counts by severity.

    Args:
        db: Database session.

    Returns:
        Alert summary.
    """
    return await _get_alert_summary(db)


async def _get_alert_summary(db: DbSession) -> AlertSummary:
    """Get alert summary from database.

    Args:
        db: Database session.

    Returns:
        Alert summary counts.
    """
    # Total count
    total = await db.scalar(select(func.count(Alert.id))) or 0

    # Count by severity
    severity_counts = {}
    for sev in ["critical", "error", "warning", "info"]:
        count = await db.scalar(
            select(func.count(Alert.id)).where(Alert.severity == sev)
        )
        severity_counts[sev] = count or 0

    # Unacknowledged count
    unacknowledged = await db.scalar(
        select(func.count(Alert.id)).where(Alert.is_acknowledged == False)
    ) or 0

    # Unresolved count
    unresolved = await db.scalar(
        select(func.count(Alert.id)).where(Alert.is_resolved == False)
    ) or 0

    return AlertSummary(
        total=total,
        critical=severity_counts["critical"],
        error=severity_counts["error"],
        warning=severity_counts["warning"],
        info=severity_counts["info"],
        unacknowledged=unacknowledged,
        unresolved=unresolved,
    )


@router.get("/{alert_id}", response_model=AlertResponse)
async def get_alert(
    alert_id: UUID,
    db: DbSession,
) -> AlertResponse:
    """Get a specific alert by ID.

    Args:
        alert_id: Alert ID.
        db: Database session.

    Returns:
        Alert details.
    """
    result = await db.execute(
        select(Alert).where(Alert.id == alert_id)
    )
    alert = result.scalar_one_or_none()

    if not alert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Alert not found: {alert_id}",
        )

    return AlertResponse.model_validate(alert)


@router.post("/{alert_id}/acknowledge", response_model=AlertResponse)
async def acknowledge_alert(
    alert_id: UUID,
    data: AlertAcknowledge,
    db: DbSession,
) -> AlertResponse:
    """Acknowledge an alert.

    Args:
        alert_id: Alert ID.
        data: Acknowledgment data.
        db: Database session.

    Returns:
        Updated alert.
    """
    result = await db.execute(
        select(Alert).where(Alert.id == alert_id)
    )
    alert = result.scalar_one_or_none()

    if not alert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Alert not found: {alert_id}",
        )

    if alert.is_acknowledged:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Alert is already acknowledged",
        )

    alert.is_acknowledged = True
    alert.acknowledged_at = datetime.utcnow()
    alert.acknowledged_by = data.acknowledged_by

    await db.commit()
    await db.refresh(alert)

    logger.info(
        "Alert acknowledged",
        alert_id=str(alert_id),
        acknowledged_by=data.acknowledged_by,
    )

    return AlertResponse.model_validate(alert)


@router.post("/{alert_id}/resolve", response_model=AlertResponse)
async def resolve_alert(
    alert_id: UUID,
    data: AlertResolve,
    db: DbSession,
) -> AlertResponse:
    """Resolve an alert.

    Args:
        alert_id: Alert ID.
        data: Resolution data.
        db: Database session.

    Returns:
        Updated alert.
    """
    result = await db.execute(
        select(Alert).where(Alert.id == alert_id)
    )
    alert = result.scalar_one_or_none()

    if not alert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Alert not found: {alert_id}",
        )

    if alert.is_resolved:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Alert is already resolved",
        )

    alert.is_resolved = True
    alert.resolved_at = datetime.utcnow()
    alert.resolved_by = data.resolved_by
    alert.resolution_notes = data.resolution_notes

    # Also acknowledge if not already
    if not alert.is_acknowledged:
        alert.is_acknowledged = True
        alert.acknowledged_at = datetime.utcnow()
        alert.acknowledged_by = data.resolved_by

    await db.commit()
    await db.refresh(alert)

    logger.info(
        "Alert resolved",
        alert_id=str(alert_id),
        resolved_by=data.resolved_by,
    )

    return AlertResponse.model_validate(alert)


@router.patch("/{alert_id}", response_model=AlertResponse)
async def update_alert(
    alert_id: UUID,
    data: AlertUpdate,
    db: DbSession,
) -> AlertResponse:
    """Update an alert.

    Args:
        alert_id: Alert ID.
        data: Update data.
        db: Database session.

    Returns:
        Updated alert.
    """
    result = await db.execute(
        select(Alert).where(Alert.id == alert_id)
    )
    alert = result.scalar_one_or_none()

    if not alert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Alert not found: {alert_id}",
        )

    # Update provided fields
    update_data = data.model_dump(exclude_unset=True)

    for field, value in update_data.items():
        setattr(alert, field, value)

    # Set timestamps for status changes
    if data.is_acknowledged and not alert.acknowledged_at:
        alert.acknowledged_at = datetime.utcnow()
    if data.is_resolved and not alert.resolved_at:
        alert.resolved_at = datetime.utcnow()

    await db.commit()
    await db.refresh(alert)

    return AlertResponse.model_validate(alert)


@router.delete("/{alert_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_alert(
    alert_id: UUID,
    db: DbSession,
) -> None:
    """Delete an alert.

    Args:
        alert_id: Alert ID.
        db: Database session.
    """
    result = await db.execute(
        select(Alert).where(Alert.id == alert_id)
    )
    alert = result.scalar_one_or_none()

    if not alert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Alert not found: {alert_id}",
        )

    await db.delete(alert)
    await db.commit()

    logger.info("Alert deleted", alert_id=str(alert_id))


@router.post("/bulk/acknowledge", response_model=dict)
async def bulk_acknowledge_alerts(
    alert_ids: list[UUID],
    data: AlertAcknowledge,
    db: DbSession,
) -> dict:
    """Acknowledge multiple alerts.

    Args:
        alert_ids: List of alert IDs.
        data: Acknowledgment data.
        db: Database session.

    Returns:
        Count of acknowledged alerts.
    """
    now = datetime.utcnow()

    result = await db.execute(
        update(Alert)
        .where(
            Alert.id.in_(alert_ids),
            Alert.is_acknowledged == False,
        )
        .values(
            is_acknowledged=True,
            acknowledged_at=now,
            acknowledged_by=data.acknowledged_by,
        )
    )

    await db.commit()

    return {"acknowledged_count": result.rowcount}


@router.post("/bulk/resolve", response_model=dict)
async def bulk_resolve_alerts(
    alert_ids: list[UUID],
    data: AlertResolve,
    db: DbSession,
) -> dict:
    """Resolve multiple alerts.

    Args:
        alert_ids: List of alert IDs.
        data: Resolution data.
        db: Database session.

    Returns:
        Count of resolved alerts.
    """
    now = datetime.utcnow()

    result = await db.execute(
        update(Alert)
        .where(
            Alert.id.in_(alert_ids),
            Alert.is_resolved == False,
        )
        .values(
            is_resolved=True,
            resolved_at=now,
            resolved_by=data.resolved_by,
            resolution_notes=data.resolution_notes,
            is_acknowledged=True,
            acknowledged_at=func.coalesce(Alert.acknowledged_at, now),
            acknowledged_by=func.coalesce(Alert.acknowledged_by, data.resolved_by),
        )
    )

    await db.commit()

    return {"resolved_count": result.rowcount}


@router.post("/notifications/test", response_model=NotificationTestResponse)
async def test_notification(
    data: NotificationTestRequest,
) -> NotificationTestResponse:
    """Test a notification channel.

    Args:
        data: Test request with channel and recipient.

    Returns:
        Test result.
    """
    manager = get_notification_manager()

    if data.channel not in manager.channels:
        return NotificationTestResponse(
            success=False,
            channel=data.channel,
            recipient=data.recipient,
            error=f"Channel '{data.channel}' is not configured",
        )

    # Create test notification
    notification = Notification(
        subject="FlowLens Test Notification",
        body="This is a test notification from FlowLens.\n\nIf you received this, your notification channel is configured correctly.",
        html_body="""
        <html>
        <body style="font-family: sans-serif;">
            <h2>FlowLens Test Notification</h2>
            <p>This is a test notification from FlowLens.</p>
            <p>If you received this, your notification channel is configured correctly.</p>
        </body>
        </html>
        """,
        priority=NotificationPriority.LOW,
    )

    try:
        results = await manager.send(
            notification,
            {data.channel: [data.recipient]},
        )

        channel_results = results.get(data.channel, [])
        if channel_results and channel_results[0].success:
            return NotificationTestResponse(
                success=True,
                channel=data.channel,
                recipient=data.recipient,
                message="Test notification sent successfully",
            )
        else:
            error = channel_results[0].error if channel_results else "Unknown error"
            return NotificationTestResponse(
                success=False,
                channel=data.channel,
                recipient=data.recipient,
                error=error,
            )

    except Exception as e:
        return NotificationTestResponse(
            success=False,
            channel=data.channel,
            recipient=data.recipient,
            error=str(e),
        )


@router.get("/notifications/channels", response_model=dict)
async def list_notification_channels() -> dict:
    """List configured notification channels.

    Returns:
        List of channel names and their status.
    """
    manager = get_notification_manager()
    settings = get_settings()

    channels = []

    # Email channel
    channels.append({
        "name": "email",
        "enabled": settings.notifications.email.enabled,
        "registered": "email" in manager.channels,
        "config": {
            "host": settings.notifications.email.host,
            "port": settings.notifications.email.port,
            "from_address": settings.notifications.email.from_address,
        } if settings.notifications.email.enabled else None,
    })

    return {
        "channels": channels,
        "routing": {
            "critical": settings.notifications.critical_channels,
            "high": settings.notifications.high_channels,
            "warning": settings.notifications.warning_channels,
            "info": settings.notifications.info_channels,
        },
    }

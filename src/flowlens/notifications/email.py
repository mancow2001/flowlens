"""Email notification channel.

Sends notifications via SMTP using aiosmtplib.
"""

import asyncio
from dataclasses import dataclass
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

import aiosmtplib

from flowlens.common.logging import get_logger
from flowlens.notifications.base import (
    Notification,
    NotificationChannel,
    NotificationPriority,
    NotificationResult,
)

logger = get_logger(__name__)


@dataclass
class EmailSettings:
    """Email channel configuration."""

    host: str = "localhost"
    port: int = 587
    username: str | None = None
    password: str | None = None
    use_tls: bool = True
    start_tls: bool = True
    from_address: str = "flowlens@localhost"
    from_name: str = "FlowLens"
    timeout: int = 30
    validate_certs: bool = True


class EmailChannel(NotificationChannel):
    """Email notification channel using SMTP."""

    def __init__(self, settings: EmailSettings | None = None) -> None:
        """Initialize email channel.

        Args:
            settings: Email configuration settings.
        """
        self._settings = settings or EmailSettings()

    @property
    def name(self) -> str:
        return "email"

    async def send(
        self,
        notification: Notification,
        recipients: list[str],
    ) -> list[NotificationResult]:
        """Send email notification to recipients.

        Args:
            notification: Notification to send.
            recipients: List of email addresses.

        Returns:
            List of results for each recipient.
        """
        results: list[NotificationResult] = []

        for recipient in recipients:
            try:
                message = self._build_message(notification, recipient)
                message_id = await self._send_email(message, recipient)

                results.append(NotificationResult(
                    success=True,
                    channel="email",
                    recipient=recipient,
                    message_id=message_id,
                ))

                logger.debug(
                    "Email sent successfully",
                    recipient=recipient,
                    subject=notification.subject,
                )

            except Exception as e:
                logger.warning(
                    "Failed to send email",
                    recipient=recipient,
                    error=str(e),
                )
                results.append(NotificationResult(
                    success=False,
                    channel="email",
                    recipient=recipient,
                    error=str(e),
                ))

        return results

    def _build_message(
        self,
        notification: Notification,
        recipient: str,
    ) -> MIMEMultipart:
        """Build email message from notification.

        Args:
            notification: Notification to convert.
            recipient: Recipient email address.

        Returns:
            MIME message.
        """
        message = MIMEMultipart("alternative")

        # Headers
        message["Subject"] = notification.subject
        message["From"] = f"{self._settings.from_name} <{self._settings.from_address}>"
        message["To"] = recipient

        # Priority header
        if notification.priority == NotificationPriority.CRITICAL:
            message["X-Priority"] = "1"
            message["Importance"] = "high"
        elif notification.priority == NotificationPriority.HIGH:
            message["X-Priority"] = "2"
            message["Importance"] = "high"
        elif notification.priority == NotificationPriority.LOW:
            message["X-Priority"] = "5"
            message["Importance"] = "low"

        # Add custom headers for tracking
        if notification.alert_id:
            message["X-FlowLens-Alert-ID"] = str(notification.alert_id)
        if notification.change_event_id:
            message["X-FlowLens-Change-ID"] = str(notification.change_event_id)

        # Body
        text_part = MIMEText(notification.body, "plain", "utf-8")
        message.attach(text_part)

        if notification.html_body:
            html_part = MIMEText(notification.html_body, "html", "utf-8")
            message.attach(html_part)

        return message

    async def _send_email(
        self,
        message: MIMEMultipart,
        recipient: str,
    ) -> str:
        """Send email via SMTP.

        Args:
            message: Email message to send.
            recipient: Recipient address.

        Returns:
            Message ID.
        """
        settings = self._settings

        # Create SMTP client
        smtp = aiosmtplib.SMTP(
            hostname=settings.host,
            port=settings.port,
            timeout=settings.timeout,
            use_tls=settings.use_tls and not settings.start_tls,
            validate_certs=settings.validate_certs,
        )

        try:
            await smtp.connect()

            # Start TLS if configured
            if settings.start_tls and not settings.use_tls:
                await smtp.starttls()

            # Authenticate if credentials provided
            if settings.username and settings.password:
                await smtp.login(settings.username, settings.password)

            # Send the message
            response = await smtp.send_message(message)

            # Generate a message ID from response
            message_id = f"{hash(response)}@flowlens"
            return message_id

        finally:
            await smtp.quit()

    async def test_connection(self) -> bool:
        """Test SMTP connection.

        Returns:
            True if connection successful.
        """
        settings = self._settings

        try:
            smtp = aiosmtplib.SMTP(
                hostname=settings.host,
                port=settings.port,
                timeout=10,
                use_tls=settings.use_tls and not settings.start_tls,
                validate_certs=settings.validate_certs,
            )

            await smtp.connect()

            if settings.start_tls and not settings.use_tls:
                await smtp.starttls()

            if settings.username and settings.password:
                await smtp.login(settings.username, settings.password)

            await smtp.quit()

            logger.info("Email channel connection test successful")
            return True

        except Exception as e:
            logger.error("Email channel connection test failed", error=str(e))
            return False


def create_alert_notification(
    alert_title: str,
    alert_message: str,
    severity: str,
    asset_name: str | None = None,
    alert_id: str | None = None,
    dashboard_url: str | None = None,
) -> Notification:
    """Create a notification for an alert.

    Args:
        alert_title: Alert title.
        alert_message: Alert message.
        severity: Alert severity.
        asset_name: Related asset name.
        alert_id: Alert ID.
        dashboard_url: Link to dashboard.

    Returns:
        Notification object.
    """
    # Map severity to priority
    priority_map = {
        "critical": NotificationPriority.CRITICAL,
        "error": NotificationPriority.HIGH,
        "warning": NotificationPriority.NORMAL,
        "info": NotificationPriority.LOW,
    }
    priority = priority_map.get(severity.lower(), NotificationPriority.NORMAL)

    # Build subject
    severity_emoji = {
        "critical": "[CRITICAL]",
        "error": "[ERROR]",
        "warning": "[WARNING]",
        "info": "[INFO]",
    }
    prefix = severity_emoji.get(severity.lower(), "[ALERT]")
    subject = f"{prefix} FlowLens: {alert_title}"

    # Build plain text body
    body_lines = [
        f"Alert: {alert_title}",
        f"Severity: {severity.upper()}",
        "",
        alert_message,
    ]

    if asset_name:
        body_lines.insert(2, f"Asset: {asset_name}")

    if dashboard_url:
        body_lines.extend(["", f"View in FlowLens: {dashboard_url}"])

    body = "\n".join(body_lines)

    # Build HTML body
    severity_colors = {
        "critical": "#dc3545",
        "error": "#fd7e14",
        "warning": "#ffc107",
        "info": "#17a2b8",
    }
    color = severity_colors.get(severity.lower(), "#6c757d")

    html_body = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }}
            .alert-box {{ border-left: 4px solid {color}; padding: 16px; margin: 16px 0; background: #f8f9fa; }}
            .severity {{ color: {color}; font-weight: bold; text-transform: uppercase; }}
            .message {{ margin-top: 12px; }}
            .footer {{ margin-top: 24px; color: #6c757d; font-size: 12px; }}
            .button {{ display: inline-block; padding: 8px 16px; background: #007bff; color: white; text-decoration: none; border-radius: 4px; }}
        </style>
    </head>
    <body>
        <div class="alert-box">
            <div class="severity">{severity.upper()}</div>
            <h2 style="margin: 8px 0;">{alert_title}</h2>
            {"<p><strong>Asset:</strong> " + asset_name + "</p>" if asset_name else ""}
            <div class="message">{alert_message}</div>
        </div>
        {f'<p><a class="button" href="{dashboard_url}">View in FlowLens</a></p>' if dashboard_url else ""}
        <div class="footer">
            <p>This alert was generated by FlowLens Application Dependency Mapping.</p>
        </div>
    </body>
    </html>
    """

    from uuid import UUID
    return Notification(
        subject=subject,
        body=body,
        html_body=html_body,
        priority=priority,
        alert_id=UUID(alert_id) if alert_id else None,
    )


def create_change_notification(
    change_type: str,
    summary: str,
    description: str | None = None,
    affected_count: int = 0,
    change_event_id: str | None = None,
    dashboard_url: str | None = None,
) -> Notification:
    """Create a notification for a change event.

    Args:
        change_type: Type of change.
        summary: Change summary.
        description: Detailed description.
        affected_count: Number of affected assets.
        change_event_id: Change event ID.
        dashboard_url: Link to dashboard.

    Returns:
        Notification object.
    """
    subject = f"[CHANGE] FlowLens: {change_type.replace('_', ' ').title()}"

    body_lines = [
        f"Change Detected: {change_type.replace('_', ' ').title()}",
        "",
        summary,
    ]

    if description:
        body_lines.extend(["", description])

    if affected_count > 0:
        body_lines.extend(["", f"Affected assets: {affected_count}"])

    if dashboard_url:
        body_lines.extend(["", f"View in FlowLens: {dashboard_url}"])

    body = "\n".join(body_lines)

    html_body = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }}
            .change-box {{ border-left: 4px solid #17a2b8; padding: 16px; margin: 16px 0; background: #f8f9fa; }}
            .change-type {{ color: #17a2b8; font-weight: bold; text-transform: uppercase; }}
            .summary {{ margin-top: 12px; font-size: 16px; }}
            .description {{ margin-top: 12px; color: #495057; }}
            .footer {{ margin-top: 24px; color: #6c757d; font-size: 12px; }}
            .button {{ display: inline-block; padding: 8px 16px; background: #007bff; color: white; text-decoration: none; border-radius: 4px; }}
        </style>
    </head>
    <body>
        <div class="change-box">
            <div class="change-type">{change_type.replace('_', ' ').title()}</div>
            <div class="summary">{summary}</div>
            {f'<div class="description">{description}</div>' if description else ""}
            {f'<p><strong>Affected assets:</strong> {affected_count}</p>' if affected_count > 0 else ""}
        </div>
        {f'<p><a class="button" href="{dashboard_url}">View in FlowLens</a></p>' if dashboard_url else ""}
        <div class="footer">
            <p>This notification was generated by FlowLens Application Dependency Mapping.</p>
        </div>
    </body>
    </html>
    """

    from uuid import UUID
    return Notification(
        subject=subject,
        body=body,
        html_body=html_body,
        priority=NotificationPriority.NORMAL,
        change_event_id=UUID(change_event_id) if change_event_id else None,
    )

"""Slack notification channel.

Sends notifications via Slack Incoming Webhooks using Block Kit formatting.
"""

import asyncio
import json
from dataclasses import dataclass
from typing import Any

import httpx

from flowlens.common.logging import get_logger
from flowlens.notifications.base import (
    Notification,
    NotificationChannel,
    NotificationPriority,
    NotificationResult,
)

logger = get_logger(__name__)


@dataclass
class SlackSettings:
    """Slack channel configuration."""

    webhook_url: str
    default_channel: str | None = None  # Optional channel override
    username: str = "FlowLens"
    icon_emoji: str = ":bell:"
    timeout: int = 30
    retry_count: int = 3
    retry_delay: float = 1.0


class SlackChannel(NotificationChannel):
    """Slack notification channel using Incoming Webhooks."""

    def __init__(self, settings: SlackSettings) -> None:
        """Initialize Slack channel.

        Args:
            settings: Slack configuration settings.
        """
        self._settings = settings

    @property
    def name(self) -> str:
        return "slack"

    def _get_severity_color(self, priority: NotificationPriority) -> str:
        """Get Slack attachment color based on priority.

        Args:
            priority: Notification priority.

        Returns:
            Hex color code.
        """
        colors = {
            NotificationPriority.CRITICAL: "#dc2626",  # Red
            NotificationPriority.HIGH: "#ea580c",  # Orange
            NotificationPriority.NORMAL: "#eab308",  # Yellow
            NotificationPriority.LOW: "#3b82f6",  # Blue
        }
        return colors.get(priority, "#6b7280")  # Gray default

    def _get_severity_emoji(self, priority: NotificationPriority) -> str:
        """Get emoji for priority level.

        Args:
            priority: Notification priority.

        Returns:
            Emoji string.
        """
        emojis = {
            NotificationPriority.CRITICAL: ":rotating_light:",
            NotificationPriority.HIGH: ":warning:",
            NotificationPriority.NORMAL: ":information_source:",
            NotificationPriority.LOW: ":bell:",
        }
        return emojis.get(priority, ":bell:")

    def _build_payload(self, notification: Notification) -> dict[str, Any]:
        """Build Slack message payload using Block Kit.

        Args:
            notification: Notification to convert.

        Returns:
            Slack message payload.
        """
        color = self._get_severity_color(notification.priority)
        emoji = self._get_severity_emoji(notification.priority)

        # Build blocks
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{emoji} {notification.subject}",
                    "emoji": True,
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": notification.body,
                }
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Priority:* {notification.priority.value.upper()} | *Time:* {notification.created_at.strftime('%Y-%m-%d %H:%M:%S UTC')}",
                    }
                ]
            },
        ]

        # Add alert link if available
        if notification.alert_id:
            blocks.append({
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "View Alert",
                            "emoji": True,
                        },
                        "url": f"/alerts/{notification.alert_id}",
                        "action_id": "view_alert",
                    }
                ]
            })

        # Add divider
        blocks.append({"type": "divider"})

        payload: dict[str, Any] = {
            "username": self._settings.username,
            "icon_emoji": self._settings.icon_emoji,
            "blocks": blocks,
            # Also include attachments for color strip
            "attachments": [
                {
                    "color": color,
                    "fallback": f"{notification.subject}: {notification.body}",
                }
            ],
        }

        # Add channel override if specified
        if self._settings.default_channel:
            payload["channel"] = self._settings.default_channel

        return payload

    async def _send_with_retry(
        self,
        client: httpx.AsyncClient,
        payload: dict[str, Any],
    ) -> tuple[bool, str | None, str | None]:
        """Send request with exponential backoff retry.

        Args:
            client: HTTP client.
            payload: Request payload.

        Returns:
            Tuple of (success, message_id, error).
        """
        settings = self._settings
        body = json.dumps(payload)

        headers = {
            "Content-Type": "application/json",
        }

        last_error = None

        for attempt in range(settings.retry_count + 1):
            try:
                response = await client.post(
                    settings.webhook_url,
                    content=body,
                    headers=headers,
                    timeout=settings.timeout,
                )

                # Slack returns "ok" for success
                if response.status_code == 200 and response.text == "ok":
                    message_id = f"slack-{hash(body)}@flowlens"
                    return True, message_id, None

                # Slack error
                if response.status_code >= 400:
                    return False, None, f"Slack error: {response.text}"

            except httpx.TimeoutException:
                last_error = "Request timed out"
                logger.warning(
                    "Slack webhook timeout, retrying",
                    attempt=attempt + 1,
                )
            except httpx.ConnectError as e:
                last_error = f"Connection failed: {str(e)}"
                logger.warning(
                    "Slack webhook connection failed, retrying",
                    error=str(e),
                    attempt=attempt + 1,
                )
            except Exception as e:
                last_error = str(e)
                logger.warning(
                    "Slack webhook request failed, retrying",
                    error=str(e),
                    attempt=attempt + 1,
                )

            # Exponential backoff before retry
            if attempt < settings.retry_count:
                delay = settings.retry_delay * (2 ** attempt)
                await asyncio.sleep(delay)

        return False, None, last_error

    async def send(
        self,
        notification: Notification,
        recipients: list[str],
    ) -> list[NotificationResult]:
        """Send Slack notification.

        For Slack webhooks, recipients are typically ignored as the destination
        is configured in the webhook URL or settings.

        Args:
            notification: Notification to send.
            recipients: List of recipient identifiers (for result tracking).

        Returns:
            List of results for each recipient.
        """
        payload = self._build_payload(notification)

        async with httpx.AsyncClient() as client:
            success, message_id, error = await self._send_with_retry(client, payload)

        # Return result for each recipient
        results = []
        for recipient in recipients:
            results.append(NotificationResult(
                success=success,
                channel="slack",
                recipient=recipient,
                message_id=message_id,
                error=error,
            ))

        if success:
            logger.debug(
                "Slack notification sent",
                subject=notification.subject,
            )
        else:
            logger.warning(
                "Slack notification failed",
                error=error,
            )

        return results

    async def test_connection(self) -> bool:
        """Test Slack webhook connectivity.

        Returns:
            True if connection successful.
        """
        test_payload = {
            "username": self._settings.username,
            "icon_emoji": self._settings.icon_emoji,
            "text": ":white_check_mark: FlowLens Slack integration test successful!",
        }

        if self._settings.default_channel:
            test_payload["channel"] = self._settings.default_channel

        async with httpx.AsyncClient() as client:
            success, _, error = await self._send_with_retry(client, test_payload)

        if success:
            logger.info("Slack channel connection test successful")
        else:
            logger.error("Slack channel connection test failed", error=error)

        return success

"""Microsoft Teams notification channel.

Sends notifications via Microsoft Teams Incoming Webhooks using Adaptive Cards.
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
class TeamsSettings:
    """Teams channel configuration."""

    webhook_url: str
    timeout: int = 30
    retry_count: int = 3
    retry_delay: float = 1.0


class TeamsChannel(NotificationChannel):
    """Microsoft Teams notification channel using Incoming Webhooks."""

    def __init__(self, settings: TeamsSettings) -> None:
        """Initialize Teams channel.

        Args:
            settings: Teams configuration settings.
        """
        self._settings = settings

    @property
    def name(self) -> str:
        return "teams"

    def _get_severity_color(self, priority: NotificationPriority) -> str:
        """Get Teams accent color based on priority.

        Args:
            priority: Notification priority.

        Returns:
            Hex color code (without #).
        """
        colors = {
            NotificationPriority.CRITICAL: "dc2626",  # Red
            NotificationPriority.HIGH: "ea580c",  # Orange
            NotificationPriority.NORMAL: "eab308",  # Yellow
            NotificationPriority.LOW: "3b82f6",  # Blue
        }
        return colors.get(priority, "6b7280")  # Gray default

    def _get_severity_label(self, priority: NotificationPriority) -> str:
        """Get human-readable severity label.

        Args:
            priority: Notification priority.

        Returns:
            Label string.
        """
        labels = {
            NotificationPriority.CRITICAL: "🚨 Critical",
            NotificationPriority.HIGH: "⚠️ High",
            NotificationPriority.NORMAL: "ℹ️ Normal",
            NotificationPriority.LOW: "🔔 Low",
        }
        return labels.get(priority, "Info")

    def _build_adaptive_card(self, notification: Notification) -> dict[str, Any]:
        """Build Teams Adaptive Card payload.

        Args:
            notification: Notification to convert.

        Returns:
            Teams message card payload.
        """
        color = self._get_severity_color(notification.priority)
        severity_label = self._get_severity_label(notification.priority)

        # Build Adaptive Card body
        body = [
            {
                "type": "TextBlock",
                "size": "Large",
                "weight": "Bolder",
                "text": notification.subject,
                "wrap": True,
            },
            {
                "type": "ColumnSet",
                "columns": [
                    {
                        "type": "Column",
                        "width": "auto",
                        "items": [
                            {
                                "type": "TextBlock",
                                "text": severity_label,
                                "weight": "Bolder",
                                "color": "attention" if notification.priority in [
                                    NotificationPriority.CRITICAL,
                                    NotificationPriority.HIGH,
                                ] else "default",
                            }
                        ]
                    },
                    {
                        "type": "Column",
                        "width": "stretch",
                        "items": [
                            {
                                "type": "TextBlock",
                                "text": notification.created_at.strftime("%Y-%m-%d %H:%M:%S UTC"),
                                "isSubtle": True,
                                "horizontalAlignment": "Right",
                            }
                        ]
                    }
                ]
            },
            {
                "type": "TextBlock",
                "text": notification.body,
                "wrap": True,
                "spacing": "Medium",
            },
        ]

        # Add facts for metadata
        facts = []
        if notification.alert_id:
            facts.append({
                "title": "Alert ID",
                "value": str(notification.alert_id),
            })
        if notification.asset_id:
            facts.append({
                "title": "Asset ID",
                "value": str(notification.asset_id),
            })

        if facts:
            body.append({
                "type": "FactSet",
                "facts": facts,
                "spacing": "Medium",
            })

        # Build actions
        actions = []
        if notification.alert_id:
            actions.append({
                "type": "Action.OpenUrl",
                "title": "View Alert",
                "url": f"/alerts/{notification.alert_id}",
            })

        # Build the Adaptive Card
        card = {
            "type": "message",
            "attachments": [
                {
                    "contentType": "application/vnd.microsoft.card.adaptive",
                    "contentUrl": None,
                    "content": {
                        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                        "type": "AdaptiveCard",
                        "version": "1.4",
                        "msteams": {
                            "width": "Full",
                        },
                        "body": body,
                        "actions": actions if actions else None,
                    }
                }
            ]
        }

        return card

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

                # Teams returns 200 for success
                if response.status_code == 200:
                    message_id = f"teams-{hash(body)}@flowlens"
                    return True, message_id, None

                # Teams error - check response
                if response.status_code >= 400:
                    error_text = response.text[:200] if response.text else f"HTTP {response.status_code}"
                    return False, None, f"Teams error: {error_text}"

            except httpx.TimeoutException:
                last_error = "Request timed out"
                logger.warning(
                    "Teams webhook timeout, retrying",
                    attempt=attempt + 1,
                )
            except httpx.ConnectError as e:
                last_error = f"Connection failed: {str(e)}"
                logger.warning(
                    "Teams webhook connection failed, retrying",
                    error=str(e),
                    attempt=attempt + 1,
                )
            except Exception as e:
                last_error = str(e)
                logger.warning(
                    "Teams webhook request failed, retrying",
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
        """Send Teams notification.

        For Teams webhooks, recipients are typically ignored as the destination
        is configured in the webhook URL.

        Args:
            notification: Notification to send.
            recipients: List of recipient identifiers (for result tracking).

        Returns:
            List of results for each recipient.
        """
        payload = self._build_adaptive_card(notification)

        async with httpx.AsyncClient() as client:
            success, message_id, error = await self._send_with_retry(client, payload)

        # Return result for each recipient
        results = []
        for recipient in recipients:
            results.append(NotificationResult(
                success=success,
                channel="teams",
                recipient=recipient,
                message_id=message_id,
                error=error,
            ))

        if success:
            logger.debug(
                "Teams notification sent",
                subject=notification.subject,
            )
        else:
            logger.warning(
                "Teams notification failed",
                error=error,
            )

        return results

    async def test_connection(self) -> bool:
        """Test Teams webhook connectivity.

        Returns:
            True if connection successful.
        """
        test_payload = {
            "type": "message",
            "attachments": [
                {
                    "contentType": "application/vnd.microsoft.card.adaptive",
                    "content": {
                        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                        "type": "AdaptiveCard",
                        "version": "1.4",
                        "body": [
                            {
                                "type": "TextBlock",
                                "size": "Medium",
                                "weight": "Bolder",
                                "text": "✅ FlowLens Integration Test",
                            },
                            {
                                "type": "TextBlock",
                                "text": "Microsoft Teams integration is working correctly!",
                                "wrap": True,
                            }
                        ]
                    }
                }
            ]
        }

        async with httpx.AsyncClient() as client:
            success, _, error = await self._send_with_retry(client, test_payload)

        if success:
            logger.info("Teams channel connection test successful")
        else:
            logger.error("Teams channel connection test failed", error=error)

        return success

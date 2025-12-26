"""PagerDuty notification channel.

Sends notifications via PagerDuty Events API v2.
"""

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime
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

# PagerDuty Events API v2 endpoint
PAGERDUTY_EVENTS_API = "https://events.pagerduty.com/v2/enqueue"


@dataclass
class PagerDutySettings:
    """PagerDuty channel configuration."""

    routing_key: str  # Integration key from PagerDuty service
    service_name: str = "FlowLens"
    timeout: int = 30
    retry_count: int = 3
    retry_delay: float = 1.0


class PagerDutyChannel(NotificationChannel):
    """PagerDuty notification channel using Events API v2."""

    def __init__(self, settings: PagerDutySettings) -> None:
        """Initialize PagerDuty channel.

        Args:
            settings: PagerDuty configuration settings.
        """
        self._settings = settings

    @property
    def name(self) -> str:
        return "pagerduty"

    def _get_severity(self, priority: NotificationPriority) -> str:
        """Map notification priority to PagerDuty severity.

        PagerDuty supports: critical, error, warning, info

        Args:
            priority: Notification priority.

        Returns:
            PagerDuty severity string.
        """
        mapping = {
            NotificationPriority.CRITICAL: "critical",
            NotificationPriority.HIGH: "error",
            NotificationPriority.NORMAL: "warning",
            NotificationPriority.LOW: "info",
        }
        return mapping.get(priority, "info")

    def _get_dedup_key(self, notification: Notification) -> str:
        """Generate a dedup key for the notification.

        PagerDuty uses dedup_key to group related events.

        Args:
            notification: The notification.

        Returns:
            Dedup key string.
        """
        if notification.alert_id:
            return f"flowlens-alert-{notification.alert_id}"
        if notification.change_event_id:
            return f"flowlens-change-{notification.change_event_id}"
        if notification.asset_id:
            return f"flowlens-asset-{notification.asset_id}-{notification.subject}"
        return f"flowlens-{hash(notification.subject)}"

    def _build_payload(
        self,
        notification: Notification,
        action: str = "trigger",
    ) -> dict[str, Any]:
        """Build PagerDuty Events API v2 payload.

        Args:
            notification: Notification to convert.
            action: Event action (trigger, acknowledge, resolve).

        Returns:
            PagerDuty event payload.
        """
        severity = self._get_severity(notification.priority)
        dedup_key = self._get_dedup_key(notification)

        payload: dict[str, Any] = {
            "routing_key": self._settings.routing_key,
            "event_action": action,
            "dedup_key": dedup_key,
        }

        # For trigger events, include full payload
        if action == "trigger":
            payload["payload"] = {
                "summary": notification.subject,
                "source": self._settings.service_name,
                "severity": severity,
                "timestamp": notification.created_at.isoformat() + "Z",
                "class": "alert",
            }

            # Add custom details
            custom_details: dict[str, Any] = {
                "description": notification.body,
            }

            if notification.alert_id:
                custom_details["alert_id"] = str(notification.alert_id)
            if notification.change_event_id:
                custom_details["change_event_id"] = str(notification.change_event_id)
            if notification.asset_id:
                custom_details["asset_id"] = str(notification.asset_id)
            if notification.metadata:
                custom_details.update(notification.metadata)

            payload["payload"]["custom_details"] = custom_details

            # Add links
            links = []
            if notification.alert_id:
                links.append({
                    "href": f"/alerts/{notification.alert_id}",
                    "text": "View Alert in FlowLens",
                })
            if notification.asset_id:
                links.append({
                    "href": f"/assets/{notification.asset_id}",
                    "text": "View Asset in FlowLens",
                })
            if links:
                payload["links"] = links

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
                    PAGERDUTY_EVENTS_API,
                    content=body,
                    headers=headers,
                    timeout=settings.timeout,
                )

                # PagerDuty returns 202 for accepted events
                if response.status_code == 202:
                    try:
                        response_data = response.json()
                        message_id = response_data.get("dedup_key")
                        return True, message_id, None
                    except Exception:
                        return True, payload.get("dedup_key"), None

                # Handle specific PagerDuty errors
                if response.status_code == 400:
                    error_text = response.text[:200]
                    return False, None, f"Invalid request: {error_text}"

                if response.status_code == 429:
                    # Rate limited - wait and retry
                    last_error = "Rate limited"
                    logger.warning(
                        "PagerDuty rate limited, retrying",
                        attempt=attempt + 1,
                    )
                else:
                    # Other error
                    last_error = f"HTTP {response.status_code}: {response.text[:100]}"
                    logger.warning(
                        "PagerDuty request failed",
                        status_code=response.status_code,
                        attempt=attempt + 1,
                    )

            except httpx.TimeoutException:
                last_error = "Request timed out"
                logger.warning(
                    "PagerDuty timeout, retrying",
                    attempt=attempt + 1,
                )
            except httpx.ConnectError as e:
                last_error = f"Connection failed: {str(e)}"
                logger.warning(
                    "PagerDuty connection failed, retrying",
                    error=str(e),
                    attempt=attempt + 1,
                )
            except Exception as e:
                last_error = str(e)
                logger.warning(
                    "PagerDuty request failed, retrying",
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
        """Send PagerDuty notification.

        Creates a PagerDuty incident via Events API v2.

        Args:
            notification: Notification to send.
            recipients: List of recipient identifiers (for result tracking).

        Returns:
            List of results for each recipient.
        """
        payload = self._build_payload(notification, action="trigger")

        async with httpx.AsyncClient() as client:
            success, message_id, error = await self._send_with_retry(client, payload)

        # Return result for each recipient
        results = []
        for recipient in recipients:
            results.append(NotificationResult(
                success=success,
                channel="pagerduty",
                recipient=recipient,
                message_id=message_id,
                error=error,
            ))

        if success:
            logger.debug(
                "PagerDuty notification sent",
                subject=notification.subject,
                dedup_key=message_id,
            )
        else:
            logger.warning(
                "PagerDuty notification failed",
                error=error,
            )

        return results

    async def resolve_incident(
        self,
        notification: Notification,
    ) -> NotificationResult:
        """Resolve a PagerDuty incident.

        Uses the same dedup_key as the original alert to resolve it.

        Args:
            notification: Original notification (used for dedup_key).

        Returns:
            Result of the resolve operation.
        """
        payload = self._build_payload(notification, action="resolve")

        async with httpx.AsyncClient() as client:
            success, message_id, error = await self._send_with_retry(client, payload)

        if success:
            logger.info(
                "PagerDuty incident resolved",
                dedup_key=payload.get("dedup_key"),
            )
        else:
            logger.warning(
                "PagerDuty incident resolution failed",
                error=error,
            )

        return NotificationResult(
            success=success,
            channel="pagerduty",
            recipient="pagerduty",
            message_id=message_id,
            error=error,
        )

    async def acknowledge_incident(
        self,
        notification: Notification,
    ) -> NotificationResult:
        """Acknowledge a PagerDuty incident.

        Uses the same dedup_key as the original alert to acknowledge it.

        Args:
            notification: Original notification (used for dedup_key).

        Returns:
            Result of the acknowledge operation.
        """
        payload = self._build_payload(notification, action="acknowledge")

        async with httpx.AsyncClient() as client:
            success, message_id, error = await self._send_with_retry(client, payload)

        if success:
            logger.info(
                "PagerDuty incident acknowledged",
                dedup_key=payload.get("dedup_key"),
            )
        else:
            logger.warning(
                "PagerDuty incident acknowledgment failed",
                error=error,
            )

        return NotificationResult(
            success=success,
            channel="pagerduty",
            recipient="pagerduty",
            message_id=message_id,
            error=error,
        )

    async def test_connection(self) -> bool:
        """Test PagerDuty integration connectivity.

        Sends a test event that immediately resolves.

        Returns:
            True if connection successful.
        """
        test_notification = Notification(
            subject="FlowLens PagerDuty Integration Test",
            body="This is a test notification from FlowLens to verify PagerDuty integration.",
            priority=NotificationPriority.LOW,
        )

        # Send trigger
        trigger_payload = self._build_payload(test_notification, action="trigger")

        async with httpx.AsyncClient() as client:
            success, dedup_key, error = await self._send_with_retry(client, trigger_payload)

            if not success:
                logger.error("PagerDuty connection test failed", error=error)
                return False

            # Immediately resolve the test incident
            resolve_payload = {
                "routing_key": self._settings.routing_key,
                "event_action": "resolve",
                "dedup_key": dedup_key or trigger_payload["dedup_key"],
            }

            await self._send_with_retry(client, resolve_payload)

        logger.info("PagerDuty channel connection test successful")
        return True

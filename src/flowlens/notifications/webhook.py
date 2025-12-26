"""Webhook notification channel.

Sends notifications via HTTP POST with HMAC signature support.
"""

import asyncio
import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx

from flowlens.common.logging import get_logger
from flowlens.notifications.base import (
    Notification,
    NotificationChannel,
    NotificationResult,
)

logger = get_logger(__name__)


@dataclass
class WebhookSettings:
    """Webhook channel configuration."""

    url: str
    secret: str | None = None  # For HMAC signature
    timeout: int = 30
    retry_count: int = 3
    retry_delay: float = 1.0  # Base delay for exponential backoff
    headers: dict[str, str] | None = None


class WebhookChannel(NotificationChannel):
    """Webhook notification channel using HTTP POST."""

    def __init__(self, settings: WebhookSettings) -> None:
        """Initialize webhook channel.

        Args:
            settings: Webhook configuration settings.
        """
        self._settings = settings

    @property
    def name(self) -> str:
        return "webhook"

    def _compute_signature(self, payload: bytes) -> str:
        """Compute HMAC-SHA256 signature for payload.

        Args:
            payload: Request body bytes.

        Returns:
            Hex-encoded signature.
        """
        if not self._settings.secret:
            return ""

        signature = hmac.new(
            self._settings.secret.encode("utf-8"),
            payload,
            hashlib.sha256,
        )
        return signature.hexdigest()

    def _build_payload(self, notification: Notification) -> dict[str, Any]:
        """Build JSON payload from notification.

        Args:
            notification: Notification to convert.

        Returns:
            Payload dictionary.
        """
        payload = {
            "subject": notification.subject,
            "body": notification.body,
            "priority": notification.priority.value,
            "timestamp": notification.created_at.isoformat(),
        }

        # Add optional context
        if notification.alert_id:
            payload["alert_id"] = str(notification.alert_id)
        if notification.change_event_id:
            payload["change_event_id"] = str(notification.change_event_id)
        if notification.asset_id:
            payload["asset_id"] = str(notification.asset_id)

        # Add metadata
        if notification.metadata:
            payload["metadata"] = notification.metadata

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
        body = json.dumps(payload).encode("utf-8")

        # Build headers
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "FlowLens/1.0",
            "X-FlowLens-Timestamp": datetime.utcnow().isoformat(),
        }

        # Add HMAC signature if secret configured
        if settings.secret:
            signature = self._compute_signature(body)
            headers["X-FlowLens-Signature"] = f"sha256={signature}"

        # Add custom headers
        if settings.headers:
            headers.update(settings.headers)

        last_error = None

        for attempt in range(settings.retry_count + 1):
            try:
                response = await client.post(
                    settings.url,
                    content=body,
                    headers=headers,
                    timeout=settings.timeout,
                )

                if response.status_code >= 200 and response.status_code < 300:
                    # Success - try to get message ID from response
                    message_id = None
                    try:
                        response_data = response.json()
                        message_id = response_data.get("id") or response_data.get("message_id")
                    except Exception:
                        pass

                    if not message_id:
                        message_id = f"webhook-{hash(body)}@flowlens"

                    return True, message_id, None

                # Server error - retry
                if response.status_code >= 500:
                    last_error = f"Server error: {response.status_code}"
                    logger.warning(
                        "Webhook server error, retrying",
                        status_code=response.status_code,
                        attempt=attempt + 1,
                    )
                else:
                    # Client error - don't retry
                    return False, None, f"HTTP {response.status_code}: {response.text[:200]}"

            except httpx.TimeoutException:
                last_error = "Request timed out"
                logger.warning(
                    "Webhook timeout, retrying",
                    url=settings.url,
                    attempt=attempt + 1,
                )
            except httpx.ConnectError as e:
                last_error = f"Connection failed: {str(e)}"
                logger.warning(
                    "Webhook connection failed, retrying",
                    error=str(e),
                    attempt=attempt + 1,
                )
            except Exception as e:
                last_error = str(e)
                logger.warning(
                    "Webhook request failed, retrying",
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
        """Send webhook notification.

        For webhooks, recipients are typically ignored as the destination
        is configured in settings. Each recipient in the list will get
        a separate result for consistency with other channels.

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
                channel="webhook",
                recipient=recipient,
                message_id=message_id,
                error=error,
            ))

        if success:
            logger.debug(
                "Webhook notification sent",
                url=self._settings.url,
                subject=notification.subject,
            )
        else:
            logger.warning(
                "Webhook notification failed",
                url=self._settings.url,
                error=error,
            )

        return results

    async def test_connection(self) -> bool:
        """Test webhook endpoint connectivity.

        Sends a test payload to verify the webhook is reachable.

        Returns:
            True if connection successful.
        """
        test_payload = {
            "subject": "FlowLens Webhook Test",
            "body": "This is a test notification from FlowLens.",
            "priority": "low",
            "timestamp": datetime.utcnow().isoformat(),
            "metadata": {"test": True},
        }

        async with httpx.AsyncClient() as client:
            success, _, error = await self._send_with_retry(client, test_payload)

        if success:
            logger.info("Webhook channel connection test successful")
        else:
            logger.error("Webhook channel connection test failed", error=error)

        return success

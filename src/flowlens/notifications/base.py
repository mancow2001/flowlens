"""Base notification system interfaces.

Defines the notification channel interface and manager.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from flowlens.common.logging import get_logger

logger = get_logger(__name__)


class NotificationPriority(str, Enum):
    """Notification priority levels."""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class Notification:
    """A notification to be sent."""

    subject: str
    body: str
    priority: NotificationPriority = NotificationPriority.NORMAL
    html_body: str | None = None

    # Context
    alert_id: UUID | None = None
    change_event_id: UUID | None = None
    asset_id: UUID | None = None

    # Metadata
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class NotificationResult:
    """Result of sending a notification."""

    success: bool
    channel: str
    recipient: str
    message_id: str | None = None
    error: str | None = None
    sent_at: datetime = field(default_factory=datetime.utcnow)


class NotificationChannel(ABC):
    """Abstract base class for notification channels."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Channel name (e.g., 'email', 'slack')."""
        ...

    @abstractmethod
    async def send(
        self,
        notification: Notification,
        recipients: list[str],
    ) -> list[NotificationResult]:
        """Send notification to recipients.

        Args:
            notification: Notification to send.
            recipients: List of recipient addresses.

        Returns:
            List of results for each recipient.
        """
        ...

    @abstractmethod
    async def test_connection(self) -> bool:
        """Test if channel is properly configured.

        Returns:
            True if connection successful.
        """
        ...


class NotificationManager:
    """Manages notification channels and sending.

    Coordinates sending notifications across multiple channels.
    """

    def __init__(self) -> None:
        """Initialize notification manager."""
        self._channels: dict[str, NotificationChannel] = {}

    def register_channel(self, channel: NotificationChannel) -> None:
        """Register a notification channel.

        Args:
            channel: Channel to register.
        """
        self._channels[channel.name] = channel
        logger.info(f"Registered notification channel: {channel.name}")

    def unregister_channel(self, name: str) -> None:
        """Unregister a notification channel.

        Args:
            name: Channel name to unregister.
        """
        if name in self._channels:
            del self._channels[name]
            logger.info(f"Unregistered notification channel: {name}")

    def get_channel(self, name: str) -> NotificationChannel | None:
        """Get a registered channel by name.

        Args:
            name: Channel name.

        Returns:
            Channel if found, None otherwise.
        """
        return self._channels.get(name)

    @property
    def channels(self) -> list[str]:
        """Get list of registered channel names."""
        return list(self._channels.keys())

    async def send(
        self,
        notification: Notification,
        recipients: dict[str, list[str]],
    ) -> dict[str, list[NotificationResult]]:
        """Send notification to recipients across channels.

        Args:
            notification: Notification to send.
            recipients: Dict mapping channel name to list of recipients.

        Returns:
            Dict mapping channel name to list of results.
        """
        results: dict[str, list[NotificationResult]] = {}

        for channel_name, channel_recipients in recipients.items():
            channel = self._channels.get(channel_name)

            if channel is None:
                logger.warning(f"Unknown notification channel: {channel_name}")
                results[channel_name] = [
                    NotificationResult(
                        success=False,
                        channel=channel_name,
                        recipient=r,
                        error=f"Unknown channel: {channel_name}",
                    )
                    for r in channel_recipients
                ]
                continue

            try:
                channel_results = await channel.send(notification, channel_recipients)
                results[channel_name] = channel_results

                # Log results
                success_count = sum(1 for r in channel_results if r.success)
                fail_count = len(channel_results) - success_count

                if fail_count > 0:
                    logger.warning(
                        f"Notification send partial failure",
                        channel=channel_name,
                        success=success_count,
                        failed=fail_count,
                    )
                else:
                    logger.info(
                        f"Notification sent successfully",
                        channel=channel_name,
                        recipients=success_count,
                    )

            except Exception as e:
                logger.error(
                    f"Failed to send notification via {channel_name}",
                    error=str(e),
                )
                results[channel_name] = [
                    NotificationResult(
                        success=False,
                        channel=channel_name,
                        recipient=r,
                        error=str(e),
                    )
                    for r in channel_recipients
                ]

        return results

    async def send_to_all_channels(
        self,
        notification: Notification,
        recipients_per_channel: dict[str, list[str]],
    ) -> dict[str, list[NotificationResult]]:
        """Send notification to all configured channels.

        Convenience method that sends to all registered channels.

        Args:
            notification: Notification to send.
            recipients_per_channel: Recipients for each channel.

        Returns:
            Results from all channels.
        """
        return await self.send(notification, recipients_per_channel)

    async def test_all_channels(self) -> dict[str, bool]:
        """Test all registered channels.

        Returns:
            Dict mapping channel name to test result.
        """
        results = {}

        for name, channel in self._channels.items():
            try:
                results[name] = await channel.test_connection()
            except Exception as e:
                logger.error(f"Channel test failed: {name}", error=str(e))
                results[name] = False

        return results

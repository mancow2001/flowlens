"""WebSocket connection manager for real-time updates.

Manages WebSocket connections and broadcasts events to subscribed clients.
"""

import asyncio
import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from fastapi import WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from flowlens.common.logging import get_logger

logger = get_logger(__name__)


class EventType(str, Enum):
    """WebSocket event types."""

    # Asset events
    ASSET_CREATED = "asset.created"
    ASSET_UPDATED = "asset.updated"
    ASSET_DELETED = "asset.deleted"

    # Dependency events
    DEPENDENCY_CREATED = "dependency.created"
    DEPENDENCY_UPDATED = "dependency.updated"
    DEPENDENCY_DELETED = "dependency.deleted"

    # Change events
    CHANGE_DETECTED = "change.detected"
    CHANGE_PROCESSED = "change.processed"

    # Alert events
    ALERT_CREATED = "alert.created"
    ALERT_ACKNOWLEDGED = "alert.acknowledged"
    ALERT_RESOLVED = "alert.resolved"

    # System events
    SYSTEM_STATUS = "system.status"
    INGESTION_STATS = "ingestion.stats"

    # Topology events
    TOPOLOGY_UPDATED = "topology.updated"


@dataclass
class WebSocketClient:
    """Represents a connected WebSocket client."""

    websocket: WebSocket
    client_id: str
    connected_at: datetime = field(default_factory=datetime.utcnow)
    subscriptions: set[str] = field(default_factory=set)
    metadata: dict[str, Any] = field(default_factory=dict)

    def is_subscribed(self, event_type: str) -> bool:
        """Check if client is subscribed to an event type."""
        if "*" in self.subscriptions:
            return True
        if event_type in self.subscriptions:
            return True
        # Check for wildcard category subscriptions (e.g., "asset.*")
        category = event_type.split(".")[0]
        if f"{category}.*" in self.subscriptions:
            return True
        return False


@dataclass
class WebSocketEvent:
    """WebSocket event message."""

    event_type: str
    data: dict[str, Any]
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def to_json(self) -> str:
        """Serialize event to JSON."""
        return json.dumps({
            "type": self.event_type,
            "data": self.data,
            "timestamp": self.timestamp.isoformat(),
        }, default=str)


class ConnectionManager:
    """Manages WebSocket connections and message broadcasting."""

    def __init__(self, max_connections: int = 1000):
        """Initialize connection manager.

        Args:
            max_connections: Maximum number of concurrent connections.
        """
        self.max_connections = max_connections
        self._clients: dict[str, WebSocketClient] = {}
        self._lock = asyncio.Lock()
        self._message_queue: asyncio.Queue[WebSocketEvent] = asyncio.Queue()
        self._broadcaster_task: asyncio.Task | None = None
        self._running = False

    @property
    def connection_count(self) -> int:
        """Get current number of connections."""
        return len(self._clients)

    async def start(self) -> None:
        """Start the connection manager."""
        if self._running:
            return

        self._running = True
        self._broadcaster_task = asyncio.create_task(self._broadcast_loop())
        logger.info("WebSocket connection manager started")

    async def stop(self) -> None:
        """Stop the connection manager."""
        self._running = False

        if self._broadcaster_task:
            self._broadcaster_task.cancel()
            try:
                await self._broadcaster_task
            except asyncio.CancelledError:
                pass

        # Close all connections
        async with self._lock:
            for client in list(self._clients.values()):
                try:
                    await client.websocket.close()
                except Exception:
                    pass
            self._clients.clear()

        logger.info("WebSocket connection manager stopped")

    async def connect(
        self,
        websocket: WebSocket,
        client_id: str,
        subscriptions: set[str] | None = None,
    ) -> WebSocketClient | None:
        """Accept a new WebSocket connection.

        Args:
            websocket: The WebSocket connection.
            client_id: Unique client identifier.
            subscriptions: Event types to subscribe to.

        Returns:
            WebSocketClient if connected, None if rejected.
        """
        async with self._lock:
            if len(self._clients) >= self.max_connections:
                logger.warning(
                    "Connection rejected: max connections reached",
                    client_id=client_id,
                    max_connections=self.max_connections,
                )
                return None

            await websocket.accept()

            client = WebSocketClient(
                websocket=websocket,
                client_id=client_id,
                subscriptions=subscriptions or {"*"},
            )
            self._clients[client_id] = client

        logger.info(
            "WebSocket client connected",
            client_id=client_id,
            subscriptions=list(client.subscriptions),
        )

        # Send welcome message
        await self._send_to_client(
            client,
            WebSocketEvent(
                event_type="system.connected",
                data={
                    "client_id": client_id,
                    "subscriptions": list(client.subscriptions),
                    "message": "Connected to FlowLens WebSocket",
                },
            ),
        )

        return client

    async def disconnect(self, client_id: str) -> None:
        """Disconnect a client.

        Args:
            client_id: Client to disconnect.
        """
        async with self._lock:
            client = self._clients.pop(client_id, None)

        if client:
            try:
                if client.websocket.client_state == WebSocketState.CONNECTED:
                    await client.websocket.close()
            except Exception:
                pass

            logger.info("WebSocket client disconnected", client_id=client_id)

    async def subscribe(self, client_id: str, event_types: set[str]) -> bool:
        """Subscribe a client to event types.

        Args:
            client_id: Client to subscribe.
            event_types: Event types to subscribe to.

        Returns:
            True if successful.
        """
        async with self._lock:
            client = self._clients.get(client_id)
            if not client:
                return False

            client.subscriptions.update(event_types)

        logger.debug(
            "Client subscribed",
            client_id=client_id,
            event_types=list(event_types),
        )
        return True

    async def unsubscribe(self, client_id: str, event_types: set[str]) -> bool:
        """Unsubscribe a client from event types.

        Args:
            client_id: Client to unsubscribe.
            event_types: Event types to unsubscribe from.

        Returns:
            True if successful.
        """
        async with self._lock:
            client = self._clients.get(client_id)
            if not client:
                return False

            client.subscriptions -= event_types

        logger.debug(
            "Client unsubscribed",
            client_id=client_id,
            event_types=list(event_types),
        )
        return True

    async def broadcast(self, event: WebSocketEvent) -> None:
        """Queue an event for broadcast to all subscribed clients.

        Args:
            event: Event to broadcast.
        """
        await self._message_queue.put(event)

    async def broadcast_immediate(self, event: WebSocketEvent) -> int:
        """Immediately broadcast an event to all subscribed clients.

        Args:
            event: Event to broadcast.

        Returns:
            Number of clients that received the message.
        """
        sent_count = 0

        async with self._lock:
            clients = list(self._clients.values())

        for client in clients:
            if client.is_subscribed(event.event_type):
                if await self._send_to_client(client, event):
                    sent_count += 1

        return sent_count

    async def send_to_client(
        self,
        client_id: str,
        event: WebSocketEvent,
    ) -> bool:
        """Send an event to a specific client.

        Args:
            client_id: Target client.
            event: Event to send.

        Returns:
            True if sent successfully.
        """
        async with self._lock:
            client = self._clients.get(client_id)

        if not client:
            return False

        return await self._send_to_client(client, event)

    async def _send_to_client(
        self,
        client: WebSocketClient,
        event: WebSocketEvent,
    ) -> bool:
        """Send event to a client, handling errors.

        Args:
            client: Target client.
            event: Event to send.

        Returns:
            True if sent successfully.
        """
        try:
            if client.websocket.client_state != WebSocketState.CONNECTED:
                return False

            await client.websocket.send_text(event.to_json())
            return True

        except WebSocketDisconnect:
            await self.disconnect(client.client_id)
            return False

        except Exception as e:
            logger.error(
                "Failed to send WebSocket message",
                client_id=client.client_id,
                error=str(e),
            )
            await self.disconnect(client.client_id)
            return False

    async def _broadcast_loop(self) -> None:
        """Background task to process broadcast queue."""
        while self._running:
            try:
                # Wait for event with timeout
                try:
                    event = await asyncio.wait_for(
                        self._message_queue.get(),
                        timeout=1.0,
                    )
                except asyncio.TimeoutError:
                    continue

                # Broadcast to all subscribed clients
                await self.broadcast_immediate(event)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Broadcast loop error", error=str(e))

    def get_stats(self) -> dict[str, Any]:
        """Get connection manager statistics.

        Returns:
            Statistics dictionary.
        """
        subscription_counts: dict[str, int] = defaultdict(int)

        for client in self._clients.values():
            for sub in client.subscriptions:
                subscription_counts[sub] += 1

        return {
            "total_connections": len(self._clients),
            "max_connections": self.max_connections,
            "queue_size": self._message_queue.qsize(),
            "subscriptions": dict(subscription_counts),
        }


# Singleton instance
_manager: ConnectionManager | None = None


def get_connection_manager() -> ConnectionManager:
    """Get or create the singleton connection manager."""
    global _manager
    if _manager is None:
        _manager = ConnectionManager()
    return _manager


# Helper functions for common event broadcasts


async def broadcast_asset_event(
    event_type: EventType,
    asset_id: UUID,
    asset_data: dict[str, Any],
) -> None:
    """Broadcast an asset-related event.

    Args:
        event_type: Type of asset event.
        asset_id: Asset ID.
        asset_data: Asset data.
    """
    manager = get_connection_manager()
    await manager.broadcast(
        WebSocketEvent(
            event_type=event_type.value,
            data={
                "asset_id": str(asset_id),
                **asset_data,
            },
        )
    )


async def broadcast_dependency_event(
    event_type: EventType,
    dependency_id: UUID,
    dependency_data: dict[str, Any],
) -> None:
    """Broadcast a dependency-related event.

    Args:
        event_type: Type of dependency event.
        dependency_id: Dependency ID.
        dependency_data: Dependency data.
    """
    manager = get_connection_manager()
    await manager.broadcast(
        WebSocketEvent(
            event_type=event_type.value,
            data={
                "dependency_id": str(dependency_id),
                **dependency_data,
            },
        )
    )


async def broadcast_change_event(
    event_type: EventType,
    change_id: UUID,
    change_data: dict[str, Any],
) -> None:
    """Broadcast a change-related event.

    Args:
        event_type: Type of change event.
        change_id: Change event ID.
        change_data: Change data.
    """
    manager = get_connection_manager()
    await manager.broadcast(
        WebSocketEvent(
            event_type=event_type.value,
            data={
                "change_id": str(change_id),
                **change_data,
            },
        )
    )


async def broadcast_alert_event(
    event_type: EventType,
    alert_id: UUID,
    alert_data: dict[str, Any],
) -> None:
    """Broadcast an alert-related event.

    Args:
        event_type: Type of alert event.
        alert_id: Alert ID.
        alert_data: Alert data.
    """
    manager = get_connection_manager()
    await manager.broadcast(
        WebSocketEvent(
            event_type=event_type.value,
            data={
                "alert_id": str(alert_id),
                **alert_data,
            },
        )
    )


async def broadcast_topology_update() -> None:
    """Broadcast a topology update event."""
    manager = get_connection_manager()
    await manager.broadcast(
        WebSocketEvent(
            event_type=EventType.TOPOLOGY_UPDATED.value,
            data={"message": "Topology has been updated"},
        )
    )

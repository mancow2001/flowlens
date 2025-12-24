"""WebSocket API router.

Provides WebSocket endpoints for real-time updates.
"""

import uuid
from typing import Any

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from flowlens.api.websocket import get_connection_manager
from flowlens.common.logging import get_logger

logger = get_logger(__name__)
router = APIRouter(tags=["websocket"])


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    subscriptions: str = Query(default="*", description="Comma-separated event subscriptions"),
):
    """WebSocket endpoint for real-time updates.

    Connect to receive real-time updates about assets, dependencies,
    changes, and alerts.

    Subscription patterns:
    - "*" - All events
    - "asset.*" - All asset events
    - "dependency.*" - All dependency events
    - "change.*" - All change events
    - "alert.*" - All alert events
    - "system.*" - All system events
    - "asset.created" - Specific event type

    Query Parameters:
        subscriptions: Comma-separated list of event patterns to subscribe to.

    Message Protocol:
        Received messages (from server):
        ```json
        {
            "type": "event.type",
            "data": {...},
            "timestamp": "2024-01-01T00:00:00Z"
        }
        ```

        Send messages (to server):
        ```json
        {
            "action": "subscribe" | "unsubscribe" | "ping",
            "events": ["event.type1", "event.type2"]  // for subscribe/unsubscribe
        }
        ```
    """
    manager = get_connection_manager()
    client_id = str(uuid.uuid4())

    # Parse initial subscriptions
    sub_set = set(s.strip() for s in subscriptions.split(",") if s.strip())

    # Connect client
    client = await manager.connect(websocket, client_id, sub_set)
    if not client:
        await websocket.close(code=1008, reason="Max connections reached")
        return

    try:
        while True:
            # Wait for messages from client
            data = await websocket.receive_json()

            action = data.get("action")

            if action == "subscribe":
                events = set(data.get("events", []))
                await manager.subscribe(client_id, events)
                await websocket.send_json({
                    "type": "system.subscribed",
                    "data": {"events": list(events)},
                })

            elif action == "unsubscribe":
                events = set(data.get("events", []))
                await manager.unsubscribe(client_id, events)
                await websocket.send_json({
                    "type": "system.unsubscribed",
                    "data": {"events": list(events)},
                })

            elif action == "ping":
                await websocket.send_json({
                    "type": "system.pong",
                    "data": {"message": "pong"},
                })

            else:
                await websocket.send_json({
                    "type": "system.error",
                    "data": {"message": f"Unknown action: {action}"},
                })

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error("WebSocket error", client_id=client_id, error=str(e))
    finally:
        await manager.disconnect(client_id)


@router.get("/ws/stats")
async def get_websocket_stats() -> dict[str, Any]:
    """Get WebSocket connection statistics.

    Returns:
        Statistics about current WebSocket connections.
    """
    manager = get_connection_manager()
    return manager.get_stats()

/**
 * @fileoverview WebSocket hook for real-time event streaming in FlowLens.
 *
 * This module provides a React hook and Zustand store for managing WebSocket
 * connections to the FlowLens backend. It handles:
 * - Automatic connection management with protocol detection (ws/wss)
 * - Automatic reconnection with a fixed 5-second delay on disconnection
 * - Event subscription/unsubscription for selective event filtering
 * - Centralized state management via Zustand store
 *
 * ## Architecture
 *
 * The module separates concerns into two parts:
 * 1. **useWebSocketStore** - Zustand store for shared state (connection status, events)
 * 2. **useWebSocket** - React hook for WebSocket operations (connect, disconnect, send)
 *
 * This separation allows components to:
 * - Access connection state without managing the socket (via useWebSocketStore)
 * - Control the socket lifecycle when needed (via useWebSocket)
 *
 * ## Event Buffer
 *
 * The store maintains a rolling buffer of the last 100 events. Older events are
 * automatically evicted when new events arrive. This prevents memory issues
 * during long-running sessions while preserving recent event history.
 *
 * ## Usage Example
 *
 * ```tsx
 * import { useWebSocket, useWebSocketStore } from '../hooks/useWebSocket';
 *
 * function MyComponent() {
 *   const { connect, disconnect, subscribe } = useWebSocket();
 *   const { isConnected, lastEvent, events } = useWebSocketStore();
 *
 *   useEffect(() => {
 *     connect();
 *     return () => disconnect();
 *   }, [connect, disconnect]);
 *
 *   // Subscribe to specific event types
 *   useEffect(() => {
 *     if (isConnected) {
 *       subscribe(['flow.new', 'asset.updated']);
 *     }
 *   }, [isConnected, subscribe]);
 *
 *   return <div>Connected: {isConnected ? 'Yes' : 'No'}</div>;
 * }
 * ```
 *
 * @module useWebSocket
 */

import { useCallback, useRef } from 'react';
import { create } from 'zustand';
import type { WebSocketEvent } from '../types';

/**
 * Delay in milliseconds before attempting to reconnect after disconnection.
 * Using a fixed delay rather than exponential backoff for simplicity.
 * The server is expected to be available, so a simple retry is sufficient.
 */
const RECONNECT_DELAY_MS = 5000;

/**
 * Maximum number of events to retain in the event buffer.
 * Events beyond this limit are evicted (oldest first) to prevent memory issues.
 */
const MAX_EVENT_BUFFER_SIZE = 100;

/**
 * Shape of the WebSocket state managed by Zustand.
 *
 * This state is shared across all components that use useWebSocketStore,
 * ensuring consistent connection status and event data throughout the app.
 *
 * @interface WebSocketState
 */
interface WebSocketState {
  /**
   * Whether the WebSocket is currently connected.
   * Updated automatically on open/close events.
   */
  isConnected: boolean;

  /**
   * The most recently received WebSocket event, or null if none received.
   * Useful for components that only care about the latest event.
   */
  lastEvent: WebSocketEvent | null;

  /**
   * Rolling buffer of recent events (max 100).
   * New events are appended; oldest events are evicted when buffer is full.
   */
  events: WebSocketEvent[];

  /**
   * Updates the connection status.
   * @param connected - New connection state
   */
  setConnected: (connected: boolean) => void;

  /**
   * Adds a new event to the buffer and updates lastEvent.
   * Automatically maintains buffer size limit.
   * @param event - The WebSocket event to add
   */
  addEvent: (event: WebSocketEvent) => void;

  /**
   * Clears all events from the buffer and resets lastEvent to null.
   * Useful when switching contexts or cleaning up.
   */
  clearEvents: () => void;
}

/**
 * Zustand store for WebSocket state management.
 *
 * This store provides reactive access to WebSocket connection status and events.
 * Components can subscribe to state changes and will re-render when the
 * connection status or events change.
 *
 * @example
 * ```tsx
 * // In a React component
 * const { isConnected, lastEvent, events, clearEvents } = useWebSocketStore();
 *
 * // Access specific state with selector for optimized re-renders
 * const isConnected = useWebSocketStore((state) => state.isConnected);
 * ```
 */
export const useWebSocketStore = create<WebSocketState>((set) => ({
  isConnected: false,
  lastEvent: null,
  events: [],
  setConnected: (connected) => set({ isConnected: connected }),
  addEvent: (event) =>
    set((state) => ({
      lastEvent: event,
      // Keep only the last (MAX_EVENT_BUFFER_SIZE - 1) events plus the new one
      events: [...state.events.slice(-(MAX_EVENT_BUFFER_SIZE - 1)), event],
    })),
  clearEvents: () => set({ events: [], lastEvent: null }),
}));

/**
 * React hook for managing WebSocket connections to the FlowLens backend.
 *
 * This hook provides methods to control the WebSocket lifecycle and send messages.
 * Connection state is managed separately in useWebSocketStore, allowing multiple
 * components to access state without each managing their own connection.
 *
 * ## Connection Behavior
 *
 * - **Protocol Detection**: Automatically uses `wss:` for HTTPS pages, `ws:` for HTTP
 * - **Initial Subscription**: Connects with `subscriptions=*` to receive all events
 * - **Auto-Reconnect**: Automatically attempts reconnection after disconnection
 * - **Reconnect Delay**: Fixed 5-second delay between reconnection attempts
 *
 * ## Error Handling
 *
 * - Connection errors are logged to console but do not throw
 * - Malformed messages (non-JSON) are logged and silently dropped
 * - The hook continues to function and will reconnect on connection loss
 *
 * ## Cleanup
 *
 * Always call `disconnect()` when unmounting to prevent:
 * - Memory leaks from orphaned WebSocket connections
 * - Infinite reconnection loops after component unmount
 *
 * @returns Object containing WebSocket control methods
 *
 * @example
 * ```tsx
 * function App() {
 *   const { connect, disconnect, send, subscribe, unsubscribe } = useWebSocket();
 *
 *   useEffect(() => {
 *     connect();
 *     return () => disconnect();
 *   }, [connect, disconnect]);
 *
 *   const handleAction = () => {
 *     send('custom_action', { data: 'value' });
 *   };
 *
 *   return <button onClick={handleAction}>Send</button>;
 * }
 * ```
 */
export function useWebSocket() {
  /** Reference to the active WebSocket instance */
  const wsRef = useRef<WebSocket | null>(null);

  /** Reference to the pending reconnection timeout (for cleanup) */
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  const { setConnected, addEvent } = useWebSocketStore();

  /**
   * Establishes a WebSocket connection to the backend.
   *
   * The connection URL is derived from the current page location:
   * - Protocol: `wss:` for HTTPS, `ws:` for HTTP
   * - Host: Same as the page host
   * - Path: `/api/v1/ws`
   * - Query: `subscriptions=*` (subscribe to all events initially)
   *
   * If a connection is already open, this method is a no-op.
   *
   * ## Lifecycle Events
   *
   * - **onopen**: Updates store to connected, clears pending reconnect timer
   * - **onclose**: Updates store to disconnected, schedules reconnection
   * - **onerror**: Logs error to console (connection will close and trigger onclose)
   * - **onmessage**: Parses JSON and adds to event store
   *
   * @example
   * ```tsx
   * const { connect } = useWebSocket();
   *
   * useEffect(() => {
   *   connect();
   * }, [connect]);
   * ```
   */
  const connect = useCallback(() => {
    // Prevent duplicate connections
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      return;
    }

    // Derive WebSocket URL from current page location
    // This ensures the connection works in both development and production
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/api/v1/ws?subscriptions=*`;

    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      setConnected(true);

      // Clear any pending reconnection attempt since we're now connected
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
        reconnectTimeoutRef.current = null;
      }
    };

    ws.onclose = () => {
      setConnected(false);

      // Schedule automatic reconnection attempt
      // Uses a fixed delay rather than exponential backoff for simplicity
      reconnectTimeoutRef.current = setTimeout(() => {
        connect();
      }, RECONNECT_DELAY_MS);
    };

    ws.onerror = (error) => {
      // Log the error; the subsequent onclose event will trigger reconnection
      console.error('WebSocket error:', error);
    };

    ws.onmessage = (event) => {
      try {
        // Parse the JSON message and add to the event store
        // Type assertion assumes the server sends valid WebSocketEvent format
        const data = JSON.parse(event.data) as WebSocketEvent;
        addEvent(data);
      } catch (error) {
        // Malformed messages are logged but not fatal
        // The connection remains open for subsequent messages
        console.error('Failed to parse WebSocket message:', error);
      }
    };
  }, [setConnected, addEvent]);

  /**
   * Closes the WebSocket connection and cancels any pending reconnection.
   *
   * This method should be called when:
   * - The component using the WebSocket unmounts
   * - The user logs out
   * - The connection is no longer needed
   *
   * Calling disconnect() prevents the automatic reconnection behavior,
   * ensuring clean shutdown without orphaned connections.
   *
   * @example
   * ```tsx
   * const { connect, disconnect } = useWebSocket();
   *
   * useEffect(() => {
   *   connect();
   *   return () => disconnect(); // Clean up on unmount
   * }, [connect, disconnect]);
   * ```
   */
  const disconnect = useCallback(() => {
    // Cancel any scheduled reconnection to prevent reconnecting after disconnect
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }

    // Close the WebSocket connection if open
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
  }, []);

  /**
   * Sends a message to the WebSocket server.
   *
   * Messages are sent as JSON with the format: `{ action: string, ...data }`.
   * If the WebSocket is not connected, the message is silently dropped.
   *
   * ## Message Format
   *
   * The server expects messages in this format:
   * ```json
   * {
   *   "action": "action_name",
   *   "key1": "value1",
   *   "key2": "value2"
   * }
   * ```
   *
   * @param action - The action type/name for the message
   * @param data - Optional additional data to include in the message
   *
   * @example
   * ```tsx
   * const { send } = useWebSocket();
   *
   * // Simple action
   * send('ping');
   *
   * // Action with data
   * send('filter', { assetId: '123', eventType: 'flow.new' });
   * ```
   */
  const send = useCallback((action: string, data?: Record<string, unknown>) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ action, ...data }));
    }
  }, []);

  /**
   * Subscribes to specific event types from the server.
   *
   * By default, the connection subscribes to all events (`subscriptions=*`).
   * Use this method to change the subscription to specific event types.
   *
   * ## Available Event Types
   *
   * Common event types include:
   * - `flow.new` - New flow detected
   * - `flow.updated` - Flow statistics updated
   * - `asset.created` - New asset discovered
   * - `asset.updated` - Asset metadata changed
   * - `dependency.new` - New dependency detected
   * - `alert.triggered` - Alert condition met
   *
   * @param events - Array of event type strings to subscribe to
   *
   * @example
   * ```tsx
   * const { subscribe } = useWebSocket();
   * const { isConnected } = useWebSocketStore();
   *
   * useEffect(() => {
   *   if (isConnected) {
   *     subscribe(['flow.new', 'asset.updated']);
   *   }
   * }, [isConnected, subscribe]);
   * ```
   */
  const subscribe = useCallback(
    (events: string[]) => {
      send('subscribe', { events });
    },
    [send]
  );

  /**
   * Unsubscribes from specific event types.
   *
   * Use this to stop receiving events you no longer need,
   * reducing unnecessary network traffic and processing.
   *
   * @param events - Array of event type strings to unsubscribe from
   *
   * @example
   * ```tsx
   * const { unsubscribe } = useWebSocket();
   *
   * // Stop receiving flow events
   * unsubscribe(['flow.new', 'flow.updated']);
   * ```
   */
  const unsubscribe = useCallback(
    (events: string[]) => {
      send('unsubscribe', { events });
    },
    [send]
  );

  return {
    /**
     * Establishes WebSocket connection to backend.
     * Safe to call multiple times (no-op if already connected).
     */
    connect,
    /**
     * Closes connection and cancels pending reconnection.
     * Call this on component unmount.
     */
    disconnect,
    /**
     * Sends a message to the server.
     * Silently drops if not connected.
     */
    send,
    /**
     * Subscribes to specific event types.
     * Replaces default "all events" subscription.
     */
    subscribe,
    /**
     * Unsubscribes from specific event types.
     */
    unsubscribe,
  };
}

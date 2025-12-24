import { useCallback, useRef } from 'react';
import { create } from 'zustand';
import type { WebSocketEvent } from '../types';

interface WebSocketState {
  isConnected: boolean;
  lastEvent: WebSocketEvent | null;
  events: WebSocketEvent[];
  setConnected: (connected: boolean) => void;
  addEvent: (event: WebSocketEvent) => void;
  clearEvents: () => void;
}

export const useWebSocketStore = create<WebSocketState>((set) => ({
  isConnected: false,
  lastEvent: null,
  events: [],
  setConnected: (connected) => set({ isConnected: connected }),
  addEvent: (event) =>
    set((state) => ({
      lastEvent: event,
      events: [...state.events.slice(-99), event],
    })),
  clearEvents: () => set({ events: [], lastEvent: null }),
}));

export function useWebSocket() {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const { setConnected, addEvent } = useWebSocketStore();

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      return;
    }

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/api/v1/ws?subscriptions=*`;

    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      console.log('WebSocket connected');
      setConnected(true);

      // Clear any pending reconnection
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
        reconnectTimeoutRef.current = null;
      }
    };

    ws.onclose = () => {
      console.log('WebSocket disconnected');
      setConnected(false);

      // Attempt to reconnect after 5 seconds
      reconnectTimeoutRef.current = setTimeout(() => {
        console.log('Attempting to reconnect...');
        connect();
      }, 5000);
    };

    ws.onerror = (error) => {
      console.error('WebSocket error:', error);
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data) as WebSocketEvent;
        addEvent(data);
      } catch (error) {
        console.error('Failed to parse WebSocket message:', error);
      }
    };
  }, [setConnected, addEvent]);

  const disconnect = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }

    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
  }, []);

  const send = useCallback((action: string, data?: Record<string, unknown>) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ action, ...data }));
    }
  }, []);

  const subscribe = useCallback(
    (events: string[]) => {
      send('subscribe', { events });
    },
    [send]
  );

  const unsubscribe = useCallback(
    (events: string[]) => {
      send('unsubscribe', { events });
    },
    [send]
  );

  return {
    connect,
    disconnect,
    send,
    subscribe,
    unsubscribe,
  };
}

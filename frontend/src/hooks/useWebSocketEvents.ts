import { useEffect, useCallback } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useWebSocketStore } from './useWebSocket';
import type { WebSocketEvent } from '../types';

interface EventHandlers {
  onAlertCreated?: (data: Record<string, unknown>) => void;
  onAlertAcknowledged?: (data: Record<string, unknown>) => void;
  onAlertResolved?: (data: Record<string, unknown>) => void;
  onChangeDetected?: (data: Record<string, unknown>) => void;
  onTopologyUpdated?: (data: Record<string, unknown>) => void;
}

/**
 * Hook that listens to WebSocket events and invalidates React Query caches.
 * Also provides callbacks for UI notifications.
 */
export function useWebSocketEvents(handlers?: EventHandlers) {
  const queryClient = useQueryClient();
  const lastEvent = useWebSocketStore((state) => state.lastEvent);

  const handleEvent = useCallback(
    (event: WebSocketEvent) => {
      const { type, data } = event;

      // Invalidate React Query caches based on event type
      switch (type) {
        // Alert events
        case 'alert.created':
          queryClient.invalidateQueries({ queryKey: ['alerts'] });
          queryClient.invalidateQueries({ queryKey: ['alert-summary'] });
          handlers?.onAlertCreated?.(data);
          break;

        case 'alert.acknowledged':
          queryClient.invalidateQueries({ queryKey: ['alerts'] });
          queryClient.invalidateQueries({ queryKey: ['alert-summary'] });
          handlers?.onAlertAcknowledged?.(data);
          break;

        case 'alert.resolved':
          queryClient.invalidateQueries({ queryKey: ['alerts'] });
          queryClient.invalidateQueries({ queryKey: ['alert-summary'] });
          handlers?.onAlertResolved?.(data);
          break;

        // Change events
        case 'change.detected':
        case 'change.processed':
          queryClient.invalidateQueries({ queryKey: ['changes'] });
          queryClient.invalidateQueries({ queryKey: ['change-summary'] });
          handlers?.onChangeDetected?.(data);
          break;

        // Asset events
        case 'asset.created':
        case 'asset.updated':
        case 'asset.deleted':
          queryClient.invalidateQueries({ queryKey: ['assets'] });
          queryClient.invalidateQueries({ queryKey: ['asset'] });
          queryClient.invalidateQueries({ queryKey: ['dashboard-stats'] });
          // Asset changes affect topology
          queryClient.invalidateQueries({ queryKey: ['topology'] });
          break;

        // Dependency events
        case 'dependency.created':
        case 'dependency.updated':
        case 'dependency.deleted':
          queryClient.invalidateQueries({ queryKey: ['dependencies'] });
          queryClient.invalidateQueries({ queryKey: ['dependency'] });
          queryClient.invalidateQueries({ queryKey: ['dashboard-stats'] });
          // Dependency changes affect topology
          queryClient.invalidateQueries({ queryKey: ['topology'] });
          break;

        // Topology events
        case 'topology.updated':
          queryClient.invalidateQueries({ queryKey: ['topology'] });
          handlers?.onTopologyUpdated?.(data);
          break;

        // System events
        case 'system.connected':
        case 'system.status':
        case 'ingestion.stats':
          // These are informational, no cache invalidation needed
          break;

        default:
          console.log('Unhandled WebSocket event type:', type);
      }
    },
    [queryClient, handlers]
  );

  useEffect(() => {
    if (lastEvent) {
      handleEvent(lastEvent);
    }
  }, [lastEvent, handleEvent]);

  return {
    lastEvent,
  };
}

/**
 * Hook for managing the force simulation Web Worker
 * Offloads force calculations to a separate thread for better performance
 */

import { useEffect, useRef, useCallback, useState } from 'react';

export interface SimulationNode {
  id: string;
  x: number;
  y: number;
  vx?: number;
  vy?: number;
  fx?: number | null;
  fy?: number | null;
  groupKey?: string;
}

export interface SimulationLink {
  source: string;
  target: string;
  id: string;
}

export interface SimulationConfig {
  linkDistance?: number;
  chargeStrength?: number;
  collisionRadius?: number;
  alphaDecay?: number;
  velocityDecay?: number;
  groupForceStrength?: number;
  groupCenters?: Record<string, { x: number; y: number }>;
  useBarnesHut?: boolean;
  theta?: number;
}

export interface NodePosition {
  id: string;
  x: number;
  y: number;
}

interface WorkerMessage {
  type: 'ready' | 'tick' | 'end';
  positions?: NodePosition[];
  alpha?: number;
}

interface UseForceSimulationWorkerOptions {
  nodes: SimulationNode[];
  links: SimulationLink[];
  width: number;
  height: number;
  config?: SimulationConfig;
  onTick?: (positions: NodePosition[], alpha: number) => void;
  onEnd?: (positions: NodePosition[]) => void;
  enabled?: boolean;
}

export function useForceSimulationWorker({
  nodes,
  links,
  width,
  height,
  config,
  onTick,
  onEnd,
  enabled = true,
}: UseForceSimulationWorkerOptions) {
  const workerRef = useRef<Worker | null>(null);
  const [isReady, setIsReady] = useState(false);
  const [isRunning, setIsRunning] = useState(false);
  const [positions, setPositions] = useState<Map<string, { x: number; y: number }>>(new Map());

  // Store callbacks in refs to avoid re-initializing
  const onTickRef = useRef(onTick);
  const onEndRef = useRef(onEnd);
  onTickRef.current = onTick;
  onEndRef.current = onEnd;

  // Initialize worker
  useEffect(() => {
    if (!enabled) return;

    // Create worker using Vite's worker import syntax
    const worker = new Worker(
      new URL('../workers/forceSimulation.worker.ts', import.meta.url),
      { type: 'module' }
    );

    worker.onmessage = (event: MessageEvent<WorkerMessage>) => {
      const { type, positions: newPositions, alpha } = event.data;

      switch (type) {
        case 'ready':
          setIsReady(true);
          break;

        case 'tick':
          if (newPositions) {
            // Update positions map
            const posMap = new Map<string, { x: number; y: number }>();
            newPositions.forEach(p => posMap.set(p.id, { x: p.x, y: p.y }));
            setPositions(posMap);

            // Call tick callback
            if (onTickRef.current) {
              onTickRef.current(newPositions, alpha ?? 0);
            }
          }
          break;

        case 'end':
          setIsRunning(false);
          if (newPositions && onEndRef.current) {
            onEndRef.current(newPositions);
          }
          break;
      }
    };

    worker.onerror = (error) => {
      console.error('Force simulation worker error:', error);
    };

    workerRef.current = worker;

    return () => {
      worker.terminate();
      workerRef.current = null;
      setIsReady(false);
    };
  }, [enabled]);

  // Initialize simulation when ready and data changes
  useEffect(() => {
    if (!isReady || !workerRef.current || nodes.length === 0) return;

    const workerNodes = nodes.map(n => ({
      id: n.id,
      x: n.x ?? width / 2 + (Math.random() - 0.5) * 100,
      y: n.y ?? height / 2 + (Math.random() - 0.5) * 100,
      vx: n.vx ?? 0,
      vy: n.vy ?? 0,
      fx: n.fx ?? null,
      fy: n.fy ?? null,
      groupKey: n.groupKey,
    }));

    const workerLinks = links.map(l => ({
      source: l.source,
      target: l.target,
      id: l.id,
    }));

    workerRef.current.postMessage({
      type: 'init',
      nodes: workerNodes,
      links: workerLinks,
      width,
      height,
      config: config ?? {},
    });

    setIsRunning(true);
  }, [isReady, nodes, links, width, height, config]);

  // Drag handlers
  const startDrag = useCallback((nodeId: string, x: number, y: number) => {
    if (!workerRef.current) return;
    workerRef.current.postMessage({
      type: 'drag',
      nodeId,
      x,
      y,
      phase: 'start',
    });
  }, []);

  const drag = useCallback((nodeId: string, x: number, y: number) => {
    if (!workerRef.current) return;
    workerRef.current.postMessage({
      type: 'drag',
      nodeId,
      x,
      y,
      phase: 'drag',
    });
  }, []);

  const endDrag = useCallback((nodeId: string, x: number, y: number) => {
    if (!workerRef.current) return;
    workerRef.current.postMessage({
      type: 'drag',
      nodeId,
      x,
      y,
      phase: 'end',
    });
  }, []);

  // Control methods
  const stop = useCallback(() => {
    if (!workerRef.current) return;
    workerRef.current.postMessage({ type: 'stop' });
    setIsRunning(false);
  }, []);

  const restart = useCallback((alpha = 1) => {
    if (!workerRef.current) return;
    workerRef.current.postMessage({ type: 'restart', alpha });
    setIsRunning(true);
  }, []);

  const tick = useCallback(() => {
    if (!workerRef.current) return;
    workerRef.current.postMessage({ type: 'tick' });
  }, []);

  return {
    isReady,
    isRunning,
    positions,
    startDrag,
    drag,
    endDrag,
    stop,
    restart,
    tick,
  };
}

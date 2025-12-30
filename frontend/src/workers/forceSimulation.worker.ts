/**
 * Web Worker for D3 Force Simulation
 * Offloads expensive force calculations from the main thread
 */

import * as d3 from 'd3';

interface WorkerNode {
  id: string;
  x: number;
  y: number;
  vx: number;
  vy: number;
  fx: number | null;
  fy: number | null;
  groupKey?: string;
}

interface WorkerLink {
  source: string;
  target: string;
  id: string;
}

interface InitMessage {
  type: 'init';
  nodes: WorkerNode[];
  links: WorkerLink[];
  width: number;
  height: number;
  config: SimulationConfig;
}

interface UpdateMessage {
  type: 'update';
  nodes?: Partial<WorkerNode>[];
  config?: Partial<SimulationConfig>;
}

interface DragMessage {
  type: 'drag';
  nodeId: string;
  x: number;
  y: number;
  phase: 'start' | 'drag' | 'end';
}

interface ControlMessage {
  type: 'stop' | 'restart' | 'tick';
  alpha?: number;
}

type IncomingMessage = InitMessage | UpdateMessage | DragMessage | ControlMessage;

interface SimulationConfig {
  linkDistance: number;
  chargeStrength: number;
  collisionRadius: number;
  alphaDecay: number;
  velocityDecay: number;
  groupForceStrength: number;
  groupCenters?: Map<string, { x: number; y: number }>;
  useBarnesHut: boolean;
  theta: number; // Barnes-Hut approximation parameter (0.9 = fast, 0.5 = accurate)
}

let simulation: d3.Simulation<WorkerNode, WorkerLink> | null = null;
let nodes: WorkerNode[] = [];
let links: WorkerLink[] = [];
let width = 800;
let height = 600;
let config: SimulationConfig = {
  linkDistance: 150,
  chargeStrength: -400,
  collisionRadius: 40,
  alphaDecay: 0.0228, // Default D3 value
  velocityDecay: 0.4,
  groupForceStrength: 0.1,
  useBarnesHut: true,
  theta: 0.9,
};

// Track if we need to send updates
let tickCount = 0;
const TICK_THROTTLE = 2; // Send every N ticks for performance

function createSimulation() {
  if (simulation) {
    simulation.stop();
  }

  simulation = d3.forceSimulation<WorkerNode>(nodes)
    .alphaDecay(config.alphaDecay)
    .velocityDecay(config.velocityDecay);

  // Link force
  const linkForce = d3.forceLink<WorkerNode, WorkerLink>(links)
    .id(d => d.id)
    .distance(config.linkDistance);
  simulation.force('link', linkForce);

  // Charge force with Barnes-Hut approximation
  const chargeForce = d3.forceManyBody<WorkerNode>()
    .strength(config.chargeStrength);

  if (config.useBarnesHut) {
    chargeForce.theta(config.theta);
  }
  simulation.force('charge', chargeForce);

  // Center force
  simulation.force('center', d3.forceCenter(width / 2, height / 2));

  // Collision force
  simulation.force('collision', d3.forceCollide<WorkerNode>().radius(config.collisionRadius));

  // Group forces (if group centers are provided)
  if (config.groupCenters && config.groupCenters.size > 0) {
    const groupCentersMap = config.groupCenters;
    simulation.force('groupX', d3.forceX<WorkerNode>(d => {
      if (d.groupKey && groupCentersMap.has(d.groupKey)) {
        return groupCentersMap.get(d.groupKey)!.x;
      }
      return width / 2;
    }).strength(config.groupForceStrength));

    simulation.force('groupY', d3.forceY<WorkerNode>(d => {
      if (d.groupKey && groupCentersMap.has(d.groupKey)) {
        return groupCentersMap.get(d.groupKey)!.y;
      }
      return height / 2;
    }).strength(config.groupForceStrength));
  }

  // On tick, send positions back to main thread
  simulation.on('tick', () => {
    tickCount++;

    // Throttle updates to reduce message passing overhead
    if (tickCount % TICK_THROTTLE !== 0) return;

    const positions = nodes.map(n => ({
      id: n.id,
      x: n.x,
      y: n.y,
    }));

    self.postMessage({
      type: 'tick',
      positions,
      alpha: simulation!.alpha(),
    });
  });

  // When simulation ends
  simulation.on('end', () => {
    const positions = nodes.map(n => ({
      id: n.id,
      x: n.x,
      y: n.y,
    }));

    self.postMessage({
      type: 'end',
      positions,
    });
  });
}

function handleMessage(event: MessageEvent<IncomingMessage>) {
  const message = event.data;

  switch (message.type) {
    case 'init': {
      nodes = message.nodes.map(n => ({ ...n }));
      links = message.links.map(l => ({ ...l }));
      width = message.width;
      height = message.height;

      if (message.config) {
        config = { ...config, ...message.config };
        // Convert groupCenters array to Map if needed
        if (message.config.groupCenters) {
          config.groupCenters = new Map(
            Object.entries(message.config.groupCenters as unknown as Record<string, { x: number; y: number }>)
          );
        }
      }

      createSimulation();
      break;
    }

    case 'update': {
      if (message.nodes) {
        // Update specific node properties
        message.nodes.forEach(update => {
          const node = nodes.find(n => n.id === update.id);
          if (node) {
            Object.assign(node, update);
          }
        });
      }

      if (message.config) {
        config = { ...config, ...message.config };
        if (message.config.groupCenters) {
          config.groupCenters = new Map(
            Object.entries(message.config.groupCenters as unknown as Record<string, { x: number; y: number }>)
          );
        }
        // Recreate simulation with new config
        createSimulation();
      }
      break;
    }

    case 'drag': {
      const node = nodes.find(n => n.id === message.nodeId);
      if (!node || !simulation) break;

      switch (message.phase) {
        case 'start':
          simulation.alphaTarget(0.3).restart();
          node.fx = message.x;
          node.fy = message.y;
          break;
        case 'drag':
          node.fx = message.x;
          node.fy = message.y;
          break;
        case 'end':
          simulation.alphaTarget(0);
          node.fx = null;
          node.fy = null;
          break;
      }
      break;
    }

    case 'stop': {
      if (simulation) {
        simulation.stop();
      }
      break;
    }

    case 'restart': {
      if (simulation) {
        simulation.alpha(message.alpha ?? 1).restart();
      }
      break;
    }

    case 'tick': {
      // Manual tick for static layout
      if (simulation) {
        simulation.tick();
        const positions = nodes.map(n => ({
          id: n.id,
          x: n.x,
          y: n.y,
        }));
        self.postMessage({
          type: 'tick',
          positions,
          alpha: simulation.alpha(),
        });
      }
      break;
    }
  }
}

self.onmessage = handleMessage;

// Signal that worker is ready
self.postMessage({ type: 'ready' });

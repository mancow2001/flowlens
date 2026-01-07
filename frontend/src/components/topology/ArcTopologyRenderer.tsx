/**
 * Arc Topology Renderer
 * Canvas-based renderer for arc/sunburst visualization of folder hierarchy.
 */

import { useRef, useEffect, useCallback, useState, useMemo } from 'react';
import * as d3 from 'd3';
import type { ArcTopologyData, FolderTreeNode } from '../../types';
import {
  buildFolderOnlyHierarchy,
  buildExpandableHierarchy,
  applyPartitionLayout,
  createArcGenerator,
  findNodeAtPoint,
  findConnectionAtPoint,
  mapDependenciesToConnections,
  mapFolderDependenciesToConnections,
  getAncestors,
  getRelatedNodeIds,
  getRelatedConnections,
  computeNodeOpacity,
  computeConnectionOpacity,
  formatBytes,
  type ArcNode,
  type ArcLayoutConfig,
  type VisualConnection,
} from '../../utils/arcLayout';

interface ArcTopologyRendererProps {
  data: ArcTopologyData;
  width: number;
  height: number;
  onFolderClick?: (folderId: string) => void;
  onApplicationClick?: (appId: string) => void;
  onApplicationSelect?: (appId: string | null) => void;
  onFolderDoubleClick?: (folderId: string) => void;
  focusedFolderId?: string | null;
  expandedFolderIds?: Set<string>;
  selectedAppId?: string | null;
}

interface TooltipState {
  visible: boolean;
  x: number;
  y: number;
  content: {
    title: string;
    type: 'folder' | 'application' | 'connection';
    details: { label: string; value: string }[];
  } | null;
}

export function ArcTopologyRenderer({
  data,
  width,
  height,
  onFolderClick,
  onApplicationClick,
  onApplicationSelect,
  onFolderDoubleClick,
  focusedFolderId,
  expandedFolderIds = new Set(),
  selectedAppId = null,
}: ArcTopologyRendererProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [hoveredNode, setHoveredNode] = useState<d3.HierarchyRectangularNode<ArcNode> | null>(null);
  const [hoveredConnection, setHoveredConnection] = useState<VisualConnection | null>(null);
  const [tooltip, setTooltip] = useState<TooltipState>({ visible: false, x: 0, y: 0, content: null });
  const [transform, setTransform] = useState<d3.ZoomTransform>(d3.zoomIdentity);

  // Layout configuration
  const config: ArcLayoutConfig = useMemo(() => {
    const minDim = Math.min(width, height);
    return {
      innerRadius: minDim * 0.1,
      outerRadius: minDim * 0.45,
      padAngle: 0.01,
      cornerRadius: 3,
    };
  }, [width, height]);

  // Build hierarchy and layout
  // By default, show only folders. When a folder is expanded, show its applications.
  const { nodes, connections, arcGenerator, folderConnections } = useMemo(() => {
    const hasExpandedFolders = expandedFolderIds.size > 0;

    let hierarchy;
    if (hasExpandedFolders) {
      // Build hierarchy with expanded folders replaced by their applications
      hierarchy = buildExpandableHierarchy(data, expandedFolderIds);
    } else {
      // Default: folder-only view
      hierarchy = buildFolderOnlyHierarchy(data);
    }

    const root = applyPartitionLayout(hierarchy, config);
    const allNodes = root.descendants();
    const arcGen = createArcGenerator(config);

    // Map connections based on what's visible
    // For expanded folders, show app-level dependencies for those apps
    // Always show folder-level dependencies between collapsed folders
    const appConns = hasExpandedFolders
      ? mapDependenciesToConnections(data.dependencies, allNodes, config)
      : [];
    const folderConns = mapFolderDependenciesToConnections(
      data.folder_dependencies || [],
      allNodes,
      config
    );

    return {
      nodes: allNodes,
      connections: appConns,
      folderConnections: folderConns,
      arcGenerator: arcGen,
    };
  }, [data, config, expandedFolderIds]);

  // Get focused node and related nodes
  const focusedData = useMemo(() => {
    // Merge app-level and folder-level connections based on view mode
    const hasExpandedFolders = expandedFolderIds.size > 0;
    const activeConnections = hasExpandedFolders
      ? [...folderConnections, ...connections]
      : folderConnections;

    if (!focusedFolderId) {
      return {
        visibleNodes: nodes,
        visibleConnections: activeConnections,
        relevantIds: undefined,
      };
    }

    const focusNode = nodes.find(n => n.data.id === focusedFolderId);
    if (!focusNode) {
      return {
        visibleNodes: nodes,
        visibleConnections: activeConnections,
        relevantIds: undefined,
      };
    }

    const descendants = new Set(focusNode.descendants().map(n => n.data.id));
    const ancestors = new Set(getAncestors(focusNode).map(n => n.data.id));
    const relevantIds = new Set([...descendants, ...ancestors]);

    const visibleNodes = nodes;
    const visibleConnections = activeConnections.filter(
      c => descendants.has(c.sourceId) || descendants.has(c.targetId)
    );

    return { visibleNodes, visibleConnections, relevantIds };
  }, [focusedFolderId, nodes, connections, folderConnections, expandedFolderIds]);

  // Compute selection-related data for filtering/dimming
  const selectionData = useMemo(() => {
    if (!selectedAppId) {
      return { relatedNodeIds: null, relatedConnectionIds: null };
    }

    const relatedNodeIds = getRelatedNodeIds(
      selectedAppId,
      data.dependencies,
      data.folder_dependencies || [],
      nodes
    );

    const relatedConnectionIds = getRelatedConnections(
      selectedAppId,
      focusedData.visibleConnections
    );

    return { relatedNodeIds, relatedConnectionIds };
  }, [selectedAppId, data.dependencies, data.folder_dependencies, nodes, focusedData.visibleConnections]);

  // Render function
  const render = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const dpr = window.devicePixelRatio || 1;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, width, height);

    // Apply transform
    const centerX = width / 2;
    const centerY = height / 2;
    ctx.save();
    ctx.translate(centerX + transform.x, centerY + transform.y);
    ctx.scale(transform.k, transform.k);

    // Draw connections (folder-level always visible, app-level when expanded)
    const { visibleConnections, relevantIds } = focusedData;

    // Helper function to draw arrow head at a point along the bezier curve
    const drawArrowHead = (
      ctx: CanvasRenderingContext2D,
      pathStr: string,
      t: number, // position along curve (0-1)
      size: number,
      color: string
    ) => {
      // Parse bezier path: M x1,y1 Q cx,cy x2,y2
      const pathMatch = pathStr.match(/M\s*([-\d.e+]+)[,\s]+([-\d.e+]+)\s*Q\s*([-\d.e+]+)[,\s]+([-\d.e+]+)\s*([-\d.e+]+)[,\s]+([-\d.e+]+)/i);
      if (!pathMatch) return;

      const x1 = parseFloat(pathMatch[1]);
      const y1 = parseFloat(pathMatch[2]);
      const cx = parseFloat(pathMatch[3]);
      const cy = parseFloat(pathMatch[4]);
      const x2 = parseFloat(pathMatch[5]);
      const y2 = parseFloat(pathMatch[6]);

      // Calculate point at t on quadratic bezier
      const px = (1 - t) * (1 - t) * x1 + 2 * (1 - t) * t * cx + t * t * x2;
      const py = (1 - t) * (1 - t) * y1 + 2 * (1 - t) * t * cy + t * t * y2;

      // Calculate tangent direction at t
      const dx = 2 * (1 - t) * (cx - x1) + 2 * t * (x2 - cx);
      const dy = 2 * (1 - t) * (cy - y1) + 2 * t * (y2 - cy);
      const angle = Math.atan2(dy, dx);

      // Draw arrow head
      ctx.save();
      ctx.translate(px, py);
      ctx.rotate(angle);
      ctx.beginPath();
      ctx.moveTo(size, 0);
      ctx.lineTo(-size * 0.6, -size * 0.5);
      ctx.lineTo(-size * 0.6, size * 0.5);
      ctx.closePath();
      ctx.fillStyle = color;
      ctx.fill();
      ctx.restore();
    };

    // Always show connections (folder-level by default, app-level when folders expanded)
    // Get selection-related IDs for connection filtering
    const { relatedConnectionIds: selRelatedConns } = selectionData;

    if (visibleConnections.length > 0) {
      ctx.lineCap = 'round';
      for (const conn of visibleConnections) {
        const isHighlighted =
          hoveredConnection?.id === conn.id ||
          hoveredNode?.data.id === conn.sourceId ||
          hoveredNode?.data.id === conn.targetId;

        // Compute selection-based opacity for connections
        const connOpacity = computeConnectionOpacity(conn, selectedAppId, selRelatedConns);
        const isRelatedToSelection = !selectedAppId || (selRelatedConns && selRelatedConns.has(conn.id));

        ctx.beginPath();
        const path2D = new Path2D(conn.path);

        let strokeColor: string;
        if (isHighlighted) {
          // Draw a glow effect for highlighted connections
          ctx.strokeStyle = 'rgba(59, 130, 246, 0.3)';
          ctx.lineWidth = conn.strokeWidth * 3;
          ctx.stroke(path2D);
          // Draw the main highlighted line
          ctx.strokeStyle = 'rgba(59, 130, 246, 1)';
          ctx.lineWidth = conn.strokeWidth * 1.5;
          ctx.stroke(path2D);
          strokeColor = 'rgba(59, 130, 246, 1)';
        } else {
          // Apply selection-based opacity
          const effectiveOpacity = Math.max(connOpacity, 0.1);
          strokeColor = `rgba(100, 116, 139, ${effectiveOpacity})`;
          ctx.strokeStyle = strokeColor;
          ctx.lineWidth = Math.max(conn.strokeWidth, isRelatedToSelection ? 2 : 1);
          ctx.stroke(path2D);
        }

        // Draw direction arrows based on edge direction (only if not dimmed)
        if (isRelatedToSelection || isHighlighted) {
          const arrowSize = isHighlighted ? 8 : 6;
          const arrowColor = isHighlighted ? 'rgba(59, 130, 246, 1)' : `rgba(100, 116, 139, ${Math.max(connOpacity + 0.2, 0.7)})`;

          if (conn.direction === 'out' || conn.direction === 'bi') {
            // Arrow pointing toward target (at t=0.75 along curve)
            drawArrowHead(ctx, conn.path, 0.75, arrowSize, arrowColor);
          }
          if (conn.direction === 'in' || conn.direction === 'bi') {
            // Arrow pointing toward source (at t=0.25, flipped)
            // For 'in' direction, we draw at 0.25 but need to flip the arrow
            const pathMatch = conn.path.match(/M\s*([-\d.e+]+)[,\s]+([-\d.e+]+)\s*Q\s*([-\d.e+]+)[,\s]+([-\d.e+]+)\s*([-\d.e+]+)[,\s]+([-\d.e+]+)/i);
            if (pathMatch) {
              const x1 = parseFloat(pathMatch[1]);
              const y1 = parseFloat(pathMatch[2]);
              const cx = parseFloat(pathMatch[3]);
              const cy = parseFloat(pathMatch[4]);
              const x2 = parseFloat(pathMatch[5]);
              const y2 = parseFloat(pathMatch[6]);

              const t = 0.25;
              const px = (1 - t) * (1 - t) * x1 + 2 * (1 - t) * t * cx + t * t * x2;
              const py = (1 - t) * (1 - t) * y1 + 2 * (1 - t) * t * cy + t * t * y2;

              // Calculate tangent direction at t (pointing toward source = reverse direction)
              const dx = 2 * (1 - t) * (cx - x1) + 2 * t * (x2 - cx);
              const dy = 2 * (1 - t) * (cy - y1) + 2 * t * (y2 - cy);
              const angle = Math.atan2(dy, dx) + Math.PI; // Flip by 180 degrees

              ctx.save();
              ctx.translate(px, py);
              ctx.rotate(angle);
              ctx.beginPath();
              ctx.moveTo(arrowSize, 0);
              ctx.lineTo(-arrowSize * 0.6, -arrowSize * 0.5);
              ctx.lineTo(-arrowSize * 0.6, arrowSize * 0.5);
              ctx.closePath();
              ctx.fillStyle = arrowColor;
              ctx.fill();
              ctx.restore();
            }
          }
        }
      }
    }

    // Draw arcs
    const { relatedNodeIds } = selectionData;

    for (const node of focusedData.visibleNodes) {
      if (node.data.type === 'root') continue;

      const isHovered = hoveredNode?.data.id === node.data.id;
      const isSelected = node.data.id === selectedAppId;
      const isFocusDimmed = focusedFolderId && !relevantIds?.has(node.data.id);

      // Compute selection-based opacity
      const selectionOpacity = computeNodeOpacity(node.data.id, selectedAppId, relatedNodeIds);
      const isSelectionDimmed = selectedAppId && selectionOpacity < 0.5;

      // Generate arc path
      const arcPath = arcGenerator(node);
      if (!arcPath) continue;

      ctx.beginPath();
      const path2D = new Path2D(arcPath);

      // Fill color
      let fillColor = node.data.color || '#64748b';
      if (node.data.type === 'application') {
        // Slightly lighter for applications
        fillColor = d3.color(fillColor)?.brighter(0.3)?.formatHex() || fillColor;
      }

      // Apply opacity based on state (selection takes precedence, then focus, then hover)
      let opacity = selectionOpacity;
      if (isFocusDimmed && !selectedAppId) opacity = 0.2;
      if (isHovered) opacity = Math.max(opacity, 0.9);
      if (isSelected) opacity = 1;

      const rgbColor = d3.color(fillColor);
      if (rgbColor) {
        rgbColor.opacity = opacity;
        ctx.fillStyle = rgbColor.formatRgb();
      } else {
        ctx.fillStyle = fillColor;
      }
      ctx.fill(path2D);

      // Stroke - highlight selected/hovered nodes
      const isDimmed = isFocusDimmed || isSelectionDimmed;
      ctx.strokeStyle = isSelected
        ? 'rgba(234, 179, 8, 1)' // yellow for selected
        : isHovered
        ? 'rgba(59, 130, 246, 1)'
        : isDimmed
        ? 'rgba(226, 232, 240, 0.3)'
        : 'rgba(226, 232, 240, 0.8)';
      ctx.lineWidth = isSelected ? 3 : isHovered ? 2 : 1;
      ctx.stroke(path2D);

      // Labels (only for larger arcs)
      const arcAngle = node.x1! - node.x0!;
      const arcRadius = config.innerRadius + (node.y0! + node.y1!) / 2;
      const arcLength = arcAngle * arcRadius;

      if (arcLength > 40 && !isDimmed) {
        const midAngle = (node.x0! + node.x1!) / 2 - Math.PI / 2;
        const labelRadius = config.innerRadius + node.y0! + (node.y1! - node.y0!) * 0.5;
        const labelX = Math.cos(midAngle) * labelRadius;
        const labelY = Math.sin(midAngle) * labelRadius;

        ctx.save();
        ctx.translate(labelX, labelY);

        // Rotate text to follow arc
        let textAngle = midAngle + Math.PI / 2;
        if (textAngle > Math.PI / 2 && textAngle < (3 * Math.PI) / 2) {
          textAngle += Math.PI;
        }
        ctx.rotate(textAngle);

        const label = node.data.displayName || node.data.name;
        const truncatedLabel = label.length > 15 ? label.substring(0, 12) + '...' : label;

        ctx.font = node.data.type === 'folder' ? 'bold 11px sans-serif' : '10px sans-serif';
        ctx.fillStyle = isHovered ? '#1e293b' : '#475569';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(truncatedLabel, 0, 0);
        ctx.restore();
      }
    }

    ctx.restore();
  }, [
    focusedData,
    hoveredNode,
    hoveredConnection,
    transform,
    arcGenerator,
    config,
    width,
    height,
    selectionData,
    selectedAppId,
  ]);

  // Set up canvas and rendering
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const dpr = window.devicePixelRatio || 1;
    canvas.width = width * dpr;
    canvas.height = height * dpr;
    canvas.style.width = `${width}px`;
    canvas.style.height = `${height}px`;

    render();
  }, [width, height, render]);

  // Set up zoom behavior
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const zoom = d3.zoom<HTMLCanvasElement, unknown>()
      .scaleExtent([0.5, 4])
      .on('zoom', (event) => {
        setTransform(event.transform);
      });

    const selection = d3.select(canvas);
    selection.call(zoom);
    // Disable default double-click zoom so our custom handler works
    selection.on('dblclick.zoom', null);

    return () => {
      selection.on('.zoom', null);
    };
  }, []);

  // Handle mouse move for hover detection
  const handleMouseMove = useCallback(
    (event: React.MouseEvent<HTMLCanvasElement>) => {
      const canvas = canvasRef.current;
      if (!canvas) return;

      const rect = canvas.getBoundingClientRect();
      const centerX = width / 2;
      const centerY = height / 2;

      // Transform mouse coordinates
      const mouseX = (event.clientX - rect.left - centerX - transform.x) / transform.k;
      const mouseY = (event.clientY - rect.top - centerY - transform.y) / transform.k;

      // Find node under mouse
      const node = findNodeAtPoint(mouseX, mouseY, focusedData.visibleNodes, config);

      // Check for connection hover (always check since connections are always visible)
      let connection: VisualConnection | null = null;
      if (!node && focusedData.visibleConnections.length > 0) {
        // Adjust threshold based on zoom level - when zoomed out, need larger threshold
        const adjustedThreshold = 20 / transform.k;
        connection = findConnectionAtPoint(mouseX, mouseY, focusedData.visibleConnections, adjustedThreshold);
      }

      setHoveredNode(node);
      setHoveredConnection(connection);

      // Update tooltip for connection
      if (connection) {
        // Format direction for display
        const directionLabel = connection.direction === 'bi'
          ? 'Bi-directional'
          : connection.direction === 'out'
          ? 'Outgoing'
          : 'Incoming';

        const details: { label: string; value: string }[] = [
          { label: 'From', value: connection.sourceName },
          { label: 'To', value: connection.targetName },
          { label: 'Direction', value: directionLabel },
          { label: 'Connections', value: connection.connectionCount.toLocaleString() },
          { label: 'Data transferred', value: formatBytes(connection.bytesTotal) },
          { label: 'Last 24h', value: formatBytes(connection.bytesLast24h) },
        ];

        setTooltip({
          visible: true,
          x: event.clientX,
          y: event.clientY,
          content: {
            title: 'Dependency',
            type: 'connection',
            details,
          },
        });
        return;
      }

      // Update tooltip for node
      if (node && node.data.type !== 'root') {
        const details: { label: string; value: string }[] = [];

        if (node.data.type === 'folder') {
          const folder = node.data.data as FolderTreeNode;
          if (folder) {
            details.push({ label: 'Applications', value: `${folder.applications.length}` });
            details.push({ label: 'Subfolders', value: `${folder.children.length}` });
            if (folder.team) details.push({ label: 'Team', value: folder.team });
          }
        } else if (node.data.type === 'application') {
          const app = node.data.data as any;
          if (app) {
            if (app.environment) details.push({ label: 'Environment', value: app.environment });
            if (app.criticality) details.push({ label: 'Criticality', value: app.criticality });
            if (app.team) details.push({ label: 'Team', value: app.team });
          }
        }

        setTooltip({
          visible: true,
          x: event.clientX,
          y: event.clientY,
          content: {
            title: node.data.displayName || node.data.name,
            type: node.data.type as 'folder' | 'application',
            details,
          },
        });
      } else {
        setTooltip({ visible: false, x: 0, y: 0, content: null });
        setHoveredNode(null);
        setHoveredConnection(null);
      }
    },
    [focusedData.visibleNodes, focusedData.visibleConnections, config, transform, width, height]
  );

  // Handle click
  const handleClick = useCallback(
    (event: React.MouseEvent<HTMLCanvasElement>) => {
      const canvas = canvasRef.current;
      if (!canvas) return;

      const rect = canvas.getBoundingClientRect();
      const centerX = width / 2;
      const centerY = height / 2;

      const mouseX = (event.clientX - rect.left - centerX - transform.x) / transform.k;
      const mouseY = (event.clientY - rect.top - centerY - transform.y) / transform.k;

      const node = findNodeAtPoint(mouseX, mouseY, focusedData.visibleNodes, config);
      if (node) {
        if (node.data.type === 'folder') {
          // Clear app selection when clicking a folder
          if (onApplicationSelect) {
            onApplicationSelect(null);
          }
          if (onFolderClick) {
            onFolderClick(node.data.id);
          }
        } else if (node.data.type === 'application') {
          // Toggle application selection
          if (onApplicationSelect) {
            const newSelection = selectedAppId === node.data.id ? null : node.data.id;
            onApplicationSelect(newSelection);
          }
          // Also trigger the navigation callback if provided
          if (onApplicationClick) {
            onApplicationClick(node.data.id);
          }
        }
      } else {
        // Clicked on empty space - clear selection
        if (onApplicationSelect) {
          onApplicationSelect(null);
        }
      }
    },
    [focusedData.visibleNodes, config, transform, width, height, onFolderClick, onApplicationClick, onApplicationSelect, selectedAppId]
  );

  // Handle double click
  const handleDoubleClick = useCallback(
    (event: React.MouseEvent<HTMLCanvasElement>) => {
      const canvas = canvasRef.current;
      if (!canvas) return;

      const rect = canvas.getBoundingClientRect();
      const centerX = width / 2;
      const centerY = height / 2;

      const mouseX = (event.clientX - rect.left - centerX - transform.x) / transform.k;
      const mouseY = (event.clientY - rect.top - centerY - transform.y) / transform.k;

      const node = findNodeAtPoint(mouseX, mouseY, focusedData.visibleNodes, config);
      if (node && node.data.type === 'folder' && onFolderDoubleClick) {
        onFolderDoubleClick(node.data.id);
      }
    },
    [focusedData.visibleNodes, config, transform, width, height, onFolderDoubleClick]
  );

  const handleMouseLeave = useCallback(() => {
    setTooltip({ visible: false, x: 0, y: 0, content: null });
    setHoveredNode(null);
    setHoveredConnection(null);
  }, []);

  return (
    <div className="relative">
      <canvas
        ref={canvasRef}
        className="cursor-pointer"
        onMouseMove={handleMouseMove}
        onClick={handleClick}
        onDoubleClick={handleDoubleClick}
        onMouseLeave={handleMouseLeave}
      />

      {/* Tooltip */}
      {tooltip.visible && tooltip.content && (
        <div
          className="absolute z-50 bg-white dark:bg-gray-800 rounded-lg shadow-lg border border-gray-200 dark:border-gray-700 p-3 pointer-events-none"
          style={{
            left: tooltip.x + 10,
            top: tooltip.y + 10,
            transform: 'translate(0, 0)',
          }}
        >
          <div className="flex items-center gap-2 mb-2">
            {tooltip.content.type === 'connection' ? (
              <div className="w-4 h-0.5 bg-blue-500 rounded" />
            ) : (
              <span
                className={`inline-block w-2 h-2 rounded-full ${
                  tooltip.content.type === 'folder' ? 'bg-blue-500' : 'bg-green-500'
                }`}
              />
            )}
            <span className="font-medium text-gray-900 dark:text-gray-100">
              {tooltip.content.title}
            </span>
          </div>
          {tooltip.content.details.length > 0 && (
            <div className="space-y-1">
              {tooltip.content.details.map((detail, i) => (
                <div key={i} className="text-sm text-gray-600 dark:text-gray-400">
                  <span className="text-gray-500">{detail.label}:</span> {detail.value}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Legend */}
      <div className="absolute bottom-4 left-4 bg-white dark:bg-gray-800 rounded-lg shadow-lg border border-gray-200 dark:border-gray-700 p-3">
        <div className="text-xs font-medium text-gray-700 dark:text-gray-300 mb-2">Legend</div>
        <div className="space-y-1">
          <div className="flex items-center gap-2 text-xs text-gray-600 dark:text-gray-400">
            <div className="w-3 h-3 rounded-sm bg-blue-500" />
            <span>Folder</span>
          </div>
          <div className="flex items-center gap-2 text-xs text-gray-600 dark:text-gray-400">
            <div className="w-3 h-3 rounded-sm bg-blue-300" />
            <span>Application</span>
          </div>
          <div className="flex items-center gap-2 text-xs text-gray-600 dark:text-gray-400">
            <div className="flex items-center">
              <div className="w-4 h-0.5 bg-gray-400" />
              <div className="w-0 h-0 border-t-2 border-b-2 border-l-4 border-transparent border-l-gray-400" />
            </div>
            <span>One-way flow</span>
          </div>
          <div className="flex items-center gap-2 text-xs text-gray-600 dark:text-gray-400">
            <div className="flex items-center">
              <div className="w-0 h-0 border-t-2 border-b-2 border-r-4 border-transparent border-r-gray-400" />
              <div className="w-3 h-0.5 bg-gray-400" />
              <div className="w-0 h-0 border-t-2 border-b-2 border-l-4 border-transparent border-l-gray-400" />
            </div>
            <span>Bi-directional</span>
          </div>
        </div>
      </div>

      {/* Stats */}
      <div className="absolute top-4 right-4 bg-white dark:bg-gray-800 rounded-lg shadow-lg border border-gray-200 dark:border-gray-700 p-3">
        <div className="text-xs space-y-1 text-gray-600 dark:text-gray-400">
          <div>Folders: {data.statistics.total_folders}</div>
          <div>Applications: {data.statistics.total_applications}</div>
          <div>Dependencies: {data.statistics.total_dependencies}</div>
        </div>
      </div>

      {/* Instructions */}
      <div className="absolute bottom-4 right-4 text-xs text-gray-500 dark:text-gray-400">
        <div>Click: Select | Double-click: Expand folder</div>
        <div className="mt-0.5">Hover over edges for details</div>
      </div>
    </div>
  );
}

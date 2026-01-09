import React from 'react';
import { SparklesIcon } from '@heroicons/react/24/outline';
import { getProtocolName, formatPort } from '../../utils/network';

interface EdgeTooltipProps {
  edge: {
    source: { name: string; ip_address: string };
    target: { name: string; ip_address: string };
    target_port: number;
    target_ports?: number[];
    protocol: number;
    bytes_last_24h?: number;
    last_seen?: string;
    service_type?: string | null;
    dependency_id?: string;
  };
  position: { x: number; y: number };
  containerBounds?: DOMRect;
  onExplain?: (dependencyId: string) => Promise<string>;
  explanation?: string | null;
  isExplaining?: boolean;
  aiEnabled?: boolean;
}

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(1024));
  const value = bytes / Math.pow(1024, i);
  return `${value.toFixed(value < 10 ? 1 : 0)} ${units[i]}`;
}

function formatRelativeTime(dateString: string): string {
  const date = new Date(dateString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMs / 3600000);
  const diffDays = Math.floor(diffMs / 86400000);

  if (diffMins < 1) return 'Just now';
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays < 7) return `${diffDays}d ago`;
  return date.toLocaleDateString();
}

const EdgeTooltip: React.FC<EdgeTooltipProps> = ({
  edge,
  position,
  containerBounds,
  onExplain,
  explanation,
  isExplaining,
  aiEnabled = false,
}) => {
  const protocolName = getProtocolName(edge.protocol);
  const canExplain = aiEnabled && edge.dependency_id && onExplain && !edge.source.name.includes('clients');
  // Use target_ports if available, otherwise fall back to single port
  const ports = edge.target_ports && edge.target_ports.length > 0
    ? edge.target_ports
    : [edge.target_port];
  const portDisplay = ports.length > 1
    ? ports.map(p => formatPort(p, true)).join(', ')
    : formatPort(ports[0], true);

  // Calculate tooltip position with bounds checking
  const tooltipWidth = 280;
  const tooltipHeight = 180;
  let left = position.x + 10;
  let top = position.y + 10;

  if (containerBounds) {
    // Prevent overflow on right edge
    if (left + tooltipWidth > containerBounds.right) {
      left = position.x - tooltipWidth - 10;
    }
    // Prevent overflow on bottom edge
    if (top + tooltipHeight > containerBounds.bottom) {
      top = position.y - tooltipHeight - 10;
    }
    // Prevent going above container
    if (top < containerBounds.top) {
      top = containerBounds.top + 10;
    }
    // Prevent going left of container
    if (left < containerBounds.left) {
      left = containerBounds.left + 10;
    }
  }

  return (
    <div
      style={{
        position: 'fixed',
        left: `${left}px`,
        top: `${top}px`,
        backgroundColor: 'rgba(30, 30, 30, 0.95)',
        border: '1px solid #444',
        borderRadius: '6px',
        padding: '12px',
        color: '#fff',
        fontSize: '12px',
        zIndex: 10000,
        pointerEvents: canExplain ? 'auto' : 'none',
        minWidth: '220px',
        maxWidth: `${tooltipWidth}px`,
        boxShadow: '0 4px 12px rgba(0, 0, 0, 0.4)',
      }}
    >
      {/* Connection Header */}
      <div style={{ marginBottom: '10px', borderBottom: '1px solid #444', paddingBottom: '8px' }}>
        <div style={{ fontWeight: 600, color: '#4ade80', marginBottom: '4px' }}>
          Connection Details
        </div>
      </div>

      {/* Direction */}
      <div style={{ marginBottom: '8px' }}>
        <div style={{ color: '#888', fontSize: '10px', textTransform: 'uppercase', marginBottom: '2px' }}>
          Direction
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <span style={{ color: '#60a5fa' }}>{edge.source.name}</span>
          <span style={{ color: '#888' }}>→</span>
          <span style={{ color: '#f97316' }}>{edge.target.name}</span>
        </div>
      </div>

      {/* Source */}
      <div style={{ marginBottom: '6px' }}>
        <div style={{ color: '#888', fontSize: '10px', textTransform: 'uppercase', marginBottom: '2px' }}>
          Source
        </div>
        <div>
          <span style={{ color: '#60a5fa' }}>{edge.source.name}</span>
          <span style={{ color: '#666', marginLeft: '6px' }}>({edge.source.ip_address})</span>
        </div>
      </div>

      {/* Target */}
      <div style={{ marginBottom: '8px' }}>
        <div style={{ color: '#888', fontSize: '10px', textTransform: 'uppercase', marginBottom: '2px' }}>
          Target
        </div>
        <div>
          <span style={{ color: '#f97316' }}>{edge.target.name}</span>
          <span style={{ color: '#666', marginLeft: '6px' }}>({edge.target.ip_address})</span>
        </div>
      </div>

      {/* Protocol and Port */}
      <div style={{ display: 'flex', gap: '16px', marginBottom: '8px' }}>
        <div>
          <div style={{ color: '#888', fontSize: '10px', textTransform: 'uppercase', marginBottom: '2px' }}>
            Protocol
          </div>
          <div style={{ color: '#a78bfa' }}>{protocolName}</div>
        </div>
        <div>
          <div style={{ color: '#888', fontSize: '10px', textTransform: 'uppercase', marginBottom: '2px' }}>
            {ports.length > 1 ? 'Ports' : 'Port'}
          </div>
          <div style={{ color: '#fbbf24' }}>{portDisplay}</div>
        </div>
        {edge.service_type && (
          <div>
            <div style={{ color: '#888', fontSize: '10px', textTransform: 'uppercase', marginBottom: '2px' }}>
              Service
            </div>
            <div style={{ color: '#22d3ee' }}>{edge.service_type}</div>
          </div>
        )}
      </div>

      {/* Traffic and Last Seen */}
      <div style={{ display: 'flex', gap: '16px', borderTop: '1px solid #333', paddingTop: '8px' }}>
        {edge.bytes_last_24h !== undefined && (
          <div>
            <div style={{ color: '#888', fontSize: '10px', textTransform: 'uppercase', marginBottom: '2px' }}>
              Traffic (24h)
            </div>
            <div style={{ color: '#34d399' }}>{formatBytes(edge.bytes_last_24h)}</div>
          </div>
        )}
        {edge.last_seen && (
          <div>
            <div style={{ color: '#888', fontSize: '10px', textTransform: 'uppercase', marginBottom: '2px' }}>
              Last Seen
            </div>
            <div style={{ color: '#9ca3af' }}>{formatRelativeTime(edge.last_seen)}</div>
          </div>
        )}
      </div>

      {/* AI Explanation Section */}
      {canExplain && (
        <div style={{ borderTop: '1px solid #333', paddingTop: '8px', marginTop: '8px' }}>
          {explanation ? (
            <div>
              <div style={{ color: '#888', fontSize: '10px', textTransform: 'uppercase', marginBottom: '4px', display: 'flex', alignItems: 'center', gap: '4px' }}>
                <SparklesIcon style={{ width: 12, height: 12 }} />
                AI Explanation
              </div>
              <div style={{ color: '#e2e8f0', fontSize: '11px', lineHeight: '1.5' }}>
                {explanation}
              </div>
            </div>
          ) : (
            <button
              onClick={() => edge.dependency_id && onExplain?.(edge.dependency_id)}
              disabled={isExplaining}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
                padding: '6px 10px',
                backgroundColor: isExplaining ? '#374151' : '#4f46e5',
                color: '#fff',
                border: 'none',
                borderRadius: '4px',
                cursor: isExplaining ? 'wait' : 'pointer',
                fontSize: '11px',
                fontWeight: 500,
                width: '100%',
                justifyContent: 'center',
              }}
            >
              <SparklesIcon style={{ width: 14, height: 14 }} />
              {isExplaining ? 'Analyzing...' : 'Explain this connection'}
            </button>
          )}
        </div>
      )}
    </div>
  );
};

export default EdgeTooltip;

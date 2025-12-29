import { useState, useEffect, useRef, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  BellIcon,
  MagnifyingGlassIcon,
  XMarkIcon,
  ChevronDownIcon,
  ChevronUpIcon,
  ArrowRightIcon,
} from '@heroicons/react/24/outline';
import { useWebSocketStore } from '../../hooks/useWebSocket';
import { searchApi, alertApi } from '../../services/api';
import Badge from '../common/Badge';
import clsx from 'clsx';
import { getProtocolName } from '../../utils/network';
import type { Alert, AssetSummary, ConnectionMatch } from '../../types';

type SearchMode = 'simple' | 'advanced';

export default function Header() {
  const navigate = useNavigate();
  const isConnected = useWebSocketStore((state) => state.isConnected);

  // Search state
  const [searchMode, setSearchMode] = useState<SearchMode>('simple');
  const [simpleQuery, setSimpleQuery] = useState('');
  const [sourceQuery, setSourceQuery] = useState('');
  const [destinationQuery, setDestinationQuery] = useState('');
  const [portQuery, setPortQuery] = useState('');
  const [isSearchOpen, setIsSearchOpen] = useState(false);
  const searchRef = useRef<HTMLDivElement>(null);

  // Debounced search params
  const [debouncedParams, setDebouncedParams] = useState<{
    q?: string;
    source?: string;
    destination?: string;
    port?: number;
  }>({});

  // Notification state
  const [isNotificationsOpen, setIsNotificationsOpen] = useState(false);
  const notificationRef = useRef<HTMLDivElement>(null);

  // Debounce search inputs
  useEffect(() => {
    const timer = setTimeout(() => {
      if (searchMode === 'simple') {
        setDebouncedParams({ q: simpleQuery || undefined });
      } else {
        setDebouncedParams({
          source: sourceQuery || undefined,
          destination: destinationQuery || undefined,
          port: portQuery ? parseInt(portQuery, 10) : undefined,
        });
      }
    }, 300);
    return () => clearTimeout(timer);
  }, [searchMode, simpleQuery, sourceQuery, destinationQuery, portQuery]);

  // Check if we should search
  const shouldSearch = useMemo(() => {
    if (searchMode === 'simple') {
      return (debouncedParams.q?.length ?? 0) >= 2;
    }
    return !!(debouncedParams.source || debouncedParams.destination || debouncedParams.port);
  }, [searchMode, debouncedParams]);

  // Search results query
  const { data: searchResults, isLoading: isSearching } = useQuery({
    queryKey: ['unified-search', debouncedParams],
    queryFn: () => searchApi.search({ ...debouncedParams, limit: 10 }),
    enabled: shouldSearch,
  });

  // Recent alerts query
  const { data: recentAlerts } = useQuery({
    queryKey: ['alerts', 'recent'],
    queryFn: () => alertApi.list({ page_size: 5, is_resolved: false }),
    refetchInterval: 30000,
  });

  // Click outside handlers
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (searchRef.current && !searchRef.current.contains(event.target as Node)) {
        setIsSearchOpen(false);
      }
      if (notificationRef.current && !notificationRef.current.contains(event.target as Node)) {
        setIsNotificationsOpen(false);
      }
    }

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Handle asset result click
  const handleAssetClick = (asset: AssetSummary) => {
    navigate(`/assets/${asset.id}`);
    clearSearch();
  };

  // Handle connection result click
  const handleConnectionClick = (connection: ConnectionMatch) => {
    navigate(`/topology?source=${connection.source.id}&target=${connection.target.id}`);
    clearSearch();
  };

  // Handle alert click
  const handleAlertClick = (_alert: Alert) => {
    navigate('/alerts');
    setIsNotificationsOpen(false);
  };

  // Clear search
  const clearSearch = () => {
    setSimpleQuery('');
    setSourceQuery('');
    setDestinationQuery('');
    setPortQuery('');
    setIsSearchOpen(false);
  };

  // Toggle search mode
  const toggleSearchMode = () => {
    setSearchMode(searchMode === 'simple' ? 'advanced' : 'simple');
    clearSearch();
    setIsSearchOpen(true);
  };

  const unreadCount = recentAlerts?.summary?.unacknowledged ?? 0;
  const hasAssets = (searchResults?.assets?.length ?? 0) > 0;
  const hasConnections = (searchResults?.connections?.length ?? 0) > 0;

  return (
    <header className="h-16 bg-slate-800 border-b border-slate-700 flex items-center justify-between px-6">
      {/* Search */}
      <div className="flex items-center flex-1 max-w-2xl" ref={searchRef}>
        <div className="relative w-full">
          {/* Simple Search Mode */}
          {searchMode === 'simple' ? (
            <div className="flex items-center gap-2">
              <div className="relative flex-1">
                <MagnifyingGlassIcon className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-400" />
                <input
                  type="text"
                  value={simpleQuery}
                  onChange={(e) => {
                    setSimpleQuery(e.target.value);
                    setIsSearchOpen(true);
                  }}
                  onFocus={() => setIsSearchOpen(true)}
                  placeholder="Search assets, IPs, hostnames..."
                  className="w-full pl-10 pr-10 py-2 bg-slate-700 border border-slate-600 rounded-lg text-slate-100 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent"
                />
                {simpleQuery && (
                  <button
                    onClick={clearSearch}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-white"
                  >
                    <XMarkIcon className="w-4 h-4" />
                  </button>
                )}
              </div>
              <button
                onClick={toggleSearchMode}
                className="flex items-center gap-1 px-3 py-2 text-slate-400 hover:text-white hover:bg-slate-700 rounded-lg transition-colors text-sm"
                title="Advanced search"
              >
                <ChevronDownIcon className="w-4 h-4" />
              </button>
            </div>
          ) : (
            /* Advanced Search Mode */
            <div className="flex items-center gap-2">
              <div className="flex items-center gap-2 flex-1">
                <div className="relative flex-1">
                  <span className="absolute left-3 top-1/2 -translate-y-1/2 text-xs text-slate-500 uppercase">Src</span>
                  <input
                    type="text"
                    value={sourceQuery}
                    onChange={(e) => {
                      setSourceQuery(e.target.value);
                      setIsSearchOpen(true);
                    }}
                    onFocus={() => setIsSearchOpen(true)}
                    placeholder="Source IP/hostname"
                    className="w-full pl-10 pr-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-slate-100 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent text-sm"
                  />
                </div>
                <ArrowRightIcon className="w-4 h-4 text-slate-500 flex-shrink-0" />
                <div className="relative flex-1">
                  <span className="absolute left-3 top-1/2 -translate-y-1/2 text-xs text-slate-500 uppercase">Dst</span>
                  <input
                    type="text"
                    value={destinationQuery}
                    onChange={(e) => {
                      setDestinationQuery(e.target.value);
                      setIsSearchOpen(true);
                    }}
                    onFocus={() => setIsSearchOpen(true)}
                    placeholder="Dest IP/hostname"
                    className="w-full pl-10 pr-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-slate-100 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent text-sm"
                  />
                </div>
                <div className="relative w-24 flex-shrink-0">
                  <input
                    type="number"
                    value={portQuery}
                    onChange={(e) => {
                      setPortQuery(e.target.value);
                      setIsSearchOpen(true);
                    }}
                    onFocus={() => setIsSearchOpen(true)}
                    placeholder="Port"
                    min="0"
                    max="65535"
                    className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-slate-100 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent text-sm"
                  />
                </div>
              </div>
              {(sourceQuery || destinationQuery || portQuery) && (
                <button
                  onClick={clearSearch}
                  className="p-2 text-slate-400 hover:text-white hover:bg-slate-700 rounded-lg transition-colors"
                >
                  <XMarkIcon className="w-4 h-4" />
                </button>
              )}
              <button
                onClick={toggleSearchMode}
                className="flex items-center gap-1 px-3 py-2 text-slate-400 hover:text-white hover:bg-slate-700 rounded-lg transition-colors text-sm"
                title="Simple search"
              >
                <ChevronUpIcon className="w-4 h-4" />
              </button>
            </div>
          )}

          {/* Search Results Dropdown */}
          {isSearchOpen && shouldSearch && (
            <div className="absolute top-full left-0 right-0 mt-1 bg-slate-800 border border-slate-700 rounded-lg shadow-xl z-50 max-h-96 overflow-y-auto">
              {isSearching ? (
                <div className="p-4 text-center text-slate-400">Searching...</div>
              ) : !hasAssets && !hasConnections ? (
                <div className="p-4 text-center text-slate-400">No results found</div>
              ) : (
                <div>
                  {/* Assets Section */}
                  {hasAssets && (
                    <>
                      <div className="px-3 py-2 text-xs font-medium text-slate-500 uppercase tracking-wider border-b border-slate-700 bg-slate-800/50">
                        Assets ({searchResults!.assets.length})
                      </div>
                      {searchResults!.assets.map((asset) => (
                        <button
                          key={asset.id}
                          onClick={() => handleAssetClick(asset)}
                          className="w-full px-4 py-3 text-left hover:bg-slate-700 transition-colors border-b border-slate-700/50"
                        >
                          <div className="flex items-center justify-between">
                            <div>
                              <div className="font-medium text-white">{asset.name}</div>
                              <div className="text-sm text-slate-400">
                                {asset.ip_address}
                                {asset.hostname && ` • ${asset.hostname}`}
                              </div>
                            </div>
                            <Badge variant={asset.is_internal ? 'info' : 'warning'}>
                              {asset.asset_type}
                            </Badge>
                          </div>
                        </button>
                      ))}
                    </>
                  )}

                  {/* Connections Section */}
                  {hasConnections && (
                    <>
                      <div className="px-3 py-2 text-xs font-medium text-slate-500 uppercase tracking-wider border-b border-slate-700 bg-slate-800/50">
                        Connections ({searchResults!.connections.length})
                      </div>
                      {searchResults!.connections.map((conn) => (
                        <button
                          key={conn.id}
                          onClick={() => handleConnectionClick(conn)}
                          className="w-full px-4 py-3 text-left hover:bg-slate-700 transition-colors border-b border-slate-700/50"
                        >
                          <div className="flex items-center gap-3">
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center gap-2 text-sm">
                                <span className="text-white font-medium truncate">
                                  {conn.source.name}
                                </span>
                                <ArrowRightIcon className="w-3 h-3 text-slate-500 flex-shrink-0" />
                                <span className="text-white font-medium truncate">
                                  {conn.target.name}
                                </span>
                              </div>
                              <div className="text-xs text-slate-400 mt-0.5">
                                {conn.source.ip_address} → {conn.target.ip_address}
                              </div>
                            </div>
                            <div className="text-right flex-shrink-0">
                              <Badge variant="default">
                                {getProtocolName(conn.protocol)}/{conn.target_port}
                              </Badge>
                            </div>
                          </div>
                        </button>
                      ))}
                    </>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Right side */}
      <div className="flex items-center gap-4">
        {/* Connection status */}
        <div className="flex items-center gap-2">
          <div
            className={clsx(
              'w-2 h-2 rounded-full',
              isConnected ? 'bg-green-500' : 'bg-red-500'
            )}
          />
          <span className="text-sm text-slate-400">
            {isConnected ? 'Connected' : 'Disconnected'}
          </span>
        </div>

        {/* Notifications */}
        <div className="relative" ref={notificationRef}>
          <button
            onClick={() => setIsNotificationsOpen(!isNotificationsOpen)}
            className="relative p-2 text-slate-400 hover:text-white hover:bg-slate-700 rounded-lg transition-colors"
          >
            <BellIcon className="w-5 h-5" />
            {unreadCount > 0 && (
              <span className="absolute -top-1 -right-1 min-w-[18px] h-[18px] flex items-center justify-center bg-red-500 text-white text-xs font-medium rounded-full px-1">
                {unreadCount > 99 ? '99+' : unreadCount}
              </span>
            )}
          </button>

          {/* Notifications Dropdown */}
          {isNotificationsOpen && (
            <div className="absolute top-full right-0 mt-1 w-80 bg-slate-800 border border-slate-700 rounded-lg shadow-xl z-50">
              <div className="px-4 py-3 border-b border-slate-700 flex items-center justify-between">
                <span className="font-medium text-white">Notifications</span>
                {unreadCount > 0 && (
                  <Badge variant="error">{unreadCount} unread</Badge>
                )}
              </div>

              <div className="max-h-96 overflow-y-auto">
                {recentAlerts?.items && recentAlerts.items.length > 0 ? (
                  recentAlerts.items.map((alert) => (
                    <button
                      key={alert.id}
                      onClick={() => handleAlertClick(alert)}
                      className={clsx(
                        'w-full px-4 py-3 text-left hover:bg-slate-700 transition-colors border-b border-slate-700/50 last:border-0',
                        !alert.is_acknowledged && 'bg-slate-700/30'
                      )}
                    >
                      <div className="flex items-start gap-3">
                        <div
                          className={clsx(
                            'w-2 h-2 rounded-full mt-2 flex-shrink-0',
                            alert.severity === 'critical' && 'bg-red-500',
                            alert.severity === 'error' && 'bg-orange-500',
                            alert.severity === 'warning' && 'bg-yellow-500',
                            alert.severity === 'info' && 'bg-blue-500'
                          )}
                        />
                        <div className="flex-1 min-w-0">
                          <div className="font-medium text-white text-sm truncate">
                            {alert.title}
                          </div>
                          <div className="text-xs text-slate-400 truncate">
                            {alert.message}
                          </div>
                          <div className="text-xs text-slate-500 mt-1">
                            {new Date(alert.created_at).toLocaleString()}
                          </div>
                        </div>
                      </div>
                    </button>
                  ))
                ) : (
                  <div className="px-4 py-8 text-center text-slate-400">
                    No recent alerts
                  </div>
                )}
              </div>

              <div className="px-4 py-2 border-t border-slate-700">
                <button
                  onClick={() => {
                    navigate('/alerts');
                    setIsNotificationsOpen(false);
                  }}
                  className="w-full text-center text-sm text-primary-400 hover:text-primary-300 py-1"
                >
                  View all alerts
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}

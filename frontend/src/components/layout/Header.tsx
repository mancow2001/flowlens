import { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { BellIcon, MagnifyingGlassIcon, XMarkIcon } from '@heroicons/react/24/outline';
import { useWebSocketStore } from '../../hooks/useWebSocket';
import { assetApi, alertApi } from '../../services/api';
import Badge from '../common/Badge';
import clsx from 'clsx';
import type { Asset, Alert } from '../../types';

export default function Header() {
  const navigate = useNavigate();
  const isConnected = useWebSocketStore((state) => state.isConnected);

  // Search state
  const [searchQuery, setSearchQuery] = useState('');
  const [isSearchOpen, setIsSearchOpen] = useState(false);
  const [debouncedQuery, setDebouncedQuery] = useState('');
  const searchRef = useRef<HTMLDivElement>(null);

  // Notification state
  const [isNotificationsOpen, setIsNotificationsOpen] = useState(false);
  const notificationRef = useRef<HTMLDivElement>(null);

  // Debounce search query
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedQuery(searchQuery);
    }, 300);
    return () => clearTimeout(timer);
  }, [searchQuery]);

  // Search results query
  const { data: searchResults, isLoading: isSearching } = useQuery({
    queryKey: ['search', debouncedQuery],
    queryFn: () => assetApi.list({ search: debouncedQuery, page_size: 10 }),
    enabled: debouncedQuery.length >= 2,
  });

  // Recent alerts query
  const { data: recentAlerts } = useQuery({
    queryKey: ['alerts', 'recent'],
    queryFn: () => alertApi.list({ page_size: 5, is_resolved: false }),
    refetchInterval: 30000, // Refresh every 30 seconds
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

  // Handle search result click
  const handleAssetClick = (asset: Asset) => {
    navigate(`/assets/${asset.id}`);
    setSearchQuery('');
    setIsSearchOpen(false);
  };

  // Handle alert click
  const handleAlertClick = (_alert: Alert) => {
    navigate('/alerts');
    setIsNotificationsOpen(false);
  };

  const unreadCount = recentAlerts?.summary?.unacknowledged ?? 0;

  return (
    <header className="h-16 bg-slate-800 border-b border-slate-700 flex items-center justify-between px-6">
      {/* Search */}
      <div className="flex items-center flex-1 max-w-md" ref={searchRef}>
        <div className="relative w-full">
          <MagnifyingGlassIcon className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-400" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => {
              setSearchQuery(e.target.value);
              setIsSearchOpen(true);
            }}
            onFocus={() => setIsSearchOpen(true)}
            placeholder="Search assets, IPs, hostnames..."
            className="w-full pl-10 pr-10 py-2 bg-slate-700 border border-slate-600 rounded-lg text-slate-100 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent"
          />
          {searchQuery && (
            <button
              onClick={() => {
                setSearchQuery('');
                setIsSearchOpen(false);
              }}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-white"
            >
              <XMarkIcon className="w-4 h-4" />
            </button>
          )}

          {/* Search Results Dropdown */}
          {isSearchOpen && searchQuery.length >= 2 && (
            <div className="absolute top-full left-0 right-0 mt-1 bg-slate-800 border border-slate-700 rounded-lg shadow-xl z-50 max-h-96 overflow-y-auto">
              {isSearching ? (
                <div className="p-4 text-center text-slate-400">
                  Searching...
                </div>
              ) : searchResults?.items && searchResults.items.length > 0 ? (
                <div>
                  <div className="px-3 py-2 text-xs font-medium text-slate-500 uppercase tracking-wider border-b border-slate-700">
                    Assets ({searchResults.total} found)
                  </div>
                  {searchResults.items.map((asset) => (
                    <button
                      key={asset.id}
                      onClick={() => handleAssetClick(asset)}
                      className="w-full px-4 py-3 text-left hover:bg-slate-700 transition-colors border-b border-slate-700/50 last:border-0"
                    >
                      <div className="flex items-center justify-between">
                        <div>
                          <div className="font-medium text-white">{asset.name}</div>
                          <div className="text-sm text-slate-400">
                            {asset.ip_address}
                            {asset.hostname && ` • ${asset.hostname}`}
                          </div>
                        </div>
                        <Badge
                          variant={asset.is_internal ? 'info' : 'warning'}
                        >
                          {asset.asset_type}
                        </Badge>
                      </div>
                    </button>
                  ))}
                  {searchResults.total > 10 && (
                    <button
                      onClick={() => {
                        navigate(`/assets?search=${encodeURIComponent(searchQuery)}`);
                        setSearchQuery('');
                        setIsSearchOpen(false);
                      }}
                      className="w-full px-4 py-2 text-center text-primary-400 hover:text-primary-300 hover:bg-slate-700 text-sm"
                    >
                      View all {searchResults.total} results
                    </button>
                  )}
                </div>
              ) : (
                <div className="p-4 text-center text-slate-400">
                  No assets found for "{searchQuery}"
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

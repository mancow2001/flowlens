/**
 * Application Details SlideOver
 * Right-side panel showing dependency details for a selected application.
 */

import { Fragment, useState, useCallback, useMemo } from 'react';
import { Dialog, Transition, Tab } from '@headlessui/react';
import { XMarkIcon, ArrowDownTrayIcon } from '@heroicons/react/24/outline';
import { useQuery } from '@tanstack/react-query';
import { arcTopologyApi } from '../../services/api';
import { formatBytes } from '../../utils/format';
import type { ApplicationDependencySummary, ConnectionDetail, EdgeDirection } from '../../types';

interface ApplicationDetailsSlideOverProps {
  appId: string | null;
  appName?: string;
  isOpen: boolean;
  onClose: () => void;
}

function classNames(...classes: string[]) {
  return classes.filter(Boolean).join(' ');
}

function DirectionBadge({ direction }: { direction: EdgeDirection }) {
  const colors = {
    in: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
    out: 'bg-green-500/20 text-green-400 border-green-500/30',
    bi: 'bg-purple-500/20 text-purple-400 border-purple-500/30',
  };

  const labels = {
    in: 'Incoming',
    out: 'Outgoing',
    bi: 'Bi-directional',
  };

  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium border ${colors[direction]}`}>
      {labels[direction]}
    </span>
  );
}

const PROTOCOL_NAMES: Record<number, string> = {
  1: 'ICMP',
  6: 'TCP',
  17: 'UDP',
};

function TopConnectionsTable({
  connections,
  direction,
  isLoading,
}: {
  connections: ConnectionDetail[];
  direction: 'incoming' | 'outgoing';
  isLoading: boolean;
}) {
  // Filter connections by direction
  const filteredConnections = useMemo(() => {
    const directionFilter = direction === 'incoming' ? 'in' : 'out';
    return connections.filter((c) => c.direction === directionFilter).slice(0, 10);
  }, [connections, direction]);

  if (isLoading) {
    return null;
  }

  if (filteredConnections.length === 0) {
    return null;
  }

  return (
    <div className="mb-4">
      <h4 className="text-xs font-medium text-slate-400 uppercase tracking-wider mb-2">
        Top {filteredConnections.length} Connections
      </h4>
      <div className="overflow-x-auto bg-slate-900/30 rounded-lg">
        <table className="min-w-full divide-y divide-slate-700/50">
          <thead>
            <tr>
              <th className="px-2 py-1.5 text-left text-xs font-medium text-slate-500">
                {direction === 'incoming' ? 'Source IP' : 'Dest IP'}
              </th>
              <th className="px-2 py-1.5 text-left text-xs font-medium text-slate-500">
                Port
              </th>
              <th className="px-2 py-1.5 text-right text-xs font-medium text-slate-500">
                Data (24h)
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-700/30">
            {filteredConnections.map((conn, idx) => (
              <tr key={idx} className="hover:bg-slate-700/20">
                <td className="px-2 py-1.5 text-xs font-mono text-slate-300">
                  {direction === 'incoming' ? conn.source_ip : conn.destination_ip}
                </td>
                <td className="px-2 py-1.5 text-xs text-slate-300">
                  {conn.destination_port}/{PROTOCOL_NAMES[conn.protocol] || conn.protocol}
                </td>
                <td className="px-2 py-1.5 text-right text-xs text-slate-300">
                  {formatBytes(conn.bytes_last_24h)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function DependencyTable({
  dependencies,
  isLoading,
}: {
  dependencies: ApplicationDependencySummary[];
  isLoading: boolean;
}) {
  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-500"></div>
      </div>
    );
  }

  if (dependencies.length === 0) {
    return (
      <div className="text-center py-12 text-slate-400">
        No dependencies found
      </div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="min-w-full divide-y divide-slate-700">
        <thead>
          <tr>
            <th className="px-3 py-2 text-left text-xs font-medium text-slate-400 uppercase tracking-wider">
              Counterparty
            </th>
            <th className="px-3 py-2 text-left text-xs font-medium text-slate-400 uppercase tracking-wider">
              Direction
            </th>
            <th className="px-3 py-2 text-right text-xs font-medium text-slate-400 uppercase tracking-wider">
              Connections
            </th>
            <th className="px-3 py-2 text-right text-xs font-medium text-slate-400 uppercase tracking-wider">
              Data (24h)
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-700/50">
          {dependencies.map((dep) => (
            <tr key={dep.counterparty_id} className="hover:bg-slate-700/30">
              <td className="px-3 py-2">
                <div className="text-sm text-white">{dep.counterparty_name}</div>
                {dep.counterparty_folder_name && (
                  <div className="text-xs text-slate-400">{dep.counterparty_folder_name}</div>
                )}
              </td>
              <td className="px-3 py-2">
                <DirectionBadge direction={dep.direction} />
              </td>
              <td className="px-3 py-2 text-right text-sm text-slate-300">
                {dep.connection_count.toLocaleString()}
              </td>
              <td className="px-3 py-2 text-right text-sm text-slate-300">
                {formatBytes(dep.bytes_last_24h)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function ApplicationDetailsSlideOver({
  appId,
  appName,
  isOpen,
  onClose,
}: ApplicationDetailsSlideOverProps) {
  const [selectedTab, setSelectedTab] = useState<'incoming' | 'outgoing'>('outgoing');
  const [isExporting, setIsExporting] = useState(false);

  // Fetch incoming dependencies
  const { data: incomingData, isLoading: isLoadingIncoming } = useQuery({
    queryKey: ['app-dependencies', appId, 'incoming'],
    queryFn: () => arcTopologyApi.getAppDependencies(appId!, 'incoming'),
    enabled: !!appId && isOpen,
  });

  // Fetch outgoing dependencies
  const { data: outgoingData, isLoading: isLoadingOutgoing } = useQuery({
    queryKey: ['app-dependencies', appId, 'outgoing'],
    queryFn: () => arcTopologyApi.getAppDependencies(appId!, 'outgoing'),
    enabled: !!appId && isOpen,
  });

  // Fetch both to get all top_connections for display
  const { data: bothData } = useQuery({
    queryKey: ['app-dependencies', appId, 'both'],
    queryFn: () => arcTopologyApi.getAppDependencies(appId!, 'both'),
    enabled: !!appId && isOpen,
  });

  const handleExport = useCallback(async () => {
    if (!appId) return;
    setIsExporting(true);
    try {
      // Export always exports all connections (both directions)
      await arcTopologyApi.exportAppDependencies(appId);
    } catch (error) {
      console.error('Export failed:', error);
    } finally {
      setIsExporting(false);
    }
  }, [appId]);

  const displayName = useMemo(
    () => appName || incomingData?.app_name || outgoingData?.app_name || 'Application',
    [appName, incomingData?.app_name, outgoingData?.app_name]
  );

  // Get current tab data - memoized to avoid unnecessary re-renders
  const currentData = useMemo(
    () => selectedTab === 'incoming' ? incomingData : outgoingData,
    [selectedTab, incomingData, outgoingData]
  );
  const isLoading = selectedTab === 'incoming' ? isLoadingIncoming : isLoadingOutgoing;

  return (
    <Transition.Root show={isOpen} as={Fragment}>
      <Dialog as="div" className="relative z-50" onClose={onClose}>
        <Transition.Child
          as={Fragment}
          enter="ease-in-out duration-300"
          enterFrom="opacity-0"
          enterTo="opacity-100"
          leave="ease-in-out duration-300"
          leaveFrom="opacity-100"
          leaveTo="opacity-0"
        >
          <div className="fixed inset-0 bg-black/50 transition-opacity" />
        </Transition.Child>

        <div className="fixed inset-0 overflow-hidden">
          <div className="absolute inset-0 overflow-hidden">
            <div className="pointer-events-none fixed inset-y-0 right-0 flex max-w-full pl-10">
              <Transition.Child
                as={Fragment}
                enter="transform transition ease-in-out duration-300"
                enterFrom="translate-x-full"
                enterTo="translate-x-0"
                leave="transform transition ease-in-out duration-300"
                leaveFrom="translate-x-0"
                leaveTo="translate-x-full"
              >
                <Dialog.Panel className="pointer-events-auto w-screen max-w-lg">
                  <div className="flex h-full flex-col overflow-y-auto bg-slate-800 shadow-xl">
                    {/* Header */}
                    <div className="px-6 py-4 border-b border-slate-700">
                      <div className="flex items-start justify-between">
                        <div>
                          <Dialog.Title className="text-lg font-semibold text-white">
                            {displayName}
                          </Dialog.Title>
                          <p className="text-sm text-slate-400 mt-1">
                            Dependency Details
                          </p>
                        </div>
                        <button
                          type="button"
                          className="rounded-md text-slate-400 hover:text-white focus:outline-none focus:ring-2 focus:ring-primary-500"
                          onClick={onClose}
                        >
                          <span className="sr-only">Close panel</span>
                          <XMarkIcon className="h-6 w-6" aria-hidden="true" />
                        </button>
                      </div>
                    </div>

                    {/* Summary Stats */}
                    <div className="px-6 py-4 bg-slate-900/50 border-b border-slate-700">
                      <div className="grid grid-cols-3 gap-4">
                        <div>
                          <div className="text-xs text-slate-400 uppercase tracking-wider">
                            Total Connections
                          </div>
                          <div className="text-lg font-semibold text-white mt-1">
                            {currentData?.total_connections.toLocaleString() ?? '-'}
                          </div>
                        </div>
                        <div>
                          <div className="text-xs text-slate-400 uppercase tracking-wider">
                            Total Data
                          </div>
                          <div className="text-lg font-semibold text-white mt-1">
                            {currentData ? formatBytes(currentData.total_bytes) : '-'}
                          </div>
                        </div>
                        <div>
                          <div className="text-xs text-slate-400 uppercase tracking-wider">
                            Last 24h
                          </div>
                          <div className="text-lg font-semibold text-primary-400 mt-1">
                            {currentData ? formatBytes(currentData.total_bytes_24h) : '-'}
                          </div>
                        </div>
                      </div>
                    </div>

                    {/* Tabs */}
                    <div className="px-6 pt-4">
                      <Tab.Group
                        selectedIndex={selectedTab === 'outgoing' ? 0 : 1}
                        onChange={(index) => setSelectedTab(index === 0 ? 'outgoing' : 'incoming')}
                      >
                        <Tab.List className="flex space-x-1 rounded-lg bg-slate-900/50 p-1">
                          <Tab
                            className={({ selected }) =>
                              classNames(
                                'w-full rounded-md py-2 text-sm font-medium leading-5',
                                'focus:outline-none focus:ring-2 focus:ring-primary-500/50',
                                selected
                                  ? 'bg-primary-600 text-white shadow'
                                  : 'text-slate-400 hover:text-white hover:bg-slate-700/50'
                              )
                            }
                          >
                            <span className="flex items-center justify-center gap-2">
                              Outgoing
                              {outgoingData && (
                                <span className="text-xs opacity-70">
                                  ({outgoingData.dependencies.length})
                                </span>
                              )}
                            </span>
                          </Tab>
                          <Tab
                            className={({ selected }) =>
                              classNames(
                                'w-full rounded-md py-2 text-sm font-medium leading-5',
                                'focus:outline-none focus:ring-2 focus:ring-primary-500/50',
                                selected
                                  ? 'bg-primary-600 text-white shadow'
                                  : 'text-slate-400 hover:text-white hover:bg-slate-700/50'
                              )
                            }
                          >
                            <span className="flex items-center justify-center gap-2">
                              Incoming
                              {incomingData && (
                                <span className="text-xs opacity-70">
                                  ({incomingData.dependencies.length})
                                </span>
                              )}
                            </span>
                          </Tab>
                        </Tab.List>
                      </Tab.Group>
                    </div>

                    {/* Dependency List with Top Connections */}
                    <div className="flex-1 px-6 py-4 overflow-y-auto">
                      {/* Top Connections Table */}
                      <TopConnectionsTable
                        connections={bothData?.top_connections ?? []}
                        direction={selectedTab}
                        isLoading={isLoading}
                      />

                      {/* Counterparty Summary Table */}
                      <h4 className="text-xs font-medium text-slate-400 uppercase tracking-wider mb-2">
                        {selectedTab === 'incoming' ? 'Incoming' : 'Outgoing'} Counterparties
                      </h4>
                      <DependencyTable
                        dependencies={currentData?.dependencies ?? []}
                        isLoading={isLoading}
                      />
                    </div>

                    {/* Footer with Export Button */}
                    <div className="px-6 py-4 border-t border-slate-700 bg-slate-900/50">
                      <button
                        onClick={handleExport}
                        disabled={isExporting || !bothData?.total_connections}
                        className={classNames(
                          'w-full flex items-center justify-center gap-2 px-4 py-2 rounded-md text-sm font-medium',
                          'transition-colors duration-150',
                          bothData?.total_connections
                            ? 'bg-slate-700 text-white hover:bg-slate-600'
                            : 'bg-slate-800 text-slate-500 cursor-not-allowed'
                        )}
                      >
                        {isExporting ? (
                          <>
                            <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
                            Exporting...
                          </>
                        ) : (
                          <>
                            <ArrowDownTrayIcon className="h-4 w-4" />
                            Export All Connections as CSV
                          </>
                        )}
                      </button>
                    </div>
                  </div>
                </Dialog.Panel>
              </Transition.Child>
            </div>
          </div>
        </div>
      </Dialog>
    </Transition.Root>
  );
}

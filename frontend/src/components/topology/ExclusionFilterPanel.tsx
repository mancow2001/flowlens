/**
 * Exclusion Filter Panel
 * Allows users to manage which folders/applications are excluded from the arc topology view.
 */

import { useState } from 'react';
import { XMarkIcon, EyeSlashIcon, PlusIcon } from '@heroicons/react/24/outline';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { exclusionsApi } from '../../services/api';
import type { TopologyExclusion, ExclusionEntityType, ArcTopologyData } from '../../types';

interface ExclusionFilterPanelProps {
  /** The full topology data (before exclusions) for entity selection */
  topologyData?: ArcTopologyData;
  /** Whether the panel is expanded */
  isExpanded: boolean;
  /** Callback when panel expansion changes */
  onToggleExpand: () => void;
}

export function ExclusionFilterPanel({
  topologyData,
  isExpanded,
  onToggleExpand,
}: ExclusionFilterPanelProps) {
  const queryClient = useQueryClient();
  const [selectedType, setSelectedType] = useState<ExclusionEntityType>('folder');
  const [selectedEntityId, setSelectedEntityId] = useState<string>('');
  const [isAdding, setIsAdding] = useState(false);

  // Fetch current exclusions
  const { data: exclusions, isLoading } = useQuery({
    queryKey: ['topology-exclusions'],
    queryFn: exclusionsApi.list,
  });

  // Create exclusion mutation
  const createMutation = useMutation({
    mutationFn: exclusionsApi.create,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['topology-exclusions'] });
      queryClient.invalidateQueries({ queryKey: ['arc-topology'] });
      setSelectedEntityId('');
      setIsAdding(false);
    },
  });

  // Delete exclusion mutation
  const deleteMutation = useMutation({
    mutationFn: exclusionsApi.delete,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['topology-exclusions'] });
      queryClient.invalidateQueries({ queryKey: ['arc-topology'] });
    },
  });

  // Get available entities for selection (folders and applications)
  const availableFolders = topologyData?.hierarchy.roots.filter(
    f => f.id !== 'unassigned' && !exclusions?.items.some(e => e.entity_id === f.id)
  ) ?? [];

  const availableApplications = topologyData?.hierarchy.roots.flatMap(folder => [
    ...folder.applications,
    ...folder.children.flatMap(child => child.applications),
  ]).filter(
    app => !exclusions?.items.some(e => e.entity_id === app.id)
  ) ?? [];

  const handleAddExclusion = () => {
    if (!selectedEntityId) return;
    createMutation.mutate({
      entity_type: selectedType,
      entity_id: selectedEntityId,
    });
  };

  const handleRemoveExclusion = (exclusion: TopologyExclusion) => {
    deleteMutation.mutate(exclusion.id);
  };

  const exclusionCount = exclusions?.items.length ?? 0;

  return (
    <div className="bg-slate-800 border border-slate-700 rounded-lg overflow-hidden">
      {/* Header */}
      <button
        onClick={onToggleExpand}
        className="w-full px-4 py-3 flex items-center justify-between hover:bg-slate-700/50 transition-colors"
      >
        <div className="flex items-center gap-2">
          <EyeSlashIcon className="h-5 w-5 text-slate-400" />
          <span className="text-sm font-medium text-white">
            Exclusions
          </span>
          {exclusionCount > 0 && (
            <span className="px-2 py-0.5 text-xs bg-amber-500/20 text-amber-400 rounded-full">
              {exclusionCount}
            </span>
          )}
        </div>
        <svg
          className={`h-4 w-4 text-slate-400 transition-transform ${isExpanded ? 'rotate-180' : ''}`}
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {/* Content */}
      {isExpanded && (
        <div className="px-4 pb-4 border-t border-slate-700">
          {/* Current exclusions list */}
          <div className="mt-3">
            {isLoading ? (
              <div className="flex items-center justify-center py-4">
                <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-primary-500"></div>
              </div>
            ) : exclusions?.items.length === 0 ? (
              <p className="text-sm text-slate-400 py-2">
                No exclusions. All folders and applications are visible.
              </p>
            ) : (
              <ul className="space-y-2">
                {exclusions?.items.map(exclusion => (
                  <li
                    key={exclusion.id}
                    className="flex items-center justify-between bg-slate-900/50 rounded-md px-3 py-2"
                  >
                    <div className="flex items-center gap-2 min-w-0">
                      <span className={`px-1.5 py-0.5 text-[10px] uppercase tracking-wider rounded ${
                        exclusion.entity_type === 'folder'
                          ? 'bg-blue-500/20 text-blue-400'
                          : 'bg-green-500/20 text-green-400'
                      }`}>
                        {exclusion.entity_type === 'folder' ? 'Folder' : 'App'}
                      </span>
                      <span className="text-sm text-white truncate">
                        {exclusion.entity_name || exclusion.entity_id}
                      </span>
                    </div>
                    <button
                      onClick={() => handleRemoveExclusion(exclusion)}
                      disabled={deleteMutation.isPending}
                      className="p-1 text-slate-400 hover:text-red-400 hover:bg-red-500/10 rounded transition-colors"
                      title="Remove exclusion"
                    >
                      <XMarkIcon className="h-4 w-4" />
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>

          {/* Add exclusion form */}
          {isAdding ? (
            <div className="mt-3 space-y-3 p-3 bg-slate-900/50 rounded-md">
              {/* Entity type selector */}
              <div className="flex gap-2">
                <button
                  onClick={() => {
                    setSelectedType('folder');
                    setSelectedEntityId('');
                  }}
                  className={`flex-1 px-3 py-1.5 text-sm rounded transition-colors ${
                    selectedType === 'folder'
                      ? 'bg-primary-600 text-white'
                      : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
                  }`}
                >
                  Folder
                </button>
                <button
                  onClick={() => {
                    setSelectedType('application');
                    setSelectedEntityId('');
                  }}
                  className={`flex-1 px-3 py-1.5 text-sm rounded transition-colors ${
                    selectedType === 'application'
                      ? 'bg-primary-600 text-white'
                      : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
                  }`}
                >
                  Application
                </button>
              </div>

              {/* Entity selector */}
              <select
                value={selectedEntityId}
                onChange={(e) => setSelectedEntityId(e.target.value)}
                className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded text-sm text-white focus:outline-none focus:ring-2 focus:ring-primary-500"
              >
                <option value="">
                  Select {selectedType === 'folder' ? 'a folder' : 'an application'}...
                </option>
                {selectedType === 'folder'
                  ? availableFolders.map(folder => (
                      <option key={folder.id} value={folder.id}>
                        {folder.name}
                      </option>
                    ))
                  : availableApplications.map(app => (
                      <option key={app.id} value={app.id}>
                        {app.name}
                      </option>
                    ))
                }
              </select>

              {/* Action buttons */}
              <div className="flex gap-2">
                <button
                  onClick={() => {
                    setIsAdding(false);
                    setSelectedEntityId('');
                  }}
                  className="flex-1 px-3 py-1.5 text-sm bg-slate-700 text-slate-300 rounded hover:bg-slate-600 transition-colors"
                >
                  Cancel
                </button>
                <button
                  onClick={handleAddExclusion}
                  disabled={!selectedEntityId || createMutation.isPending}
                  className="flex-1 px-3 py-1.5 text-sm bg-primary-600 text-white rounded hover:bg-primary-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                >
                  {createMutation.isPending ? 'Adding...' : 'Exclude'}
                </button>
              </div>
            </div>
          ) : (
            <button
              onClick={() => setIsAdding(true)}
              className="mt-3 w-full flex items-center justify-center gap-2 px-3 py-2 text-sm bg-slate-700 text-slate-300 rounded hover:bg-slate-600 transition-colors"
            >
              <PlusIcon className="h-4 w-4" />
              Add Exclusion
            </button>
          )}
        </div>
      )}
    </div>
  );
}

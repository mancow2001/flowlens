import { useState } from 'react';
import { useMutation, useQueryClient, useQuery } from '@tanstack/react-query';
import {
  XMarkIcon,
  TrashIcon,
  ExclamationTriangleIcon,
  TagIcon,
} from '@heroicons/react/24/outline';
import Button from '../common/Button';
import Card from '../common/Card';
import { assetBulkApi, classificationApi } from '../../services/api';

interface BulkActionToolbarProps {
  selectedIds: string[];
  onClear: () => void;
  onSuccess?: () => void;
}

type ActionType = 'environment' | 'datacenter' | 'critical' | 'delete' | null;

export default function BulkActionToolbar({
  selectedIds,
  onClear,
  onSuccess,
}: BulkActionToolbarProps) {
  const queryClient = useQueryClient();
  const [activeAction, setActiveAction] = useState<ActionType>(null);
  const [selectedValue, setSelectedValue] = useState<string>('');
  const [showConfirm, setShowConfirm] = useState(false);

  // Fetch environments and datacenters for dropdowns
  const { data: environments } = useQuery({
    queryKey: ['environments'],
    queryFn: () => classificationApi.listEnvironments(),
  });

  const { data: datacenters } = useQuery({
    queryKey: ['datacenters'],
    queryFn: () => classificationApi.listDatacenters(),
  });

  const updateMutation = useMutation({
    mutationFn: ({ ids, updates }: { ids: string[]; updates: Record<string, string | boolean | null> }) =>
      assetBulkApi.bulkUpdate(ids, updates),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ['assets'] });
      alert(`Updated ${result.updated} assets`);
      onClear();
      setActiveAction(null);
      setSelectedValue('');
      onSuccess?.();
    },
    onError: (error: Error) => {
      alert(`Failed to update assets: ${error.message}`);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (ids: string[]) => assetBulkApi.bulkDelete(ids),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ['assets'] });
      alert(`Deleted ${result.deleted} assets`);
      onClear();
      setActiveAction(null);
      setShowConfirm(false);
      onSuccess?.();
    },
    onError: (error: Error) => {
      alert(`Failed to delete assets: ${error.message}`);
    },
  });

  const handleApply = () => {
    if (!activeAction || activeAction === 'delete') return;

    const updates: Record<string, string | boolean | null> = {};

    switch (activeAction) {
      case 'environment':
        updates.environment = selectedValue || null;
        break;
      case 'datacenter':
        updates.datacenter = selectedValue || null;
        break;
      case 'critical':
        updates.is_critical = selectedValue === 'true';
        break;
    }

    updateMutation.mutate({ ids: selectedIds, updates });
  };

  const handleDelete = () => {
    setActiveAction('delete');
    setShowConfirm(true);
  };

  const confirmDelete = () => {
    deleteMutation.mutate(selectedIds);
  };

  if (selectedIds.length === 0) {
    return null;
  }

  return (
    <>
      <Card className="!p-3 bg-primary-900/30 border-primary-600">
        <div className="flex items-center gap-4">
          {/* Selection count */}
          <div className="flex items-center gap-2">
            <span className="text-primary-300 font-medium">
              {selectedIds.length} selected
            </span>
            <button
              onClick={onClear}
              className="p-1 text-slate-400 hover:text-white rounded"
            >
              <XMarkIcon className="w-4 h-4" />
            </button>
          </div>

          <div className="h-6 w-px bg-slate-600" />

          {/* Action buttons */}
          <div className="flex items-center gap-2">
            <Button
              variant={activeAction === 'environment' ? 'primary' : 'secondary'}
              size="sm"
              onClick={() => {
                setActiveAction(activeAction === 'environment' ? null : 'environment');
                setSelectedValue('');
              }}
            >
              <TagIcon className="w-4 h-4 mr-1" />
              Environment
            </Button>

            <Button
              variant={activeAction === 'datacenter' ? 'primary' : 'secondary'}
              size="sm"
              onClick={() => {
                setActiveAction(activeAction === 'datacenter' ? null : 'datacenter');
                setSelectedValue('');
              }}
            >
              <TagIcon className="w-4 h-4 mr-1" />
              Datacenter
            </Button>

            <Button
              variant={activeAction === 'critical' ? 'primary' : 'secondary'}
              size="sm"
              onClick={() => {
                setActiveAction(activeAction === 'critical' ? null : 'critical');
                setSelectedValue('');
              }}
            >
              <ExclamationTriangleIcon className="w-4 h-4 mr-1" />
              Critical
            </Button>

            <div className="h-6 w-px bg-slate-600" />

            <Button
              variant="ghost"
              size="sm"
              className="text-red-400 hover:text-red-300 hover:bg-red-500/20"
              onClick={handleDelete}
            >
              <TrashIcon className="w-4 h-4 mr-1" />
              Delete
            </Button>
          </div>

          {/* Value selector */}
          {activeAction && activeAction !== 'delete' && (
            <>
              <div className="h-6 w-px bg-slate-600" />
              <div className="flex items-center gap-2">
                {activeAction === 'environment' && (
                  <select
                    value={selectedValue}
                    onChange={(e) => setSelectedValue(e.target.value)}
                    className="px-3 py-1.5 bg-slate-700 border border-slate-600 rounded text-sm text-slate-100 focus:outline-none focus:ring-2 focus:ring-primary-500"
                  >
                    <option value="">Clear environment</option>
                    {environments?.map((env) => (
                      <option key={env} value={env}>
                        {env}
                      </option>
                    ))}
                  </select>
                )}

                {activeAction === 'datacenter' && (
                  <select
                    value={selectedValue}
                    onChange={(e) => setSelectedValue(e.target.value)}
                    className="px-3 py-1.5 bg-slate-700 border border-slate-600 rounded text-sm text-slate-100 focus:outline-none focus:ring-2 focus:ring-primary-500"
                  >
                    <option value="">Clear datacenter</option>
                    {datacenters?.map((dc) => (
                      <option key={dc} value={dc}>
                        {dc}
                      </option>
                    ))}
                  </select>
                )}

                {activeAction === 'critical' && (
                  <select
                    value={selectedValue}
                    onChange={(e) => setSelectedValue(e.target.value)}
                    className="px-3 py-1.5 bg-slate-700 border border-slate-600 rounded text-sm text-slate-100 focus:outline-none focus:ring-2 focus:ring-primary-500"
                  >
                    <option value="">Select...</option>
                    <option value="true">Mark as Critical</option>
                    <option value="false">Mark as Non-Critical</option>
                  </select>
                )}

                <Button
                  variant="primary"
                  size="sm"
                  disabled={!selectedValue || updateMutation.isPending}
                  onClick={handleApply}
                >
                  {updateMutation.isPending ? 'Applying...' : 'Apply'}
                </Button>
              </div>
            </>
          )}
        </div>
      </Card>

      {/* Delete confirmation modal */}
      {showConfirm && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <Card className="w-full max-w-md">
            <div className="flex items-start gap-4">
              <div className="p-2 bg-red-500/20 rounded-lg">
                <ExclamationTriangleIcon className="w-6 h-6 text-red-400" />
              </div>
              <div className="flex-1">
                <h3 className="text-lg font-semibold text-white">
                  Delete {selectedIds.length} Assets?
                </h3>
                <p className="text-slate-400 mt-1">
                  This action cannot be undone. The selected assets will be
                  permanently removed from the system.
                </p>
              </div>
            </div>

            <div className="flex justify-end gap-2 mt-6">
              <Button
                variant="ghost"
                onClick={() => {
                  setShowConfirm(false);
                  setActiveAction(null);
                }}
              >
                Cancel
              </Button>
              <Button
                variant="primary"
                className="bg-red-600 hover:bg-red-700"
                disabled={deleteMutation.isPending}
                onClick={confirmDelete}
              >
                {deleteMutation.isPending ? 'Deleting...' : 'Delete Assets'}
              </Button>
            </div>
          </Card>
        </div>
      )}
    </>
  );
}

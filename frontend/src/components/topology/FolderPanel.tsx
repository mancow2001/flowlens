/**
 * Folder management panel for organizing applications into folders.
 */

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { folderApi, arcTopologyApi, applicationsApi } from '../../services/api';
import type { FolderTreeNode, FolderCreate, Application } from '../../types';
import Card from '../common/Card';
import Button from '../common/Button';

interface FolderPanelProps {
  onFolderSelect?: (folderId: string | null) => void;
  selectedFolderId?: string | null;
}

export function FolderPanel({ onFolderSelect, selectedFolderId }: FolderPanelProps) {
  const queryClient = useQueryClient();
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [newFolderName, setNewFolderName] = useState('');
  const [newFolderParentId, setNewFolderParentId] = useState<string | null>(null);
  const [expandedFolders, setExpandedFolders] = useState<Set<string>>(new Set());
  const [showAssignModal, setShowAssignModal] = useState(false);
  const [assignToFolderId, setAssignToFolderId] = useState<string | null>(null);

  // Fetch folder tree
  const { data: folderTree, isLoading: isLoadingFolders } = useQuery({
    queryKey: ['folders', 'tree'],
    queryFn: () => folderApi.getTree(),
  });

  // Fetch applications for assignment
  const { data: applications } = useQuery({
    queryKey: ['applications', 'list'],
    queryFn: () => applicationsApi.list({ page_size: 1000 }),
    enabled: showAssignModal,
  });

  // Create folder mutation
  const createFolderMutation = useMutation({
    mutationFn: (data: FolderCreate) => folderApi.create(data),
    onSuccess: () => {
      // Invalidate folder tree to refresh the panel
      queryClient.invalidateQueries({ queryKey: ['folders', 'tree'] });
      // Invalidate arc topology to refresh the visualization
      queryClient.invalidateQueries({ queryKey: ['topology', 'arc'] });
      setShowCreateForm(false);
      setNewFolderName('');
      setNewFolderParentId(null);
    },
  });

  // Delete folder mutation
  const deleteFolderMutation = useMutation({
    mutationFn: (id: string) => folderApi.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['folders', 'tree'] });
      queryClient.invalidateQueries({ queryKey: ['topology', 'arc'] });
    },
  });

  // Move application to folder mutation
  const moveAppMutation = useMutation({
    mutationFn: ({ appId, folderId }: { appId: string; folderId: string | null }) =>
      arcTopologyApi.moveApplicationToFolder(appId, { folder_id: folderId }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['folders', 'tree'] });
      queryClient.invalidateQueries({ queryKey: ['topology', 'arc'] });
      queryClient.invalidateQueries({ queryKey: ['applications'] });
      setShowAssignModal(false);
      setAssignToFolderId(null);
    },
  });

  const toggleExpanded = (folderId: string) => {
    const newExpanded = new Set(expandedFolders);
    if (newExpanded.has(folderId)) {
      newExpanded.delete(folderId);
    } else {
      newExpanded.add(folderId);
    }
    setExpandedFolders(newExpanded);
  };

  const handleCreateFolder = () => {
    if (!newFolderName.trim()) return;
    // Color is auto-assigned by the backend
    createFolderMutation.mutate({
      name: newFolderName.trim(),
      parent_id: newFolderParentId,
    });
  };

  const renderFolderNode = (folder: FolderTreeNode, depth: number = 0) => {
    const isExpanded = expandedFolders.has(folder.id);
    const isSelected = selectedFolderId === folder.id;
    const hasChildren = folder.children.length > 0 || folder.applications.length > 0;

    return (
      <div key={folder.id}>
        <div
          className={`flex items-center gap-2 px-2 py-1.5 rounded cursor-pointer transition-colors ${
            isSelected
              ? 'bg-primary-600/30 border border-primary-500'
              : 'hover:bg-slate-700/50'
          }`}
          style={{ paddingLeft: `${depth * 16 + 8}px` }}
          onClick={() => onFolderSelect?.(folder.id)}
        >
          {/* Expand/collapse toggle */}
          {hasChildren ? (
            <button
              onClick={(e) => {
                e.stopPropagation();
                toggleExpanded(folder.id);
              }}
              className="text-slate-400 hover:text-slate-200"
            >
              <svg
                className={`w-4 h-4 transform transition-transform ${isExpanded ? 'rotate-90' : ''}`}
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
              </svg>
            </button>
          ) : (
            <div className="w-4" />
          )}

          {/* Folder icon with color */}
          <div
            className="w-4 h-4 rounded"
            style={{ backgroundColor: folder.color || '#64748b' }}
          />

          {/* Folder name */}
          <span className="flex-1 text-sm text-slate-200 truncate">
            {folder.display_name || folder.name}
          </span>

          {/* App count badge */}
          {folder.applications.length > 0 && (
            <span className="text-xs text-slate-400 bg-slate-700 px-1.5 py-0.5 rounded">
              {folder.applications.length}
            </span>
          )}

          {/* Actions dropdown */}
          <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100">
            <button
              onClick={(e) => {
                e.stopPropagation();
                setAssignToFolderId(folder.id);
                setShowAssignModal(true);
              }}
              className="text-slate-400 hover:text-slate-200 p-1"
              title="Assign applications"
            >
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
              </svg>
            </button>
            <button
              onClick={(e) => {
                e.stopPropagation();
                if (confirm(`Delete folder "${folder.name}"?`)) {
                  deleteFolderMutation.mutate(folder.id);
                }
              }}
              className="text-slate-400 hover:text-red-400 p-1"
              title="Delete folder"
            >
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
              </svg>
            </button>
          </div>
        </div>

        {/* Children */}
        {isExpanded && (
          <div>
            {folder.children.map((child) => renderFolderNode(child, depth + 1))}
            {folder.applications.map((app) => (
              <div
                key={app.id}
                className="flex items-center gap-2 px-2 py-1 text-sm text-slate-400 hover:text-slate-200 hover:bg-slate-700/30 rounded cursor-pointer"
                style={{ paddingLeft: `${(depth + 1) * 16 + 24}px` }}
                onClick={() => window.location.href = `/applications/${app.id}`}
              >
                <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
                <span className="truncate">{app.display_name || app.name}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    );
  };

  // Flatten folders for parent selection dropdown
  const flattenFolders = (folders: FolderTreeNode[], depth = 0): Array<{ id: string; name: string; depth: number }> => {
    const result: Array<{ id: string; name: string; depth: number }> = [];
    for (const folder of folders) {
      result.push({ id: folder.id, name: folder.display_name || folder.name, depth });
      result.push(...flattenFolders(folder.children, depth + 1));
    }
    return result;
  };

  const flatFolders = folderTree ? flattenFolders(folderTree.roots) : [];

  return (
    <Card title="Folders" className="h-full flex flex-col">
      <div className="flex-1 overflow-y-auto">
        {isLoadingFolders ? (
          <div className="text-slate-400 text-sm p-2">Loading...</div>
        ) : folderTree && folderTree.roots.length > 0 ? (
          <div className="space-y-0.5 group">
            {folderTree.roots.map((folder) => renderFolderNode(folder))}
          </div>
        ) : (
          <div className="text-slate-400 text-sm p-2 text-center">
            No folders yet. Create one to organize your applications.
          </div>
        )}
      </div>

      {/* Create folder form */}
      {showCreateForm ? (
        <div className="mt-3 pt-3 border-t border-slate-700 space-y-3">
          <input
            type="text"
            placeholder="Folder name"
            value={newFolderName}
            onChange={(e) => setNewFolderName(e.target.value)}
            className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-slate-100 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
            autoFocus
          />

          <select
            value={newFolderParentId || ''}
            onChange={(e) => setNewFolderParentId(e.target.value || null)}
            className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-slate-100 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
          >
            <option value="">Root level</option>
            {flatFolders.map((f) => (
              <option key={f.id} value={f.id}>
                {'  '.repeat(f.depth)}{f.name}
              </option>
            ))}
          </select>

          <div className="flex gap-2">
            <Button
              variant="ghost"
              size="sm"
              className="flex-1"
              onClick={() => {
                setShowCreateForm(false);
                setNewFolderName('');
              }}
            >
              Cancel
            </Button>
            <Button
              variant="primary"
              size="sm"
              className="flex-1"
              onClick={handleCreateFolder}
              disabled={!newFolderName.trim() || createFolderMutation.isPending}
            >
              {createFolderMutation.isPending ? 'Creating...' : 'Create'}
            </Button>
          </div>
        </div>
      ) : (
        <Button
          variant="secondary"
          size="sm"
          className="mt-3 w-full"
          onClick={() => setShowCreateForm(true)}
        >
          <svg className="w-4 h-4 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
          </svg>
          New Folder
        </Button>
      )}

      {/* Assign applications modal */}
      {showAssignModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <Card className="w-96 max-h-[80vh] flex flex-col">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold text-white">Assign Applications</h3>
              <button
                onClick={() => {
                  setShowAssignModal(false);
                  setAssignToFolderId(null);
                }}
                className="text-slate-400 hover:text-slate-200"
              >
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            <div className="flex-1 overflow-y-auto space-y-1">
              {applications?.items.map((app: Application) => (
                <button
                  key={app.id}
                  onClick={() => moveAppMutation.mutate({ appId: app.id, folderId: assignToFolderId })}
                  disabled={moveAppMutation.isPending}
                  className="w-full flex items-center gap-2 px-3 py-2 text-left text-sm text-slate-300 hover:bg-slate-700 rounded-lg disabled:opacity-50"
                >
                  <svg className="w-4 h-4 text-slate-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                  </svg>
                  <span className="flex-1 truncate">{app.display_name || app.name}</span>
                  {app.environment && (
                    <span className="text-xs text-slate-500">{app.environment}</span>
                  )}
                </button>
              ))}
              {(!applications || applications.items.length === 0) && (
                <div className="text-slate-400 text-sm text-center py-4">
                  No applications found
                </div>
              )}
            </div>
          </Card>
        </div>
      )}
    </Card>
  );
}

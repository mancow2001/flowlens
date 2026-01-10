import { useState, useRef, useCallback } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import {
  MagnifyingGlassIcon,
  ArrowDownTrayIcon,
  ArrowUpTrayIcon,
  XMarkIcon,
} from '@heroicons/react/24/outline';
import Card from '../components/common/Card';
import Table from '../components/common/Table';
import Badge from '../components/common/Badge';
import Button from '../components/common/Button';
import { LoadingPage } from '../components/common/Loading';
import BulkActionToolbar from '../components/assets/BulkActionToolbar';
import ClassificationBadge from '../components/ml/ClassificationBadge';
import { assetApi, assetBulkApi, AssetImportPreview } from '../services/api';
import { formatRelativeTime } from '../utils/format';
import type { Asset, AssetType } from '../types';
import clsx from 'clsx';

const ASSET_TYPES: { value: AssetType | ''; label: string }[] = [
  { value: '', label: 'All Types' },
  { value: 'server', label: 'Server' },
  { value: 'database', label: 'Database' },
  { value: 'workstation', label: 'Workstation' },
  { value: 'load_balancer', label: 'Load Balancer' },
  { value: 'firewall', label: 'Firewall' },
  { value: 'router', label: 'Router' },
  { value: 'switch', label: 'Switch' },
  { value: 'storage', label: 'Storage' },
  { value: 'container', label: 'Container' },
  { value: 'virtual_machine', label: 'Virtual Machine' },
  { value: 'cloud_service', label: 'Cloud Service' },
  { value: 'unknown', label: 'Unknown' },
];

export default function Assets() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [assetType, setAssetType] = useState<AssetType | ''>('');
  const [isInternal, setIsInternal] = useState<boolean | undefined>(undefined);
  const [showImportModal, setShowImportModal] = useState(false);
  const [importFile, setImportFile] = useState<File | null>(null);
  const [importPreview, setImportPreview] = useState<AssetImportPreview | null>(null);
  const [importError, setImportError] = useState<string | null>(null);
  const [selectedAssets, setSelectedAssets] = useState<Set<string>>(new Set());

  const { data, isLoading } = useQuery({
    queryKey: ['assets', page, search, assetType, isInternal],
    queryFn: () =>
      assetApi.list({
        page,
        page_size: 20,
        search: search || undefined,
        asset_type: assetType || undefined,
        is_internal: isInternal,
      }),
    placeholderData: (prev) => prev,
  });

  const previewMutation = useMutation({
    mutationFn: (file: File) => assetBulkApi.previewImport(file),
    onSuccess: (data) => {
      setImportPreview(data);
      setImportError(null);
    },
    onError: (error: Error) => {
      setImportError(error.message);
      setImportPreview(null);
    },
  });

  const importMutation = useMutation({
    mutationFn: ({ file, skipErrors }: { file: File; skipErrors: boolean }) =>
      assetBulkApi.import(file, skipErrors),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ['assets'] });
      setShowImportModal(false);
      setImportFile(null);
      setImportPreview(null);
      alert(`Import complete: ${result.created} created, ${result.updated} updated, ${result.skipped} skipped, ${result.errors} errors`);
    },
    onError: (error: Error) => {
      setImportError(error.message);
    },
  });

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setImportFile(file);
      previewMutation.mutate(file);
    }
  };

  const handleImport = () => {
    if (importFile) {
      importMutation.mutate({ file: importFile, skipErrors: true });
    }
  };

  const handleExport = (format: 'csv' | 'json') => {
    const url = assetBulkApi.exportUrl(format, {
      assetType: assetType || undefined,
      isInternal,
    });
    window.open(url, '_blank');
  };

  // Selection handlers
  const handleSelectAll = useCallback(() => {
    if (!data?.items) return;
    const allIds = data.items.map((a) => a.id);
    const allSelected = allIds.every((id) => selectedAssets.has(id));

    if (allSelected) {
      // Deselect all on current page
      setSelectedAssets((prev) => {
        const next = new Set(prev);
        allIds.forEach((id) => next.delete(id));
        return next;
      });
    } else {
      // Select all on current page
      setSelectedAssets((prev) => {
        const next = new Set(prev);
        allIds.forEach((id) => next.add(id));
        return next;
      });
    }
  }, [data?.items, selectedAssets]);

  const handleSelectOne = useCallback((id: string) => {
    setSelectedAssets((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }, []);

  const clearSelection = useCallback(() => {
    setSelectedAssets(new Set());
  }, []);

  // Get a display character for the asset avatar
  // I = Internal, E = External
  const getAvatarChar = (asset: Asset): string => {
    return asset.is_internal ? 'I' : 'E';
  };

  // Check if all items on current page are selected
  const allPageSelected =
    data?.items && data.items.length > 0
      ? data.items.every((a) => selectedAssets.has(a.id))
      : false;

  const columns = [
    {
      key: 'checkbox',
      header: (
        <input
          type="checkbox"
          checked={allPageSelected}
          onChange={handleSelectAll}
          className="w-4 h-4 rounded border-slate-500 bg-slate-700 text-primary-600 focus:ring-primary-500 focus:ring-offset-0 cursor-pointer"
        />
      ),
      render: (asset: Asset) => (
        <input
          type="checkbox"
          checked={selectedAssets.has(asset.id)}
          onChange={(e) => {
            e.stopPropagation();
            handleSelectOne(asset.id);
          }}
          onClick={(e) => e.stopPropagation()}
          className="w-4 h-4 rounded border-slate-500 bg-slate-700 text-primary-600 focus:ring-primary-500 focus:ring-offset-0 cursor-pointer"
        />
      ),
      width: '40px',
    },
    {
      key: 'name',
      header: 'Name',
      render: (asset: Asset) => (
        <div className="flex items-center gap-3">
          <div
            className={clsx(
              'w-8 h-8 rounded-lg flex items-center justify-center text-white text-sm font-medium',
              asset.is_internal ? 'bg-green-600' : 'bg-orange-600'
            )}
          >
            {getAvatarChar(asset)}
          </div>
          <div>
            <div className="font-medium text-white">{asset.name}</div>
            {asset.hostname && (
              <div className="text-sm text-slate-400">{asset.hostname}</div>
            )}
          </div>
        </div>
      ),
    },
    {
      key: 'type',
      header: 'Type',
      render: (asset: Asset) => (
        <Badge>
          {asset.asset_type?.replace('_', ' ') ?? 'Unknown'}
        </Badge>
      ),
    },
    {
      key: 'ip_address',
      header: 'IP Address',
      render: (asset: Asset) => (
        <span className="font-mono text-slate-300">
          {asset.ip_address || '-'}
        </span>
      ),
    },
    {
      key: 'location',
      header: 'Location',
      render: (asset: Asset) => (
        <div className="flex items-center gap-2">
          <Badge variant={asset.is_internal ? 'success' : 'warning'}>
            {asset.is_internal ? 'Internal' : 'External'}
          </Badge>
          {asset.is_critical && <Badge variant="error">Critical</Badge>}
        </div>
      ),
    },
    {
      key: 'classification',
      header: 'Classification',
      render: (asset: Asset) => (
        <ClassificationBadge
          method={asset.classification_method}
          confidence={asset.classification_confidence}
        />
      ),
    },
    {
      key: 'last_seen',
      header: 'Last Seen',
      render: (asset: Asset) => (
        <span className="text-slate-400">
          {formatRelativeTime(asset.last_seen)}
        </span>
      ),
    },
  ];

  if (isLoading) {
    return <LoadingPage />;
  }

  const totalPages = Math.ceil((data?.total ?? 0) / 20);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Assets</h1>
          <p className="text-slate-400 mt-1">
            {data?.total ?? 0} assets discovered
          </p>
        </div>
        <div className="flex items-center gap-2">
          {/* Export dropdown */}
          <div className="relative group">
            <Button variant="secondary">
              <ArrowDownTrayIcon className="w-4 h-4 mr-2" />
              Export
            </Button>
            <div className="absolute right-0 mt-1 w-40 bg-slate-800 border border-slate-700 rounded-lg shadow-lg opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all z-10">
              <button
                onClick={() => handleExport('csv')}
                className="w-full px-4 py-2 text-left text-sm text-slate-200 hover:bg-slate-700 rounded-t-lg"
              >
                Export as CSV
              </button>
              <button
                onClick={() => handleExport('json')}
                className="w-full px-4 py-2 text-left text-sm text-slate-200 hover:bg-slate-700 rounded-b-lg"
              >
                Export as JSON
              </button>
            </div>
          </div>
          {/* Import button */}
          <Button variant="primary" onClick={() => setShowImportModal(true)}>
            <ArrowUpTrayIcon className="w-4 h-4 mr-2" />
            Import
          </Button>
        </div>
      </div>

      {/* Bulk Action Toolbar */}
      <BulkActionToolbar
        selectedIds={Array.from(selectedAssets)}
        onClear={clearSelection}
      />

      {/* Filters */}
      <Card>
        <div className="flex flex-wrap items-center gap-4">
          {/* Search */}
          <div className="flex-1 min-w-[200px] max-w-md">
            <div className="relative">
              <MagnifyingGlassIcon className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-400" />
              <input
                type="text"
                placeholder="Search by name, IP, hostname..."
                value={search}
                onChange={(e) => {
                  setSearch(e.target.value);
                  setPage(1);
                }}
                className="w-full pl-10 pr-4 py-2 bg-slate-700 border border-slate-600 rounded-lg text-slate-100 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-primary-500"
              />
            </div>
          </div>

          {/* Type filter */}
          <select
            value={assetType}
            onChange={(e) => {
              setAssetType(e.target.value as AssetType | '');
              setPage(1);
            }}
            className="px-4 py-2 bg-slate-700 border border-slate-600 rounded-lg text-slate-100 focus:outline-none focus:ring-2 focus:ring-primary-500"
          >
            {ASSET_TYPES.map((type) => (
              <option key={type.value} value={type.value}>
                {type.label}
              </option>
            ))}
          </select>

          {/* Location filter */}
          <select
            value={isInternal === undefined ? '' : isInternal.toString()}
            onChange={(e) => {
              const val = e.target.value;
              setIsInternal(val === '' ? undefined : val === 'true');
              setPage(1);
            }}
            className="px-4 py-2 bg-slate-700 border border-slate-600 rounded-lg text-slate-100 focus:outline-none focus:ring-2 focus:ring-primary-500"
          >
            <option value="">All Locations</option>
            <option value="true">Internal</option>
            <option value="false">External</option>
          </select>

          {/* Clear filters */}
          {(search || assetType || isInternal !== undefined) && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                setSearch('');
                setAssetType('');
                setIsInternal(undefined);
                setPage(1);
              }}
            >
              Clear Filters
            </Button>
          )}
        </div>
      </Card>

      {/* Assets Table */}
      <Card>
        <Table
          columns={columns}
          data={data?.items ?? []}
          keyExtractor={(item) => item.id}
          onRowClick={(asset) => navigate(`/assets/${asset.id}`)}
          emptyMessage="No assets found"
        />

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="flex items-center justify-between mt-4 pt-4 border-t border-slate-700">
            <div className="text-sm text-slate-400">
              Page {page} of {totalPages}
            </div>
            <div className="flex items-center gap-2">
              <Button
                variant="secondary"
                size="sm"
                disabled={page === 1}
                onClick={() => setPage(page - 1)}
              >
                Previous
              </Button>
              <Button
                variant="secondary"
                size="sm"
                disabled={page === totalPages}
                onClick={() => setPage(page + 1)}
              >
                Next
              </Button>
            </div>
          </div>
        )}
      </Card>

      {/* Import Modal */}
      {showImportModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <Card className="w-full max-w-2xl max-h-[80vh] overflow-y-auto">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold text-white">Import Assets</h2>
              <button
                onClick={() => {
                  setShowImportModal(false);
                  setImportFile(null);
                  setImportPreview(null);
                  setImportError(null);
                }}
                className="text-slate-400 hover:text-white"
              >
                <XMarkIcon className="w-5 h-5" />
              </button>
            </div>

            <div className="space-y-4">
              {/* File Upload */}
              <div>
                <label className="block text-sm text-slate-400 mb-2">
                  Upload CSV or JSON file
                </label>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".csv,.json"
                  onChange={handleFileSelect}
                  className="hidden"
                />
                <div
                  onClick={() => fileInputRef.current?.click()}
                  className="border-2 border-dashed border-slate-600 rounded-lg p-6 text-center cursor-pointer hover:border-primary-500 transition-colors"
                >
                  {importFile ? (
                    <div>
                      <p className="text-white font-medium">{importFile.name}</p>
                      <p className="text-sm text-slate-400 mt-1">
                        Click to choose a different file
                      </p>
                    </div>
                  ) : (
                    <div>
                      <ArrowUpTrayIcon className="w-8 h-8 mx-auto text-slate-400 mb-2" />
                      <p className="text-slate-300">
                        Click to upload or drag and drop
                      </p>
                      <p className="text-sm text-slate-400 mt-1">
                        CSV or JSON files only
                      </p>
                    </div>
                  )}
                </div>
              </div>

              {/* Error */}
              {importError && (
                <div className="p-3 bg-red-500/20 border border-red-500/50 rounded-lg text-red-400">
                  {importError}
                </div>
              )}

              {/* Preview */}
              {importPreview && (
                <div className="space-y-3">
                  <h3 className="text-white font-medium">Import Preview</h3>
                  <div className="grid grid-cols-4 gap-3">
                    <div className="p-3 bg-slate-700/50 rounded-lg text-center">
                      <div className="text-2xl font-bold text-white">
                        {importPreview.total_rows}
                      </div>
                      <div className="text-xs text-slate-400">Total Rows</div>
                    </div>
                    <div className="p-3 bg-green-500/20 rounded-lg text-center">
                      <div className="text-2xl font-bold text-green-400">
                        {importPreview.to_create}
                      </div>
                      <div className="text-xs text-slate-400">New Assets</div>
                    </div>
                    <div className="p-3 bg-blue-500/20 rounded-lg text-center">
                      <div className="text-2xl font-bold text-blue-400">
                        {importPreview.to_update}
                      </div>
                      <div className="text-xs text-slate-400">Updates</div>
                    </div>
                    <div className="p-3 bg-red-500/20 rounded-lg text-center">
                      <div className="text-2xl font-bold text-red-400">
                        {importPreview.errors}
                      </div>
                      <div className="text-xs text-slate-400">Errors</div>
                    </div>
                  </div>

                  {/* Validation details */}
                  {importPreview.validations.length > 0 && (
                    <div className="max-h-48 overflow-y-auto border border-slate-700 rounded-lg">
                      <table className="w-full text-sm">
                        <thead className="bg-slate-700/50 sticky top-0">
                          <tr className="text-left text-slate-400">
                            <th className="px-3 py-2">Row</th>
                            <th className="px-3 py-2">IP Address</th>
                            <th className="px-3 py-2">Status</th>
                            <th className="px-3 py-2">Details</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-700">
                          {importPreview.validations.slice(0, 50).map((v) => (
                            <tr key={v.row_number} className="text-slate-300">
                              <td className="px-3 py-2">{v.row_number}</td>
                              <td className="px-3 py-2 font-mono">{v.ip_address || '-'}</td>
                              <td className="px-3 py-2">
                                <Badge
                                  variant={
                                    v.status === 'create'
                                      ? 'success'
                                      : v.status === 'update'
                                      ? 'info'
                                      : v.status === 'error'
                                      ? 'error'
                                      : 'default'
                                  }
                                >
                                  {v.status}
                                </Badge>
                              </td>
                              <td className="px-3 py-2 text-slate-400">{v.message}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                      {importPreview.validations.length > 50 && (
                        <p className="px-3 py-2 text-slate-400 text-sm text-center">
                          ... and {importPreview.validations.length - 50} more rows
                        </p>
                      )}
                    </div>
                  )}
                </div>
              )}

              {/* Actions */}
              <div className="flex justify-end gap-2 pt-4 border-t border-slate-700">
                <Button
                  variant="ghost"
                  onClick={() => {
                    setShowImportModal(false);
                    setImportFile(null);
                    setImportPreview(null);
                    setImportError(null);
                  }}
                >
                  Cancel
                </Button>
                <Button
                  variant="primary"
                  disabled={!importPreview || importMutation.isPending}
                  onClick={handleImport}
                >
                  {importMutation.isPending ? 'Importing...' : 'Import Assets'}
                </Button>
              </div>
            </div>
          </Card>
        </div>
      )}
    </div>
  );
}

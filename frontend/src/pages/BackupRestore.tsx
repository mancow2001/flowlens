import { useState, useRef } from 'react';
import { useMutation } from '@tanstack/react-query';
import {
  ArrowDownTrayIcon,
  ArrowUpTrayIcon,
  ExclamationTriangleIcon,
  CheckCircleIcon,
  XCircleIcon,
  DocumentArrowDownIcon,
  ServerStackIcon,
  CircleStackIcon,
} from '@heroicons/react/24/outline';
import Card from '../components/common/Card';
import Button from '../components/common/Button';
import { backupApi, downloadWithAuth, BackupPreview, RestoreResponse, BackupType } from '../services/api';

export default function BackupRestore() {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<BackupPreview | null>(null);
  const [restoreResult, setRestoreResult] = useState<RestoreResponse | null>(null);
  const [showConfirmDialog, setShowConfirmDialog] = useState(false);
  const [downloadingConfig, setDownloadingConfig] = useState(false);
  const [downloadingFull, setDownloadingFull] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Preview mutation
  const previewMutation = useMutation({
    mutationFn: (file: File) => backupApi.previewRestore(file),
    onSuccess: (data) => {
      setPreview(data);
      setRestoreResult(null);
    },
    onError: (error: Error & { response?: { data?: { detail?: string } } }) => {
      alert(`Preview failed: ${error.response?.data?.detail || error.message}`);
    },
  });

  // Restore mutation
  const restoreMutation = useMutation({
    mutationFn: (file: File) => backupApi.restore(file, true),
    onSuccess: (data) => {
      setRestoreResult(data);
      setShowConfirmDialog(false);
      setPreview(null);
      setSelectedFile(null);
    },
    onError: (error: Error & { response?: { data?: { detail?: string } } }) => {
      alert(`Restore failed: ${error.response?.data?.detail || error.message}`);
      setShowConfirmDialog(false);
    },
  });

  const handleFileSelect = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (file) {
      setSelectedFile(file);
      setPreview(null);
      setRestoreResult(null);
      previewMutation.mutate(file);
    }
  };

  const handleDownload = async (backupType: BackupType) => {
    const setDownloading = backupType === 'configuration' ? setDownloadingConfig : setDownloadingFull;
    setDownloading(true);
    try {
      const url = backupApi.downloadUrl(backupType);
      const filename = `flowlens_backup_${backupType}_${new Date().toISOString().slice(0, 10)}.json.gz`;
      await downloadWithAuth(url, filename);
    } catch (error) {
      console.error('Download failed:', error);
      alert('Failed to download backup. Please try again.');
    } finally {
      setDownloading(false);
    }
  };

  const handleRestore = () => {
    if (selectedFile) {
      restoreMutation.mutate(selectedFile);
    }
  };

  const formatBytes = (bytes: number): string => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(2)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
  };

  const totalRows = preview
    ? Object.values(preview.table_counts).reduce((a, b) => a + b, 0)
    : 0;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-white">Backup & Restore</h1>
        <p className="text-slate-400 mt-1">
          Create backups of your FlowLens configuration and data, or restore from a previous backup.
        </p>
      </div>

      {/* Backup Section */}
      <Card>
        <div className="p-6">
          <h2 className="text-xl font-semibold text-white mb-4 flex items-center gap-2">
            <ArrowDownTrayIcon className="w-6 h-6" />
            Create Backup
          </h2>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* Configuration Backup */}
            <div className="bg-slate-700/50 rounded-lg p-6">
              <div className="flex items-center gap-3 mb-4">
                <ServerStackIcon className="w-8 h-8 text-primary-400" />
                <div>
                  <h3 className="text-lg font-medium text-white">Configuration + Assets</h3>
                  <p className="text-sm text-slate-400">Recommended for most use cases</p>
                </div>
              </div>
              <p className="text-slate-300 text-sm mb-4">
                Includes alert rules, classification rules, applications, segmentation policies,
                saved views, settings, assets, dependencies, and services.
              </p>
              <Button
                onClick={() => handleDownload('configuration')}
                loading={downloadingConfig}
                className="w-full flex items-center justify-center gap-2"
              >
                <DocumentArrowDownIcon className="w-5 h-5" />
                Download Configuration Backup
              </Button>
            </div>

            {/* Full Backup */}
            <div className="bg-slate-700/50 rounded-lg p-6">
              <div className="flex items-center gap-3 mb-4">
                <CircleStackIcon className="w-8 h-8 text-yellow-400" />
                <div>
                  <h3 className="text-lg font-medium text-white">Full Database</h3>
                  <p className="text-sm text-slate-400">Complete backup including flow data</p>
                </div>
              </div>
              <p className="text-slate-300 text-sm mb-4">
                Includes everything above plus flow_records and flow_aggregates.
                This may result in a very large file.
              </p>
              <Button
                variant="secondary"
                onClick={() => handleDownload('full')}
                loading={downloadingFull}
                className="w-full flex items-center justify-center gap-2"
              >
                <DocumentArrowDownIcon className="w-5 h-5" />
                Download Full Backup
              </Button>
            </div>
          </div>
        </div>
      </Card>

      {/* Restore Section */}
      <Card>
        <div className="p-6">
          <h2 className="text-xl font-semibold text-white mb-4 flex items-center gap-2">
            <ArrowUpTrayIcon className="w-6 h-6" />
            Restore from Backup
          </h2>

          <div className="bg-yellow-500/20 border border-yellow-500/50 rounded-lg p-4 mb-6">
            <div className="flex gap-3">
              <ExclamationTriangleIcon className="w-6 h-6 text-yellow-400 flex-shrink-0" />
              <div>
                <p className="text-yellow-400 font-medium">Warning: Destructive Operation</p>
                <p className="text-yellow-400/80 text-sm">
                  Restoring from a backup will replace ALL existing data. This operation cannot be undone.
                  Create a backup of current data before proceeding.
                </p>
              </div>
            </div>
          </div>

          <div className="space-y-4">
            <div>
              <input
                ref={fileInputRef}
                type="file"
                accept=".gz,.json"
                onChange={handleFileSelect}
                className="hidden"
              />
              <Button
                variant="secondary"
                onClick={() => fileInputRef.current?.click()}
                className="flex items-center gap-2"
              >
                <ArrowUpTrayIcon className="w-5 h-5" />
                Select Backup File
              </Button>
              {selectedFile && (
                <p className="mt-2 text-sm text-slate-400">
                  Selected: {selectedFile.name} ({formatBytes(selectedFile.size)})
                </p>
              )}
            </div>

            {/* Preview Loading */}
            {previewMutation.isPending && (
              <div className="text-slate-400">Analyzing backup file...</div>
            )}

            {/* Preview */}
            {preview && (
              <div className="bg-slate-700/50 rounded-lg p-4 space-y-4">
                <h3 className="font-medium text-white">Backup Preview</h3>

                <div className="grid grid-cols-2 gap-4 text-sm">
                  <div>
                    <span className="text-slate-400">Backup Type:</span>
                    <span className="ml-2 text-white capitalize">{preview.backup_type}</span>
                  </div>
                  <div>
                    <span className="text-slate-400">Created:</span>
                    <span className="ml-2 text-white">
                      {new Date(preview.backup_created_at).toLocaleString()}
                    </span>
                  </div>
                  <div>
                    <span className="text-slate-400">App Version (Backup):</span>
                    <span className="ml-2 text-white">{preview.app_version_backup}</span>
                  </div>
                  <div>
                    <span className="text-slate-400">App Version (Current):</span>
                    <span className="ml-2 text-white">{preview.app_version_current}</span>
                  </div>
                </div>

                {preview.warnings.length > 0 && (
                  <div className="bg-yellow-500/20 border border-yellow-500/50 rounded p-3">
                    {preview.warnings.map((warning, idx) => (
                      <p key={idx} className="text-yellow-400 text-sm">{warning}</p>
                    ))}
                  </div>
                )}

                <div>
                  <p className="text-slate-400 text-sm mb-2">
                    Tables to restore ({Object.keys(preview.table_counts).length} tables, {totalRows.toLocaleString()} total rows):
                  </p>
                  <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 text-sm max-h-48 overflow-y-auto">
                    {Object.entries(preview.table_counts)
                      .sort(([, a], [, b]) => b - a)
                      .map(([table, count]) => (
                        <div key={table} className="text-slate-300">
                          {table}: <span className="text-white">{count.toLocaleString()}</span>
                        </div>
                      ))}
                  </div>
                </div>

                <Button
                  variant="danger"
                  onClick={() => setShowConfirmDialog(true)}
                  disabled={!preview.is_compatible}
                  className="flex items-center gap-2"
                >
                  <ExclamationTriangleIcon className="w-5 h-5" />
                  Restore from Backup
                </Button>
                {!preview.is_compatible && (
                  <p className="text-red-400 text-sm">
                    This backup is not compatible with the current version.
                  </p>
                )}
              </div>
            )}

            {/* Restore Result */}
            {restoreResult && (
              <div
                className={`rounded-lg p-4 ${
                  restoreResult.success
                    ? 'bg-green-500/20 border border-green-500/50'
                    : 'bg-red-500/20 border border-red-500/50'
                }`}
              >
                <div className="flex items-center gap-2 mb-2">
                  {restoreResult.success ? (
                    <CheckCircleIcon className="w-6 h-6 text-green-400" />
                  ) : (
                    <XCircleIcon className="w-6 h-6 text-red-400" />
                  )}
                  <span className={restoreResult.success ? 'text-green-400' : 'text-red-400'}>
                    {restoreResult.message}
                  </span>
                </div>
                {restoreResult.success && (
                  <p className="text-sm text-slate-300">
                    Restored {Object.values(restoreResult.rows_restored).reduce((a, b) => a + b, 0).toLocaleString()} rows
                    across {restoreResult.tables_restored.length} tables.
                  </p>
                )}
                {restoreResult.errors.length > 0 && (
                  <div className="mt-2">
                    <p className="text-sm text-red-400 font-medium">Errors:</p>
                    <ul className="text-sm text-red-300 list-disc list-inside">
                      {restoreResult.errors.map((err, idx) => (
                        <li key={idx}>{err}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </Card>

      {/* Confirmation Dialog */}
      {showConfirmDialog && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-slate-800 rounded-lg p-6 max-w-md w-full mx-4 border border-slate-700">
            <h3 className="text-lg font-semibold text-white mb-4">Confirm Restore</h3>
            <p className="text-slate-300 mb-6">
              This will permanently delete all existing data and replace it with the backup.
              Are you absolutely sure you want to proceed?
            </p>
            <div className="flex gap-4 justify-end">
              <Button variant="secondary" onClick={() => setShowConfirmDialog(false)}>
                Cancel
              </Button>
              <Button
                variant="danger"
                onClick={handleRestore}
                loading={restoreMutation.isPending}
              >
                Yes, Restore Now
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

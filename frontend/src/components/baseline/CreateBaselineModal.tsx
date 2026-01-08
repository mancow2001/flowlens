import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { XMarkIcon } from '@heroicons/react/24/outline';
import { baselineApi } from '../../services/api';

interface CreateBaselineModalProps {
  isOpen: boolean;
  onClose: () => void;
  applicationId: string;
  hopDepth: number;
}

export default function CreateBaselineModal({
  isOpen,
  onClose,
  applicationId,
  hopDepth,
}: CreateBaselineModalProps) {
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [includePositions, setIncludePositions] = useState(true);
  const queryClient = useQueryClient();

  const createMutation = useMutation({
    mutationFn: () =>
      baselineApi.create(applicationId, {
        name,
        description: description || undefined,
        hop_depth: hopDepth,
        include_positions: includePositions,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['baselines', applicationId] });
      handleClose();
    },
  });

  const handleClose = () => {
    setName('');
    setDescription('');
    setIncludePositions(true);
    onClose();
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (name.trim()) {
      createMutation.mutate();
    }
  };

  // Generate default name based on current date/time
  const generateDefaultName = () => {
    const now = new Date();
    const dateStr = now.toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    });
    const timeStr = now.toLocaleTimeString('en-US', {
      hour: 'numeric',
      minute: '2-digit',
      hour12: true,
    });
    setName(`Baseline - ${dateStr} ${timeStr}`);
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={handleClose}
      />

      {/* Modal */}
      <div className="relative bg-slate-800 rounded-lg shadow-xl w-full max-w-md mx-4">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-700">
          <h2 className="text-lg font-semibold text-white">Create Baseline</h2>
          <button
            onClick={handleClose}
            className="text-slate-400 hover:text-white transition-colors"
          >
            <XMarkIcon className="h-5 w-5" />
          </button>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit}>
          <div className="px-6 py-4 space-y-4">
            {/* Name input */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <label className="block text-sm font-medium text-slate-300">
                  Baseline Name
                </label>
                <button
                  type="button"
                  onClick={generateDefaultName}
                  className="text-xs text-blue-400 hover:text-blue-300"
                >
                  Auto-generate
                </button>
              </div>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Enter baseline name..."
                className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                autoFocus
              />
            </div>

            {/* Description input */}
            <div>
              <label className="block text-sm font-medium text-slate-300 mb-2">
                Description (optional)
              </label>
              <textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Describe what this baseline captures..."
                rows={3}
                className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent resize-none"
              />
            </div>

            {/* Include positions toggle */}
            <label className="flex items-center gap-3 cursor-pointer">
              <input
                type="checkbox"
                checked={includePositions}
                onChange={(e) => setIncludePositions(e.target.checked)}
                className="w-4 h-4 rounded border-slate-600 bg-slate-700 text-blue-500 focus:ring-blue-500 focus:ring-offset-slate-800"
              />
              <div>
                <span className="text-sm text-slate-300">Include node positions</span>
                <p className="text-xs text-slate-500">
                  Save current layout positions with this baseline
                </p>
              </div>
            </label>

            {/* Info box */}
            <div className="bg-slate-900/50 rounded-lg p-3 text-sm text-slate-400">
              <p>This baseline will capture:</p>
              <ul className="list-disc list-inside mt-1 space-y-0.5 text-slate-500">
                <li>All application members</li>
                <li>Dependencies and connections</li>
                <li>Entry points configuration</li>
                <li>Traffic volumes (last 24h)</li>
                {includePositions && <li>Current layout positions</li>}
              </ul>
            </div>
          </div>

          {/* Footer */}
          <div className="flex justify-end gap-3 px-6 py-4 border-t border-slate-700">
            <button
              type="button"
              onClick={handleClose}
              className="px-4 py-2 text-sm font-medium text-slate-300 hover:text-white transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={!name.trim() || createMutation.isPending}
              className="px-4 py-2 text-sm font-medium bg-blue-600 text-white rounded-lg hover:bg-blue-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {createMutation.isPending ? 'Creating...' : 'Create Baseline'}
            </button>
          </div>

          {/* Error message */}
          {createMutation.isError && (
            <div className="px-6 pb-4">
              <p className="text-sm text-red-400">
                Failed to create baseline. Please try again.
              </p>
            </div>
          )}
        </form>
      </div>
    </div>
  );
}

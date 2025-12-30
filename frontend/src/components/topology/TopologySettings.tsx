/**
 * Topology Performance Settings Component
 * Allows users to configure rendering quality and layout options
 */

import { Fragment, useState } from 'react';
import { Dialog, Transition, RadioGroup, Switch } from '@headlessui/react';
import type { LayoutType } from '../../utils/graphLayouts';

export type RenderMode = 'auto' | 'svg' | 'canvas';
export type PerformanceMode = 'auto' | 'quality' | 'performance';

export interface TopologySettings {
  renderMode: RenderMode;
  performanceMode: PerformanceMode;
  layoutType: LayoutType | 'force';
  showLabels: boolean;
  showEdgeLabels: boolean;
  animateLayout: boolean;
  maxVisibleNodes: number;
  maxVisibleEdges: number;
}

export const DEFAULT_SETTINGS: TopologySettings = {
  renderMode: 'auto',
  performanceMode: 'auto',
  layoutType: 'force',
  showLabels: true,
  showEdgeLabels: true,
  animateLayout: true,
  maxVisibleNodes: 1000,
  maxVisibleEdges: 2000,
};

interface TopologySettingsDialogProps {
  isOpen: boolean;
  onClose: () => void;
  settings: TopologySettings;
  onSettingsChange: (settings: TopologySettings) => void;
  nodeCount: number;
  edgeCount: number;
}

const RENDER_MODES: { value: RenderMode; label: string; description: string }[] = [
  { value: 'auto', label: 'Auto', description: 'Automatically choose based on graph size' },
  { value: 'svg', label: 'SVG', description: 'Best quality, slower for large graphs' },
  { value: 'canvas', label: 'Canvas', description: 'Faster rendering, recommended for 200+ nodes' },
];

const PERFORMANCE_MODES: { value: PerformanceMode; label: string; description: string }[] = [
  { value: 'auto', label: 'Auto', description: 'Balance quality and performance' },
  { value: 'quality', label: 'Quality', description: 'Full detail, may be slow with many nodes' },
  { value: 'performance', label: 'Performance', description: 'Optimized for speed, reduced detail when zoomed out' },
];

const LAYOUT_TYPES: { value: LayoutType | 'force'; label: string; description: string }[] = [
  { value: 'force', label: 'Force-Directed', description: 'Physics simulation (interactive)' },
  { value: 'hierarchical', label: 'Hierarchical', description: 'Top-down tree layout' },
  { value: 'radial', label: 'Radial', description: 'Circular layers from center' },
  { value: 'circular', label: 'Circular', description: 'All nodes on a circle' },
  { value: 'grid', label: 'Grid', description: 'Simple grid arrangement' },
  { value: 'internal-external', label: 'Int/Ext Split', description: 'Internal nodes center, external outer' },
];

export default function TopologySettingsDialog({
  isOpen,
  onClose,
  settings,
  onSettingsChange,
  nodeCount,
  edgeCount,
}: TopologySettingsDialogProps) {
  const [localSettings, setLocalSettings] = useState(settings);

  const handleSave = () => {
    onSettingsChange(localSettings);
    onClose();
  };

  const handleReset = () => {
    setLocalSettings(DEFAULT_SETTINGS);
  };

  const isLargeGraph = nodeCount > 200 || edgeCount > 500;

  return (
    <Transition appear show={isOpen} as={Fragment}>
      <Dialog as="div" className="relative z-50" onClose={onClose}>
        <Transition.Child
          as={Fragment}
          enter="ease-out duration-200"
          enterFrom="opacity-0"
          enterTo="opacity-100"
          leave="ease-in duration-150"
          leaveFrom="opacity-100"
          leaveTo="opacity-0"
        >
          <div className="fixed inset-0 bg-black/50" />
        </Transition.Child>

        <div className="fixed inset-0 overflow-y-auto">
          <div className="flex min-h-full items-center justify-center p-4">
            <Transition.Child
              as={Fragment}
              enter="ease-out duration-200"
              enterFrom="opacity-0 scale-95"
              enterTo="opacity-100 scale-100"
              leave="ease-in duration-150"
              leaveFrom="opacity-100 scale-100"
              leaveTo="opacity-0 scale-95"
            >
              <Dialog.Panel className="w-full max-w-lg transform rounded-lg bg-slate-800 p-6 shadow-xl transition-all">
                <Dialog.Title className="text-lg font-semibold text-slate-100 mb-4">
                  Topology Settings
                </Dialog.Title>

                {/* Graph stats */}
                <div className="mb-4 p-3 rounded bg-slate-700/50 text-sm">
                  <div className="flex justify-between text-slate-300">
                    <span>Current graph:</span>
                    <span className={isLargeGraph ? 'text-amber-400' : 'text-green-400'}>
                      {nodeCount} nodes, {edgeCount} edges
                    </span>
                  </div>
                  {isLargeGraph && (
                    <p className="mt-1 text-amber-400 text-xs">
                      Large graph detected. Canvas rendering recommended.
                    </p>
                  )}
                </div>

                {/* Render Mode */}
                <div className="mb-6">
                  <label className="block text-sm font-medium text-slate-300 mb-2">
                    Render Mode
                  </label>
                  <RadioGroup
                    value={localSettings.renderMode}
                    onChange={(value: RenderMode) =>
                      setLocalSettings((s: TopologySettings) => ({ ...s, renderMode: value }))
                    }
                    className="space-y-2"
                  >
                    {RENDER_MODES.map(mode => (
                      <RadioGroup.Option
                        key={mode.value}
                        value={mode.value}
                        className={({ checked }: { checked: boolean }) =>
                          `${checked ? 'bg-blue-600/20 border-blue-500' : 'bg-slate-700/30 border-slate-600'}
                          relative flex cursor-pointer rounded-lg border p-3 focus:outline-none`
                        }
                      >
                        {({ checked }: { checked: boolean }) => (
                          <div className="flex w-full items-center justify-between">
                            <div className="flex items-center">
                              <div className="text-sm">
                                <RadioGroup.Label
                                  as="p"
                                  className={`font-medium ${checked ? 'text-blue-400' : 'text-slate-200'}`}
                                >
                                  {mode.label}
                                </RadioGroup.Label>
                                <RadioGroup.Description
                                  as="span"
                                  className="text-xs text-slate-400"
                                >
                                  {mode.description}
                                </RadioGroup.Description>
                              </div>
                            </div>
                            {checked && (
                              <div className="shrink-0 text-blue-400">
                                <svg className="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
                                  <path
                                    fillRule="evenodd"
                                    d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.857-9.809a.75.75 0 00-1.214-.882l-3.483 4.79-1.88-1.88a.75.75 0 10-1.06 1.061l2.5 2.5a.75.75 0 001.137-.089l4-5.5z"
                                    clipRule="evenodd"
                                  />
                                </svg>
                              </div>
                            )}
                          </div>
                        )}
                      </RadioGroup.Option>
                    ))}
                  </RadioGroup>
                </div>

                {/* Performance Mode */}
                <div className="mb-6">
                  <label className="block text-sm font-medium text-slate-300 mb-2">
                    Performance Mode
                  </label>
                  <RadioGroup
                    value={localSettings.performanceMode}
                    onChange={(value: PerformanceMode) =>
                      setLocalSettings((s: TopologySettings) => ({ ...s, performanceMode: value }))
                    }
                    className="space-y-2"
                  >
                    {PERFORMANCE_MODES.map(mode => (
                      <RadioGroup.Option
                        key={mode.value}
                        value={mode.value}
                        className={({ checked }: { checked: boolean }) =>
                          `${checked ? 'bg-blue-600/20 border-blue-500' : 'bg-slate-700/30 border-slate-600'}
                          relative flex cursor-pointer rounded-lg border p-3 focus:outline-none`
                        }
                      >
                        {({ checked }: { checked: boolean }) => (
                          <div className="flex w-full items-center justify-between">
                            <div className="text-sm">
                              <RadioGroup.Label
                                as="p"
                                className={`font-medium ${checked ? 'text-blue-400' : 'text-slate-200'}`}
                              >
                                {mode.label}
                              </RadioGroup.Label>
                              <RadioGroup.Description
                                as="span"
                                className="text-xs text-slate-400"
                              >
                                {mode.description}
                              </RadioGroup.Description>
                            </div>
                            {checked && (
                              <div className="shrink-0 text-blue-400">
                                <svg className="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
                                  <path
                                    fillRule="evenodd"
                                    d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.857-9.809a.75.75 0 00-1.214-.882l-3.483 4.79-1.88-1.88a.75.75 0 10-1.06 1.061l2.5 2.5a.75.75 0 001.137-.089l4-5.5z"
                                    clipRule="evenodd"
                                  />
                                </svg>
                              </div>
                            )}
                          </div>
                        )}
                      </RadioGroup.Option>
                    ))}
                  </RadioGroup>
                </div>

                {/* Layout Type */}
                <div className="mb-6">
                  <label className="block text-sm font-medium text-slate-300 mb-2">
                    Layout Algorithm
                  </label>
                  <select
                    value={localSettings.layoutType}
                    onChange={e =>
                      setLocalSettings((s: TopologySettings) => ({
                        ...s,
                        layoutType: e.target.value as LayoutType | 'force',
                      }))
                    }
                    className="w-full px-3 py-2 rounded bg-slate-700 border border-slate-600 text-slate-200 focus:outline-none focus:border-blue-500"
                  >
                    {LAYOUT_TYPES.map(layout => (
                      <option key={layout.value} value={layout.value}>
                        {layout.label} - {layout.description}
                      </option>
                    ))}
                  </select>
                  {localSettings.layoutType !== 'force' && (
                    <p className="mt-1 text-xs text-slate-400">
                      Static layouts are instant but non-interactive
                    </p>
                  )}
                </div>

                {/* Toggle Options */}
                <div className="space-y-4 mb-6">
                  <Switch.Group>
                    <div className="flex items-center justify-between">
                      <Switch.Label className="text-sm text-slate-300">
                        Show node labels
                      </Switch.Label>
                      <Switch
                        checked={localSettings.showLabels}
                        onChange={(checked: boolean) =>
                          setLocalSettings((s: TopologySettings) => ({ ...s, showLabels: checked }))
                        }
                        className={`${localSettings.showLabels ? 'bg-blue-600' : 'bg-slate-600'}
                          relative inline-flex h-6 w-11 items-center rounded-full transition-colors`}
                      >
                        <span
                          className={`${localSettings.showLabels ? 'translate-x-6' : 'translate-x-1'}
                            inline-block h-4 w-4 transform rounded-full bg-white transition-transform`}
                        />
                      </Switch>
                    </div>
                  </Switch.Group>

                  <Switch.Group>
                    <div className="flex items-center justify-between">
                      <Switch.Label className="text-sm text-slate-300">
                        Show edge labels (ports)
                      </Switch.Label>
                      <Switch
                        checked={localSettings.showEdgeLabels}
                        onChange={(checked: boolean) =>
                          setLocalSettings((s: TopologySettings) => ({ ...s, showEdgeLabels: checked }))
                        }
                        className={`${localSettings.showEdgeLabels ? 'bg-blue-600' : 'bg-slate-600'}
                          relative inline-flex h-6 w-11 items-center rounded-full transition-colors`}
                      >
                        <span
                          className={`${localSettings.showEdgeLabels ? 'translate-x-6' : 'translate-x-1'}
                            inline-block h-4 w-4 transform rounded-full bg-white transition-transform`}
                        />
                      </Switch>
                    </div>
                  </Switch.Group>

                  <Switch.Group>
                    <div className="flex items-center justify-between">
                      <Switch.Label className="text-sm text-slate-300">
                        Animate layout changes
                      </Switch.Label>
                      <Switch
                        checked={localSettings.animateLayout}
                        onChange={(checked: boolean) =>
                          setLocalSettings((s: TopologySettings) => ({ ...s, animateLayout: checked }))
                        }
                        className={`${localSettings.animateLayout ? 'bg-blue-600' : 'bg-slate-600'}
                          relative inline-flex h-6 w-11 items-center rounded-full transition-colors`}
                      >
                        <span
                          className={`${localSettings.animateLayout ? 'translate-x-6' : 'translate-x-1'}
                            inline-block h-4 w-4 transform rounded-full bg-white transition-transform`}
                        />
                      </Switch>
                    </div>
                  </Switch.Group>
                </div>

                {/* Buttons */}
                <div className="flex justify-between">
                  <button
                    onClick={handleReset}
                    className="px-4 py-2 text-sm text-slate-400 hover:text-slate-200 transition-colors"
                  >
                    Reset to defaults
                  </button>
                  <div className="space-x-3">
                    <button
                      onClick={onClose}
                      className="px-4 py-2 text-sm bg-slate-700 text-slate-200 rounded hover:bg-slate-600 transition-colors"
                    >
                      Cancel
                    </button>
                    <button
                      onClick={handleSave}
                      className="px-4 py-2 text-sm bg-blue-600 text-white rounded hover:bg-blue-500 transition-colors"
                    >
                      Apply
                    </button>
                  </div>
                </div>
              </Dialog.Panel>
            </Transition.Child>
          </div>
        </div>
      </Dialog>
    </Transition>
  );
}

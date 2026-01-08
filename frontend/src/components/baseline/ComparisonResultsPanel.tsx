import { useState } from 'react';
import {
  PlusCircleIcon,
  MinusCircleIcon,
  ArrowTrendingUpIcon,
  ChevronDownIcon,
  ChevronRightIcon,
} from '@heroicons/react/24/outline';
import type { BaselineComparisonResult } from '../../types';
import { getProtocolName } from '../../utils/network';

interface ComparisonResultsPanelProps {
  result: BaselineComparisonResult;
}

type ChangeCategory = 'dependencies' | 'entryPoints' | 'members' | 'traffic';

export default function ComparisonResultsPanel({ result }: ComparisonResultsPanelProps) {
  const [expandedCategories, setExpandedCategories] = useState<Set<ChangeCategory>>(
    new Set(['dependencies'])
  );

  const toggleCategory = (category: ChangeCategory) => {
    setExpandedCategories((prev) => {
      const next = new Set(prev);
      if (next.has(category)) {
        next.delete(category);
      } else {
        next.add(category);
      }
      return next;
    });
  };

  const hasDepChanges =
    result.dependencies_added.length > 0 || result.dependencies_removed.length > 0;
  const hasEpChanges =
    result.entry_points_added.length > 0 || result.entry_points_removed.length > 0;
  const hasMemberChanges =
    result.members_added.length > 0 || result.members_removed.length > 0;
  const hasTrafficChanges = result.traffic_deviations.length > 0;

  return (
    <div className="mt-3 space-y-2">
      {/* Dependencies */}
      {hasDepChanges && (
        <div className="bg-slate-900/50 rounded overflow-hidden">
          <button
            onClick={() => toggleCategory('dependencies')}
            className="w-full flex items-center justify-between px-3 py-2 hover:bg-slate-700/50 transition-colors"
          >
            <div className="flex items-center gap-2">
              {expandedCategories.has('dependencies') ? (
                <ChevronDownIcon className="h-4 w-4 text-slate-400" />
              ) : (
                <ChevronRightIcon className="h-4 w-4 text-slate-400" />
              )}
              <span className="text-sm text-slate-300">Dependencies</span>
            </div>
            <span className="text-xs text-slate-500">
              {result.dependencies_added.length + result.dependencies_removed.length}
            </span>
          </button>

          {expandedCategories.has('dependencies') && (
            <div className="px-3 pb-2 space-y-1">
              {result.dependencies_added.map((dep) => (
                <div
                  key={dep.id}
                  className="flex items-center gap-2 text-xs py-1 px-2 bg-green-500/10 rounded"
                >
                  <PlusCircleIcon className="h-3.5 w-3.5 text-green-400 flex-shrink-0" />
                  <span className="text-green-300 truncate">
                    {dep.source_name || dep.source_asset_id.slice(0, 8)} →{' '}
                    {dep.target_name || dep.target_asset_id.slice(0, 8)}
                    <span className="text-green-400/70 ml-1">
                      :{dep.target_port}/{getProtocolName(dep.protocol)}
                    </span>
                  </span>
                </div>
              ))}
              {result.dependencies_removed.map((dep) => (
                <div
                  key={dep.id}
                  className="flex items-center gap-2 text-xs py-1 px-2 bg-red-500/10 rounded"
                >
                  <MinusCircleIcon className="h-3.5 w-3.5 text-red-400 flex-shrink-0" />
                  <span className="text-red-300 truncate">
                    {dep.source_name || dep.source_asset_id.slice(0, 8)} →{' '}
                    {dep.target_name || dep.target_asset_id.slice(0, 8)}
                    <span className="text-red-400/70 ml-1">
                      :{dep.target_port}/{getProtocolName(dep.protocol)}
                    </span>
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Entry Points */}
      {hasEpChanges && (
        <div className="bg-slate-900/50 rounded overflow-hidden">
          <button
            onClick={() => toggleCategory('entryPoints')}
            className="w-full flex items-center justify-between px-3 py-2 hover:bg-slate-700/50 transition-colors"
          >
            <div className="flex items-center gap-2">
              {expandedCategories.has('entryPoints') ? (
                <ChevronDownIcon className="h-4 w-4 text-slate-400" />
              ) : (
                <ChevronRightIcon className="h-4 w-4 text-slate-400" />
              )}
              <span className="text-sm text-slate-300">Entry Points</span>
            </div>
            <span className="text-xs text-slate-500">
              {result.entry_points_added.length + result.entry_points_removed.length}
            </span>
          </button>

          {expandedCategories.has('entryPoints') && (
            <div className="px-3 pb-2 space-y-1">
              {result.entry_points_added.map((ep, i) => (
                <div
                  key={`ep-add-${i}`}
                  className="flex items-center gap-2 text-xs py-1 px-2 bg-green-500/10 rounded"
                >
                  <PlusCircleIcon className="h-3.5 w-3.5 text-green-400 flex-shrink-0" />
                  <span className="text-green-300 truncate">
                    {ep.asset_name || ep.asset_id.slice(0, 8)}
                    <span className="text-green-400/70 ml-1">
                      :{ep.port}/{getProtocolName(ep.protocol)}
                    </span>
                    {ep.label && (
                      <span className="text-green-400/50 ml-1">({ep.label})</span>
                    )}
                  </span>
                </div>
              ))}
              {result.entry_points_removed.map((ep, i) => (
                <div
                  key={`ep-rem-${i}`}
                  className="flex items-center gap-2 text-xs py-1 px-2 bg-red-500/10 rounded"
                >
                  <MinusCircleIcon className="h-3.5 w-3.5 text-red-400 flex-shrink-0" />
                  <span className="text-red-300 truncate">
                    {ep.asset_name || ep.asset_id.slice(0, 8)}
                    <span className="text-red-400/70 ml-1">
                      :{ep.port}/{getProtocolName(ep.protocol)}
                    </span>
                    {ep.label && (
                      <span className="text-red-400/50 ml-1">({ep.label})</span>
                    )}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Members */}
      {hasMemberChanges && (
        <div className="bg-slate-900/50 rounded overflow-hidden">
          <button
            onClick={() => toggleCategory('members')}
            className="w-full flex items-center justify-between px-3 py-2 hover:bg-slate-700/50 transition-colors"
          >
            <div className="flex items-center gap-2">
              {expandedCategories.has('members') ? (
                <ChevronDownIcon className="h-4 w-4 text-slate-400" />
              ) : (
                <ChevronRightIcon className="h-4 w-4 text-slate-400" />
              )}
              <span className="text-sm text-slate-300">Members</span>
            </div>
            <span className="text-xs text-slate-500">
              {result.members_added.length + result.members_removed.length}
            </span>
          </button>

          {expandedCategories.has('members') && (
            <div className="px-3 pb-2 space-y-1">
              {result.members_added.map((member) => (
                <div
                  key={member.asset_id}
                  className="flex items-center gap-2 text-xs py-1 px-2 bg-green-500/10 rounded"
                >
                  <PlusCircleIcon className="h-3.5 w-3.5 text-green-400 flex-shrink-0" />
                  <span className="text-green-300 truncate">
                    {member.asset_name || member.ip_address || member.asset_id.slice(0, 8)}
                  </span>
                </div>
              ))}
              {result.members_removed.map((member) => (
                <div
                  key={member.asset_id}
                  className="flex items-center gap-2 text-xs py-1 px-2 bg-red-500/10 rounded"
                >
                  <MinusCircleIcon className="h-3.5 w-3.5 text-red-400 flex-shrink-0" />
                  <span className="text-red-300 truncate">
                    {member.asset_name || member.ip_address || member.asset_id.slice(0, 8)}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Traffic Deviations */}
      {hasTrafficChanges && (
        <div className="bg-slate-900/50 rounded overflow-hidden">
          <button
            onClick={() => toggleCategory('traffic')}
            className="w-full flex items-center justify-between px-3 py-2 hover:bg-slate-700/50 transition-colors"
          >
            <div className="flex items-center gap-2">
              {expandedCategories.has('traffic') ? (
                <ChevronDownIcon className="h-4 w-4 text-slate-400" />
              ) : (
                <ChevronRightIcon className="h-4 w-4 text-slate-400" />
              )}
              <span className="text-sm text-slate-300">Traffic Deviations</span>
            </div>
            <span className="text-xs text-slate-500">
              {result.traffic_deviations.length}
            </span>
          </button>

          {expandedCategories.has('traffic') && (
            <div className="px-3 pb-2 space-y-1">
              {result.traffic_deviations.map((deviation, i) => (
                <div
                  key={`traffic-${i}`}
                  className="flex items-center gap-2 text-xs py-1 px-2 bg-amber-500/10 rounded"
                >
                  <ArrowTrendingUpIcon className="h-3.5 w-3.5 text-amber-400 flex-shrink-0" />
                  <span className="text-amber-300 truncate">
                    {deviation.asset_name || deviation.asset_id.slice(0, 8)}
                    <span className="text-amber-400/70 ml-1">
                      {deviation.deviation_percent > 0 ? '+' : ''}
                      {deviation.deviation_percent.toFixed(1)}%
                    </span>
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

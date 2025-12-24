import { useQuery } from '@tanstack/react-query';
import {
  ServerStackIcon,
  ArrowsRightLeftIcon,
  BellAlertIcon,
  ClockIcon,
} from '@heroicons/react/24/outline';
import Card from '../components/common/Card';
import StatCard from '../components/common/StatCard';
import Badge from '../components/common/Badge';
import { LoadingPage } from '../components/common/Loading';
import { alertApi, changeApi, assetApi, dependencyApi } from '../services/api';
import { formatRelativeTime, getSeverityColor } from '../utils/format';
import type { Alert, ChangeEvent } from '../types';
import clsx from 'clsx';

export default function Dashboard() {
  const { data: alertSummary, isLoading: alertsLoading } = useQuery({
    queryKey: ['alerts', 'summary'],
    queryFn: alertApi.getSummary,
  });

  const { data: changeSummary, isLoading: changesLoading } = useQuery({
    queryKey: ['changes', 'summary'],
    queryFn: changeApi.getSummary,
  });

  const { data: assetsData, isLoading: assetsLoading } = useQuery({
    queryKey: ['assets', 'list'],
    queryFn: () => assetApi.list({ page_size: 1 }),
  });

  const { data: depsData, isLoading: depsLoading } = useQuery({
    queryKey: ['dependencies', 'list'],
    queryFn: () => dependencyApi.list({ page_size: 1 }),
  });

  const { data: recentAlerts } = useQuery({
    queryKey: ['alerts', 'recent'],
    queryFn: () => alertApi.list({ page_size: 5, is_resolved: false }),
  });

  const { data: recentChanges } = useQuery({
    queryKey: ['changes', 'recent'],
    queryFn: () => changeApi.list({ page_size: 5 }),
  });

  if (alertsLoading || changesLoading || assetsLoading || depsLoading) {
    return <LoadingPage />;
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">Dashboard</h1>
        <p className="text-slate-400 mt-1">
          Overview of your application dependencies and infrastructure
        </p>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          title="Total Assets"
          value={assetsData?.total ?? 0}
          icon={<ServerStackIcon className="w-5 h-5" />}
        />
        <StatCard
          title="Dependencies"
          value={depsData?.total ?? 0}
          icon={<ArrowsRightLeftIcon className="w-5 h-5" />}
        />
        <StatCard
          title="Unresolved Alerts"
          value={alertSummary?.unresolved ?? 0}
          icon={<BellAlertIcon className="w-5 h-5" />}
        />
        <StatCard
          title="Changes (24h)"
          value={changeSummary?.last_24h ?? 0}
          icon={<ClockIcon className="w-5 h-5" />}
        />
      </div>

      {/* Alert Summary by Severity */}
      {alertSummary && (
        <Card title="Alert Summary">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="text-center p-4 bg-red-600/20 rounded-lg border border-red-600/30">
              <div className="text-2xl font-bold text-red-500">
                {alertSummary.critical}
              </div>
              <div className="text-sm text-slate-400">Critical</div>
            </div>
            <div className="text-center p-4 bg-orange-500/20 rounded-lg border border-orange-500/30">
              <div className="text-2xl font-bold text-orange-500">
                {alertSummary.error}
              </div>
              <div className="text-sm text-slate-400">Error</div>
            </div>
            <div className="text-center p-4 bg-yellow-500/20 rounded-lg border border-yellow-500/30">
              <div className="text-2xl font-bold text-yellow-500">
                {alertSummary.warning}
              </div>
              <div className="text-sm text-slate-400">Warning</div>
            </div>
            <div className="text-center p-4 bg-blue-500/20 rounded-lg border border-blue-500/30">
              <div className="text-2xl font-bold text-blue-500">
                {alertSummary.info}
              </div>
              <div className="text-sm text-slate-400">Info</div>
            </div>
          </div>
        </Card>
      )}

      {/* Two column layout */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Recent Alerts */}
        <Card title="Recent Alerts">
          <div className="space-y-3">
            {recentAlerts?.items.length === 0 && (
              <p className="text-slate-400 text-center py-4">No recent alerts</p>
            )}
            {recentAlerts?.items.map((alert: Alert) => (
              <div
                key={alert.id}
                className="flex items-start gap-3 p-3 bg-slate-700/50 rounded-lg"
              >
                <div
                  className={clsx(
                    'w-2 h-2 rounded-full mt-2',
                    getSeverityColor(alert.severity)
                  )}
                />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="font-medium text-white truncate">
                      {alert.title}
                    </span>
                    <Badge
                      variant={
                        alert.severity === 'critical'
                          ? 'error'
                          : alert.severity === 'error'
                          ? 'error'
                          : alert.severity === 'warning'
                          ? 'warning'
                          : 'info'
                      }
                    >
                      {alert.severity}
                    </Badge>
                  </div>
                  <p className="text-sm text-slate-400 truncate">
                    {alert.message}
                  </p>
                  <p className="text-xs text-slate-500 mt-1">
                    {formatRelativeTime(alert.created_at)}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </Card>

        {/* Recent Changes */}
        <Card title="Recent Changes">
          <div className="space-y-3">
            {recentChanges?.items.length === 0 && (
              <p className="text-slate-400 text-center py-4">No recent changes</p>
            )}
            {recentChanges?.items.map((change: ChangeEvent) => (
              <div
                key={change.id}
                className="flex items-start gap-3 p-3 bg-slate-700/50 rounded-lg"
              >
                <div className="w-2 h-2 rounded-full mt-2 bg-primary-500" />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="font-medium text-white truncate">
                      {change.summary}
                    </span>
                    <Badge>{change.change_type}</Badge>
                  </div>
                  {change.description && (
                    <p className="text-sm text-slate-400 truncate">
                      {change.description}
                    </p>
                  )}
                  <p className="text-xs text-slate-500 mt-1">
                    {formatRelativeTime(change.detected_at)}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </Card>
      </div>

      {/* Change Types Summary */}
      {changeSummary && changeSummary.by_type && Object.keys(changeSummary.by_type).length > 0 && (
        <Card title="Changes by Type (Last 7 Days)">
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4">
            {Object.entries(changeSummary.by_type).map(([type, count]) => (
              <div
                key={type}
                className="text-center p-4 bg-slate-700/50 rounded-lg"
              >
                <div className="text-xl font-semibold text-white">{count}</div>
                <div className="text-sm text-slate-400 truncate">{type}</div>
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  );
}

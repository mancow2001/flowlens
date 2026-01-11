import { useQuery } from '@tanstack/react-query';
import clsx from 'clsx';
import { mlApi } from '../../services/api';

interface MLStatusIndicatorProps {
  showLabel?: boolean;
}

export default function MLStatusIndicator({ showLabel = true }: MLStatusIndicatorProps) {
  const { data: status } = useQuery({
    queryKey: ['ml', 'status'],
    queryFn: () => mlApi.getStatus(),
    staleTime: 30000,
    refetchOnWindowFocus: true,
  });

  if (!status) {
    return null;
  }

  const isActive = status.ml_enabled && status.ml_available && status.model_version;
  const isDisabled = !status.ml_enabled;

  let statusColor = 'bg-slate-500';
  let statusText = 'ML: Loading';
  let tooltip = '';

  if (isDisabled) {
    statusColor = 'bg-slate-500';
    statusText = 'ML: Disabled';
    tooltip = 'ML classification is disabled';
  } else if (isActive) {
    statusColor = 'bg-green-500';
    statusText = `ML: ${status.model_version}`;
    tooltip = `ML active using model ${status.model_version}\nThreshold: ${Math.round(status.ml_confidence_threshold * 100)}%`;
  } else {
    statusColor = 'bg-blue-500';
    statusText = 'ML: Heuristic';
    tooltip = 'Using heuristic classification (no ML model active)';
  }

  return (
    <div className="flex items-center gap-2" title={tooltip}>
      <div className={clsx('w-2 h-2 rounded-full', statusColor)} />
      {showLabel && (
        <span className="text-sm text-slate-400">{statusText}</span>
      )}
    </div>
  );
}

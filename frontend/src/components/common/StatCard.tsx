import { ReactNode } from 'react';
import clsx from 'clsx';

interface StatCardProps {
  title: string;
  value: string | number;
  icon?: ReactNode;
  change?: {
    value: number;
    label: string;
  };
  className?: string;
}

export default function StatCard({
  title,
  value,
  icon,
  change,
  className,
}: StatCardProps) {
  return (
    <div
      className={clsx(
        'bg-slate-800 border border-slate-700 rounded-lg p-4',
        className
      )}
    >
      <div className="flex items-center justify-between">
        <span className="text-sm text-slate-400">{title}</span>
        {icon && <div className="text-slate-500">{icon}</div>}
      </div>
      <div className="mt-2">
        <span className="text-2xl font-semibold text-white">{value}</span>
      </div>
      {change && (
        <div className="mt-2 flex items-center gap-1">
          <span
            className={clsx(
              'text-sm font-medium',
              change.value >= 0 ? 'text-green-500' : 'text-red-500'
            )}
          >
            {change.value >= 0 ? '+' : ''}
            {change.value}%
          </span>
          <span className="text-sm text-slate-400">{change.label}</span>
        </div>
      )}
    </div>
  );
}

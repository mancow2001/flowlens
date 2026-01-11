import clsx from 'clsx';
import type { ClassificationMethod } from '../../types';

interface ClassificationBadgeProps {
  method: ClassificationMethod | string | null | undefined;
  confidence?: number | null;
  showLabel?: boolean;
  size?: 'sm' | 'md';
}

const METHOD_CONFIG: Record<string, { label: string; bgColor: string; textColor: string }> = {
  ml: {
    label: 'ML',
    bgColor: 'bg-blue-600',
    textColor: 'text-white',
  },
  heuristic: {
    label: 'Heuristic',
    bgColor: 'bg-yellow-500',
    textColor: 'text-slate-900',
  },
  hybrid: {
    label: 'Hybrid',
    bgColor: 'bg-purple-600',
    textColor: 'text-white',
  },
  manual: {
    label: 'Manual',
    bgColor: 'bg-green-600',
    textColor: 'text-white',
  },
  auto: {
    label: 'Auto',
    bgColor: 'bg-slate-600',
    textColor: 'text-white',
  },
  api: {
    label: 'API',
    bgColor: 'bg-slate-600',
    textColor: 'text-white',
  },
};

export default function ClassificationBadge({
  method,
  confidence,
  showLabel = true,
  size = 'sm',
}: ClassificationBadgeProps) {
  if (!method) return null;

  const config = METHOD_CONFIG[method] || {
    label: method,
    bgColor: 'bg-slate-600',
    textColor: 'text-white',
  };

  const sizeClasses = size === 'sm' ? 'px-1.5 py-0.5 text-xs' : 'px-2 py-1 text-sm';

  const badge = (
    <span
      className={clsx(
        'inline-flex items-center rounded font-medium',
        config.bgColor,
        config.textColor,
        sizeClasses
      )}
    >
      {showLabel ? config.label : config.label.charAt(0)}
    </span>
  );

  // If we have confidence, wrap in a tooltip-like title
  if (confidence !== null && confidence !== undefined) {
    return (
      <span title={`Classified by ${config.label} with ${Math.round(confidence * 100)}% confidence`}>
        {badge}
      </span>
    );
  }

  return badge;
}

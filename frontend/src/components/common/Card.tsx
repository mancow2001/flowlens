import { ReactNode } from 'react';
import clsx from 'clsx';

interface CardProps {
  children: ReactNode;
  className?: string;
  title?: string;
  action?: ReactNode;
}

export default function Card({ children, className, title, action }: CardProps) {
  return (
    <div
      className={clsx(
        'bg-slate-800 border border-slate-700 rounded-lg overflow-hidden',
        className
      )}
    >
      {(title || action) && (
        <div className="flex items-center justify-between px-4 py-3 border-b border-slate-700">
          {title && (
            <h3 className="text-lg font-medium text-white">{title}</h3>
          )}
          {action && <div>{action}</div>}
        </div>
      )}
      <div className="p-4">{children}</div>
    </div>
  );
}

import React from 'react';
import { cn } from '../../lib/utils';

export type StatusState = 'queued' | 'running' | 'awaiting_hitl' | 'completed' | 'failed' | 'cancelled';

export interface StatusBadgeProps extends React.HTMLAttributes<HTMLDivElement> {
  status: StatusState;
}

const statusConfig: Record<StatusState, { label: string; className: string; showDot?: boolean }> = {
  queued: { label: 'Queued', className: 'bg-muted text-muted-foreground border-muted-foreground/20' },
  running: { label: 'Running', className: 'bg-info/10 text-info border-info/20', showDot: true },
  awaiting_hitl: { label: 'Needs review', className: 'bg-warning/10 text-warning-foreground border-warning/20' },
  completed: { label: 'Completed', className: 'bg-success/10 text-success border-success/20' },
  failed: { label: 'Failed', className: 'bg-destructive/10 text-destructive border-destructive/20' },
  cancelled: { label: 'Cancelled', className: 'bg-muted text-muted-foreground border-muted-foreground/20' },
};

export const StatusBadge: React.FC<StatusBadgeProps> = ({ status, className, ...props }) => {
  const config = statusConfig[status];
  
  return (
    <div
      className={cn(
        'inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium border',
        config.className,
        className
      )}
      {...props}
    >
      {config.showDot && (
        <span className="relative flex h-2 w-2">
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-info opacity-75"></span>
          <span className="relative inline-flex rounded-full h-2 w-2 bg-info"></span>
        </span>
      )}
      {config.label}
    </div>
  );
};

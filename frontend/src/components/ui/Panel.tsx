import React from 'react';
import { cn } from '../../lib/utils';

export interface PanelProps extends React.HTMLAttributes<HTMLDivElement> {}

export const Panel = React.forwardRef<HTMLDivElement, PanelProps>(
  ({ className, ...props }, ref) => {
    return (
      <div
        ref={ref}
        className={cn(
          'rounded-[10px] border border-border bg-card text-card-foreground',
          className
        )}
        {...props}
      />
    );
  }
);

Panel.displayName = 'Panel';

import React from 'react';
import { cn } from '../../lib/utils';

export interface StickyActionBarProps extends React.HTMLAttributes<HTMLDivElement> {
  position?: 'top' | 'bottom';
}

export const StickyActionBar = React.forwardRef<HTMLDivElement, StickyActionBarProps>(
  ({ className, position = 'bottom', children, ...props }, ref) => {
    return (
      <div
        ref={ref}
        className={cn(
          'sticky z-40 w-full flex items-center justify-between px-4 py-3 bg-background/95 backdrop-blur border-border supports-[backdrop-filter]:bg-background/60 shadow-sm',
          {
            'top-14 border-b': position === 'top',
            'bottom-0 border-t': position === 'bottom',
          },
          className
        )}
        {...props}
      >
        {children}
      </div>
    );
  }
);
StickyActionBar.displayName = 'StickyActionBar';

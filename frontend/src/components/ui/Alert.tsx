import React from 'react';
import { cn } from '../../lib/utils';

export interface AlertProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?: 'default' | 'destructive' | 'warning' | 'success' | 'info';
}

export const Alert = React.forwardRef<HTMLDivElement, AlertProps>(
  ({ className, variant = 'default', ...props }, ref) => {
    return (
      <div
        ref={ref}
        role="alert"
        className={cn(
          'relative w-full rounded-lg border p-4 text-sm [&>svg]:absolute [&>svg]:left-4 [&>svg]:top-4 [&>svg]:text-foreground [&>svg~*]:pl-7',
          {
            'bg-background text-foreground': variant === 'default',
            'border-destructive/50 text-destructive dark:border-destructive [&>svg]:text-destructive bg-destructive/5': variant === 'destructive',
            'border-warning/50 text-warning-foreground dark:border-warning [&>svg]:text-warning-foreground bg-warning/5': variant === 'warning',
            'border-success/50 text-success dark:border-success [&>svg]:text-success bg-success/5': variant === 'success',
            'border-info/50 text-info dark:border-info [&>svg]:text-info bg-info/5': variant === 'info',
          },
          className
        )}
        {...props}
      />
    );
  }
);
Alert.displayName = 'Alert';

export const AlertTitle = React.forwardRef<HTMLHeadingElement, React.HTMLAttributes<HTMLHeadingElement>>(
  ({ className, ...props }, ref) => (
    <h5
      ref={ref}
      className={cn('mb-1 font-medium leading-none tracking-tight', className)}
      {...props}
    />
  )
);
AlertTitle.displayName = 'AlertTitle';

export const AlertDescription = React.forwardRef<HTMLParagraphElement, React.HTMLAttributes<HTMLParagraphElement>>(
  ({ className, ...props }, ref) => (
    <div
      ref={ref}
      className={cn('text-sm [&_p]:leading-relaxed', className)}
      {...props}
    />
  )
);
AlertDescription.displayName = 'AlertDescription';

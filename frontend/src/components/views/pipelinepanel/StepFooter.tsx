import React from "react";

export const StepFooter: React.FC<{
  currentStep: 1 | 2;
  statusText: string;
  children?: React.ReactNode;
}> = ({ currentStep, statusText, children }) => (
  <div className="sticky bottom-0 z-[5] -mx-6 border-t bg-background/95 px-4 py-4 backdrop-blur sm:px-6">
    <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
      <div className="min-w-0 space-y-2">
        <div className="flex flex-wrap items-center gap-2 text-xs font-semibold sm:gap-3">
          {[1, 2].map((step) => (
            <div key={step} className="flex items-center gap-2">
              <span
                className={`inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full border text-sm transition-colors ${
                  currentStep === step
                    ? "bg-primary text-primary-foreground border-primary"
                    : "bg-muted text-muted-foreground border-border"
                }`}
              >
                {step}
              </span>
              <span
                className={`whitespace-nowrap ${
                  currentStep === step ? "text-foreground" : "text-muted-foreground"
                }`}
              >
                {step === 1 ? "Questions" : "Resolution Plan"}
              </span>
              {step === 1 && <span className="hidden h-px w-8 bg-border sm:block" />}
            </div>
          ))}
        </div>
        <span className="block text-xs font-medium text-muted-foreground">
          {statusText}
        </span>
      </div>
      {children && <div className="flex shrink-0 justify-start lg:justify-end">{children}</div>}
    </div>
  </div>
);

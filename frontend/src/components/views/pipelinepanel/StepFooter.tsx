import React from "react";

export const StepFooter: React.FC<{
  currentStep: 1 | 2;
  statusText: string;
  children?: React.ReactNode;
}> = ({ currentStep, statusText, children }) => (
  <div className="sticky bottom-0 z-[5] -mx-6 px-6 py-4 bg-background/95 backdrop-blur border-t flex flex-col sm:flex-row items-center gap-4 justify-between">
    <div className="flex items-center gap-3 text-xs font-semibold">
      {[1, 2].map((step) => (
        <div key={step} className="flex items-center gap-2">
          <span
            className={`inline-flex h-7 w-7 items-center justify-center rounded-full border ${
              currentStep === step
                ? "bg-primary text-primary-foreground border-primary"
                : "bg-muted text-muted-foreground border-border"
            }`}
          >
            {step}
          </span>
          <span
            className={
              currentStep === step ? "text-foreground" : "text-muted-foreground"
            }
          >
            {step === 1 ? "Questions" : "Resolution Plan"}
          </span>
          {step === 1 && <span className="h-px w-8 bg-border" />}
        </div>
      ))}
      <span className="hidden md:inline text-muted-foreground font-medium">
        {statusText}
      </span>
    </div>
    {children}
  </div>
);

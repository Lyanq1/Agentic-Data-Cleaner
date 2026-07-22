import React from "react";
import { SpinnerIcon } from "./SpinnerIcon";
import { StepFooter } from "./StepFooter";
import { Alert, AlertTitle, AlertDescription } from "../../ui/Alert";

export const ValidationResolutionPendingPanel: React.FC = () => {
  return (
    <div className="mb-8 space-y-6 text-left animate-fadeIn">
      <Alert variant="info" className="flex items-start gap-3">
        <SpinnerIcon className="w-4 h-4 text-info shrink-0 mt-0.5" />
        <div>
          <AlertTitle className="font-semibold text-foreground">
            Preparing Validation Resolution Plan
          </AlertTitle>
          <AlertDescription className="text-muted-foreground mt-1">
            The AI Agent is integrating your answers into cleaning rules. This panel will update automatically when the resolution plan is ready.
          </AlertDescription>
        </div>
      </Alert>

      <StepFooter currentStep={2} statusText="Step 2 is being prepared" />
    </div>
  );
};

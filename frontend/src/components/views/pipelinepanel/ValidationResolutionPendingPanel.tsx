import React from "react";
import { SpinnerIcon } from "./SpinnerIcon";
import { StepFooter } from "./StepFooter";

export const ValidationResolutionPendingPanel: React.FC = () => {
  return (
    <div className="mb-8 rounded-2xl border-2 border-emerald-400/40 bg-emerald-50 shadow-lg overflow-hidden text-left animate-fadeIn">
      <div className="bg-emerald-600 px-6 py-4">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-full bg-white/20 backdrop-blur-sm flex items-center justify-center">
            <SpinnerIcon className="w-5 h-5 text-white" />
          </div>
          <div>
            <h3 className="text-lg font-bold text-white">
              Preparing Validation Resolution Plan
            </h3>
            <p className="text-white/80 text-sm">
              The AI Agent is integrating your answers into cleaning rules
            </p>
          </div>
        </div>
      </div>

      <div className="p-6 space-y-6">
        <div className="rounded-xl border bg-white p-5 shadow-sm">
          <div className="flex items-start gap-3">
            <div>
              <h4 className="text-sm font-semibold text-foreground">
                Waiting for LLM response
              </h4>
              <p className="text-sm text-muted-foreground mt-1 leading-relaxed">
                Your answers were submitted. This panel will update
                automatically when the resolution plan is ready.
              </p>
            </div>
          </div>
        </div>

        <StepFooter currentStep={2} statusText="Step 2 is being prepared" />
      </div>
    </div>
  );
};

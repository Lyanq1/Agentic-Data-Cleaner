import React, { useMemo } from "react";
import { StepFooter } from "./StepFooter";
import { SpinnerIcon } from "./SpinnerIcon";
import { formatDisplayValue } from "./utils";

export const ResolvedValidationPlanPanel: React.FC<{
  validationResult: any;
  onGeneratePlan: () => void;
  isGenerating: boolean;
  hasExecutionPlan?: boolean;
}> = ({ validationResult, onGeneratePlan, isGenerating, hasExecutionPlan }) => {
  const reasoning = validationResult.reasoning || "";
  const actionPlan = validationResult.action_plan || {};
  const resolvedByUser = validationResult.resolved_by_user || [];

  const submittedAnswers = useMemo(() => {
    const clarifications = validationResult.clarifications || {};
    return ["typecast", "null", "duplicate"].flatMap((cat) =>
      (Object.entries(clarifications[cat] || {}) as [string, any][])
        .filter(
          ([, question]) => question?.answer != null && question.answer !== "",
        )
        .map(([qKey, question]) => ({
          key: `${cat}.${qKey}`,
          label: `${cat} - ${qKey}`,
          question:
            question.question ||
            `${cat} - ${qKey.replace(/^Q(\d+)_/, "Question $1: ").replace(/_/g, " ")}`,
          answer: question.answer,
        })),
    );
  }, [validationResult.clarifications]);

  return (
    <div className="mb-8 rounded-2xl border-2 border-emerald-400/40 bg-emerald-50 shadow-lg overflow-hidden text-left animate-fadeIn">
      <div className="bg-emerald-600 px-6 py-4">
        <div className="flex items-center">
          <div>
            <h3 className="text-lg font-bold text-white">
              Validation Resolution Plan
            </h3>
            <p className="text-white/80 text-sm">
              The AI Agent has integrated your answers and compiled the cleaning
              rules
            </p>
          </div>
        </div>
      </div>

      <div className="p-6 space-y-6">
        {reasoning && (
          <div className="rounded-xl border bg-muted/40 p-4 text-sm leading-relaxed text-muted-foreground">
            <strong className="text-foreground block mb-1.5">
              Decision Reasoning:
            </strong>
            {formatDisplayValue(reasoning)}
          </div>
        )}

        <div className="space-y-4">
          <h4 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider">
            Generated Cleaning Instructions
          </h4>

          <div className="grid grid-cols-1 gap-4">
            {["typecast", "null", "duplicate"].map((issue) => {
              const planText = actionPlan[issue];
              if (!planText) return null;

              const title =
                issue === "null"
                  ? "Null Handling Plan"
                  : issue === "duplicate"
                    ? "Deduplication Plan"
                    : "Type Casting Plan";

              return (
                <div
                  key={issue}
                  className="flex gap-4 p-4 rounded-xl border bg-card/60 backdrop-blur-md shadow-sm"
                >
                  <div>
                    <h5 className="text-sm font-bold text-foreground mb-1">
                      {title}
                    </h5>
                    <p className="text-xs text-muted-foreground leading-relaxed whitespace-pre-line">
                      {formatDisplayValue(planText)}
                    </p>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {resolvedByUser.length > 0 && (
          <div className="rounded-xl border p-4 bg-white shadow-sm">
            <h4 className="text-sm font-semibold text-muted-foreground mb-3">
              Resolved Column Issues
            </h4>
            <div className="flex flex-wrap gap-2">
              {resolvedByUser.map((item: string, i: number) => (
                <span
                  key={i}
                  className="inline-block px-3 py-1 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200"
                >
                  {item}
                </span>
              ))}
            </div>
          </div>
        )}

        {submittedAnswers.length > 0 && (
          <details className="mt-4 text-xs font-semibold">
            <summary className="cursor-pointer text-muted-foreground hover:text-foreground font-medium select-none transition-colors">
              View your submitted answers
            </summary>
            <div className="mt-2.5 rounded-xl border bg-muted/15 p-4 space-y-2.5 divide-y divide-border/90">
              {submittedAnswers.map((item) => (
                <div key={item.key} className="pt-2 first:pt-0">
                  <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground/90 block mb-0.5">
                    {formatDisplayValue(item.label)}
                  </span>
                  <p className="text-xs text-foreground font-semibold leading-relaxed mb-1">
                    {formatDisplayValue(item.question)}
                  </p>
                  <p className="text-xs text-foreground font-medium">
                    {formatDisplayValue(item.answer)}
                  </p>
                </div>
              ))}
            </div>
          </details>
        )}

        {!hasExecutionPlan && (
          <StepFooter currentStep={2} statusText="">
            <button
              type="button"
              onClick={onGeneratePlan}
              disabled={isGenerating}
              aria-busy={isGenerating}
              className="inline-flex h-11 items-center justify-center gap-2 whitespace-nowrap rounded-xl bg-emerald-600 px-5 text-sm font-semibold text-white shadow-sm transition-all hover:bg-emerald-700 hover:shadow-md disabled:cursor-wait disabled:opacity-70 cursor-pointer"
            >
              {isGenerating ? (
                <>
                  <SpinnerIcon />
                  Generating plan...
                </>
              ) : (
                <>View Execution Plan</>
              )}
            </button>
          </StepFooter>
        )}
      </div>
    </div>
  );
};

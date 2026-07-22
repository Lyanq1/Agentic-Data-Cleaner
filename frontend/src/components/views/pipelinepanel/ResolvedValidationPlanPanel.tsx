import React, { useMemo } from "react";
import { StepFooter } from "./StepFooter";
import { SpinnerIcon } from "./SpinnerIcon";
import { formatDisplayValue } from "./utils";
import { Panel } from "../../ui/Panel";
import { Button } from "../../ui/Button";

export const ResolvedValidationPlanPanel: React.FC<{
  validationResult: any;
  onGeneratePlan: () => void;
  isGenerating: boolean;
  hasExecutionPlan?: boolean;
  pipelineMode?: string;
}> = ({ validationResult, onGeneratePlan, isGenerating, hasExecutionPlan, pipelineMode }) => {
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
    <Panel className="mb-8 text-left animate-fadeIn overflow-hidden">
      <div className="border-b px-6 py-4">
        <h3 className="text-sm font-semibold text-foreground">
          Validation Resolution Plan
        </h3>
        <p className="text-xs text-muted-foreground mt-0.5">
          The AI Agent has integrated your answers and compiled the cleaning rules
        </p>
      </div>

      <div className="p-6 space-y-6">
        {reasoning && (
          <div className="rounded-lg border bg-muted/30 p-4 text-xs leading-relaxed text-muted-foreground">
            <strong className="text-foreground block mb-1">
              Decision Reasoning:
            </strong>
            {formatDisplayValue(reasoning)}
          </div>
        )}

        <div className="space-y-4">
          <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
            Generated Cleaning Instructions
          </h4>

          <div className="grid grid-cols-1 gap-3">
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
                  className="p-4 rounded-lg border bg-muted/10"
                >
                  <h5 className="text-xs font-bold text-foreground mb-1">
                    {title}
                  </h5>
                  <p className="text-xs text-muted-foreground leading-relaxed whitespace-pre-line">
                    {formatDisplayValue(planText)}
                  </p>
                </div>
              );
            })}
          </div>
        </div>

        {resolvedByUser.length > 0 && (
          <div className="rounded-lg border p-4 bg-muted/5">
            <h4 className="text-xs font-semibold text-muted-foreground mb-2.5">
              Resolved Column Issues
            </h4>
            <div className="flex flex-wrap gap-1.5">
              {resolvedByUser.map((item: string, i: number) => (
                <span
                  key={i}
                  className="inline-block px-2.5 py-0.5 rounded-md text-xs font-medium bg-muted text-muted-foreground border"
                >
                  {item}
                </span>
              ))}
            </div>
          </div>
        )}

        {submittedAnswers.length > 0 && (
          pipelineMode === "benchmark" ? (
            <div className="mt-4">
              <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">
                Auto-resolved decisions
              </h4>
              <div className="rounded-lg border bg-muted/10 p-4 space-y-3 divide-y divide-border">
                {submittedAnswers.map((item) => (
                  <div key={item.key} className="pt-3 first:pt-0">
                    <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground block mb-0.5">
                      {formatDisplayValue(item.label)}
                    </span>
                    <p className="text-xs text-foreground font-semibold leading-relaxed mb-1">
                      {formatDisplayValue(item.question)}
                    </p>
                    <p className="text-xs text-muted-foreground bg-background rounded-md px-2 py-1 border mt-1 inline-block">
                      Selected Strategy: <strong className="text-foreground">{formatDisplayValue(item.answer)}</strong>
                    </p>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <details className="mt-4 text-xs font-semibold">
              <summary className="cursor-pointer text-muted-foreground hover:text-foreground font-medium select-none transition-colors">
                View your submitted answers
              </summary>
              <div className="mt-2.5 rounded-lg border bg-muted/10 p-4 space-y-3 divide-y divide-border">
                {submittedAnswers.map((item) => (
                  <div key={item.key} className="pt-3 first:pt-0">
                    <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground block mb-0.5">
                      {formatDisplayValue(item.label)}
                    </span>
                    <p className="text-xs text-foreground font-semibold leading-relaxed mb-1">
                      {formatDisplayValue(item.question)}
                    </p>
                    <p className="text-xs text-muted-foreground font-medium">
                      {formatDisplayValue(item.answer)}
                    </p>
                  </div>
                ))}
              </div>
            </details>
          )
        )}

        {!hasExecutionPlan && (
          <StepFooter currentStep={2} statusText="">
            <Button
              type="button"
              onClick={onGeneratePlan}
              disabled={isGenerating}
              className="cursor-pointer"
            >
              {isGenerating ? (
                <>
                  <SpinnerIcon />
                  Generating plan...
                </>
              ) : (
                <>View Execution Plan</>
              )}
            </Button>
          </StepFooter>
        )}
      </div>
    </Panel>
  );
};

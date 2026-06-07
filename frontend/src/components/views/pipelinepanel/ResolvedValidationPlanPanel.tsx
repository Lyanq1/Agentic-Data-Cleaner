import React, { useMemo } from "react";
import { StepFooter } from "./StepFooter";

export const ResolvedValidationPlanPanel: React.FC<{
  validationResult: any;
  onGeneratePlan: () => void;
  isGenerating: boolean;
}> = ({ validationResult, onGeneratePlan, isGenerating }) => {
  const reasoning = validationResult.reasoning || "";
  const actionPlan = validationResult.action_plan || {};
  const resolvedByUser = validationResult.resolved_by_user || [];

  const submittedAnswers = useMemo(() => {
    const clarifications = validationResult.clarifications || {};
    return ["null", "duplicate", "typecast"].flatMap((cat) =>
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
            {reasoning}
          </div>
        )}

        <div className="space-y-4">
          <h4 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider">
            Generated Cleaning Instructions
          </h4>

          <div className="grid grid-cols-1 gap-4">
            {["null", "duplicate", "typecast"].map((issue) => {
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
                      {planText}
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
                    {item.label}
                  </span>
                  <p className="text-xs text-foreground font-semibold leading-relaxed mb-1">
                    {item.question}
                  </p>
                  <p className="text-xs text-foreground font-medium">
                    {item.answer}
                  </p>
                </div>
              ))}
            </div>
          </details>
        )}

        <StepFooter
          currentStep={2}
          statusText="Review the generated cleaning plan"
        >
          <button
            type="button"
            onClick={onGeneratePlan}
            disabled={isGenerating}
            className="inline-flex items-center gap-2 px-5 py-2.5 bg-emerald-600 hover:bg-emerald-700 text-white rounded-xl text-sm font-semibold transition-all shadow-sm hover:shadow-md disabled:opacity-50"
          >
            {isGenerating ? <>Generating Plan...</> : <>Start Plan</>}
          </button>
        </StepFooter>
      </div>
    </div>
  );
};

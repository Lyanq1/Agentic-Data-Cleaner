import React, { useMemo } from "react";
import { StepFooter } from "./StepFooter";
import { SpinnerIcon } from "./SpinnerIcon";
import { formatDisplayValue, renderHighlightedText } from "./utils";

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

  const allDatasetColumns = useMemo(() => {
    const cols = new Set<string>();
    const clarifications = validationResult?.clarifications || {};
    ["typecast", "null", "duplicate"].forEach((cat) => {
      const catData = clarifications[cat];
      if (catData) {
        Object.keys(catData).forEach((qKey) => {
          const colName = qKey.startsWith("Q2_strategy_column_")
            ? qKey.substring("Q2_strategy_column_".length)
            : qKey.startsWith("Q1_allow_missing_column_")
              ? qKey.substring("Q1_allow_missing_column_".length)
              : qKey.startsWith("Q1_cast_column_")
                ? qKey.substring("Q1_cast_column_".length)
                : "";
          if (colName) cols.add(colName);
        });
      }
    });
    return Array.from(cols);
  }, [validationResult]);

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
            {renderHighlightedText(formatDisplayValue(reasoning), undefined, allDatasetColumns)}
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
                      {renderHighlightedText(formatDisplayValue(planText), undefined, allDatasetColumns)}
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
          pipelineMode === "benchmark" ? (
            <div className="mt-4">
              <h4 className="text-xs font-semibold text-violet-700 uppercase tracking-wider mb-2.5">
                🤖 Auto-Resolved Decisions
              </h4>
              <div className="rounded-xl border bg-violet-50/20 border-violet-100/50 p-4 space-y-2.5 divide-y divide-border/90">
                {submittedAnswers.map((item) => (
                  <div key={item.key} className="pt-2 first:pt-0">
                    <span className="text-[9px] font-bold uppercase tracking-wider text-violet-600 block mb-0.5">
                      {formatDisplayValue(item.label)}
                    </span>
                    <p className="text-xs text-foreground font-semibold leading-relaxed mb-1">
                      {renderHighlightedText(formatDisplayValue(item.question), undefined, allDatasetColumns)}
                    </p>
                    <p className="text-xs text-foreground font-medium bg-white/70 rounded px-2.5 py-1 border border-slate-100 mt-1 inline-block">
                      Selected Strategy: <strong className="text-violet-700">{formatDisplayValue(item.answer)}</strong>
                    </p>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <div className="mt-4">
              <h4 className="text-xs font-semibold text-emerald-800 uppercase tracking-wider mb-2.5 flex items-center gap-1.5">
                <span>📋 Your Submitted Answers</span>
              </h4>
              <div className="rounded-xl border bg-white/80 border-emerald-100 p-4 space-y-3 divide-y divide-emerald-100/60 shadow-2xs">
                {submittedAnswers.map((item) => (
                  <div key={item.key} className="pt-2.5 first:pt-0">
                    <span className="text-[10px] font-bold uppercase tracking-wider text-emerald-700/80 block mb-0.5">
                      {formatDisplayValue(item.label)}
                    </span>
                    <p className="text-xs text-foreground font-semibold leading-relaxed mb-1">
                      {renderHighlightedText(formatDisplayValue(item.question), undefined, allDatasetColumns)}
                    </p>
                    <p className="text-xs text-emerald-950 font-medium bg-emerald-50/60 rounded-md px-2.5 py-1 border border-emerald-200/60 mt-1 inline-block">
                      Selected Strategy: <strong className="text-emerald-700">{formatDisplayValue(item.answer)}</strong>
                    </p>
                  </div>
                ))}
              </div>
            </div>
          )
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

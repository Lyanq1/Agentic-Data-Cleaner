import React, { useState, useMemo } from "react";
import { StepFooter } from "./StepFooter";
import { TextIcon } from "./TextIcon";
import { formatDisplayValue, getOptionConsequence } from "./utils";

export const InputValidationClarificationContent: React.FC<{
  payload: any;
  isAwaiting: boolean;
  onDecision: (
    d: "approve" | "reject" | "modify",
    fb?: string,
    disambiguationAnswers?: Record<string, string | string[]>,
  ) => void;
  isPending: boolean;
}> = ({ payload, isAwaiting, onDecision, isPending }) => {
  const clarifications = payload.clarifications || {};
  const categories = ["null", "duplicate", "typecast"] as const;

  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [customInputs, setCustomInputs] = useState<Record<string, string>>({});

  const handleSelectAnswer = (key: string, val: string) => {
    setAnswers((prev) => {
      const nextAnswers = { ...prev, [key]: val };
      if (key.startsWith("null.Q1_allow_missing_column_")) {
        const colName = key.substring("null.Q1_allow_missing_column_".length);
        const q2Key = `null.Q2_strategy_column_${colName}`;
        if (val === "No" && prev[q2Key] === "keep_null") {
          delete nextAnswers[q2Key];
        }
      }
      return nextAnswers;
    });
  };

  const handleCustomInputChange = (key: string, val: string) => {
    setCustomInputs((prev) => ({ ...prev, [key]: val }));
  };

  const totalQuestions = useMemo(() => {
    let count = 0;
    categories.forEach((cat) => {
      const catData = clarifications[cat];
      if (catData) {
        count += Object.keys(catData).filter((qKey) => catData[qKey]).length;
      }
    });
    return count;
  }, [clarifications]);

  const answeredCount = useMemo(() => {
    let count = 0;
    categories.forEach((cat) => {
      const catData = clarifications[cat];
      if (catData) {
        Object.keys(catData).forEach((qKey) => {
          const key = `${cat}.${qKey}`;
          if (catData[qKey] && answers[key]) {
            if (
              answers[key].includes("Custom strategy") &&
              !customInputs[key]?.trim()
            ) {
              // Must provide text for custom strategy
            } else {
              count += 1;
            }
          }
        });
      }
    });
    return count;
  }, [clarifications, answers, customInputs]);

  const allAnswered = answeredCount === totalQuestions;

  const handleSubmit = () => {
    const finalAnswers = { ...answers };
    Object.keys(finalAnswers).forEach((key) => {
      if (finalAnswers[key].includes("Custom strategy") && customInputs[key]) {
        finalAnswers[key] = `Custom strategy: ${customInputs[key].trim()}`;
      }
    });
    onDecision("approve", "User resolved all clarifications", finalAnswers);
  };

  return (
    <div className="space-y-6">
      {payload.reasoning && (
        <div className="rounded-xl border bg-muted/30 p-4 text-sm leading-relaxed text-muted-foreground">
          <strong className="text-foreground block mb-1">Reasoning:</strong>
          {formatDisplayValue(payload.reasoning)}
        </div>
      )}

      <div className="space-y-6">
        {categories.map((cat) => {
          const catData = clarifications[cat];
          if (!catData || Object.keys(catData).length === 0) return null;

          const title =
            cat === "null"
              ? "Null Value Resolutions"
              : cat === "duplicate"
                ? "Duplicate Row Resolutions"
                : "Type Casting Resolutions";
          const badgeColor =
            cat === "null"
              ? "bg-sky-50 text-sky-700 border-sky-200"
              : cat === "duplicate"
                ? "bg-violet-50 text-violet-700 border-violet-200"
                : "bg-amber-50 text-amber-700 border-amber-200";

          return (
            <div
              key={cat}
              className="rounded-xl border bg-card/60 backdrop-blur-md shadow-sm overflow-hidden text-left"
            >
              <div className="px-4 py-3 border-b flex items-center justify-between bg-muted/20">
                <h4 className="text-sm font-semibold flex items-center gap-2">
                  <span className={`px-2 py-0.5 rounded text-xs border ${badgeColor}`}>
                    {cat.toUpperCase()}
                  </span>
                  {title}
                </h4>
              </div>
              <div className="p-4 space-y-6 divide-y divide-border/40">
                {Object.keys(catData)
                  .sort()
                  .map((qKey, qi) => {
                    const q = catData[qKey];
                    if (!q) return null;
                    const key = `${cat}.${qKey}`;
                    const selectedVal = answers[key] || "";
                    const isStrategy = q && typeof q === "object" && "options" in q;
                    let optionsToRender = q.options || [];
                    if (cat === "null" && qKey.startsWith("Q2_strategy_column_")) {
                      const colName = qKey.substring("Q2_strategy_column_".length);
                      const q1Key = `null.Q1_allow_missing_column_${colName}`;
                      const q1Answer = answers[q1Key];
                      if (q1Answer === "No") {
                        optionsToRender = optionsToRender.filter((opt: any) => opt !== "keep_null");
                      }
                    }

                    return (
                      <div
                        key={qKey}
                        className={`pt-4 ${qi === 0 ? "pt-0" : ""} text-left`}
                      >
                        <p className="text-sm font-medium text-foreground mb-3 leading-snug">
                          {qi + 1}. {formatDisplayValue(q.question)}
                        </p>

                        {isStrategy ? (
                          <div className="space-y-3">
                            <div className="space-y-3 pl-2">
                              {optionsToRender.map((opt: any) => {
                                const optionLabel = formatDisplayValue(opt);
                                const isSelected = selectedVal === optionLabel;
                                const optConsequence = getOptionConsequence(
                                  q.consequences,
                                  optionLabel,
                                );
                                return (
                                  <div key={optionLabel} className="space-y-2">
                                    <label
                                      className={`flex items-start gap-2.5 text-sm cursor-pointer rounded-lg px-3 py-2.5 border transition-all ${
                                        isSelected
                                          ? "bg-primary/5 border-primary/40 shadow-sm"
                                          : "bg-transparent border-border/60 hover:bg-muted/30"
                                      }`}
                                    >
                                      <input
                                        type="radio"
                                        name={key}
                                        value={optionLabel}
                                        checked={isSelected}
                                        onChange={() =>
                                          handleSelectAnswer(key, optionLabel)
                                        }
                                        disabled={!isAwaiting}
                                        className="text-primary mt-0.5 shrink-0"
                                      />
                                      <span className="leading-snug">
                                        {optionLabel}
                                      </span>
                                    </label>
                                    {isSelected && optConsequence && (
                                      <div className="ml-6 p-3 rounded-lg bg-indigo-50/40 border border-indigo-100/50 text-xs text-indigo-950/90 leading-relaxed flex flex-col gap-2 animate-fadeIn">
                                        <div className="flex items-start gap-2">
                                          <TextIcon className="w-4 h-4 text-indigo-500 shrink-0 mt-0.5">
                                            !
                                          </TextIcon>
                                          <div>
                                            <strong className="font-semibold text-indigo-900 block mb-0.5">
                                              Consequence:
                                            </strong>
                                            {formatDisplayValue(optConsequence)}
                                          </div>
                                        </div>
                                        {optionLabel.includes("Custom strategy") && (
                                          <div className="mt-2 w-full">
                                            <input
                                              type="text"
                                              value={customInputs[key] || ""}
                                              onChange={(e) =>
                                                handleCustomInputChange(key, e.target.value)
                                              }
                                              placeholder="E.g. fill with 'Unknown', drop the row..."
                                              className="w-full text-sm rounded-md border border-indigo-200 px-3 py-2 bg-white text-foreground focus:outline-none focus:ring-2 focus:ring-indigo-500/50"
                                              disabled={!isAwaiting}
                                            />
                                          </div>
                                        )}
                                      </div>
                                    )}
                                  </div>
                                );
                              })}
                            </div>
                          </div>
                        ) : (
                          <div className="space-y-3">
                            {q.insight && (
                              <div className="text-xs bg-muted/40 p-2.5 rounded border border-border/40 text-muted-foreground italic mb-2 leading-relaxed">
                                💡 {formatDisplayValue(q.insight)}
                              </div>
                            )}
                            <div className="flex gap-4 pl-2">
                              {["Yes", "No"].map((opt) => (
                                <label
                                  key={opt}
                                  className={`flex items-center gap-2 text-sm cursor-pointer rounded-lg px-4 py-2 border transition-all ${
                                    selectedVal === opt
                                      ? "bg-primary/5 border-primary/40 shadow-sm"
                                      : "bg-transparent border-border/60 hover:bg-muted/30"
                                  }`}
                                >
                                  <input
                                    type="radio"
                                    name={key}
                                    value={opt}
                                    checked={selectedVal === opt}
                                    onChange={() =>
                                      handleSelectAnswer(key, opt)
                                    }
                                    disabled={!isAwaiting}
                                    className="text-primary"
                                  />
                                  {opt}
                                </label>
                              ))}
                            </div>
                          </div>
                        )}
                      </div>
                    );
                  })}
              </div>
            </div>
          );
        })}
      </div>

      {isAwaiting && (
        <StepFooter
          currentStep={1}
          statusText={`Answered ${answeredCount} of ${totalQuestions} questions`}
        >
          <button
            type="button"
            onClick={handleSubmit}
            disabled={isPending || !allAnswered}
            className="w-full sm:w-auto inline-flex items-center justify-center gap-2 bg-emerald-600 hover:bg-emerald-700 text-white px-6 py-2.5 rounded-lg text-sm font-semibold transition-all shadow-sm hover:shadow-md disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Continue →
          </button>
        </StepFooter>
      )}
    </div>
  );
};

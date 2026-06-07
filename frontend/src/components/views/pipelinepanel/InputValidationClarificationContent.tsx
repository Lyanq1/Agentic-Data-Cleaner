import React, { useState, useMemo } from "react";
import { StepFooter } from "./StepFooter";
import { TextIcon } from "./TextIcon";
import { getOptionConsequence } from "./utils";

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

  const handleSelectAnswer = (key: string, val: string) => {
    setAnswers((prev) => ({ ...prev, [key]: val }));
  };

  const totalQuestions = useMemo(() => {
    let count = 0;
    categories.forEach((cat) => {
      const catData = clarifications[cat];
      if (catData) {
        count += Object.keys(catData).length;
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
          if (answers[`${cat}.${qKey}`]) {
            count += 1;
          }
        });
      }
    });
    return count;
  }, [clarifications, answers]);

  const allAnswered = answeredCount === totalQuestions;

  const handleSubmit = () => {
    onDecision("approve", "User resolved all clarifications", answers);
  };

  return (
    <div className="space-y-6">
      {payload.reasoning && (
        <div className="rounded-xl border bg-muted/30 p-4 text-sm leading-relaxed text-muted-foreground">
          <strong className="text-foreground block mb-1">Reasoning:</strong>
          {payload.reasoning}
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
                    const key = `${cat}.${qKey}`;
                    const selectedVal = answers[key] || "";
                    const isStrategy = "options" in q;

                    return (
                      <div
                        key={qKey}
                        className={`pt-4 ${qi === 0 ? "pt-0" : ""} text-left`}
                      >
                        <p className="text-sm font-medium text-foreground mb-3 leading-snug">
                          {qi + 1}. {q.question}
                        </p>

                        {isStrategy ? (
                          <div className="space-y-3">
                            <div className="space-y-3 pl-2">
                              {(q.options || []).map((opt: string) => {
                                const isSelected = selectedVal === opt;
                                const optConsequence = getOptionConsequence(
                                  q.consequences,
                                  opt,
                                );
                                return (
                                  <div key={opt} className="space-y-2">
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
                                        value={opt}
                                        checked={isSelected}
                                        onChange={() =>
                                          handleSelectAnswer(key, opt)
                                        }
                                        disabled={!isAwaiting}
                                        className="text-primary mt-0.5 shrink-0"
                                      />
                                      <span className="leading-snug">
                                        {opt}
                                      </span>
                                    </label>
                                    {isSelected && optConsequence && (
                                      <div className="ml-6 p-3 rounded-lg bg-indigo-50/40 border border-indigo-100/50 text-xs text-indigo-950/90 leading-relaxed flex items-start gap-2 animate-fadeIn">
                                        <TextIcon className="w-4 h-4 text-indigo-500 shrink-0 mt-0.5">
                                          !
                                        </TextIcon>
                                        <div>
                                          <strong className="font-semibold text-indigo-900 block mb-0.5">
                                            Consequence:
                                          </strong>
                                          {optConsequence}
                                        </div>
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
                                💡 {q.insight}
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

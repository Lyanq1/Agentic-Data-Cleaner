import React, { useState, useMemo, useEffect } from "react";
import { StepFooter } from "./StepFooter";
import { TextIcon } from "./TextIcon";
import { formatDisplayValue, getOptionConsequence, renderHighlightedText, tryFormatToISO } from "./utils";
import {
  filterStrategiesForFinalDataType,
  finalDataTypeToValidationType,
  getFillValueOptionsForColumn,
  resolveColumnFinalDataType,
} from "./clarificationDtypes";

export const InputValidationClarificationContent: React.FC<{
  payload: any;
  isAwaiting: boolean;
  onDecision: (
    d: "approve" | "reject" | "modify",
    fb?: string,
    disambiguationAnswers?: Record<string, string | string[]>,
  ) => void;
  onAnswerChange: (answers: Record<string, string | null>) => void;
  isPending: boolean;
}> = ({ payload, isAwaiting, onDecision, onAnswerChange, isPending }) => {
  const clarifications = payload.clarifications || {};
  const categories = ["typecast", "null", "duplicate"] as const;

  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [fillValueSubOption, setFillValueSubOption] = useState<Record<string, string>>({});
  const [fillValueCustom, setFillValueCustom] = useState<Record<string, string>>({});
  const hasInitializedRef = React.useRef(false);

  const allDatasetColumns = useMemo(() => {
    const cols = new Set<string>();
    if (payload?.data_profile?.columns) {
      Object.keys(payload.data_profile.columns).forEach((c) => cols.add(c));
    }
    if (payload?.semantic_profile?.columns) {
      Object.keys(payload.semantic_profile.columns).forEach((c) => cols.add(c));
    }
    if (payload?.dataset_schema) {
      Object.keys(payload.dataset_schema).forEach((c) => cols.add(c));
    }
    categories.forEach((cat) => {
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
  }, [payload, clarifications]);

  const getFillValueSubOptions = (
    colName: string,
    currentAnswers?: Record<string, string>,
  ) => getFillValueOptionsForColumn(payload, colName, currentAnswers ?? answers);

  const getColumnFinalValidationType = (qKey: string, currentAnswers?: Record<string, string>): string => {
    const colName = qKey.startsWith("Q2_strategy_column_")
      ? qKey.substring("Q2_strategy_column_".length)
      : qKey.startsWith("Q1_allow_missing_column_")
        ? qKey.substring("Q1_allow_missing_column_".length)
        : qKey.startsWith("Q1_cast_column_")
          ? qKey.substring("Q1_cast_column_".length)
          : "";
    if (!colName) return "str";
    return finalDataTypeToValidationType(
      resolveColumnFinalDataType(payload, colName, currentAnswers ?? answers),
    );
  };

  useEffect(() => {
    if (hasInitializedRef.current) return;

    const nextAnswers: Record<string, string> = {};
    const nextFillValueSubOption: Record<string, string> = {};
    const nextFillValueCustom: Record<string, string> = {};
    categories.forEach((cat) => {
      const catData = clarifications[cat];
      if (catData) {
        Object.keys(catData).forEach((qKey) => {
          const q = catData[qKey];
          if (q) {
            const ansVal = q.answer || q.previous_answer;
            if (ansVal) {
              if (ansVal === "fill_value") {
                nextAnswers[`${cat}.${qKey}`] = "fill_value";
                const colName = qKey.startsWith("Q2_strategy_column_")
                  ? qKey.substring("Q2_strategy_column_".length)
                  : "";
                if (colName) {
                  const subOpts = getFillValueSubOptions(colName, nextAnswers);
                  nextFillValueSubOption[`${cat}.${qKey}`] =
                    subOpts[0]?.value ?? "custom";
                }
              } else if (ansVal.startsWith("fill_value:")) {
                const val = ansVal.substring("fill_value:".length).trim();
                nextAnswers[`${cat}.${qKey}`] = "fill_value";
                const colName = qKey.startsWith("Q2_strategy_column_")
                  ? qKey.substring("Q2_strategy_column_".length)
                  : "";
                if (colName) {
                  const subOpts = getFillValueSubOptions(colName, nextAnswers);
                  const matchingOpt = subOpts.find(o => o.value === val);
                  if (matchingOpt && val !== "custom") {
                    nextFillValueSubOption[`${cat}.${qKey}`] = val;
                  } else {
                    nextFillValueSubOption[`${cat}.${qKey}`] = "custom";
                    const expectedType = getColumnFinalValidationType(qKey, nextAnswers);
                    nextFillValueCustom[`${cat}.${qKey}`] = tryFormatToISO(val, expectedType);
                  }
                }
              } else {
                nextAnswers[`${cat}.${qKey}`] = ansVal;
              }
            }
          }
        });
      }
    });
    setAnswers(nextAnswers);
    setFillValueSubOption(nextFillValueSubOption);
    setFillValueCustom(nextFillValueCustom);
    hasInitializedRef.current = true;
  }, [payload, clarifications, categories]);

  const handleSelectAnswer = (key: string, val: string) => {
    const nextAnswers = { ...answers, [key]: val };
    const answerUpdates: Record<string, string | null> = { [key]: val };

    if (key.startsWith("null.Q1_allow_missing_column_")) {
      const colName = key.substring("null.Q1_allow_missing_column_".length);
      const q2Key = `null.Q2_strategy_column_${colName}`;
      if (val === "No" && nextAnswers[q2Key] === "keep_null") {
        delete nextAnswers[q2Key];
        answerUpdates[q2Key] = null;
      }
    }

    if (key.startsWith("typecast.Q1_cast_column_")) {
      const colName = key.substring("typecast.Q1_cast_column_".length);
      const nullAnswerKey = `null.Q2_strategy_column_${colName}`;
      const nullQuestion =
        clarifications.null?.[`Q2_strategy_column_${colName}`];
      const finalDataType = resolveColumnFinalDataType(
        payload,
        colName,
        nextAnswers,
      );
      const compatibleOptions = filterStrategiesForFinalDataType(
        [...(nullQuestion?.options || [])],
        finalDataType,
      ).map((option) => formatDisplayValue(option));

      if (
        nextAnswers[nullAnswerKey] &&
        !compatibleOptions.includes(nextAnswers[nullAnswerKey])
      ) {
        delete nextAnswers[nullAnswerKey];
        answerUpdates[nullAnswerKey] = null;
      }

      const selectedFillValue = fillValueSubOption[nullAnswerKey];
      const fillOptions = getFillValueSubOptions(colName, nextAnswers);
      const nextFillValue =
        selectedFillValue === "custom" ||
        (selectedFillValue &&
          fillOptions.some((option) => option.value === selectedFillValue))
          ? selectedFillValue
          : (fillOptions[0]?.value ?? "custom");
      setFillValueSubOption((prev) => ({
        ...prev,
        [nullAnswerKey]: nextFillValue,
      }));

      if (
        nextAnswers[nullAnswerKey] === "fill_value" &&
        nextFillValue !== "custom"
      ) {
        answerUpdates[nullAnswerKey] = `fill_value: ${nextFillValue}`;
      }
    }

    setAnswers(nextAnswers);

    if (val === "fill_value" && !fillValueSubOption[key]) {
      const parts = key.split(".");
      if (parts.length === 2 && parts[1].startsWith("Q2_strategy_column_")) {
        const colName = parts[1].substring("Q2_strategy_column_".length);
        const subOpts = getFillValueSubOptions(colName, nextAnswers);
        if (subOpts.length > 0) {
          setFillValueSubOption((prev) => ({ ...prev, [key]: subOpts[0].value }));
          if (subOpts[0].value !== "custom") {
            answerUpdates[key] = `fill_value: ${subOpts[0].value}`;
          }
        }
      }
    }

    onAnswerChange(answerUpdates);
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
              answers[key] === "fill_value" &&
              fillValueSubOption[key] === "custom" &&
              !fillValueCustom[key]?.trim()
            ) {
              // Must provide text for custom fill value
            } else {
              count += 1;
            }
          }
        });
      }
    });
    return count;
  }, [clarifications, answers, fillValueSubOption, fillValueCustom]);

  const allAnswered = answeredCount === totalQuestions;

  const handleSubmit = () => {
    const finalAnswers = { ...answers };
    let hasChanges = false;
    const nextFillValueCustom = { ...fillValueCustom };

    Object.keys(finalAnswers).forEach((key) => {
      const qKey = key.split(".")[1];
      const expectedType = getColumnFinalValidationType(qKey, finalAnswers);

      if (finalAnswers[key] === "fill_value") {
        const colName = qKey.startsWith("Q2_strategy_column_")
          ? qKey.substring("Q2_strategy_column_".length)
          : "";
        const subOpt =
          fillValueSubOption[key] ||
          getFillValueSubOptions(colName, finalAnswers)[0]?.value ||
          "custom";
        if (subOpt === "custom") {
          const val = tryFormatToISO(fillValueCustom[key] || "", expectedType);
          finalAnswers[key] = `fill_value: ${val.trim()}`;
          if (val !== fillValueCustom[key]) {
            nextFillValueCustom[key] = val;
            hasChanges = true;
          }
        } else {
          finalAnswers[key] = `fill_value: ${subOpt}`;
        }
      }
    });

    if (hasChanges) {
      setFillValueCustom(nextFillValueCustom);
    }

    onDecision("approve", "User resolved all clarifications", finalAnswers);
  };

  return (
    <div className="space-y-6">
      {payload.reasoning && (
        <div className="rounded-xl border bg-muted/30 p-4 text-sm leading-relaxed text-muted-foreground">
          <strong className="text-foreground block mb-1">Reasoning:</strong>
          {renderHighlightedText(formatDisplayValue(payload.reasoning), undefined, allDatasetColumns)}
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
                    let optionsToRender = [...(q.options || [])].filter(
                      (opt: any) =>
                        typeof opt !== "string" ||
                        (!opt.toLowerCase().includes("custom strategy") && !opt.toLowerCase().includes("custom prompt"))
                    );

                    const colName = qKey.startsWith("Q2_strategy_column_")
                      ? qKey.substring("Q2_strategy_column_".length)
                      : qKey.startsWith("Q1_allow_missing_column_")
                        ? qKey.substring("Q1_allow_missing_column_".length)
                        : qKey.startsWith("Q1_cast_column_")
                          ? qKey.substring("Q1_cast_column_".length)
                          : "";

                    if (cat === "null" && qKey.startsWith("Q2_strategy_column_")) {
                      // 1. Filter out keep_null if allow_missing is answered "No"
                      const q1Key = `null.Q1_allow_missing_column_${colName}`;
                      const q1Answer = answers[q1Key];
                      if (q1Answer === "No") {
                        optionsToRender = optionsToRender.filter((opt: any) => opt !== "keep_null");
                      }

                      // 2. Keep the backend semantic options, then remove
                      // strategies incompatible with the user's final dtype.
                      optionsToRender = filterStrategiesForFinalDataType(
                        optionsToRender,
                        resolveColumnFinalDataType(payload, colName, answers),
                      );
                    }

                    return (
                      <div
                        key={qKey}
                        className={`pt-4 ${qi === 0 ? "pt-0" : ""} text-left`}
                      >
                        <p className="text-sm font-medium text-foreground mb-3 leading-snug">
                          {qi + 1}. {renderHighlightedText(formatDisplayValue(q.question), colName, allDatasetColumns)}
                        </p>

                        {q.error && (
                          <div className="mb-4 px-3 py-2.5 text-xs text-rose-600 bg-rose-50 border border-rose-200 rounded-lg font-medium leading-relaxed">
                            ⚠️ {formatDisplayValue(q.error)}
                          </div>
                        )}

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
                                    {isSelected && optionLabel === "fill_value" && (
                                      <div className="ml-6 p-3 rounded-lg bg-indigo-50/40 border border-indigo-100/50 text-md text-indigo-950/90 leading-relaxed flex flex-col gap-3 animate-fadeIn">
                                        {optConsequence && (
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
                                        )}
                                        <div className="border-t border-indigo-100/50 pt-2 space-y-2">
                                          <p className="text-xs font-semibold text-indigo-900/80 uppercase tracking-wider">
                                            Select or enter a fill value:
                                          </p>
                                          <div className="flex flex-wrap gap-2">
                                            {getFillValueSubOptions(colName).map((subOpt) => {
                                              const isSubSelected = fillValueSubOption[key] === subOpt.value;
                                              return (
                                                <label
                                                  key={subOpt.value}
                                                  className={`flex items-center gap-2 text-xs cursor-pointer rounded-full px-3 py-1.5 border transition-all ${
                                                    isSubSelected
                                                      ? "bg-indigo-600 border-indigo-600 text-white shadow-sm font-medium"
                                                      : "bg-white border-indigo-100 hover:border-indigo-300 text-indigo-900"
                                                  }`}
                                                >
                                                  <input
                                                    type="radio"
                                                    name={`${key}_sub`}
                                                    value={subOpt.value}
                                                    checked={isSubSelected}
                                                    onChange={() => {
                                                      setFillValueSubOption((prev) => ({
                                                        ...prev,
                                                        [key]: subOpt.value,
                                                      }));
                                                      onAnswerChange({
                                                        [key]:
                                                          subOpt.value === "custom"
                                                            ? "fill_value"
                                                            : `fill_value: ${subOpt.value}`,
                                                      });
                                                    }}
                                                    disabled={!isAwaiting}
                                                    className="sr-only"
                                                  />
                                                  {subOpt.label}
                                                </label>
                                              );
                                            })}
                                          </div>
                                          {fillValueSubOption[key] === "custom" && (
                                            <div className="mt-2 w-full animate-fadeIn">
                                              <input
                                                type="text"
                                                value={fillValueCustom[key] || ""}
                                                onChange={(e) =>
                                                  setFillValueCustom((prev) => ({ ...prev, [key]: e.target.value }))
                                                }
                                                onBlur={(e) => {
                                                  const expectedType = getColumnFinalValidationType(qKey, answers);
                                                  const formatted = tryFormatToISO(e.target.value, expectedType);
                                                  if (formatted !== e.target.value) {
                                                    setFillValueCustom((prev) => ({ ...prev, [key]: formatted }));
                                                  }
                                                  if (formatted.trim()) {
                                                    onAnswerChange({
                                                      [key]: `fill_value: ${formatted.trim()}`,
                                                    });
                                                  }
                                                }}
                                                placeholder="E.g. 'yesterday', 'unknown', or any value..."
                                                className="w-full text-sm rounded-md border border-indigo-200 px-3 py-2 bg-white text-foreground focus:outline-none focus:ring-2 focus:ring-indigo-500/50"
                                                disabled={!isAwaiting}
                                              />
                                              <p className="text-[10px] text-indigo-700/80 mt-1 italic">
                                                Tip: You can write any custom value or describe it in natural language.
                                              </p>
                                            </div>
                                          )}
                                        </div>
                                      </div>
                                    )}
                                    {isSelected && optionLabel !== "fill_value" && optConsequence && (
                                      <div className="ml-6 p-3 rounded-lg bg-indigo-50/40 border border-indigo-100/50 text-md text-indigo-950/90 leading-relaxed flex flex-col gap-2 animate-fadeIn">
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
                              <div className="text-sm bg-muted/40 p-2.5 rounded border border-border/40 text-muted-foreground italic mb-2 leading-relaxed">
                                💡 {renderHighlightedText(formatDisplayValue(q.insight), colName, allDatasetColumns)}
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

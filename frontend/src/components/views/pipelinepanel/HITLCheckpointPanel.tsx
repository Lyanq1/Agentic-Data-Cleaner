import React, { useState, useMemo, useEffect } from "react";
import { RequirementSummaryPanel } from "../RequirementSummaryPanel";
import { SpinnerIcon } from "./SpinnerIcon";
import { TextIcon } from "./TextIcon";
import { TaskCard } from "./TaskCard";
import { InputValidationClarificationContent } from "./InputValidationClarificationContent";
import { SEVERITY_STYLES, formatDisplayValue } from "./utils";
import { ValidationReviewPanel } from "./ValidationReviewPanel";
import { WorkerValidatorFlow } from "./ExecutionPlanPanel";
import { Panel } from "../../ui/Panel";
import { Button } from "../../ui/Button";
import { StickyActionBar } from "../../ui/StickyActionBar";

export const HITLCheckpointPanel: React.FC<{
  checkpoint: any;
  pipelineState?: any;
  userRequirementsText?: string;
  feedback: string;
  onFeedbackChange: (v: string) => void;
  onDecision: (
    d: "approve" | "reject" | "modify",
    fb?: string,
    disambiguationAnswers?: Record<string, string | string[]>,
  ) => void;
  isPending: boolean;
  isAwaiting: boolean;
}> = ({
  checkpoint,
  pipelineState,
  userRequirementsText,
  feedback,
  onFeedbackChange,
  onDecision,
  isPending,
  isAwaiting,
}) => {
  const payload = checkpoint.payload || {};
  const isRequirementApproval =
    checkpoint.checkpoint_type === "requirement_approval";
  const isPlanApproval = checkpoint.checkpoint_type === "plan_approval";
  const isInputValidationClarification =
    checkpoint.checkpoint_type === "input_validation_clarification";
  const modifyCount = isRequirementApproval
    ? (payload.requirement_modify_count ?? 0)
    : (payload.modify_count ?? 0);
  const maxModify = payload.max_modify_cycles as number | undefined;
  const canModify = isRequirementApproval
    ? true
    : maxModify == null || modifyCount < maxModify;

  const plan = payload.plan || {};
  const colSelection = payload.column_selection || {};
  const [showRawJson, setShowRawJson] = useState(false);
  const [mcqAnswers, setMcqAnswers] = useState<Record<string, string>>({});
  const [mcqClarifyText, setMcqClarifyText] = useState<Record<string, string>>(
    {},
  );

  useEffect(() => {
    setMcqAnswers({});
    setMcqClarifyText({});
  }, [checkpoint?.checkpoint_id]);

  const isClarifyValue = (value: string) =>
    value === "clarify" || value.toLowerCase().startsWith("clarify:");

  const isClarifySelected = (questionId: string) => {
    const raw = mcqAnswers[questionId] || "";
    if (raw === "clarify" || raw.toLowerCase().startsWith("clarify:"))
      return true;
    return raw.split(",").some((v) => isClarifyValue(v.trim()));
  };

  const hasColumnSelection = (questionId: string) => {
    const raw = mcqAnswers[questionId] || "";
    return raw
      .split(",")
      .map((v) => v.trim())
      .some((v) => v && !isClarifyValue(v));
  };

  const disambiguationQuestions: any[] =
    payload.disambiguation_questions ||
    payload.requirement_validation?.disambiguation_questions ||
    [];
  const comparisonNotes: any[] =
    payload.comparison_notes ||
    payload.requirement_validation?.comparison_notes ||
    [];

  const questionAllowsMultiple = (q: any) => {
    if (q?.allow_multiple === true) return true;
    if (q?.allow_multiple === false) return false;
    return [
      "column_select",
      "imputation_target",
      "column_drop",
      "general",
    ].includes(q?.category);
  };

  const requiredMcqIds = disambiguationQuestions
    .filter((q: any) => q.required !== false)
    .map((q: any) => q.question_id);
  const allMcqAnswered =
    requiredMcqIds.length === 0 ||
    requiredMcqIds.every((id: string) => {
      const q = disambiguationQuestions.find((x: any) => x.question_id === id);
      if (isClarifySelected(id)) {
        return Boolean(mcqClarifyText[id]?.trim());
      }
      if (questionAllowsMultiple(q)) {
        return hasColumnSelection(id);
      }
      return Boolean(mcqAnswers[id]?.trim());
    });

  const toggleMultiMcq = (
    questionId: string,
    value: string,
    checked: boolean,
  ) => {
    const isClarify = isClarifyValue(value);
    setMcqAnswers((prev) => {
      if (isClarify) {
        if (!checked) {
          setMcqClarifyText((t) => {
            const next = { ...t };
            delete next[questionId];
            return next;
          });
        }
        return { ...prev, [questionId]: checked ? value : "" };
      }
      const current = prev[questionId]
        ? prev[questionId]
            .split(",")
            .map((s) => s.trim())
            .filter(Boolean)
        : [];
      const withoutClarify = current.filter((v) => !isClarifyValue(v));
      const next = checked
        ? [...new Set([...withoutClarify, value])]
        : withoutClarify.filter((v) => v !== value);
      return { ...prev, [questionId]: next.join(",") };
    });
  };

  const buildMcqPayload = () => {
    const answers: Record<string, string | string[]> = {};
    const feedbackParts: string[] = [];

    for (const q of disambiguationQuestions) {
      const qid = q.question_id;
      const raw = mcqAnswers[qid] || "";
      const clarifyText = mcqClarifyText[qid]?.trim() || "";

      if (isClarifySelected(qid)) {
        const tokens: string[] = [];
        if (hasColumnSelection(qid)) {
          raw
            .split(",")
            .map((s) => s.trim())
            .filter((v) => v && !isClarifyValue(v))
            .forEach((v) => tokens.push(v));
        }
        if (clarifyText) {
          tokens.push(`clarify:${clarifyText}`);
          feedbackParts.push(`${q.prompt}\n${clarifyText}`);
        }
        if (tokens.length) {
          answers[qid] = tokens;
        }
        continue;
      }

      if (!raw.trim()) continue;

      if (questionAllowsMultiple(q)) {
        const parts = raw.includes(",")
          ? raw
              .split(",")
              .map((s) => s.trim())
              .filter(Boolean)
          : [raw.trim()];
        answers[qid] = parts;
      } else {
        answers[qid] = raw;
      }
    }

    const feedback =
      feedbackParts.length > 0 ? feedbackParts.join("\n\n") : undefined;
    return {
      answers: Object.keys(answers).length ? answers : undefined,
      feedback,
    };
  };

  const submitWithMcq = (
    decision: "approve" | "reject" | "modify",
    fb?: string,
  ) => {
    const { answers, feedback: clarifyFeedback } = buildMcqPayload();
    const mergedFeedback =
      [fb, clarifyFeedback].filter(Boolean).join("\n\n") || undefined;
    onDecision(decision, mergedFeedback, answers);
  };

  const allTasks = useMemo(() => {
    const tasks: { task: any; phase: string }[] = [];
    (plan.sequential_tasks || []).forEach((t: any) =>
      tasks.push({ task: t, phase: "Sequential" }),
    );
    (plan.parallel_task_groups || []).forEach((group: any[], gi: number) =>
      group.forEach((t: any) =>
        tasks.push({ task: t, phase: `Parallel #${gi + 1}` }),
      ),
    );
    return tasks;
  }, [plan]);

  const issues: any[] =
    payload.issues || payload.validation_result?.issues || [];
  // const metrics = payload.metrics || payload.validation_result?.metrics || {};
  const validationPassed = payload.validation_result?.passed;

  const spec = payload.structured_cleaning_spec || {};
  const reqErrors: string[] =
    payload.errors || payload.requirement_validation?.errors || [];
  const reqWarnings: string[] =
    payload.warnings || payload.requirement_validation?.warnings || [];
  const openQuestions: string[] =
    payload.open_questions || spec.open_questions || [];

  const requirementConfirmDisabled =
    isRequirementApproval &&
    disambiguationQuestions.length > 0 &&
    !allMcqAnswered;

  const headerConfig = isInputValidationClarification
    ? {
        title: "Input Validator Clarifications",
        subtitle:
          "Please answer the following clarification questions about your dataset",
      }
    : isRequirementApproval
      ? {
          title: "Confirm requirements",
          subtitle:
            "Review the interpretation below, answer any prompts, then confirm or cancel",
        }
      : isPlanApproval
        ? {
            title: "Plan Review Required",
            subtitle: "The AI has generated a cleaning plan for your approval",
          }
        : {
            title: "Validation Review Required",
            subtitle: "Persistent quality issues were found after processing",
          };

  return (
    <Panel
      className={`mb-8 text-left animate-fadeIn overflow-hidden ${
        isAwaiting ? "border-warning/50 bg-warning/5" : ""
      }`}
    >
      <div className="border-b px-6 py-4 flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold text-foreground">
            {headerConfig.title}
          </h3>
          <p className="text-xs text-muted-foreground mt-0.5">{headerConfig.subtitle}</p>
        </div>
        {modifyCount > 0 && (
          <span className="ml-auto text-xs bg-muted text-muted-foreground border rounded-md px-2.5 py-1 font-medium">
            {isRequirementApproval
              ? `Clarifications: ${modifyCount}`
              : `Revision ${modifyCount}${maxModify != null ? `/${maxModify}` : ""}`}
          </span>
        )}
      </div>

      <div className="p-6 space-y-6 relative">
        {isPending && (
          <div className="absolute inset-0 z-10 bg-background/85 backdrop-blur-[2px] flex flex-col items-center justify-center">
            <SpinnerIcon className="w-10 h-10 text-primary mb-4" />
            <div className="text-base font-bold text-foreground">
              Processing your decision...
            </div>
            <div className="text-sm text-muted-foreground mt-1">
              Please wait while the agents resume...
            </div>
          </div>
        )}

        {isInputValidationClarification && (
          <InputValidationClarificationContent
            key={checkpoint?.checkpoint_id}
            payload={payload}
            isAwaiting={isAwaiting}
            onDecision={onDecision}
            isPending={isPending}
          />
        )}

        {isRequirementApproval && (
          <>
            <RequirementSummaryPanel
              userRequirementsText={userRequirementsText}
              spec={spec}
              validation={payload.requirement_validation}
              compact
            />

            {checkpoint.message_to_user && (
              <p className="text-sm text-muted-foreground whitespace-pre-line rounded-lg border bg-muted/30 p-3">
                {formatDisplayValue(checkpoint.message_to_user)}
              </p>
            )}

            {openQuestions.length > 0 &&
              disambiguationQuestions.length === 0 && (
                <div className="rounded-lg bg-warning/5 border border-warning/30 p-4">
                  <h4 className="text-xs font-semibold text-warning-foreground mb-2">
                    Questions for you
                  </h4>
                  <ul className="list-disc pl-5 space-y-1 text-xs text-foreground">
                    {openQuestions.map((q: any, i: number) => (
                      <li key={i}>{formatDisplayValue(q)}</li>
                    ))}
                  </ul>
                </div>
              )}

            {reqErrors.length > 0 && (
              <div className="rounded-lg bg-destructive/5 border border-destructive/30 p-4">
                <h4 className="text-xs font-semibold text-destructive-foreground mb-2">
                  Blocking issues
                </h4>
                <ul className="list-disc pl-5 space-y-1 text-xs text-foreground">
                  {reqErrors.map((e: any, i: number) => (
                    <li key={i}>{formatDisplayValue(e)}</li>
                  ))}
                </ul>
              </div>
            )}

            {comparisonNotes.length > 0 && (
              <div className="rounded-lg border bg-card p-4">
                <h4 className="text-xs font-semibold text-muted-foreground mb-2">
                  Requirement vs EDA
                </h4>
                <ul className="space-y-2 text-xs">
                  {comparisonNotes.map((n: any, i: number) => (
                    <li key={i} className="flex gap-2">
                      <span
                        className={`text-[9px] font-bold uppercase px-1.5 py-0.5 rounded border ${SEVERITY_STYLES[n.severity] || SEVERITY_STYLES.info}`}
                      >
                        {formatDisplayValue(n.severity)}
                      </span>
                      <span className="text-foreground">{formatDisplayValue(n.message)}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {disambiguationQuestions.length > 0 && (
              <div className="rounded-lg border bg-muted/5 p-4 space-y-3">
                <h4 className="text-xs font-semibold text-foreground">
                  Your choices
                </h4>
                {disambiguationQuestions.map((q: any) => {
                  const multi = questionAllowsMultiple(q);
                  const qid = q.question_id;
                  const selectedValues = mcqAnswers[qid]
                    ? mcqAnswers[qid].split(",").map((s: string) => s.trim())
                    : [];
                  const clarifySelected = isClarifySelected(qid);
                  const clarifyOnly =
                    clarifySelected && !hasColumnSelection(qid);
                  return (
                    <div
                      key={qid}
                      role="group"
                      aria-labelledby={`mcq-label-${qid}`}
                      className="rounded-lg border border-border bg-card p-4 flex flex-col gap-4"
                    >
                      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 lg:gap-6 items-start">
                        <div id={`mcq-label-${qid}`}>
                          <p className="text-xs font-medium text-foreground leading-snug">
                            {formatDisplayValue(q.prompt)}
                          </p>
                          {multi && !clarifyOnly && (
                            <p className="text-[10px] font-normal text-muted-foreground mt-1">
                              Select one or more
                            </p>
                          )}
                        </div>
                        <div className="space-y-1 lg:border-l lg:border-border lg:pl-5 min-w-0">
                          {(q.options || []).map((opt: any) => {
                            const optionValue = formatDisplayValue(opt.value ?? opt.option_id ?? opt.label);
                            const optionLabel = formatDisplayValue(opt.label ?? opt.value);
                            return (
                              <label
                                key={formatDisplayValue(opt.option_id, optionValue)}
                                className="flex items-start gap-2.5 text-xs cursor-pointer rounded px-2 py-1.5 hover:bg-muted"
                              >
                                <input
                                  type={multi ? "checkbox" : "radio"}
                                  name={qid}
                                  value={optionValue}
                                  checked={
                                    multi
                                      ? selectedValues.includes(optionValue)
                                      : mcqAnswers[qid] === optionValue
                                  }
                                  onChange={() =>
                                    multi
                                      ? toggleMultiMcq(
                                          qid,
                                          optionValue,
                                          !selectedValues.includes(optionValue),
                                        )
                                      : setMcqAnswers((prev) => {
                                          if (isClarifyValue(optionValue)) {
                                            setMcqClarifyText((t) => {
                                              const next = { ...t };
                                              delete next[qid];
                                              return next;
                                            });
                                          }
                                          return { ...prev, [qid]: optionValue };
                                        })
                                  }
                                  disabled={!isAwaiting}
                                  className="text-primary mt-0.5 shrink-0"
                                />
                                <span className="leading-snug text-foreground">{optionLabel}</span>
                              </label>
                            );
                          })}
                        </div>
                      </div>
                      {clarifySelected && (
                        <div className="w-full border-t border-border pt-3">
                          <label
                            htmlFor={`clarify-${qid}`}
                            className="block text-[10px] font-semibold text-foreground mb-1.5"
                          >
                            Describe what you need
                          </label>
                          <textarea
                            id={`clarify-${qid}`}
                            value={mcqClarifyText[qid] || ""}
                            onChange={(e) =>
                              setMcqClarifyText((prev) => ({
                                ...prev,
                                [qid]: e.target.value,
                              }))
                            }
                            disabled={!isAwaiting}
                            placeholder="Type your clarification here — we will re-check your requirements after you confirm."
                            className="w-full min-h-[4.5rem] max-h-[40vh] sm:max-h-[12rem] resize-y rounded-lg border border-input bg-background px-3 py-2.5 text-xs leading-relaxed placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:opacity-60 text-foreground"
                          />
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}

            {isAwaiting && (
              <StickyActionBar position="bottom" className="px-6 py-4 bg-card/95 border-t flex flex-col sm:flex-row gap-3">
                <Button
                  type="button"
                  onClick={() => submitWithMcq("approve")}
                  disabled={isPending || requirementConfirmDisabled}
                  title={
                    requirementConfirmDisabled
                      ? "Select options or type a clarification for each prompt"
                      : undefined
                  }
                  className="flex-1 cursor-pointer"
                >
                  Confirm
                </Button>
                <Button
                  type="button"
                  onClick={() => submitWithMcq("reject")}
                  disabled={isPending}
                  variant="outline"
                  className="flex-1 cursor-pointer"
                >
                  Cancel
                </Button>
              </StickyActionBar>
            )}

            {!isAwaiting && (
              <div className="flex items-center justify-center py-2 px-4 bg-success/5 border border-success/30 rounded-md text-success text-xs font-medium gap-2">
                <TextIcon>OK</TextIcon>
                Decision recorded. Pipeline is proceeding.
              </div>
            )}

            {reqWarnings.length > 0 && (
              <div className="rounded-lg border bg-card p-4">
                <h4 className="text-xs font-semibold text-muted-foreground mb-2">
                  Warnings
                </h4>
                <ul className="list-disc pl-5 space-y-1 text-xs text-foreground">
                  {reqWarnings.map((w: any, i: number) => (
                    <li key={i}>{formatDisplayValue(w)}</li>
                  ))}
                </ul>
              </div>
            )}

            {spec.columns_mapping?.length > 0 && (
              <div className="rounded-lg border bg-card p-4">
                <h4 className="text-xs font-semibold mb-2 text-foreground">
                  Column mappings ({spec.columns_mapping.length})
                </h4>
                <div className="flex flex-wrap gap-1.5">
                  {spec.columns_mapping.slice(0, 24).map((m: any) => (
                    <span
                      key={m.original_name}
                      className="inline-block rounded bg-muted border px-2 py-0.5 text-xs font-mono text-muted-foreground"
                    >
                      {formatDisplayValue(m.original_name)} → {formatDisplayValue(m.target_name)}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </>
        )}        {isPlanApproval && (
          <>
            <div className="rounded-lg border bg-card p-5">
              <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2">
                Plan Summary
              </h4>
              <p className="text-xs text-foreground leading-relaxed">
                {formatDisplayValue(plan.summary || checkpoint.message_to_user)}
              </p>
            </div>

            <WorkerValidatorFlow
              executionPlan={pipelineState?.execution_plan}
              pipelineState={pipelineState}
            />

            {(colSelection.target_columns?.length > 0 ||
              colSelection.skipped_columns?.length > 0) && (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                {colSelection.target_columns?.length > 0 && (
                  <div className="rounded-lg border bg-card p-4">
                    <div className="flex items-center gap-2 mb-3">
                      <div className="w-5 h-5 rounded bg-success/5 border border-success/30 flex items-center justify-center">
                        <TextIcon className="w-3 h-3 text-success">
                          OK
                        </TextIcon>
                      </div>
                      <h4 className="text-xs font-semibold text-foreground">Target Columns</h4>
                      <span className="ml-auto text-[10px] bg-success/5 text-success rounded border px-2 py-0.5 font-medium">
                        {colSelection.target_columns.length}
                      </span>
                    </div>
                    <div className="flex flex-wrap gap-1.5">
                      {colSelection.target_columns.map((col: any) => (
                        <span
                          key={formatDisplayValue(col)}
                          className="inline-block rounded bg-muted border px-2 py-0.5 text-xs font-mono text-muted-foreground"
                        >
                          {formatDisplayValue(col)}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
                {colSelection.skipped_columns?.length > 0 && (
                  <div className="rounded-lg border bg-card p-4">
                    <div className="flex items-center gap-2 mb-3">
                      <div className="w-5 h-5 rounded bg-muted border flex items-center justify-center">
                        <TextIcon className="w-3 h-3 text-muted-foreground">
                          X
                        </TextIcon>
                      </div>
                      <h4 className="text-xs font-semibold text-muted-foreground">
                        Skipped Columns
                      </h4>
                      <span className="ml-auto text-[10px] bg-muted text-muted-foreground rounded border px-2 py-0.5 font-medium">
                        {colSelection.skipped_columns.length}
                      </span>
                    </div>
                    <div className="flex flex-wrap gap-1.5">
                      {colSelection.skipped_columns.map((col: any) => (
                        <span
                          key={formatDisplayValue(col)}
                          className="inline-block rounded bg-muted border px-2 py-0.5 text-xs font-mono text-muted-foreground"
                        >
                          {formatDisplayValue(col)}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}

            {allTasks.length > 0 && (
              <div>
                <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-3">
                  Execution Steps ({allTasks.length})
                </h4>
                <div className="space-y-3">
                  {allTasks.map(({ task, phase }, i) => (
                    <TaskCard
                      key={task.task_id || i}
                      task={task}
                      index={i}
                      phase={phase}
                    />
                  ))}
                </div>
              </div>
            )}
          </>
        )}

        {!isPlanApproval &&
          !isRequirementApproval &&
          !isInputValidationClarification && (
            <ValidationReviewPanel
              checkpoint={checkpoint}
              pipelineState={pipelineState}
              validationPassed={validationPassed}
              issues={issues}
            />
          )}

        <button
          type="button"
          onClick={() => setShowRawJson(!showRawJson)}
          className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
        >
          <TextIcon className="w-3 h-3">{showRawJson ? "^" : "v"}</TextIcon>
          {showRawJson ? "Hide" : "Show"} raw JSON
        </button>
        {showRawJson && (
          <pre className="bg-slate-950 text-slate-300 rounded-lg p-4 text-xs font-mono overflow-auto max-h-[250px] whitespace-pre-wrap break-words border border-slate-800">
            {JSON.stringify(payload, null, 2)}
          </pre>
        )}

        {!isRequirementApproval && !isInputValidationClarification && (
          <div className="rounded-lg border bg-card p-5 space-y-4">
            <div className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
              <TextIcon>...</TextIcon>
              Feedback{" "}
              {isAwaiting
                ? canModify
                  ? "(required for Modify)"
                  : "(optional)"
                : "(submitted)"}
            </div>
            <textarea
              className="flex min-h-[80px] w-full rounded-lg border border-input bg-background px-4 py-3 text-xs placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring transition-all resize-none disabled:opacity-70 text-foreground"
              placeholder={
                isRequirementApproval
                  ? "Clarify requirements or correct column names..."
                  : isPlanApproval
                    ? "Describe how you'd like the plan to change..."
                    : "Provide guidance on how to fix the remaining issues..."
              }
              value={feedback}
              onChange={(e) => onFeedbackChange(e.target.value)}
              disabled={!isAwaiting}
            />

            {isAwaiting ? (
              <StickyActionBar position="bottom" className="px-6 py-4 bg-card/95 border-t flex flex-col sm:flex-row gap-3">
                <Button
                  onClick={() => submitWithMcq("approve", feedback)}
                  disabled={
                    isPending || (isRequirementApproval && !allMcqAnswered)
                  }
                  title={
                    isRequirementApproval && !allMcqAnswered
                      ? "Answer all required questions first"
                      : ""
                  }
                  className="flex-1 cursor-pointer"
                >
                  {isRequirementApproval
                    ? "Approve Requirements"
                    : isPlanApproval
                      ? "Approve Plan"
                      : "Accept Results"}
                </Button>
                <Button
                  onClick={() => submitWithMcq("modify", feedback)}
                  disabled={
                    isPending ||
                    (!feedback.trim() && !allMcqAnswered) ||
                    !canModify
                  }
                  variant="secondary"
                  title={
                    !canModify
                      ? `Maximum ${maxModify} modifications reached`
                      : ""
                  }
                  className="flex-1 cursor-pointer"
                >
                  {canModify
                    ? isRequirementApproval
                      ? "Clarify requirements"
                      : maxModify != null
                        ? `Modify (${maxModify - modifyCount} left)`
                        : "Modify"
                    : "Max Modifications Reached"}
                </Button>
                <Button
                  onClick={() => submitWithMcq("reject", feedback)}
                  disabled={isPending}
                  variant="destructive"
                  className="flex-1 cursor-pointer"
                >
                  {isRequirementApproval
                    ? "Cancel Run"
                    : isPlanApproval
                      ? "Reject"
                      : "Reject (Export As-Is)"}
                </Button>
              </StickyActionBar>
            ) : (
              <div className="flex items-center justify-center py-2 px-4 bg-success/5 border border-success/30 rounded-md text-success text-xs font-medium gap-2">
                <TextIcon>OK</TextIcon>
                Decision recorded. Pipeline is proceeding.
              </div>
            )}
          </div>
        )}
      </div>
    </Panel>
  );
};

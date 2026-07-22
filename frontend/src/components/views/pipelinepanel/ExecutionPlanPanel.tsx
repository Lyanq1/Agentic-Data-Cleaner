import React from "react";
import { SpinnerIcon } from "./SpinnerIcon";
import { formatDisplayValue } from "./utils";
import { Panel } from "../../ui/Panel";
import { Button } from "../../ui/Button";

const WORKER_FLOW = [
  {
    taskId: "deduplication",
    label: "Dedup",
    description: "Remove exact/fuzzy duplicates before downstream statistics are computed.",
    cardClass: "bg-muted/10 border-border",
    kindClass: "text-muted-foreground",
  },
  {
    taskId: "type_casting",
    label: "Type Cast",
    description: "Cast columns to expected semantic types before resolving nulls.",
    cardClass: "bg-muted/10 border-border",
    kindClass: "text-muted-foreground",
  },
  {
    taskId: "null_handling",
    label: "Null",
    description: "Resolve missing and disguised missing values on the type-casted version.",
    cardClass: "bg-muted/10 border-border",
    kindClass: "text-muted-foreground",
  },
] as const;

const VALIDATOR_META = {
  cardClass: "bg-muted/10 border-border",
  kindClass: "text-muted-foreground",
};

const statusStyles: Record<string, string> = {
  completed: "bg-success/5 text-success border-success/30",
  running: "bg-info/5 text-info border-info/30",
  pending: "bg-muted text-muted-foreground border-border",
  skipped: "bg-muted/50 text-muted-foreground border-border",
  failed: "bg-destructive/5 text-destructive border-destructive/30",
};

type FlowStep = {
  id: string;
  kind: string;
  kindClass: string;
  label: string;
  description: string;
  statusLabel: string;
  statusClass: string;
  cardClass: string;
};

const getWorkerStatus = (
  task: any,
  activeTaskIds: string[],
  currentTaskIdx: number,
) => {
  if (task?.skip) return "skipped";
  const activeIndex = activeTaskIds.indexOf(task?.task_id);
  if (activeIndex === -1) return task ? "pending" : "skipped";
  if (activeIndex < currentTaskIdx) return "completed";
  if (activeIndex === currentTaskIdx) return "running";
  return "pending";
};

const getValidatorStatus = (taskId: string, validationResults: any[]) => {
  const latest = [...validationResults]
    .reverse()
    .find((item: any) => item.task_id === taskId);
  if (!latest) return "pending";
  return latest.passed ? "completed" : "failed";
};

const buildExecutionFlow = (
  taskById: Record<string, any>,
  activeTaskIds: string[],
  currentTaskIdx: number,
  validationResults: any[],
): FlowStep[] => {
  const steps: FlowStep[] = [];

  WORKER_FLOW.forEach((meta) => {
    const task = taskById[meta.taskId];
    const workerStatus = getWorkerStatus(task, activeTaskIds, currentTaskIdx);
    steps.push({
      id: meta.taskId,
      kind: "Worker",
      kindClass: meta.kindClass,
      label: meta.label,
      description: task?.skip
        ? formatDisplayValue(task.skip_reason, "Skipped by planner.")
        : meta.description,
      statusLabel: workerStatus,
      statusClass: statusStyles[workerStatus],
      cardClass: meta.cardClass,
    });

    const validatorStatus = task?.skip
      ? "skipped"
      : getValidatorStatus(meta.taskId, validationResults);
    steps.push({
      id: `${meta.taskId}-validator`,
      kind: "Validator",
      kindClass: VALIDATOR_META.kindClass,
      label: "Output Validators",
      description: `Validate ${meta.label.toLowerCase()} output before the next worker runs.`,
      statusLabel: validatorStatus,
      statusClass: statusStyles[validatorStatus],
      cardClass: VALIDATOR_META.cardClass,
    });
  });

  const reportReady = activeTaskIds.length > 0 && currentTaskIdx >= activeTaskIds.length;
  steps.push({
    id: "report_agent",
    kind: "Output",
    kindClass: "text-muted-foreground",
    label: "Report",
    description: "Summarize final lineage version and validation outcomes.",
    statusLabel: reportReady ? "ready" : "pending",
    statusClass:
      reportReady
        ? "bg-success/5 text-success border-success/30"
        : statusStyles.pending,
    cardClass: "bg-muted/10 border-border",
  });

  return steps;
};

export const WorkerValidatorFlow: React.FC<{
  executionPlan?: any;
  pipelineState?: any;
}> = ({ executionPlan, pipelineState }) => {
  const taskList = executionPlan?.task_list || [];
  const taskById = taskList.reduce((acc: Record<string, any>, item: any) => {
    const task = item.work_order || {};
    if (task.task_id) acc[task.task_id] = task;
    return acc;
  }, {});
  const activeTaskIds = pipelineState?.task_list || [];
  const currentTaskIdx =
    typeof pipelineState?.current_task_idx === "number"
      ? pipelineState.current_task_idx
      : 0;
  const validationResults = pipelineState?.validation_results || [];
  const flowSteps = buildExecutionFlow(
    taskById,
    activeTaskIds,
    currentTaskIdx,
    validationResults,
  );

  return (
    <div className="rounded-lg bg-card border p-5">
      <div className="flex items-start justify-between gap-3 mb-4">
        <div>
          <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
            Worker / Validator Flow
          </h4>
          <p className="text-xs text-muted-foreground mt-1">
            Mirrors the backend graph: each worker writes a new data version, then Pandera validates before the next worker runs.
          </p>
        </div>
        <span className="rounded-md border bg-muted px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider text-muted-foreground">
          Sequential
        </span>
      </div>

      <div className="flex flex-wrap items-stretch gap-2">
        {flowSteps.map((step, idx) => (
          <React.Fragment key={`${step.id}-${idx}`}>
            <div
              className={`min-w-[150px] flex-1 rounded-lg border p-3 bg-muted/5 ${step.cardClass}`}
            >
              <div className="flex items-center justify-between gap-2">
                <span className={`text-[10px] font-bold uppercase tracking-wider ${step.kindClass}`}>
                  {step.kind}
                </span>
                <span className={`rounded-md border px-2 py-0.5 text-[10px] font-semibold uppercase ${step.statusClass}`}>
                  {step.statusLabel}
                </span>
              </div>
              <div className="mt-2 text-sm font-bold text-foreground">
                {step.label}
              </div>
              <p className="mt-1 text-[11px] leading-relaxed text-muted-foreground">
                {step.description}
              </p>
            </div>
            {idx < flowSteps.length - 1 && (
              <div className="hidden md:flex items-center justify-center text-muted-foreground font-mono text-lg px-1">
                -&gt;
              </div>
            )}
          </React.Fragment>
        ))}
      </div>
    </div>
  );
};

export const ExecutionPlanPanel: React.FC<{
  executionPlan: any;
  pipelineState?: any;
  runId: string;
  onApprove: (
    nullStrategies?: Record<string, {
      strategy: string;
      fill_value: unknown;
      allow_pattern_mismatch: boolean;
      allow_dmv_sentinel: boolean;
    }>,
  ) => void;
  isApproving: boolean;
  readOnly?: boolean;
}> = ({ executionPlan, pipelineState, runId, onApprove, isApproving, readOnly }) => {
  const metadata = executionPlan.metadata || {};
  const assumptions = executionPlan.assumptions || [];
  const globalConstraints = executionPlan.global_constraints || {};
  const taskList = executionPlan.task_list || [];
  const nullConflictSection = executionPlan.review?.sections?.find(
    (section: any) => section.task_id === "null_handling",
  );
  const nullTask = taskList
    .map((item: any) => item.work_order || {})
    .find((task: any) => task.task_id === "null_handling");
  const [nullStrategies, setNullStrategies] = React.useState<
    Record<string, {
      strategy: string;
      fill_value: unknown;
      allow_pattern_mismatch: boolean;
      allow_dmv_sentinel: boolean;
    }>
  >({});

  React.useEffect(() => {
    const initial = Object.fromEntries((nullConflictSection?.fields || []).map((field: any) => {
      const column = String(field.field_key).replace(/^strategy\./, "");
      const config = nullTask?.strategy?.per_column?.[column] || {};
      const overrides = config.validation_overrides || {};
      return [column, {
        strategy: String(field.value),
        fill_value: config.fill_value ?? "",
        allow_pattern_mismatch:
          overrides.expected_str_pattern?.acknowledged_by_user === true,
        allow_dmv_sentinel: overrides.potential_dmv?.acknowledged_by_user === true,
      }];
    }));
    setNullStrategies(initial);
  }, [executionPlan.metadata?.plan_id]);

  const hasMissingFillValue = Object.values(nullStrategies).some(
    (selection) =>
      selection.strategy === "fill_value" &&
      (selection.fill_value === null || String(selection.fill_value).trim() === ""),
  );
  const fillValueConflicts = (field: any, column: string) => {
    const selection = nullStrategies[column];
    if (!selection || selection.strategy !== "fill_value") {
      return { patternMismatch: false, dmvMismatch: false };
    }
    const value = String(selection.fill_value ?? "").trim();
    const pattern = field.metadata?.expected_str_pattern;
    let patternMismatch = false;
    if (pattern && value) {
      try {
        patternMismatch = !new RegExp(pattern).test(value);
      } catch {
        patternMismatch = true;
      }
    }
    const dmvMismatch = (field.metadata?.potential_dmv || []).some(
      (candidate: unknown) => String(candidate) === String(selection.fill_value),
    );
    return { patternMismatch, dmvMismatch };
  };
  const hasUnacknowledgedConflict = (nullConflictSection?.fields || []).some((field: any) => {
    const column = String(field.field_key).replace(/^strategy\./, "");
    const conflicts = fillValueConflicts(field, column);
    const selection = nullStrategies[column];
    return (
      (conflicts.patternMismatch && !selection?.allow_pattern_mismatch) ||
      (conflicts.dmvMismatch && !selection?.allow_dmv_sentinel)
    );
  });

  return (
    <Panel className="mb-8 text-left animate-fadeIn overflow-hidden">
      <div className="border-b px-6 py-4">
        <h3 className="text-sm font-semibold text-foreground">Execution Plan</h3>
        <p className="text-xs text-muted-foreground mt-0.5">
          {readOnly ? "Completed execution details for review" : "Generated strategies"}
        </p>
      </div>

      <div className="p-6 space-y-6">
        {readOnly && (
          <div className="rounded-md border border-success/30 bg-success/5 px-4 py-3 text-xs text-success-foreground">
            <strong className="font-semibold">Final report is ready.</strong>{" "}
            This execution plan is now read-only so you can safely review what happened without re-running the pipeline.
          </div>
        )}

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="rounded-lg border bg-muted/5 p-4 text-xs space-y-2">
            <h4 className="font-bold text-foreground uppercase tracking-wider mb-2">
              Plan Details
            </h4>
            <div>
              <span className="text-muted-foreground">Plan ID:</span>{" "}
              <code className="bg-muted px-1.5 py-0.5 rounded font-mono">
                {metadata.plan_id}
              </code>
            </div>
            <div>
              <span className="text-muted-foreground">Run ID:</span>{" "}
              <code className="bg-muted px-1.5 py-0.5 rounded font-mono">
                {runId}
              </code>
            </div>
            <div>
              <span className="text-muted-foreground">Version:</span>{" "}
              {metadata.plan_version}
            </div>
          </div>
          <div className="rounded-lg border bg-muted/5 p-4 text-xs space-y-2">
            <h4 className="font-bold text-foreground uppercase tracking-wider mb-2">
              Global Constraints
            </h4>
            <div>
              <span className="text-muted-foreground">Max Retries:</span>{" "}
              {globalConstraints.max_retries_per_task}
            </div>
            <div>
              <span className="text-muted-foreground block mb-1">
                Preserve Columns:
              </span>
              <div className="flex flex-wrap gap-1">
                {globalConstraints.preserve_columns?.length > 0 ? (
                  globalConstraints.preserve_columns.map((col: string) => (
                    <span
                      key={col}
                      className="px-1.5 py-0.5 bg-muted rounded text-[10px] font-mono text-muted-foreground border"
                    >
                      {col}
                    </span>
                  ))
                ) : (
                  <span className="text-muted-foreground italic">None</span>
                )}
              </div>
            </div>
          </div>
        </div>

        {assumptions.length > 0 && (
          <div className="rounded-lg border bg-muted/20 p-4">
            <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">
              Plan Assumptions
            </h4>
            <ul className="list-disc pl-5 space-y-1 text-xs text-foreground">
              {assumptions.map((asm: any, i: number) => (
                <li key={i}>{formatDisplayValue(asm)}</li>
              ))}
            </ul>
          </div>
        )}

        <div className="rounded-lg bg-muted/5 border p-5">
          <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">
            Plan Summary
          </h4>
          <p className="text-xs text-foreground leading-relaxed">
            {formatDisplayValue(executionPlan.plan_summary)}
          </p>
        </div>

        <WorkerValidatorFlow executionPlan={executionPlan} pipelineState={pipelineState} />

        {!readOnly && nullConflictSection?.fields?.length > 0 && (
          <div className="rounded-lg border border-warning/30 bg-warning/5 p-4">
            <h4 className="text-xs font-semibold text-warning-foreground">
              Null strategy compatibility review
            </h4>
            <p className="mt-1 text-xs text-muted-foreground">
              The planner found strategies that do not match the column semantic type. Keep the
              current strategy or choose a compatible alternative before execution.
            </p>
            <div className="mt-3 space-y-3">
              {nullConflictSection.fields.map((field: any) => {
                const column = String(field.field_key).replace(/^strategy\./, "");
                const conflicts = fillValueConflicts(field, column);
                return (
                  <div key={field.field_key} className="block rounded-lg border bg-card p-3">
                    <span className="block text-xs font-semibold text-foreground">{field.label}</span>
                    <span className="mt-1 block text-[11px] leading-relaxed text-muted-foreground">
                      {field.help_text}
                    </span>
                    <select
                      value={nullStrategies[column]?.strategy ?? String(field.value)}
                      onChange={(event) =>
                        setNullStrategies((current) => ({
                          ...current,
                          [column]: {
                            strategy: event.target.value,
                            fill_value: current[column]?.fill_value ?? "",
                            allow_pattern_mismatch: false,
                            allow_dmv_sentinel: false,
                          },
                        }))
                      }
                      className="mt-2 w-full rounded-md border border-input bg-background px-3 py-2 text-xs text-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                    >
                      {(field.options || []).map((option: string) => (
                        <option key={option} value={option}>{option}</option>
                      ))}
                    </select>
                    {(nullStrategies[column]?.strategy ?? String(field.value)) === "fill_value" && (
                      <input
                        type="text"
                        value={String(nullStrategies[column]?.fill_value ?? "")}
                        onChange={(event) =>
                          setNullStrategies((current) => ({
                            ...current,
                            [column]: {
                              strategy: "fill_value",
                              fill_value: event.target.value,
                              allow_pattern_mismatch: false,
                              allow_dmv_sentinel: false,
                            },
                          }))
                        }
                        placeholder="Enter the constant value"
                        className="mt-2 w-full rounded-md border border-input bg-background px-3 py-2 text-xs text-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                      />
                    )}
                    {conflicts.patternMismatch && (
                      <label className="mt-2 flex items-start gap-2 rounded-md border border-warning/30 bg-warning/5 p-2 text-[11px] text-warning-foreground">
                        <input
                          type="checkbox"
                          checked={nullStrategies[column]?.allow_pattern_mismatch ?? false}
                          onChange={(event) =>
                            setNullStrategies((current) => {
                              const selection = current[column];
                              if (!selection) return current;
                              return {
                                ...current,
                                [column]: {
                                  ...selection,
                                  allow_pattern_mismatch: event.target.checked,
                                },
                              };
                            })
                          }
                        />
                        <span>
                          This value does not match the detected pattern
                          {field.metadata?.expected_str_pattern
                            ? ` (${field.metadata.expected_str_pattern})`
                            : ""}. Keep it and skip the pattern check for this exact default value.
                        </span>
                      </label>
                    )}
                    {conflicts.dmvMismatch && (
                      <label className="mt-2 flex items-start gap-2 rounded-md border border-warning/30 bg-warning/5 p-2 text-[11px] text-warning-foreground">
                        <input
                          type="checkbox"
                          checked={nullStrategies[column]?.allow_dmv_sentinel ?? false}
                          onChange={(event) =>
                            setNullStrategies((current) => {
                              const selection = current[column];
                              if (!selection) return current;
                              return {
                                ...current,
                                [column]: {
                                  ...selection,
                                  allow_dmv_sentinel: event.target.checked,
                                },
                              };
                            })
                          }
                        />
                        <span>
                          This value is classified as a disguised missing value. Keep it as an
                          explicitly approved sentinel.
                        </span>
                      </label>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        )}

        <div className="space-y-4">
          <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
            Work Orders ({taskList.length})
          </h4>

          <div className="space-y-4">
            {taskList.map((item: any, i: number) => {
              const task = item.work_order || {};
              const title =
                task.task_id === "deduplication"
                  ? "Exact & Fuzzy Deduplication"
                  : task.task_id === "null_handling"
                    ? "Null & Disguised Value Imputation"
                    : "Strict Type Casting";
              const agentLabel = task.agent;
              const isSkipped = task.skip;

              return (
                <div
                  key={i}
                  className={`rounded-lg border bg-card p-4 transition-all duration-200 ${isSkipped ? "opacity-60 bg-muted/10" : ""}`}
                >
                  <div className="flex items-start justify-between mb-3 flex-wrap gap-2">
                    <div className="flex items-center gap-2">
                      <span
                        className={`inline-flex items-center gap-1.5 rounded-md border px-2.5 py-0.5 text-xs font-semibold bg-muted text-muted-foreground border-border`}
                      >
                        {title}
                      </span>
                      <span className="text-xs text-muted-foreground font-mono">
                        ({agentLabel})
                      </span>
                    </div>
                    {isSkipped && (
                      <span className="text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 bg-muted text-muted-foreground rounded border">
                        Skipped
                      </span>
                    )}
                  </div>

                  {isSkipped ? (
                    <p className="text-xs text-muted-foreground italic">
                      Reason: {formatDisplayValue(task.skip_reason)}
                    </p>
                  ) : (
                    <div className="space-y-3 mt-2 text-xs">
                      {task.rationale && (
                        <p className="text-muted-foreground leading-relaxed">
                          <strong className="text-foreground">
                            Rationale:
                          </strong>{" "}
                          {formatDisplayValue(task.rationale)}
                        </p>
                      )}

                      {task.columns?.length > 0 && (
                        <div>
                          <span className="font-semibold text-foreground mr-2">
                            Target columns:
                          </span>
                          <div className="inline-flex flex-wrap gap-1.5">
                            {task.columns.map((col: any) => (
                              <span
                                key={formatDisplayValue(col)}
                                className="px-1.5 py-0.5 bg-muted text-muted-foreground border rounded text-[10px] font-mono"
                              >
                                {formatDisplayValue(col)}
                              </span>
                            ))}
                          </div>
                        </div>
                      )}

                      {task.strategy && (
                        <div className="bg-muted/10 border rounded-lg p-3">
                          <span className="font-bold text-foreground block mb-2 text-[10px] uppercase tracking-wider text-muted-foreground">
                            Strategy Configuration
                          </span>
                          {task.task_id === "deduplication" && (
                            <div className="space-y-2 text-xs">
                              {task.strategy?.dedup_scope && (
                                <div>
                                  <span className="text-muted-foreground font-semibold">Dedup Scope:</span>{" "}
                                  <span className="font-mono text-foreground">{formatDisplayValue(task.strategy.dedup_scope)}</span>
                                </div>
                              )}
                              {task.strategy?.primary_keys?.length > 0 && (
                                <div>
                                  <span className="text-muted-foreground font-semibold">Primary Keys:</span>{" "}
                                  <span className="font-mono text-foreground">
                                    {task.strategy.primary_keys.map((key: any) => formatDisplayValue(key)).join(", ")}
                                  </span>
                                </div>
                              )}
                              {task.strategy?.exact_match?.enabled && (
                                <div>
                                  <span className="text-muted-foreground font-semibold">Exact Match:</span>{" "}
                                  <span className="text-foreground">Enabled (keep: {formatDisplayValue(task.strategy.exact_match.keep, "first")})</span>
                                </div>
                              )}
                              {task.strategy?.fuzzy_matching?.enabled && (
                                <div className="mt-2 p-2.5 rounded-lg border bg-card space-y-1">
                                  <span className="font-bold text-foreground block text-[11px] uppercase tracking-wider">
                                    Fuzzy Matching Strategy
                                  </span>
                                  <div>
                                    <span className="text-muted-foreground">Method:</span>{" "}
                                    <span className="font-semibold">{formatDisplayValue(task.strategy.fuzzy_matching.method, "minhash_lsh")}</span>
                                  </div>
                                  <div>
                                    <span className="text-muted-foreground">Threshold:</span>{" "}
                                    <span className="font-mono font-semibold">{formatDisplayValue(task.strategy.fuzzy_matching.threshold)}</span>
                                  </div>
                                  {task.strategy.fuzzy_matching.blocking_columns?.length > 0 && (
                                    <div>
                                      <span className="text-muted-foreground">Blocking Columns:</span>{" "}
                                      <span className="font-mono">{task.strategy.fuzzy_matching.blocking_columns.map((col: any) => formatDisplayValue(col)).join(", ")}</span>
                                    </div>
                                  )}
                                  {task.strategy.fuzzy_matching.match_columns?.length > 0 && (
                                    <div>
                                      <span className="text-muted-foreground">Match Columns:</span>{" "}
                                      <span className="font-mono">{task.strategy.fuzzy_matching.match_columns.map((col: any) => formatDisplayValue(col)).join(", ")}</span>
                                    </div>
                                  )}
                                </div>
                              )}
                            </div>
                          )}
                          {task.task_id === "null_handling" &&
                             task.strategy.per_column && (
                              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                                {Object.entries(task.strategy.per_column).map(
                                  ([col, cfg]: [string, any]) => (
                                    <div
                                      key={col}
                                      className="bg-card border rounded p-2 text-[11px]"
                                    >
                                      <span className="font-mono font-bold text-foreground block">
                                        {col}
                                      </span>
                                      <span className="text-muted-foreground">
                                        Imputation: {formatDisplayValue(cfg.strategy)}{" "}
                                        {cfg.fill_value !== null
                                          ? `(${formatDisplayValue(cfg.fill_value)})`
                                          : ""}
                                      </span>
                                    </div>
                                  ),
                                )}
                              </div>
                            )}
                          {task.task_id === "type_casting" &&
                            task.strategy.per_column && (
                              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                                {Object.entries(task.strategy.per_column).map(
                                  ([col, cfg]: [string, any]) => (
                                    <div
                                      key={col}
                                      className="bg-card border rounded p-2 text-[11px]"
                                    >
                                      <span className="font-mono font-bold text-foreground block">
                                        {col}
                                      </span>
                                      <span className="text-muted-foreground">
                                        Cast expected: {formatDisplayValue(cfg.expected_type)}{" "}
                                        {cfg.parse_format
                                          ? `(Format: ${formatDisplayValue(cfg.parse_format)})`
                                          : ""}
                                      </span>
                                    </div>
                                  ),
                                )}
                              </div>
                            )}
                        </div>
                      )}

                      {task.verification?.pandera_checks?.length > 0 && (
                        <div>
                          <span className="font-semibold text-foreground block mb-1">
                            Validation rules:
                          </span>
                          <div className="flex flex-wrap gap-1.5">
                            {task.verification.pandera_checks.map(
                              (rule: any, ri: number) => {
                                const label = typeof rule === "object" && rule !== null
                                  ? (rule.column
                                      ? `${formatDisplayValue(rule.column)} (${formatDisplayValue(rule.type)})`
                                      : formatDisplayValue(rule.type, formatDisplayValue(rule)))
                                  : String(rule);
                                return (
                                  <span
                                    key={ri}
                                    className="px-2 py-0.5 bg-muted border rounded-md text-[10px] font-mono text-muted-foreground"
                                  >
                                    {label}
                                  </span>
                                );
                              },
                            )}
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>

        <div className="pt-4 border-t border-border flex justify-end">
          {readOnly ? (
            <div className="inline-flex items-center gap-2 rounded-lg border border-success/30 bg-success/5 px-5 py-3 text-sm font-semibold text-success">
              <span className="inline-flex h-2 w-2 rounded-full bg-success" />
              Report ready - review only
            </div>
          ) : (
            <Button
              type="button"
              onClick={() =>
                onApprove(
                  nullConflictSection?.fields?.length > 0 ? nullStrategies : undefined,
                )
              }
              disabled={isApproving || hasMissingFillValue || hasUnacknowledgedConflict}
              className="cursor-pointer"
            >
              {isApproving ? (
                <>
                  <SpinnerIcon />
                  Executing pipeline...
                </>
              ) : (
                <>
                  Approve & Execute Cleaning
                </>
              )}
            </Button>
          )}
        </div>
      </div>
    </Panel>
  );
};


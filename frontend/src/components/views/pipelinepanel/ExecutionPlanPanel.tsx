import React from "react";
import { SpinnerIcon } from "./SpinnerIcon";
import { formatDisplayValue } from "./utils";

const formatToGmt7 = (dateStr: string) => {
  if (!dateStr) return "";
  try {
    const normalizedStr =
      dateStr.endsWith("Z") || dateStr.includes("+") || dateStr.includes("-")
        ? dateStr
        : dateStr + "Z";
    const d = new Date(normalizedStr);
    if (isNaN(d.getTime())) return dateStr;
    return (
      d.toLocaleString("en-GB", {
        timeZone: "Asia/Bangkok",
        hour12: false,
      }) + " (GMT+7)"
    );
  } catch (e) {
    return dateStr;
  }
};

const WORKER_FLOW = [
  {
    taskId: "deduplication",
    label: "Dedup",
    description: "Remove exact/fuzzy duplicates before downstream statistics are computed.",
    cardClass: "bg-violet-50 border-violet-200",
    kindClass: "text-violet-700",
  },
  {
    taskId: "type_casting",
    label: "Type Cast",
    description: "Cast columns to expected semantic types before resolving nulls.",
    cardClass: "bg-amber-50 border-amber-200",
    kindClass: "text-amber-700",
  },
  {
    taskId: "null_handling",
    label: "Null",
    description: "Resolve missing and disguised missing values on the type-casted version.",
    cardClass: "bg-sky-50 border-sky-200",
    kindClass: "text-sky-700",
  },
] as const;

const VALIDATOR_META = {
  cardClass: "bg-emerald-50 border-emerald-200",
  kindClass: "text-emerald-700",
};

const statusStyles: Record<string, string> = {
  completed: "bg-emerald-50 text-emerald-700 border-emerald-200",
  running: "bg-blue-50 text-blue-700 border-blue-200",
  pending: "bg-slate-50 text-slate-500 border-slate-200",
  skipped: "bg-slate-100 text-slate-500 border-slate-200",
  failed: "bg-rose-50 text-rose-700 border-rose-200",
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
    kindClass: "text-slate-700",
    label: "Report",
    description: "Summarize final lineage version and validation outcomes.",
    statusLabel: reportReady ? "ready" : "pending",
    statusClass:
      reportReady
        ? "bg-indigo-50 text-indigo-700 border-indigo-200"
        : statusStyles.pending,
    cardClass: "bg-slate-50 border-slate-200",
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
    <div className="rounded-xl bg-white border p-5 shadow-sm">
      <div className="flex items-start justify-between gap-3 mb-4">
        <div>
          <h4 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider">
            Worker / Validator Flow
          </h4>
          <p className="text-xs text-slate-500 mt-1">
            Mirrors the backend graph: each worker writes a new data version, then Pandera validates before the next worker runs.
          </p>
        </div>
        <span className="rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider text-slate-500">
          Sequential
        </span>
      </div>

      <div className="flex flex-wrap items-stretch gap-2">
        {flowSteps.map((step, idx) => (
          <React.Fragment key={`${step.id}-${idx}`}>
            <div
              className={`min-w-[150px] flex-1 rounded-xl border p-3 ${step.cardClass}`}
            >
              <div className="flex items-center justify-between gap-2">
                <span className={`text-[10px] font-bold uppercase tracking-wider ${step.kindClass}`}>
                  {step.kind}
                </span>
                <span className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase ${step.statusClass}`}>
                  {step.statusLabel}
                </span>
              </div>
              <div className="mt-2 text-sm font-bold text-slate-800">
                {step.label}
              </div>
              <p className="mt-1 text-[11px] leading-relaxed text-slate-500">
                {step.description}
              </p>
            </div>
            {idx < flowSteps.length - 1 && (
              <div className="hidden md:flex items-center justify-center text-slate-300 font-mono text-lg px-1">
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
  onApprove: () => void;
  isApproving: boolean;
  readOnly?: boolean;
}> = ({ executionPlan, pipelineState, runId, onApprove, isApproving, readOnly }) => {
  const metadata = executionPlan.metadata || {};
  const assumptions = executionPlan.assumptions || [];
  const globalConstraints = executionPlan.global_constraints || {};
  const taskList = executionPlan.task_list || [];

  return (
    <div className="mb-8 rounded-2xl border-2 border-indigo-400/40 bg-indigo-50 shadow-lg overflow-hidden text-left animate-fadeIn">
      <div className="bg-indigo-600 px-6 py-4">
        <div className="flex items-center gap-3">
          <div>
            <h3 className="text-lg font-bold text-white">Execution Plan</h3>
            <p className="text-white/80 text-sm">
              {readOnly ? "Completed execution details for review" : "Generated strategies"}
            </p>
          </div>
        </div>
      </div>

      <div className="p-6 space-y-6">
        {readOnly && (
          <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800 shadow-sm">
            <strong className="font-semibold">Final report is ready.</strong>{" "}
            This execution plan is now read-only so you can safely review what happened without re-running the pipeline.
          </div>
        )}

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="rounded-xl border bg-white p-4 shadow-sm text-xs space-y-2">
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
            <div>
              <span className="text-muted-foreground">Created At:</span>{" "}
              {formatToGmt7(metadata.created_at)}
            </div>
          </div>
          <div className="rounded-xl border bg-white p-4 shadow-sm text-xs space-y-2">
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
                      className="px-1.5 py-0.5 bg-slate-100 rounded text-[10px] font-mono text-slate-700"
                    >
                      {col}
                    </span>
                  ))
                ) : (
                  <span className="text-slate-400 italic">None</span>
                )}
              </div>
            </div>
          </div>
        </div>

        {assumptions.length > 0 && (
          <div className="rounded-xl border bg-muted/20 p-4">
            <h4 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider mb-2">
              Plan Assumptions
            </h4>
            <ul className="list-disc pl-5 space-y-1 text-xs text-foreground">
              {assumptions.map((asm: any, i: number) => (
                <li key={i}>{formatDisplayValue(asm)}</li>
              ))}
            </ul>
          </div>
        )}

        <div className="rounded-xl bg-white border p-5 shadow-sm">
          <h4 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider mb-2">
            Plan Summary
          </h4>
          <p className="text-xs text-foreground leading-relaxed leading-5">
            {formatDisplayValue(executionPlan.plan_summary)}
          </p>
        </div>

        <WorkerValidatorFlow executionPlan={executionPlan} pipelineState={pipelineState} />

        <div className="space-y-4">
          <h4 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider">
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
                  className={`rounded-xl border bg-card p-4 shadow-sm transition-all duration-200 ${isSkipped ? "opacity-60 bg-muted/10" : "hover:shadow-md"}`}
                >
                  <div className="flex items-start justify-between mb-3 flex-wrap gap-2">
                    <div className="flex items-center gap-2">
                      <span
                        className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-semibold ${
                          isSkipped
                            ? "bg-slate-100 text-slate-500 border-slate-200"
                            : task.task_id === "deduplication"
                              ? "bg-violet-500/10 text-violet-600 border-violet-200"
                              : task.task_id === "null_handling"
                                ? "bg-sky-500/10 text-sky-600 border-sky-200"
                                : "bg-amber-500/10 text-amber-600 border-amber-200"
                        }`}
                      >
                        {title}
                      </span>
                      <span className="text-xs text-muted-foreground font-mono">
                        ({agentLabel})
                      </span>
                    </div>
                    {isSkipped && (
                      <span className="text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 bg-gray-100 text-gray-500 rounded border border-gray-200">
                        Skipped
                      </span>
                    )}
                  </div>

                  {isSkipped ? (
                    <p className="text-xs text-slate-500 italic">
                      Reason: {formatDisplayValue(task.skip_reason)}
                    </p>
                  ) : (
                    <div className="space-y-3 mt-2 text-xs">
                      {task.rationale && (
                        <p className="text-slate-600 leading-relaxed">
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
                          <div className="inline-flex flex-wrap gap-1">
                            {task.columns.map((col: any) => (
                              <span
                                key={formatDisplayValue(col)}
                                className="px-1.5 py-0.5 bg-indigo-50 border border-indigo-100 rounded text-[10px] font-mono text-indigo-600"
                              >
                                {formatDisplayValue(col)}
                              </span>
                            ))}
                          </div>
                        </div>
                      )}

                      {task.strategy && (
                        <div className="bg-muted/30 border rounded-lg p-3">
                          <span className="font-bold text-foreground block mb-2 text-[11px] uppercase tracking-wider text-muted-foreground/80">
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
                                <div className="mt-2 p-2.5 rounded-lg border bg-white shadow-sm space-y-1">
                                  <span className="font-bold text-slate-700 block text-[11px] uppercase tracking-wider">
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
                                      className="bg-white border rounded p-2 text-[11px]"
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
                                      className="bg-white border rounded p-2 text-[11px]"
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
                                    className="px-2 py-0.5 bg-emerald-50 border border-emerald-100 rounded-md text-[10px] font-mono text-emerald-700"
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

        <div className="pt-4 border-t border-slate-100 flex justify-end">
          {readOnly ? (
            <div className="inline-flex items-center gap-2 rounded-xl border border-emerald-200 bg-emerald-50 px-5 py-3 text-sm font-semibold text-emerald-700">
              <span className="inline-flex h-2 w-2 rounded-full bg-emerald-500" />
              Report ready - review only
            </div>
          ) : (
            <button
              type="button"
              onClick={onApprove}
              disabled={isApproving}
              aria-busy={isApproving}
              className="inline-flex items-center gap-2 px-6 py-3 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl text-sm font-semibold transition-all shadow-md hover:shadow-lg disabled:cursor-wait disabled:opacity-70 cursor-pointer"
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
            </button>
          )}
        </div>
      </div>
    </div>
  );
};

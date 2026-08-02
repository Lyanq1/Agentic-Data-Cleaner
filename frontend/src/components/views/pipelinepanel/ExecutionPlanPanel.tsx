import React from "react";
import { SpinnerIcon } from "./SpinnerIcon";
import { formatDisplayValue } from "./utils";


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
  completed: "status-ring-completed",
  running: "status-ring-running",
  pending: "status-ring-pending",
  skipped: "status-ring-skipped",
  failed: "status-ring-error",
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

    let validatorStatus = "pending";
    if (task?.skip) {
      validatorStatus = "skipped";
    } else if (workerStatus === "completed") {
      validatorStatus = getValidatorStatus(meta.taskId, validationResults);
    }

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
    statusLabel: reportReady ? "completed" : "pending",
    statusClass:
      reportReady
        ? "status-ring-completed"
        : statusStyles.pending,
    cardClass: "",
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
    <div className="rounded-xl glass-panel p-5">
      <div className="flex items-start justify-between gap-3 mb-4">
        <div>
          <h4 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider">
            Worker / Validator Flow
          </h4>
          <p className="text-xs text-foreground/60 mt-1">
            Mirrors the backend graph: each worker writes a new data version, then Pandera validates before the next worker runs.
          </p>
        </div>
        <span className="rounded-full border border-white/20 bg-background/50 px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider text-muted-foreground">
          Sequential
        </span>
      </div>

      <div className="relative py-6 w-full">
        <div 
          className="grid w-full relative z-10 px-2 sm:px-4"
          style={{ gridTemplateColumns: `repeat(${flowSteps.length}, minmax(0, 1fr))` }}
        >
          {flowSteps.map((step, idx) => {
            const isCompleted = step.statusLabel === "completed";
            const isRunning = step.statusLabel === "running";
            const isFailed = step.statusLabel === "failed";
            const isSkipped = step.statusLabel === "skipped";
            
            // Should the line going OUT of this node be highlighted?
            // A skipped node's line should only highlight if the pipeline has physically moved past it.
            const hasActiveNodeAfter = flowSteps.some(
              (s, sIdx) => sIdx > idx && ["running", "completed", "failed"].includes(s.statusLabel)
            );
            const lineHighlight = isCompleted || (isSkipped && hasActiveNodeAfter);

            return (
              <div key={`${step.id}-${idx}`} className="flex flex-col items-center relative group w-full">
                {/* Connecting Line to next node */}
                {idx < flowSteps.length - 1 && (
                  <div 
                    className={`absolute top-4 left-[50%] w-full h-[2px] -z-10 transition-colors duration-500
                      ${lineHighlight ? 'bg-primary dark:bg-primary/80' : 'bg-slate-200 dark:bg-white/10'}
                    `} 
                  />
                )}

                {/* Node Dot */}
                <div className="flex items-center justify-center h-8 relative mb-3">
                  {isCompleted || isSkipped ? (
                    <div className={`w-5 h-5 rounded-full flex items-center justify-center text-[10px] text-white shadow-md z-10 transition-all duration-300
                      ${isCompleted ? 'bg-primary shadow-primary/40' : 'bg-slate-300 dark:bg-slate-700 shadow-none opacity-80'}
                    `}>
                        {isCompleted ? '✓' : '—'}
                    </div>
                  ) : isFailed ? (
                    <div className="w-5 h-5 rounded-full flex items-center justify-center text-[10px] text-white bg-destructive shadow-md shadow-destructive/40 z-10">
                        ✕
                    </div>
                  ) : isRunning ? (
                    <div className="w-8 h-8 rounded-full border border-primary/30 bg-primary/10 flex items-center justify-center z-10 shadow-[0_0_15px_rgba(var(--color-primary),0.3)] backdrop-blur-sm relative">
                      <div className="absolute inset-0 rounded-full animate-ping bg-primary/20" />
                      <div className="w-5 h-5 rounded-full bg-background flex items-center justify-center border border-primary/50 text-xs text-primary font-bold shadow-inner">
                          {idx + 1}
                      </div>
                    </div>
                  ) : (
                    /* Pending Node: No background circle, just the number resting on the line hole */
                    <div className="w-6 h-6 bg-background rounded-full flex items-center justify-center text-xs font-semibold text-muted-foreground/40 z-10 border border-background">
                      {idx + 1}
                    </div>
                  )}
                </div>

                {/* Text Container */}
                <div className="text-center flex flex-col items-center max-w-[85px]">
                  <span className={`text-[8px] sm:text-[9px] uppercase tracking-widest font-bold mb-0.5 transition-colors
                    ${isRunning || isCompleted ? 'text-primary/70 dark:text-primary/90' : isFailed ? 'text-destructive/70' : 'text-muted-foreground/40'}
                  `}>
                    {step.kind}
                  </span>
                  <span className={`text-[10px] sm:text-[11px] font-medium leading-tight text-center px-1 transition-colors
                    ${isRunning ? 'text-foreground font-bold' : isCompleted || isSkipped ? 'text-foreground/80' : isFailed ? 'text-destructive' : 'text-muted-foreground/50'}
                  `}>
                    {step.label}
                  </span>
                </div>
              </div>
            );
          })}
        </div>
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
    dedupReview?: {
      key_columns?: string[];
      identifier_columns?: string[];
      ignored_columns?: string[];
      keep_rule?: string;
      fuzzy_enabled?: boolean;
    }
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
  const dedupTask = taskList
    .map((item: any) => item.work_order || {})
    .find((task: any) => task.task_id === "deduplication");
  const [nullStrategies, setNullStrategies] = React.useState<
    Record<string, {
      strategy: string;
      fill_value: unknown;
      allow_pattern_mismatch: boolean;
      allow_dmv_sentinel: boolean;
    }>
  >({});
  
  const [dedupKeyColumns, setDedupKeyColumns] = React.useState<string[]>([]);
  const [dedupIdentifierColumns, setDedupIdentifierColumns] = React.useState<string[]>([]);
  const [dedupIgnoredColumns, setDedupIgnoredColumns] = React.useState<string[]>([]);
  const [dedupKeepRule, setDedupKeepRule] = React.useState<string>("keep_most_complete");
  const [dedupFuzzyEnabled, setDedupFuzzyEnabled] = React.useState<boolean>(false);

  const availableColumns = pipelineState?.dataset_schema 
    ? Object.keys(pipelineState.dataset_schema) 
    : Object.keys(pipelineState?.data_profile?.columns || {});

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

    // Read initial deduplication values
    if (dedupTask?.strategy) {
      setDedupKeyColumns(dedupTask.strategy.primary_keys || []);
      setDedupIdentifierColumns(dedupTask.strategy.identifier_columns || []);
      setDedupIgnoredColumns(dedupTask.strategy.ignored_columns || []);
      setDedupKeepRule(dedupTask.strategy.keep_rule || "keep_most_complete");
      setDedupFuzzyEnabled(!!dedupTask.strategy.fuzzy_matching?.enabled);
    }
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

        {!readOnly && dedupTask && (
          <div className={`rounded-xl border p-4 shadow-sm transition-all duration-500 ${dedupTask.skip ? 'border-amber-300 bg-amber-50' : 'border-violet-300 bg-violet-50'}`}>
            <h4 className={`text-sm font-semibold ${dedupTask.skip ? 'text-amber-900' : 'text-violet-900'}`}>
              Deduplication strategy review
            </h4>
            <p className={`mt-1 text-xs ${dedupTask.skip ? 'text-amber-800' : 'text-violet-800'}`}>
              The planner has identified the following columns for deduplication. You can tweak these choices before executing the plan.
            </p>
            {dedupTask.skip && (
              <div className="mt-3 rounded-lg border-l-4 border-amber-500 bg-amber-100 p-3 shadow-inner flex items-start gap-2">
                <span className="text-amber-600 text-sm mt-0.5 animate-bounce">⚠️</span>
                <div className="text-xs text-amber-900 leading-relaxed font-medium">
                  <strong>Notice:</strong> Deduplication is currently marked as SKIPPED because there are no duplicate rows or identifiers detected! These configurations are shown for your reference but won't be actively executed.
                </div>
              </div>
            )}
            <div className={`mt-3 space-y-4 ${dedupTask.skip ? 'opacity-75 grayscale-[20%]' : ''}`}>
              
              <div className="rounded-lg border bg-white p-3">
                <span className="block text-xs font-semibold text-slate-800">Key Columns</span>
                <span className="mt-1 block text-[11px] leading-relaxed text-slate-500">
                  Columns that uniquely identify a record. Exact matches on these columns are considered duplicates.
                </span>
                <div className="mt-2 flex flex-wrap gap-2">
                  {availableColumns.map((col) => {
                    const isDisabled = dedupIgnoredColumns.includes(col);
                    return (
                      <label key={col} className={`flex items-center gap-1 text-xs border border-slate-200 px-2 py-1 rounded ${isDisabled ? 'opacity-50 cursor-not-allowed bg-slate-100 text-slate-500' : 'text-slate-700 bg-slate-50 cursor-pointer hover:bg-slate-100'}`}>
                        <input 
                          type="checkbox" 
                          disabled={isDisabled}
                          checked={dedupKeyColumns.includes(col)}
                          onChange={(e) => {
                            if (e.target.checked) setDedupKeyColumns(prev => [...prev, col]);
                            else setDedupKeyColumns(prev => prev.filter(c => c !== col));
                          }}
                        />
                        <span>{col}</span>
                      </label>
                    );
                  })}
                </div>
              </div>

              <div className={`overflow-hidden rounded-lg border transition-all duration-300 ${dedupFuzzyEnabled ? 'border-violet-300 shadow-sm ring-1 ring-violet-50' : 'border-slate-200 bg-white'}`}>
                <div className={`p-3 flex flex-col sm:flex-row sm:items-center justify-between gap-4 transition-colors hover:bg-slate-50 ${dedupFuzzyEnabled ? 'bg-violet-50/50 border-b border-violet-100' : ''}`}>
                  <div>
                    <span className="block text-xs font-semibold text-slate-800">Fuzzy Matching</span>
                    <span className="mt-1 block text-[11px] leading-relaxed text-slate-500">
                      Enable fuzzy candidate generation to surface near-matches (e.g. typos).
                    </span>
                  </div>
                  <button
                    type="button"
                    role="switch"
                    aria-checked={dedupFuzzyEnabled}
                    className={`${
                      dedupFuzzyEnabled ? 'bg-violet-600' : 'bg-slate-200'
                    } relative inline-flex h-5 w-9 shrink-0 cursor-pointer items-center rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-violet-600 focus:ring-offset-2`}
                    onClick={() => setDedupFuzzyEnabled(!dedupFuzzyEnabled)}
                  >
                    <span
                      aria-hidden="true"
                      className={`${
                        dedupFuzzyEnabled ? 'translate-x-4' : 'translate-x-0'
                      } pointer-events-none inline-block h-4 w-4 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out`}
                    />
                  </button>
                </div>

                {dedupFuzzyEnabled && (
                  <div className="bg-slate-50/50 p-4 space-y-4 animate-in fade-in slide-in-from-top-1 duration-300">
                    <div className="rounded-md border border-slate-200/60 bg-white p-3 shadow-sm">
                      <span className="block text-xs font-semibold text-slate-800">Identifier Columns</span>
                      <span className="mt-1 block text-[11px] leading-relaxed text-slate-500">
                        Additional unique identifiers (e.g. emails, phone numbers) used for fuzzy block matching and cross-referencing.
                      </span>
                      <div className="mt-2 flex flex-wrap gap-2">
                        {availableColumns.map((col) => {
                          const isDisabled = dedupIgnoredColumns.includes(col);
                          return (
                            <label key={col} className={`flex items-center gap-1 text-xs border border-slate-200 px-2 py-1 rounded ${isDisabled ? 'opacity-50 cursor-not-allowed bg-slate-100 text-slate-500' : 'text-slate-700 bg-slate-50 cursor-pointer hover:bg-slate-100'}`}>
                              <input 
                                type="checkbox" 
                                disabled={isDisabled}
                                checked={dedupIdentifierColumns.includes(col)}
                                onChange={(e) => {
                                  if (e.target.checked) setDedupIdentifierColumns(prev => [...prev, col]);
                                  else setDedupIdentifierColumns(prev => prev.filter(c => c !== col));
                                }}
                              />
                              <span>{col}</span>
                            </label>
                          );
                        })}
                      </div>
                    </div>

                    <div className="rounded-md border border-slate-200/60 bg-white p-3 shadow-sm">
                      <span className="block text-xs font-semibold text-slate-800">Ignored Columns</span>
                      <span className="mt-1 block text-[11px] leading-relaxed text-slate-500">
                        Columns to ignore when comparing rows (e.g. timestamps, auto-generated IDs).
                      </span>
                      <div className="mt-2 flex flex-wrap gap-2">
                        {availableColumns.map((col) => {
                          const isDisabled = dedupKeyColumns.includes(col) || dedupIdentifierColumns.includes(col);
                          return (
                            <label key={col} className={`flex items-center gap-1 text-xs border border-slate-200 px-2 py-1 rounded ${isDisabled ? 'opacity-50 cursor-not-allowed bg-slate-100 text-slate-500' : 'text-slate-700 bg-slate-50 cursor-pointer hover:bg-slate-100'}`}>
                              <input 
                                type="checkbox" 
                                disabled={isDisabled}
                                checked={dedupIgnoredColumns.includes(col)}
                                onChange={(e) => {
                                  if (e.target.checked) setDedupIgnoredColumns(prev => [...prev, col]);
                                  else setDedupIgnoredColumns(prev => prev.filter(c => c !== col));
                                }}
                              />
                              <span>{col}</span>
                            </label>
                          );
                        })}
                      </div>
                    </div>
                  </div>
                )}
              </div>

              <div className="rounded-lg border bg-white p-3">
                <span className="block text-xs font-semibold text-slate-800">Survivor Keep Rule</span>
                <span className="mt-1 block text-[11px] leading-relaxed text-slate-500">
                  Rule to determine which data row survives when collapsing duplicates.
                </span>
                <div className="mt-2 flex gap-4">
                  <label className="flex items-center gap-1.5 text-xs text-slate-700 cursor-pointer">
                    <input 
                      type="radio" 
                      name="keepRule" 
                      value="keep_most_complete" 
                      checked={dedupKeepRule === "keep_most_complete"}
                      onChange={(e) => setDedupKeepRule(e.target.value)}
                    />
                    Keep Most Complete
                  </label>
                  <label className="flex items-center gap-1.5 text-xs text-slate-700 cursor-pointer">
                    <input 
                      type="radio" 
                      name="keepRule" 
                      value="keep_first" 
                      checked={dedupKeepRule === "keep_first"}
                      onChange={(e) => setDedupKeepRule(e.target.value)}
                    />
                    Keep First
                  </label>
                  <label className="flex items-center gap-1.5 text-xs text-slate-700 cursor-pointer">
                    <input 
                      type="radio" 
                      name="keepRule" 
                      value="keep_last" 
                      checked={dedupKeepRule === "keep_last"}
                      onChange={(e) => setDedupKeepRule(e.target.value)}
                    />
                    Keep Last
                  </label>
                </div>
              </div>

            </div>
          </div>
        )}

        {!readOnly && nullConflictSection?.fields?.length > 0 && (
          <div className="rounded-xl border border-amber-300 bg-amber-50 p-4 shadow-sm">
            <h4 className="text-sm font-semibold text-amber-900">
              Null strategy compatibility review
            </h4>
            <p className="mt-1 text-xs text-amber-800">
              The planner found strategies that do not match the column semantic type. Keep the
              current strategy or choose a compatible alternative before execution.
            </p>
            <div className="mt-3 space-y-3">
              {nullConflictSection.fields.map((field: any) => {
                const column = String(field.field_key).replace(/^strategy\./, "");
                const conflicts = fillValueConflicts(field, column);
                return (
                  <label key={field.field_key} className="block rounded-lg border bg-white p-3">
                    <span className="block text-xs font-semibold text-slate-800">{field.label}</span>
                    <span className="mt-1 block text-[11px] leading-relaxed text-amber-800">
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
                      className="mt-2 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-xs"
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
                        className="mt-2 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-xs"
                      />
                    )}
                    {conflicts.patternMismatch && (
                      <label className="mt-2 flex items-start gap-2 rounded-md border border-amber-300 bg-amber-50 p-2 text-[11px] text-amber-900">
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
                      <label className="mt-2 flex items-start gap-2 rounded-md border border-amber-300 bg-amber-50 p-2 text-[11px] text-amber-900">
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
                  </label>
                );
              })}
            </div>
          </div>
        )}

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
              onClick={() => {
                const nullReview = nullConflictSection?.fields?.length > 0 ? nullStrategies : undefined;
                const dedupReview = dedupTask ? {
                  key_columns: dedupKeyColumns,
                  identifier_columns: dedupIdentifierColumns,
                  ignored_columns: dedupIgnoredColumns,
                  keep_rule: dedupKeepRule,
                  fuzzy_enabled: dedupFuzzyEnabled,
                } : undefined;
                onApprove(nullReview, dedupReview);
              }}
              disabled={isApproving || hasMissingFillValue || hasUnacknowledgedConflict}
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

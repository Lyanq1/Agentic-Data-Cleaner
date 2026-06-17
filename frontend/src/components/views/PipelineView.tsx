import React, { useEffect, useMemo, useRef, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { wsBaseURL } from "../../api/client";
import { pipelineApi } from "../../api/services";
import {
  HITLCheckpointPanel,
  ResolvedValidationPlanPanel,
  ExecutionPlanPanel,
  ValidationResolutionPendingPanel,
} from "./PipelinePanel";
import { RequirementSummaryPanel } from "./RequirementSummaryPanel";

interface PipelineViewProps {
  runId: string;
  onComplete: () => void;
  onOpenProfile?: () => void;
}

/* ── Status Badge ───────────────────────────────────────────────────────── */

const SpinnerIcon: React.FC<{ className?: string }> = ({
  className = "w-4 h-4",
}) => (
  <span
    aria-hidden="true"
    className={`inline-block rounded-full border-2 border-current border-t-transparent animate-spin ${className}`}
  />
);

const TextIcon: React.FC<{ children: React.ReactNode; className?: string }> = ({
  children,
  className = "w-4 h-4",
}) => (
  <span
    aria-hidden="true"
    className={`inline-flex items-center justify-center text-[10px] font-bold leading-none ${className}`}
  >
    {children}
  </span>
);

const STATUS_CONFIG: Record<
  string,
  { label: string; class: string; icon: React.ReactNode }
> = {
  queued: { label: "Queued", class: "text-slate-500", icon: <SpinnerIcon /> },
  running: { label: "Running", class: "text-blue-600", icon: <SpinnerIcon /> },
  awaiting_hitl: {
    label: "Awaiting Review",
    class: "text-amber-600",
    icon: <TextIcon>!</TextIcon>,
  },
  completed: {
    label: "Completed",
    class: "text-emerald-600",
    icon: <TextIcon>OK</TextIcon>,
  },
  failed: {
    label: "Failed",
    class: "text-red-600",
    icon: <TextIcon>X</TextIcon>,
  },
  cancelled: {
    label: "Cancelled",
    class: "text-gray-500",
    icon: <TextIcon>X</TextIcon>,
  },
};

const StatusBadge: React.FC<{ status: string }> = ({ status }) => {
  const cfg = STATUS_CONFIG[status] ?? STATUS_CONFIG.queued;
  return (
    <span
      className={`inline-flex items-center gap-1.5 text-sm font-semibold ${cfg.class}`}
    >
      {cfg.icon}
      {cfg.label}
    </span>
  );
};

const ReviewSection: React.FC<{
  step: number;
  title: string;
  description: string;
  children: React.ReactNode;
}> = ({ step, title, description, children }) => (
  <section className="space-y-3">
    <div className="flex items-start gap-3">
      <span className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-indigo-600 text-xs font-bold text-white">
        {step}
      </span>
      <div className="min-w-0">
        <h3 className="text-sm font-bold text-foreground">{title}</h3>
        <p className="text-xs text-muted-foreground">{description}</p>
      </div>
    </div>
    <div className="pl-0 sm:pl-10">{children}</div>
  </section>
);

const CompletedPipelineReviewPanel: React.FC<{
  state: any;
  runId: string;
  onOpenProfile?: () => void;
}> = ({ state, runId, onOpenProfile }) => (
  <div className="mb-8 rounded-2xl border-2 border-emerald-300/60 bg-emerald-50/60 shadow-lg overflow-hidden text-left animate-fadeIn">
    <div className="bg-emerald-600 px-6 py-4">
      <h3 className="text-lg font-bold text-white">Completed Pipeline Review</h3>
      <p className="text-white/80 text-sm">
        Review the full path that led to the final report. This view is read-only.
      </p>
    </div>

    <div className="p-6 space-y-8">
      <div className="rounded-xl border border-emerald-200 bg-white px-4 py-3 text-sm text-emerald-800 shadow-sm">
        <strong className="font-semibold">Final report is ready.</strong>{" "}
        You can inspect each stage below without re-running the pipeline.
      </div>

      <ReviewSection
        step={1}
        title="Statistical Profile"
        description="Initial EDA profile generated before HITL validation and planning."
      >
        <div className="rounded-xl border bg-white p-4 shadow-sm space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div className="rounded-lg border bg-muted/20 p-3">
              <div className="text-lg font-bold text-foreground">
                {(state?.data_profile?.total_rows ?? 0).toLocaleString()}
              </div>
              <div className="text-[10px] uppercase tracking-wide text-muted-foreground mt-1">
                Total rows
              </div>
            </div>
            <div className="rounded-lg border bg-muted/20 p-3">
              <div className="text-lg font-bold text-foreground">
                {state?.data_profile?.total_columns ?? 0}
              </div>
              <div className="text-[10px] uppercase tracking-wide text-muted-foreground mt-1">
                Total columns
              </div>
            </div>
            <div className="rounded-lg border bg-muted/20 p-3">
              <div className="text-lg font-bold text-foreground">
                {(state?.data_profile?.duplicate_rows ?? 0).toLocaleString()}
              </div>
              <div className="text-[10px] uppercase tracking-wide text-muted-foreground mt-1">
                Duplicate rows
              </div>
            </div>
          </div>

          <button
            type="button"
            onClick={onOpenProfile}
            disabled={!onOpenProfile}
            className="inline-flex items-center justify-center rounded-lg border bg-background px-4 py-2 text-xs font-semibold text-foreground transition-colors hover:bg-muted disabled:cursor-not-allowed disabled:opacity-50"
          >
            Open full Statistical Profile
          </button>
        </div>
      </ReviewSection>

      <ReviewSection
        step={2}
        title="Requirement And Dataset Specification"
        description="Original user intent, parsed column mapping, and validation summary."
      >
        <RequirementSummaryPanel
          userRequirementsText={state?.user_requirements?.raw_text}
          spec={state?.structured_cleaning_spec}
          validation={state?.requirement_validation}
          compact
        />
      </ReviewSection>

      {state?.input_validation_result && (
        <ReviewSection
          step={3}
          title="Resolved Validation Plan"
          description="Clarifications and cleaning instructions produced before execution planning."
        >
          <ResolvedValidationPlanPanel
            validationResult={state.input_validation_result}
            onGeneratePlan={() => undefined}
            isGenerating={false}
            hasExecutionPlan
          />
        </ReviewSection>
      )}

      {state?.execution_plan && (
        <ReviewSection
          step={4}
          title="Execution Plan And Worker Results"
          description="Worker order, validation gates, strategies, and rules used during the run."
        >
          <ExecutionPlanPanel
            executionPlan={state.execution_plan}
            pipelineState={state}
            runId={runId}
            onApprove={() => undefined}
            isApproving={false}
            readOnly
          />
        </ReviewSection>
      )}
    </div>
  </div>
);

/* ── Main View ──────────────────────────────────────────────────────────── */

export const PipelineView: React.FC<PipelineViewProps> = ({
  runId,
  onComplete,
  onOpenProfile,
}) => {
  const queryClient = useQueryClient();
  const [wsStatus, setWsStatus] = useState<string>("connecting");
  const [liveLogs, setLiveLogs] = useState<any[]>([]);
  const terminalRef = useRef<HTMLDivElement | null>(null);
  const [feedback, setFeedback] = useState("");
  const [isTransitioning, setIsTransitioning] = useState(false);
  const [lastSubmittedCheckpointId, setLastSubmittedCheckpointId] = useState<
    string | null
  >(null);

  // View toggles
  const [showHitl, setShowHitl] = useState(true);
  const [showLogs, setShowLogs] = useState(true);
  const [lastCheckpoint, setLastCheckpoint] = useState<any>(null);
  const [showSpecDetails, setShowSpecDetails] = useState(false);

  const [isGeneratingPlan, setIsGeneratingPlan] = useState(false);
  const [showExecutionPlan, setShowExecutionPlan] = useState(false);
  const [isApprovingPlan, setIsApprovingPlan] = useState(false);

  useEffect(() => {
    setShowExecutionPlan(false);
    setIsGeneratingPlan(false);
    setIsApprovingPlan(false);
    setLiveLogs([]);
  }, [runId]);

  const handleGeneratePlan = () => {
    setIsGeneratingPlan(true);
    setTimeout(() => {
      setIsGeneratingPlan(false);
      setShowExecutionPlan(true);
    }, 2000);
  };

  // Fetch full state periodically or when invalidated
  const { data: state } = useQuery({
    queryKey: ["pipeline-state", runId],
    queryFn: () => pipelineApi.getFullState(runId),
    refetchInterval: (query) => {
      const status = query.state?.data?.status;
      if (query.state?.data?.resolving_hitl) return 1000;
      return status === "completed" || status === "failed" ? false : 3000;
    },
  });

  const [activeLogTab, setActiveLogTab] = useState<"logs" | "thinking">("logs");
  const [expandedAccordions, setExpandedAccordions] = useState<Record<string, boolean>>({
    semantic_profiler: true,
    input_validator: true,
    planner: true,
    validator: true,
  });

  const toggleAccordion = (key: string) => {
    setExpandedAccordions((prev) => ({
      ...prev,
      [key]: !prev[key],
    }));
  };

  const isAgentActive = (agentKey: string) => {
    if (state?.status === "completed" || state?.status === "failed") return false;
    const currentStep = state?.current_step;
    if (agentKey === "semantic_profiler" && currentStep === "semantic_profile") return true;
    if (agentKey === "input_validator" && currentStep === "input_validation") return true;
    if (agentKey === "planner" && currentStep === "planning") return true;
    if (agentKey === "validator" && currentStep === "validation") return true;
    return false;
  };

  useEffect(() => {
    if (!state) return;
    const currentStep = state.current_step;
    let activeKey = "";
    if (currentStep === "semantic_profile") activeKey = "semantic_profiler";
    else if (currentStep === "input_validation") activeKey = "input_validator";
    else if (currentStep === "planning") activeKey = "planner";
    else if (currentStep === "validation") activeKey = "validator";

    if (activeKey) {
      setExpandedAccordions((prev) => ({
        ...prev,
        [activeKey]: true,
      }));
    }
  }, [state?.current_step]);

  const renderFormattedThinking = (text: string) => {
    if (!text) return <span className="text-slate-400 italic">No thinking recorded.</span>;
    return (
      <div className="space-y-2 leading-relaxed text-slate-700 text-sm whitespace-pre-wrap font-sans">
        {text.split('\n').map((line, idx) => {
          const trimmed = line.trim();
          if (trimmed.startsWith('- ') || trimmed.startsWith('* ')) {
            return (
              <div key={idx} className="flex gap-2 pl-2 text-slate-700">
                <span className="text-violet-600 select-none">•</span>
                <span>{line.substring(line.indexOf(trimmed.charAt(0)) + 2)}</span>
              </div>
            );
          }
          if (/^\d+\.\s/.test(trimmed)) {
            const match = trimmed.match(/^(\d+\.)\s(.*)/);
            if (match) {
              return (
                <div key={idx} className="flex gap-2 pl-2 text-slate-700">
                  <span className="text-violet-600 font-bold select-none">{match[1]}</span>
                  <span>{match[2]}</span>
                </div>
              );
            }
          }
          if (trimmed.startsWith('### ')) {
            return (
              <h4 key={idx} className="text-xs font-bold text-violet-700 mt-2 mb-1">
                {trimmed.substring(4)}
              </h4>
            );
          }
          if (trimmed.startsWith('## ')) {
            return (
              <h3 key={idx} className="text-xs font-bold text-violet-700 mt-3 mb-2 border-b border-slate-200 pb-0.5">
                {trimmed.substring(3)}
              </h3>
            );
          }
          if (trimmed.startsWith('# ')) {
            return (
              <h2 key={idx} className="text-sm font-bold text-slate-900 mt-4 mb-2">
                {trimmed.substring(2)}
              </h2>
            );
          }
          return <p key={idx} className="text-slate-700">{line}</p>;
        })}
      </div>
    );
  };

  const thinkingKeys = [
    { key: "semantic_profiler", label: "Semantic Profiler Agent", icon: "🔍" },
    { key: "input_validator", label: "Input Validator Agent", icon: "🛡️" },
    { key: "planner", label: "Execution Planner Agent", icon: "📋" },
    { key: "validator", label: "Output Validator Agent", icon: "⚖️" },
  ];

  const { data: checkpoint } = useQuery({
    queryKey: ["hitl-checkpoint", runId],
    queryFn: () => pipelineApi.getCheckpoint(runId),
    enabled:
      !!state?.status &&
      state?.status !== "completed" &&
      state?.status !== "failed" &&
      state?.awaiting_hitl === true,
  });

  useEffect(() => {
    if (checkpoint) {
      setLastCheckpoint(checkpoint);
    } else if (!state?.awaiting_hitl) {
      setLastCheckpoint(null);
    }
  }, [checkpoint, state?.awaiting_hitl]);

  // WebSocket for real-time status updates
  useEffect(() => {
    const ws = new WebSocket(`${wsBaseURL}/${runId}`);

    ws.onopen = () => setWsStatus("connected");
    ws.onclose = () => setWsStatus("disconnected");
    ws.onerror = () => setWsStatus("error");

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.event === "log" && data.log) {
          setLiveLogs((prev) => {
            const key = `${data.log.timestamp}-${data.log.agent}-${data.log.message}`;
            if (prev.some((log) => `${log.timestamp}-${log.agent}-${log.message}` === key)) {
              return prev;
            }
            return [...prev, data.log].slice(-500);
          });
        }
        if (data.event === "status_change") {
          queryClient.invalidateQueries({
            queryKey: ["pipeline-state", runId],
          });
          queryClient.invalidateQueries({
            queryKey: ["hitl-checkpoint", runId],
          });
          if (data.status === "completed") {
            onComplete();
          }
        }
      } catch (e) {
        console.error("WS parse error", e);
      }
    };

    return () => ws.close();
  }, [runId, queryClient, onComplete]);

  // Handle completion check based on state fallback (if WS misses it)
  useEffect(() => {
    if (state?.status === "completed") {
      onComplete();
    }
  }, [state?.status, onComplete]);

  const submitDecisionMutation = useMutation({
    mutationFn: (data: {
      decision: "approve" | "reject" | "modify";
      feedback?: string;
      disambiguation_answers?: Record<string, string | string[]>;
    }) => {
      setIsTransitioning(true);
      if (!checkpoint) throw new Error("No checkpoint active");
      setLastSubmittedCheckpointId(checkpoint.checkpoint_id);
      return pipelineApi.submitDecision(runId, {
        checkpoint_id: checkpoint.checkpoint_id,
        decision: data.decision,
        feedback: data.feedback,
        disambiguation_answers: data.disambiguation_answers,
      });
    },
    onSuccess: async () => {
      setFeedback("");
      await queryClient.refetchQueries({ queryKey: ["pipeline-state", runId] });
      await queryClient.refetchQueries({
        queryKey: ["hitl-checkpoint", runId],
      });
    },
    onError: () => {
      setIsTransitioning(false);
    },
  });

  const approvePlanMutation = useMutation({
    mutationFn: () => {
      setIsApprovingPlan(true);
      return pipelineApi.approvePlan(runId);
    },
    onSuccess: async () => {
      await queryClient.refetchQueries({ queryKey: ["pipeline-state", runId] });
      await queryClient.refetchQueries({
        queryKey: ["hitl-checkpoint", runId],
      });
    },
    onError: (err: any) => {
      setIsApprovingPlan(false);
      alert(`Error approving plan: ${err.message || err}`);
    },
  });

  useEffect(() => {
    if (!state) return;

    if (
      isApprovingPlan &&
      (state.status === "completed" ||
        state.status === "failed")
    ) {
      setIsApprovingPlan(false);
    }

    if (!state.awaiting_hitl && !state.resolving_hitl) {
      setIsTransitioning(false);
      return;
    }

    // Clear transitioning state if we hit a NEW checkpoint
    if (
      state.current_checkpoint_id &&
      state.current_checkpoint_id !== lastSubmittedCheckpointId
    ) {
      setIsTransitioning(false);
    }
  }, [
    isApprovingPlan,
    state?.status,
    state?.awaiting_hitl,
    state?.resolving_hitl,
    state?.current_checkpoint_id,
    lastSubmittedCheckpointId,
  ]);

  const wsIndicator = (
    <span
      className={`inline-flex items-center gap-1.5 text-xs ${wsStatus === "connected" ? "text-emerald-500" : "text-muted-foreground"}`}
    >
      <span
        className={`w-1.5 h-1.5 rounded-full ${wsStatus === "connected" ? "bg-emerald-500 animate-pulse" : "bg-gray-400"}`}
      />
      {wsStatus === "connected" ? "Live" : wsStatus}
    </span>
  );

  const terminalLogs = useMemo(() => {
    const merged = [...(state?.agent_logs || []), ...liveLogs];
    const seen = new Set<string>();
    return merged.filter((log: any) => {
      const key = `${log.timestamp}-${log.agent}-${log.message}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
  }, [state?.agent_logs, liveLogs]);

  useEffect(() => {
    if (!terminalRef.current) return;
    terminalRef.current.scrollTop = terminalRef.current.scrollHeight;
  }, [terminalLogs.length]);

  const activeCheckpoint = state?.awaiting_hitl
    ? checkpoint || lastCheckpoint
    : null;
  const hasHitl = Boolean(activeCheckpoint);
  const isPipelineCompleted = state?.status === "completed";
  const isValidationReady = state?.input_validation_result?.status === "ready";
  const isWaitingForResolution = Boolean(state?.resolving_hitl);

  const displayHitl = hasHitl && showHitl;
  const displayPendingResolution =
    isWaitingForResolution && showHitl && !hasHitl;
  const displayExecutionReview = Boolean(
    showHitl && state?.execution_plan && (showExecutionPlan || isPipelineCompleted),
  );
  const displayResolvedPlan =
    isValidationReady && showHitl && !hasHitl && !displayExecutionReview;
  const showLeftPanel =
    displayHitl || displayPendingResolution || displayExecutionReview || displayResolvedPlan;
  const reviewPanelAvailable =
    hasHitl || isWaitingForResolution || isValidationReady || Boolean(state?.execution_plan);
  const displayLogs = showLogs || !showLeftPanel;

  const isRequirementHitl =
    displayHitl && activeCheckpoint?.checkpoint_type === "requirement_approval";
  const showRequirementSummaryBar =
    Boolean(
      state?.structured_cleaning_spec || state?.user_requirements?.raw_text,
    ) && !isRequirementHitl;

  return (
    <div className="w-full h-full flex flex-col flex-1 min-h-0 text-left">
      {/* Header */}
      <div className="flex-none flex flex-col gap-3 bg-card px-3 py-3 border rounded-xl shadow-sm sm:px-4 md:flex-row md:items-center md:justify-between mb-4">
        <div className="min-w-0">
          <h2 className="text-xl font-bold tracking-tight">
            Pipeline Processing
          </h2>
          <p className="text-xs text-muted-foreground mt-0.5 min-w-0">
            Run ID:{" "}
            <code className="inline-block max-w-full bg-muted px-1.5 py-0.5 rounded font-mono align-bottom truncate">
              {runId}
            </code>
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-3 sm:gap-4">
          <div className="flex items-center gap-1 border bg-muted/30 p-1 rounded-lg">
            <button
              onClick={() => setShowHitl(!showHitl)}
              disabled={!reviewPanelAvailable}
              className={`p-1.5 rounded text-sm flex items-center gap-2 transition-colors ${
                showLeftPanel
                  ? "bg-white shadow-sm text-foreground"
                  : reviewPanelAvailable
                    ? "text-muted-foreground hover:bg-muted/50"
                    : "text-muted-foreground/30 cursor-not-allowed"
              }`}
              title="Toggle Review Panel"
            >
              <TextIcon>{showLeftPanel ? "<<" : "<"}</TextIcon>
              <span className="hidden sm:inline text-xs font-medium">
                Review
              </span>
            </button>
            <button
              onClick={() => setShowLogs(!showLogs)}
              className={`p-1.5 rounded text-sm flex items-center gap-2 transition-colors ${
                displayLogs
                  ? "bg-white shadow-sm text-foreground"
                  : "text-muted-foreground hover:bg-muted/50"
              }`}
              title="Toggle Logs Terminal"
            >
              <TextIcon>{displayLogs ? ">>" : ">"}</TextIcon>
              <span className="hidden sm:inline text-xs font-medium">Logs</span>
            </button>
          </div>
          <div className="h-6 w-px bg-border"></div>
          <StatusBadge status={state?.status || "queued"} />
        </div>
      </div>

      {showRequirementSummaryBar && (
        <div className="flex-none mb-4 bg-card border rounded-xl shadow-sm overflow-hidden">
          <button
            type="button"
            onClick={() => setShowSpecDetails(!showSpecDetails)}
            className="w-full px-4 py-3 flex items-center justify-between text-xs font-semibold hover:bg-muted/40 transition-colors"
          >
            <span className="flex items-center gap-2">
              📋 Dataset Specification Mapping & Validation Summary
            </span>
            <span className="text-[10px] text-muted-foreground uppercase tracking-wider font-semibold">
              {showSpecDetails ? "Hide details" : "Show details"}
            </span>
          </button>
          {showSpecDetails && (
            <div className="border-t max-h-[35vh] overflow-y-auto p-4 custom-scrollbar bg-muted/10">
              <RequirementSummaryPanel
                userRequirementsText={state?.user_requirements?.raw_text}
                spec={state?.structured_cleaning_spec}
                validation={state?.requirement_validation}
              />
            </div>
          )}
        </div>
      )}

      {/* Split View Container */}
      <div className="flex-1 min-h-0 flex flex-col lg:flex-row gap-4 lg:gap-6 overflow-y-auto lg:overflow-hidden custom-scrollbar">
        {/* Left Column: HITL Review Panel or Action Plan Summary */}
        {showLeftPanel && (
          <div
            className={`flex flex-col min-h-0 min-w-0 transition-all duration-300 ${displayLogs ? "lg:w-1/2" : "w-full"} ${displayLogs ? "min-h-[320px] lg:min-h-0" : ""} lg:flex-1`}
          >
            <div className="flex-1 min-h-0 overflow-y-auto pr-2 pb-4 custom-scrollbar">
              {displayHitl ? (
                <HITLCheckpointPanel
                  checkpoint={activeCheckpoint}
                  pipelineState={state}
                  userRequirementsText={state?.user_requirements?.raw_text}
                  feedback={feedback}
                  onFeedbackChange={setFeedback}
                  onDecision={(decision, fb, disambiguation_answers) =>
                    submitDecisionMutation.mutate({
                      decision,
                      feedback: fb,
                      disambiguation_answers,
                    })
                  }
                  isPending={
                    submitDecisionMutation.isPending || isTransitioning
                  }
                  isAwaiting={Boolean(state?.awaiting_hitl && checkpoint)}
                />
              ) : displayPendingResolution ? (
                <ValidationResolutionPendingPanel />
              ) : displayExecutionReview && isPipelineCompleted ? (
                <CompletedPipelineReviewPanel
                  state={state}
                  runId={runId}
                  onOpenProfile={onOpenProfile}
                />
              ) : displayExecutionReview && state?.execution_plan ? (
                <ExecutionPlanPanel
                  executionPlan={state.execution_plan}
                  pipelineState={state}
                  runId={runId}
                  onApprove={() => approvePlanMutation.mutate()}
                  isApproving={isApprovingPlan || approvePlanMutation.isPending}
                />
              ) : (
                <ResolvedValidationPlanPanel
                  validationResult={state.input_validation_result}
                  onGeneratePlan={handleGeneratePlan}
                  isGenerating={isGeneratingPlan}
                />
              )}

              {/* Mutation error feedback */}
              {submitDecisionMutation.isError && (
                <div className="mt-4 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
                  <strong>Error submitting decision:</strong>{" "}
                  {(submitDecisionMutation.error as Error)?.message ||
                    "Unknown error"}
                </div>
              )}
            </div>
          </div>
        )}

        {/* Right Column: Execution Logs */}
        {displayLogs && (
          <div
            className={`flex flex-col min-h-0 min-w-0 transition-all duration-300 ${showLeftPanel ? "lg:w-1/2" : "w-full"} ${showLeftPanel ? "min-h-[320px] lg:min-h-0" : ""} lg:flex-1`}
          >
            <div className="flex-1 bg-card border rounded-xl shadow-sm flex flex-col min-h-[300px] overflow-hidden">
              <div className="border-b bg-muted/30 flex justify-between items-center flex-none px-2">
                <div className="flex items-center gap-1">
                  <button
                    onClick={() => setActiveLogTab("logs")}
                    className={`px-3 py-2.5 text-xs font-semibold flex items-center gap-2 border-b-2 transition-all cursor-pointer ${
                      activeLogTab === "logs"
                        ? "border-primary text-foreground"
                        : "border-transparent text-muted-foreground hover:text-foreground"
                    }`}
                  >
                    <TextIcon className="w-3.5 h-3.5">&gt;_</TextIcon>
                    Agent Terminal
                  </button>
                  <button
                    onClick={() => setActiveLogTab("thinking")}
                    className={`px-3 py-2.5 text-xs font-semibold flex items-center gap-2 border-b-2 transition-all cursor-pointer ${
                      activeLogTab === "thinking"
                        ? "border-primary text-foreground"
                        : "border-transparent text-muted-foreground hover:text-foreground"
                    }`}
                  >
                    <span className="text-xs">🧠</span>
                    LLM Thinking Process
                  </button>
                </div>
                <div className="pr-3">
                  {wsIndicator}
                </div>
              </div>
              <div
                ref={activeLogTab === "logs" ? terminalRef : null}
                className={`flex-1 overflow-auto custom-scrollbar flex flex-col min-h-0 ${
                  activeLogTab === "logs" 
                    ? "bg-slate-950 text-slate-300" 
                    : "bg-white text-slate-800"
                }`}
              >
                {activeLogTab === "logs" ? (
                  <div className="p-4 font-mono text-[11px] leading-relaxed flex-1">
                    {terminalLogs.length ? (
                      terminalLogs.map((log: any, i: number) => (
                        <div
                          key={i}
                          className="mb-2 pb-2 border-b border-slate-800/50"
                        >
                          <span className="text-blue-400">
                            [
                            {log.timestamp
                              ? new Date(log.timestamp * 1000).toLocaleTimeString(
                                  "en-GB",
                                  { timeZone: "Asia/Bangkok" },
                                )
                              : new Date().toLocaleTimeString("en-GB", {
                                  timeZone: "Asia/Bangkok",
                                })}
                            ]
                          </span>{" "}
                          <span className="text-purple-400 font-semibold">
                            {log.agent || "system"}:
                          </span>{" "}
                          {log.level && log.level !== "info" && (
                            <span
                              className={`mr-1 font-semibold uppercase ${
                                log.level === "error" ? "text-red-400" : "text-amber-300"
                              }`}
                            >
                              [{log.level}]
                            </span>
                          )}
                          <span
                            className={`break-words whitespace-pre-wrap ${
                              log.level === "error"
                                ? "text-red-300"
                                : log.level === "warning"
                                  ? "text-amber-300"
                                  : "text-slate-200"
                            }`}
                          >
                            {log.message || JSON.stringify(log)}
                          </span>
                        </div>
                      ))
                    ) : (
                      <div className="text-slate-500 flex items-center gap-2 h-full justify-center min-h-[200px]">
                        <SpinnerIcon className="w-4 h-4 opacity-50" />
                        Waiting for agents to start...
                      </div>
                    )}
                    {state?.error_message && (
                      <div className="text-red-400 mt-4 border border-red-900/50 bg-red-950/30 p-3 rounded font-sans text-xs">
                        <strong>Fatal Error:</strong> {state.error_message}
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="p-4 space-y-4 flex-1">
                    {thinkingKeys.map(({ key, label, icon }) => {
                      const thinking = state?.agent_thinkings?.[key] || "";
                      const isActive = isAgentActive(key);
                      const isExpanded = expandedAccordions[key];
                      const hasThinking = Boolean(thinking);

                      return (
                        <div key={key} className="border border-slate-200 bg-white rounded-xl overflow-hidden shadow-sm transition-all duration-300 hover:border-slate-300">
                          <button
                            onClick={() => toggleAccordion(key)}
                            className="w-full px-4 py-3 flex items-center justify-between text-left hover:bg-slate-50 transition-colors"
                          >
                            <div className="flex items-center gap-2">
                              <span className="text-xs select-none">{icon}</span>
                              <span className="text-sm font-bold text-slate-800">{label}</span>
                              {isActive && (
                                <span className="flex items-center gap-1 text-[10px] bg-violet-100 text-violet-700 border border-violet-200 px-2 py-0.5 rounded-full font-semibold">
                                  <span className="w-1.5 h-1.5 rounded-full bg-violet-500 animate-ping" />
                                  Thinking...
                                </span>
                              )}
                              {!isActive && hasThinking && (
                                <span className="text-[9px] bg-emerald-100 text-emerald-700 border border-emerald-200 px-2 py-0.5 rounded-full font-semibold">
                                  Complete
                                </span>
                              )}
                              {!isActive && !hasThinking && (
                                <span className="text-[9px] bg-slate-100 text-slate-500 border border-slate-200 px-2 py-0.5 rounded-full font-semibold">
                                  Pending
                                </span>
                              )}
                            </div>
                            <span className="text-[10px] text-slate-400 font-mono transition-transform duration-200">
                              {isExpanded ? "▲" : "▼"}
                            </span>
                          </button>
                          
                          {isExpanded && (
                            <div className="px-4 pb-4 border-t border-slate-100 pt-3 bg-slate-50/50">
                              {isActive && !hasThinking ? (
                                <div className="flex items-center gap-2 py-4 text-slate-500 justify-center font-sans">
                                  <SpinnerIcon className="w-3.5 h-3.5 text-violet-500 animate-spin" />
                                  <span>Analyzing dataset context and formulating decisions...</span>
                                </div>
                              ) : hasThinking ? (
                                <div className="border-l-2 border-violet-400 pl-3">
                                  {renderFormattedThinking(thinking)}
                                </div>
                              ) : (
                                <div className="py-3 text-slate-400 text-[10px] italic text-center font-sans">
                                  Awaiting pipeline execution of this agent.
                                </div>
                              )}
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

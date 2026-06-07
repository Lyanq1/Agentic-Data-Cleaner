import React, { useEffect, useState } from "react";
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

/* ── Main View ──────────────────────────────────────────────────────────── */

export const PipelineView: React.FC<PipelineViewProps> = ({
  runId,
  onComplete,
}) => {
  const queryClient = useQueryClient();
  const [wsStatus, setWsStatus] = useState<string>("connecting");
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
      setIsApprovingPlan(false);
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

  const activeCheckpoint = state?.awaiting_hitl
    ? checkpoint || lastCheckpoint
    : null;
  const hasHitl = Boolean(activeCheckpoint);
  const isValidationReady = state?.input_validation_result?.status === "ready";
  const isWaitingForResolution = Boolean(state?.resolving_hitl);

  const displayHitl = hasHitl && showHitl;
  const displayPendingResolution =
    isWaitingForResolution && showHitl && !hasHitl;
  const displayResolvedPlan = isValidationReady && showHitl && !hasHitl;
  const showLeftPanel =
    displayHitl || displayPendingResolution || displayResolvedPlan;
  const reviewPanelAvailable =
    hasHitl || isWaitingForResolution || isValidationReady;
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
      <div className="flex-none flex flex-wrap items-center justify-between mb-4 gap-4 bg-card px-4 py-3 border rounded-xl shadow-sm">
        <div>
          <h2 className="text-xl font-bold tracking-tight">
            Pipeline Processing
          </h2>
          <p className="text-xs text-muted-foreground mt-0.5">
            Run ID:{" "}
            <code className="bg-muted px-1.5 py-0.5 rounded font-mono">
              {runId}
            </code>
          </p>
        </div>

        <div className="flex items-center gap-4">
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
      <div className="flex-1 min-h-0 flex gap-6 overflow-hidden">
        {/* Left Column: HITL Review Panel or Action Plan Summary */}
        {showLeftPanel && (
          <div
            className={`flex flex-col min-h-0 min-w-0 transition-all duration-300 ${displayLogs ? "w-1/2" : "w-full"}`}
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
              ) : showExecutionPlan && state?.execution_plan ? (
                <ExecutionPlanPanel
                  executionPlan={state.execution_plan}
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
            className={`flex flex-col min-h-0 min-w-0 transition-all duration-300 ${showLeftPanel ? "w-1/2" : "w-full"}`}
          >
            <div className="flex-1 bg-card border rounded-xl shadow-sm flex flex-col min-h-[300px] overflow-hidden">
              <div className="border-b px-4 py-3 bg-muted/30 flex justify-between items-center flex-none">
                <div className="flex items-center gap-2 text-foreground font-semibold text-sm">
                  <TextIcon>&gt;_</TextIcon>
                  Agent Execution Logs
                </div>
                {wsIndicator}
              </div>
              <div className="flex-1 p-4 overflow-auto font-mono text-[11px] leading-relaxed bg-slate-950 text-slate-300 custom-scrollbar">
                {state?.agent_logs?.length ? (
                  state.agent_logs.map((log: any, i: number) => (
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
                      <span className="text-slate-200 break-words whitespace-pre-wrap">
                        {log.message || JSON.stringify(log)}
                      </span>
                    </div>
                  ))
                ) : (
                  <div className="text-slate-500 flex items-center gap-2 h-full justify-center">
                    <SpinnerIcon className="w-4 h-4 opacity-50" />
                    Waiting for agents to start...
                  </div>
                )}
                {state?.error_message && (
                  <div className="text-red-400 mt-4 border border-red-900/50 bg-red-950/30 p-3 rounded">
                    <strong>Fatal Error:</strong> {state.error_message}
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

import React, { useState, useEffect, useCallback, useMemo, useRef } from "react";
import { pipelineApi } from "../../api/services";
import {
  Upload,
  Play,
  Square,
  Plus,
  Trash2,
  AlertCircle,
  CheckCircle2,
  Layers,
  Settings2,
  Check,
  Database,
  Loader2
} from "lucide-react";
import { formatDisplayValue, getOptionConsequence, tryFormatToISO } from "./pipelinepanel/utils";

interface QueueItem {
  id: string;
  file: File | null;
  cleanFile: File | null;
  requirements: string;
  runId: string | null;
  status: "idle" | "uploading" | "running" | "needs_clarification" | "resuming" | "completed" | "failed";
  progress: number;
  error: string | null;
  checkpoint: any;
  report: any;
}

export const MassUploadView: React.FC = () => {
  const [queue, setQueue] = useState<QueueItem[]>([]);
  const [autoApprove, setAutoApprove] = useState<boolean>(true);
  const [maxConcurrency, setMaxConcurrency] = useState<number>(2);
  const [selectedInspectId, setSelectedInspectId] = useState<string | null>(null);
  const [defaultPrompt] = useState<string>("");
  const [isProcessing, setIsProcessing] = useState<boolean>(false);

  // For managing answers to clarifications
  const [mcqAnswers, setMcqAnswers] = useState<Record<string, string>>({});
  const [customInputs, setCustomInputs] = useState<Record<string, string>>({});
  const [submittingAnswers, setSubmittingAnswers] = useState<boolean>(false);

  const pollIntervalsRef = useRef<Record<string, number>>({});
  const approvedCheckpointsRef = useRef<Set<string>>(new Set());
  const lastStartTimestampRef = useRef<number>(0);
  const startTimeoutRef = useRef<number | null>(null);

  const queueRef = useRef<QueueItem[]>([]);
  const selectedInspectIdRef = useRef<string | null>(null);

  useEffect(() => {
    queueRef.current = queue;
  }, [queue]);

  useEffect(() => {
    selectedInspectIdRef.current = selectedInspectId;
  }, [selectedInspectId]);

  const getColumnExpectedTypeFromPayload = (payload: any, qKey: string, currentAnswers?: Record<string, string>): string => {
    const colName = qKey.startsWith("Q2_strategy_column_")
      ? qKey.substring("Q2_strategy_column_".length)
      : qKey.startsWith("Q1_allow_missing_column_")
        ? qKey.substring("Q1_allow_missing_column_".length)
        : qKey.startsWith("Q1_cast_column_")
          ? qKey.substring("Q1_cast_column_".length)
          : "";
    if (!colName) return "str";
    const semProfile = payload?.semantic_profile || {};
    const colDetail = semProfile.columns?.[colName];
    const expectedType = colDetail?.expected_type || "str";

    let castAnswer: string | undefined = currentAnswers?.[`typecast.Q1_cast_column_${colName}`];
    if (!castAnswer && payload?.clarifications?.typecast?.[`Q1_cast_column_${colName}`]) {
      const castQ = payload.clarifications.typecast[`Q1_cast_column_${colName}`];
      castAnswer = castQ.answer || castQ.previous_answer || undefined;
    }
    
    if (castAnswer === "No") {
      return "str";
    }

    return expectedType;
  };

  useEffect(() => {
    if (!activeItem || !activeItem.checkpoint || activeItem.checkpoint.checkpoint_type !== "input_validation_clarification") {
      setMcqAnswers({});
      setCustomInputs({});
      return;
    }

    const payload = activeItem.checkpoint.payload || {};
    const clarifications = payload.clarifications || {};
    const categories = ["typecast", "null", "duplicate"] as const;

    const nextAnswers: Record<string, string> = {};
    const nextCustom: Record<string, string> = {};

    categories.forEach((cat) => {
      const catData = clarifications[cat];
      if (catData) {
        Object.keys(catData).forEach((qKey) => {
          const q = catData[qKey];
          if (q) {
            const ansVal = q.answer || q.previous_answer;
            if (ansVal) {
              if (ansVal.startsWith("Custom strategy:")) {
                nextAnswers[`${cat}.${qKey}`] = "Custom strategy (describe in your next prompt)";
                const rawCustom = ansVal.substring("Custom strategy:".length).trim();
                const expectedType = getColumnExpectedTypeFromPayload(payload, qKey, nextAnswers);
                nextCustom[`${cat}.${qKey}`] = tryFormatToISO(rawCustom, expectedType);
              } else if (ansVal.startsWith("fill_value:")) {
                nextAnswers[`${cat}.${qKey}`] = "fill_value";
                const val = ansVal.substring("fill_value:".length).trim();
                const expectedType = getColumnExpectedTypeFromPayload(payload, qKey, nextAnswers);
                nextCustom[`${cat}.${qKey}`] = tryFormatToISO(val, expectedType);
              } else {
                nextAnswers[`${cat}.${qKey}`] = ansVal;
              }
            }
          }
        });
      }
    });

    setMcqAnswers(nextAnswers);
    setCustomInputs(nextCustom);
  }, [activeItem?.id, activeItem?.checkpoint?.checkpoint_id]);

  // Add a new row to the queue
  const addRow = () => {
    const newItem: QueueItem = {
      id: Math.random().toString(36).substring(2, 9),
      file: null,
      cleanFile: null,
      requirements: defaultPrompt,
      runId: null,
      status: "idle",
      progress: 0,
      error: null,
      checkpoint: null,
      report: null,
    };
    setQueue((prev) => [...prev, newItem]);
  };

  // Pre-populate with 3 rows on mount if empty
  useEffect(() => {
    if (queue.length === 0) {
      setQueue([
        {
          id: "row-1",
          file: null,
          cleanFile: null,
          requirements: "",
          runId: null,
          status: "idle",
          progress: 0,
          error: null,
          checkpoint: null,
          report: null,
        },
        {
          id: "row-2",
          file: null,
          cleanFile: null,
          requirements: "",
          runId: null,
          status: "idle",
          progress: 0,
          error: null,
          checkpoint: null,
          report: null,
        }
      ]);
    }
  }, []);

  // Update a single item's fields in the queue
  const updateItem = (id: string, updates: Partial<QueueItem>) => {
    setQueue((prev) =>
      prev.map((item) => (item.id === id ? { ...item, ...updates } : item))
    );
  };

  // Remove a row
  const removeRow = (id: string) => {
    const item = queue.find((q) => q.id === id);
    if (item && (item.status === "uploading" || item.status === "running" || item.status === "resuming")) {
      alert("Cannot remove a running file.");
      return;
    }

    stopPolling(id);
    setQueue((prev) => prev.filter((item) => item.id !== id));

    if (selectedInspectId === id) {
      const nextNeedsClarification = queue.find((item) => item.id !== id && item.status === "needs_clarification");
      if (nextNeedsClarification) {
        setSelectedInspectId(nextNeedsClarification.id);
      } else {
        setSelectedInspectId(null);
      }
    }
  };

  // Clear all idle rows
  const clearQueue = () => {
    if (isProcessing) {
      alert("Cannot clear queue while processing is active.");
      return;
    }
    setQueue([]);
  };

  // Helper: Estimate progress based on completed steps
  const estimateProgress = (state: any): number => {
    if (!state) return 0;
    if (state.status === "completed") return 100;
    
    const steps = state.completed_steps || [];
    let progress = 10; // Ingestion done
    if (steps.includes("profiling")) progress += 20;
    if (steps.includes("input_validation")) progress += 20;
    if (steps.includes("planning")) progress += 10;
    if (steps.includes("deduplication") || steps.includes("null_handling") || steps.includes("type_casting")) {
      progress += 25;
    }
    if (steps.includes("validation")) progress += 10;
    return Math.min(progress, 95);
  };

  // Submit manual decision / resume for active item
  const handleResolveClarification = async () => {
    // Find the item currently awaiting HITL (either selected or first priority)
    const activeItem = selectedInspectId
      ? queue.find((item) => item.id === selectedInspectId)
      : queue.find((item) => item.status === "needs_clarification");
    
    if (!activeItem || !activeItem.runId || !activeItem.checkpoint) return;

    setSubmittingAnswers(true);
    try {
      const checkpoint = activeItem.checkpoint;
      const type = checkpoint.checkpoint_type;

      if (type === "input_validation_clarification") {
        const finalAnswers = { ...mcqAnswers };
        Object.keys(finalAnswers).forEach((key) => {
          if (finalAnswers[key].includes("Custom strategy") && customInputs[key]) {
            finalAnswers[key] = `Custom strategy: ${customInputs[key].trim()}`;
          }
        });

        await pipelineApi.submitDecision(activeItem.runId, {
          checkpoint_id: checkpoint.checkpoint_id,
          decision: "approve",
          disambiguation_answers: finalAnswers,
        });
      } else {
        // Plan approval or validation review
        await pipelineApi.approvePlan(activeItem.runId);
      }

      setMcqAnswers({});
      setCustomInputs({});
      updateItem(activeItem.id, { status: "resuming", checkpoint: null });
      
      // Auto-select the next item in the queue that needs clarification
      const nextNeedsClarification = queue.find(
        (item) => item.id !== activeItem.id && item.status === "needs_clarification"
      );
      if (nextNeedsClarification) {
        setSelectedInspectId(nextNeedsClarification.id);
      }

      // Restart the polling loop
      resumePolling(activeItem.id);
    } catch (err: any) {
      alert(`Failed to submit answers: ${err.message || err}`);
    } finally {
      setSubmittingAnswers(false);
    }
  };

  // Start polling function
  const startPolling = (runId: string, itemId: string) => {
    if (pollIntervalsRef.current[itemId]) {
      clearInterval(pollIntervalsRef.current[itemId]);
      delete pollIntervalsRef.current[itemId];
    }

    const checkState = async () => {
      try {
        const state = await pipelineApi.getFullState(runId);
        
        // Handle completed state
        if (state.status === "completed") {
          if (pollIntervalsRef.current[itemId]) {
            clearInterval(pollIntervalsRef.current[itemId]);
            delete pollIntervalsRef.current[itemId];
          }

          const report = await pipelineApi.getReport(runId);
          updateItem(itemId, {
            status: "completed",
            progress: 100,
            report,
          });
          return;
        }

        // Handle failed state
        if (state.status === "failed") {
          if (pollIntervalsRef.current[itemId]) {
            clearInterval(pollIntervalsRef.current[itemId]);
            delete pollIntervalsRef.current[itemId];
          }

          updateItem(itemId, {
            status: "failed",
            error: state.error_message || "Backend pipeline run failed.",
          });
          return;
        }

        // Handle checkpoints (needs clarifications)
        const hasUnanswered = state.awaiting_hitl && state.input_validation_result?.status === "needs_clarification";
        if (hasUnanswered) {
          const checkpoint = await pipelineApi.getCheckpoint(runId);
          if (checkpoint && checkpoint.checkpoint_type === "input_validation_clarification") {
            if (pollIntervalsRef.current[itemId]) {
              clearInterval(pollIntervalsRef.current[itemId]);
              delete pollIntervalsRef.current[itemId];
            }

            updateItem(itemId, {
              status: "needs_clarification",
              checkpoint,
            });

            // Only select this item if the user is not currently inspecting another item that needs clarification
            const currentQueue = queueRef.current;
            const currentSelectedId = selectedInspectIdRef.current;
            const currentlyInspectedItem = currentQueue.find((q) => q.id === currentSelectedId);
            const isUserBusyWithClarification = currentlyInspectedItem && currentlyInspectedItem.status === "needs_clarification";
            if (!isUserBusyWithClarification) {
              setSelectedInspectId(itemId);
            }
            return;
          }
        }

        // Handle paused before worker tasks (Plan approval)
        const isPausedAtPlanApproval = state.next_node && state.next_node.some((node: string) =>
          ["deduplication", "type_casting", "null_handling"].includes(node)
        );

        // Handle paused before report generation (Validation review)
        const isPausedAtValidationReview = state.next_node && state.next_node.includes("report_agent");

        if (isPausedAtPlanApproval || isPausedAtValidationReview) {
          if (autoApprove) {
            // Automatically approve plan/review exactly once per checkpoint key to avoid loops
            const checkpointKey = runId + "_" + (isPausedAtPlanApproval ? "plan" : "review");
            if (!approvedCheckpointsRef.current.has(checkpointKey)) {
              approvedCheckpointsRef.current.add(checkpointKey);
              updateItem(itemId, { status: "resuming" });
              await pipelineApi.approvePlan(runId);
            }
          } else {
            // Stop polling and display manual approval dialog to the user
            if (pollIntervalsRef.current[itemId]) {
              clearInterval(pollIntervalsRef.current[itemId]);
              delete pollIntervalsRef.current[itemId];
            }

            const checkpoint = await pipelineApi.getCheckpoint(runId) || {
              checkpoint_id: runId + (isPausedAtPlanApproval ? "_plan" : "_review"),
              checkpoint_type: isPausedAtPlanApproval ? "plan_approval" : "validation_review",
              message_to_user: isPausedAtPlanApproval 
                ? "Execution plan generated. Please review and approve."
                : "Validation checks completed. Please review and finalize.",
              payload: state
            };

            updateItem(itemId, {
              status: "needs_clarification",
              checkpoint,
            });

            // Only select this item if the user is not currently inspecting another item that needs clarification
            const currentQueue = queueRef.current;
            const currentSelectedId = selectedInspectIdRef.current;
            const currentlyInspectedItem = currentQueue.find((q) => q.id === currentSelectedId);
            const isUserBusyWithClarification = currentlyInspectedItem && currentlyInspectedItem.status === "needs_clarification";
            if (!isUserBusyWithClarification) {
              setSelectedInspectId(itemId);
            }
          }
          return;
        }

        // Update progress if still running
        updateItem(itemId, {
          status: "running",
          progress: estimateProgress(state),
        });

      } catch (err) {
        console.error(`Error polling backend state for item ${itemId}:`, err);
      }
    };

    // Run first check immediately, then periodically
    checkState();
    pollIntervalsRef.current[itemId] = window.setInterval(checkState, 2000);
  };

  // Stop polling helper
  const stopPolling = (itemId?: string) => {
    if (itemId) {
      if (pollIntervalsRef.current[itemId]) {
        clearInterval(pollIntervalsRef.current[itemId]);
        delete pollIntervalsRef.current[itemId];
      }
    } else {
      Object.keys(pollIntervalsRef.current).forEach((id) => {
        clearInterval(pollIntervalsRef.current[id]);
      });
      pollIntervalsRef.current = {};
    }
  };

  // Resume polling for the active item
  const resumePolling = (itemId: string) => {
    const item = queue.find((q) => q.id === itemId);
    if (item && item.runId) {
      startPolling(item.runId, item.id);
    }
  };

  // Run the item by its ID
  const runActiveItem = useCallback(async (itemId: string) => {
    const item = queue.find((q) => q.id === itemId);
    if (!item || !item.file) return;

    updateItem(item.id, { status: "uploading", progress: 5, error: null });

    try {
      const response = await pipelineApi.uploadFile(item.file, item.requirements, item.cleanFile);
      updateItem(item.id, {
        runId: response.run_id,
        status: "running",
        progress: 15,
      });

      // Start the state polling loop
      startPolling(response.run_id, item.id);
    } catch (err: any) {
      updateItem(item.id, {
        status: "failed",
        error: err.response?.data?.detail || err.message || "Failed to upload file.",
      });
    }
  }, [queue]);

  // Monitor queue and trigger jobs concurrently
  useEffect(() => {
    if (!isProcessing) {
      if (startTimeoutRef.current) {
        clearTimeout(startTimeoutRef.current);
        startTimeoutRef.current = null;
      }
      return;
    }

    const activePool = queue.filter(
      (item) =>
        item.status === "uploading" ||
        item.status === "running" ||
        item.status === "resuming"
    );

    const hasClarification = queue.some((item) => item.status === "needs_clarification");

    if (activePool.length < maxConcurrency) {
      // Find the next idle item that has a file to process
      const nextIdle = queue.find((item) => item.status === "idle" && item.file);

      if (nextIdle) {
        // Rate limit starting jobs
        const now = Date.now();
        const timeSinceLastStart = now - lastStartTimestampRef.current;
        const delay = Math.max(0, 1500 - timeSinceLastStart);

        if (delay === 0) {
          lastStartTimestampRef.current = now;
          // Temporarily set status to "uploading" to prevent double-spawning in next tick
          updateItem(nextIdle.id, { status: "uploading", progress: 1 });
          runActiveItem(nextIdle.id);
        } else {
          if (!startTimeoutRef.current) {
            startTimeoutRef.current = window.setTimeout(() => {
              startTimeoutRef.current = null;
              // Re-check queue state inside the timeout to ensure safety
              setQueue((currentQueue) => {
                const refreshedIdle = currentQueue.find((item) => item.id === nextIdle.id && item.status === "idle");
                if (refreshedIdle && refreshedIdle.file) {
                  lastStartTimestampRef.current = Date.now();
                  // Temporarily update state
                  setTimeout(() => {
                    updateItem(refreshedIdle.id, { status: "uploading", progress: 1 });
                    runActiveItem(refreshedIdle.id);
                  }, 0);
                }
                return currentQueue;
              });
            }, delay);
          }
        }
      } else {
        // No more idle items. If nothing is active and no items are waiting for clarification, stop processing
        if (activePool.length === 0 && !hasClarification) {
          setIsProcessing(false);
        }
      }
    }
  }, [queue, isProcessing, maxConcurrency, runActiveItem]);

  // Clean up polling timers on unmount
  useEffect(() => {
    return () => {
      stopPolling();
      if (startTimeoutRef.current) clearTimeout(startTimeoutRef.current);
    };
  }, []);

  // Trigger processing of the queue
  const startProcessing = () => {
    if (queue.length === 0) {
      alert("The queue is empty. Please add files first.");
      return;
    }
    const hasUnpicked = queue.some((item) => !item.file);
    if (hasUnpicked) {
      alert("Please select a data file for all rows in the queue.");
      return;
    }

    approvedCheckpointsRef.current.clear();
    setIsProcessing(true);
  };

  // Stop processing loop
  const stopProcessing = () => {
    approvedCheckpointsRef.current.clear();
    setIsProcessing(false);
    stopPolling();
    if (startTimeoutRef.current) {
      clearTimeout(startTimeoutRef.current);
      startTimeoutRef.current = null;
    }
    // Set all uploading/running items back to idle
    setQueue((prev) =>
      prev.map((item) =>
        item.status === "uploading" || item.status === "running" || item.status === "resuming"
          ? { ...item, status: "idle", progress: 0, runId: null, checkpoint: null }
          : item
      )
    );
  };

  // Export and download actions
  const handleDownload = (runId: string, format: "csv" | "xlsx" | "parquet") => {
    window.location.href = pipelineApi.getDownloadUrl(runId, format);
  };

  // Aggregate executive metrics for the finished jobs
  const executiveStats = useMemo(() => {
    const finished = queue.filter((item) => item.status === "completed" && item.report);
    const failed = queue.filter((item) => item.status === "failed");
    
    let totalRows = 0;
    let totalTokens = 0;
    let sumF1 = 0;
    let countF1 = 0;

    finished.forEach((item) => {
      const rep = item.report;
      totalRows += rep.summary?.input_rows || 0;
      totalTokens += rep.summary?.total_tokens_used || 0;
      
      const f1Val = rep.validation?.metrics?.["F1-Score Evaluation"]?.f1_score;
      if (typeof f1Val === "number") {
        sumF1 += f1Val;
        countF1 += 1;
      }
    });

    return {
      completedCount: finished.length,
      failedCount: failed.length,
      totalCount: queue.length,
      totalRows,
      totalTokens,
      avgF1: countF1 > 0 ? (sumF1 / countF1) * 100 : null,
    };
  }, [queue]);

  const activeItem = useMemo(() => {
    if (selectedInspectId) {
      return queue.find((item) => item.id === selectedInspectId) || null;
    }
    // Fallback to first running/needs_clarification item if nothing selected
    const priorityItem = queue.find((item) => 
      item.status === "needs_clarification" || 
      item.status === "running" || 
      item.status === "uploading"
    );
    return priorityItem || queue[0] || null;
  }, [queue, selectedInspectId]);

  const isAwaitingHitl = activeItem && activeItem.status === "needs_clarification" && activeItem.checkpoint;

  return (
    <div className="flex-1 w-full flex flex-col min-h-0 text-left">
      {/* Top Banner Dashboard summary */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
        <div className="rounded-xl border bg-card p-4 shadow-sm relative overflow-hidden">
          <div className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Queue Progress</div>
          <div className="text-2xl font-bold mt-2 text-foreground">
            {executiveStats.completedCount} / {executiveStats.totalCount} Done
          </div>
          {executiveStats.failedCount > 0 && (
            <span className="absolute top-4 right-4 bg-red-100 text-red-700 text-[10px] font-bold px-2 py-0.5 rounded-full">
              {executiveStats.failedCount} Failed
            </span>
          )}
        </div>
        <div className="rounded-xl border bg-card p-4 shadow-sm">
          <div className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Total Rows Cleaned</div>
          <div className="text-2xl font-bold mt-2 text-foreground">
            {executiveStats.totalRows.toLocaleString()}
          </div>
        </div>
        <div className="rounded-xl border bg-card p-4 shadow-sm">
          <div className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Total Tokens Used</div>
          <div className="text-2xl font-bold mt-2 text-foreground">
            {executiveStats.totalTokens.toLocaleString()}
          </div>
        </div>
        <div className="rounded-xl border bg-card p-4 shadow-sm">
          <div className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Average F1 Accuracy</div>
          <div className="text-2xl font-bold mt-2 text-primary">
            {executiveStats.avgF1 !== null ? (executiveStats.avgF1 / 100).toFixed(2) : "N/A"}
          </div>
        </div>
      </div>

      {/* Main Console Layout */}
      <div className="flex-1 grid grid-cols-1 lg:grid-cols-3 gap-6 min-h-0 overflow-y-auto lg:overflow-hidden pr-1 pb-4">
        {/* Left 2 Columns: Ingestion Queue list */}
        <div className="lg:col-span-2 flex flex-col min-h-0 bg-card border rounded-xl shadow-sm overflow-hidden">
          {/* Action and Control Bar */}
          <div className="flex flex-wrap items-center justify-between gap-4 p-4 border-b bg-muted/10">
            <div className="flex items-center gap-3">
              <h3 className="font-bold text-foreground flex items-center gap-2">
                <Layers className="w-5 h-5 text-violet-500" />
                Mass Ingestion Queue
              </h3>
              <div className="h-4 w-px bg-border"></div>
              <label className="flex items-center gap-2 text-xs font-medium cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={autoApprove}
                  onChange={(e) => setAutoApprove(e.target.checked)}
                  disabled={isProcessing}
                  className="rounded text-primary focus:ring-primary h-4 w-4"
                />
                Auto-Approve Plans & Reviews
              </label>
              <div className="h-4 w-px bg-border"></div>
              <label className="flex items-center gap-1.5 text-xs font-medium cursor-pointer select-none">
                <span>Concurrency:</span>
                <select
                  value={maxConcurrency}
                  onChange={(e) => setMaxConcurrency(Number(e.target.value))}
                  disabled={isProcessing}
                  className="rounded border border-input bg-background px-1.5 py-0.5 text-xs focus:ring-1 focus:ring-primary focus:outline-none"
                >
                  <option value={1}>1 (Sequential)</option>
                  <option value={2}>2 (Standard)</option>
                  <option value={3}>3 (Fast)</option>
                  <option value={4}>4 (Max)</option>
                </select>
              </label>
            </div>
            
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={addRow}
                disabled={isProcessing}
                className="inline-flex items-center justify-center rounded-lg border bg-background px-3 py-1.5 text-xs font-semibold text-foreground hover:bg-muted transition-colors disabled:opacity-50"
              >
                <Plus className="w-3.5 h-3.5 mr-1" /> Add File Row
              </button>
              <button
                type="button"
                onClick={clearQueue}
                disabled={isProcessing || queue.length === 0}
                className="inline-flex items-center justify-center rounded-lg border border-destructive/20 bg-background text-destructive hover:bg-destructive/5 px-3 py-1.5 text-xs font-semibold transition-colors disabled:opacity-50"
              >
                <Trash2 className="w-3.5 h-3.5 mr-1" /> Clear Queue
              </button>
              <div className="h-6 w-px bg-border mx-1"></div>
              {!isProcessing ? (
                <button
                  type="button"
                  onClick={startProcessing}
                  disabled={queue.length === 0}
                  className="inline-flex items-center justify-center rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white px-4 py-1.5 text-xs font-semibold shadow-sm hover:shadow transition-colors disabled:opacity-50"
                >
                  <Play className="w-3.5 h-3.5 mr-1 fill-current" /> Start Queue
                </button>
              ) : (
                <button
                  type="button"
                  onClick={stopProcessing}
                  className="inline-flex items-center justify-center rounded-lg bg-red-600 hover:bg-red-700 text-white px-4 py-1.5 text-xs font-semibold shadow-sm hover:shadow transition-colors"
                >
                  <Square className="w-3.5 h-3.5 mr-1 fill-current" /> Stop Ingestion
                </button>
              )}
            </div>
          </div>

          {/* Queue Rows Table */}
          <div className="flex-1 overflow-auto custom-scrollbar">
            {queue.length === 0 ? (
              <div className="h-64 flex flex-col items-center justify-center text-muted-foreground">
                <Upload className="w-10 h-10 mb-3 text-muted-foreground/40 stroke-[1.5]" />
                <p className="text-sm font-medium">Ingestion queue is empty.</p>
                <p className="text-xs text-muted-foreground mt-1">Click "Add File Row" to upload datasets.</p>
              </div>
            ) : (
              <div className="min-w-[650px]">
                <table className="w-full border-separate border-spacing-0 text-left text-xs">
                  <thead>
                    <tr className="bg-muted/30 border-b">
                      <th className="py-3 px-4 font-semibold text-muted-foreground border-b w-12 text-center">No.</th>
                      <th className="py-3 px-4 font-semibold text-muted-foreground border-b w-[220px]">Data File</th>
                      <th className="py-3 px-4 font-semibold text-muted-foreground border-b w-[200px]">Clean File (Optional)</th>
                      <th className="py-3 px-4 font-semibold text-muted-foreground border-b">User Prompt</th>
                      <th className="py-3 px-4 font-semibold text-muted-foreground border-b w-[110px]">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {queue.map((item, idx) => {
                      let statusBadge = (
                        <span className="inline-flex items-center rounded-full bg-slate-50 border border-slate-200 text-slate-600 px-2 py-0.5 font-medium font-sans">
                          Draft
                        </span>
                      );
                      if (item.status === "uploading") {
                        statusBadge = (
                          <span className="inline-flex items-center gap-1 rounded-full bg-blue-50 border border-blue-200 text-blue-700 px-2 py-0.5 font-medium animate-pulse font-sans">
                            <span className="w-1.5 h-1.5 rounded-full bg-blue-500 animate-ping" />
                            Uploading
                          </span>
                        );
                      } else if (item.status === "running") {
                        statusBadge = (
                          <span className="inline-flex items-center gap-1 rounded-full bg-indigo-50 border border-indigo-200 text-indigo-700 px-2 py-0.5 font-medium animate-pulse font-sans">
                            <span className="w-1.5 h-1.5 rounded-full bg-indigo-500 animate-ping" />
                            Running
                          </span>
                        );
                      } else if (item.status === "needs_clarification") {
                        statusBadge = (
                          <span className="inline-flex items-center gap-1 rounded-full bg-amber-50 border border-amber-300 text-amber-800 px-2 py-0.5 font-bold animate-pulse font-sans">
                            Action Required
                          </span>
                        );
                      } else if (item.status === "resuming") {
                        statusBadge = (
                          <span className="inline-flex items-center gap-1 rounded-full bg-purple-50 border border-purple-200 text-purple-700 px-2 py-0.5 font-medium animate-pulse font-sans">
                            Resuming
                          </span>
                        );
                      } else if (item.status === "completed") {
                        statusBadge = (
                          <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 border border-emerald-200 text-emerald-700 px-2 py-0.5 font-medium font-sans">
                            <Check className="w-3.5 h-3.5 text-emerald-600" />
                            Done
                          </span>
                        );
                      } else if (item.status === "failed") {
                        statusBadge = (
                          <span className="inline-flex items-center gap-1 rounded-full bg-rose-50 border border-rose-200 text-rose-700 px-2 py-0.5 font-medium font-sans" title={item.error || ""}>
                            Failed
                          </span>
                        );
                      }

                      const isCurrentlyActive = item.status === "uploading" || item.status === "running" || item.status === "resuming";
                      const isSelected = selectedInspectId === item.id || (selectedInspectId === null && activeItem?.id === item.id);

                      return (
                        <tr
                          key={item.id}
                          onClick={() => setSelectedInspectId(item.id)}
                          className={`group hover:bg-muted/10 transition-colors cursor-pointer ${
                            isSelected 
                              ? "bg-indigo-50/40 border-l-2 border-l-primary" 
                              : item.status === "needs_clarification"
                              ? "bg-amber-50/50 border-l-2 border-l-amber-500"
                              : isCurrentlyActive ? "bg-indigo-50/10 border-l-2 border-l-primary/40" : ""
                          }`}
                        >
                          {/* Row Index */}
                          <td className="py-3 px-4 border-b font-medium text-center border-r border-r-border/30">
                            #{idx + 1}
                          </td>
                          
                          {/* Data File Selection */}
                          <td className="py-3 px-4 border-b border-r border-r-border/30 max-w-[220px]">
                            {item.file ? (
                              <div className="flex items-center justify-between bg-muted/30 border rounded px-2 py-1 text-foreground font-medium truncate">
                                <span className="truncate" title={item.file.name}>{item.file.name}</span>
                                {!isProcessing && (
                                  <button
                                    onClick={() => updateItem(item.id, { file: null, progress: 0 })}
                                    className="text-muted-foreground hover:text-destructive shrink-0 ml-1.5"
                                  >
                                    ✕
                                  </button>
                                )}
                              </div>
                            ) : (
                              <label className="flex items-center justify-center border-dashed border-2 hover:border-primary border-border/80 rounded-lg py-2.5 px-3 bg-card hover:bg-muted/10 cursor-pointer transition-all">
                                <Upload className="w-3.5 h-3.5 text-muted-foreground mr-1.5" />
                                <span className="text-[10px] text-muted-foreground font-semibold">Select Dataset</span>
                                <input
                                  type="file"
                                  accept=".csv,.tsv,.xlsx,.json,.jsonl"
                                  onChange={(e) => {
                                    const files = e.target.files;
                                    if (files && files[0]) {
                                      updateItem(item.id, { file: files[0] });
                                    }
                                  }}
                                  className="hidden"
                                />
                              </label>
                            )}
                          </td>

                          {/* Clean File Selection */}
                          <td className="py-3 px-4 border-b border-r border-r-border/30 max-w-[200px]">
                            {item.cleanFile ? (
                              <div className="flex items-center justify-between bg-muted/30 border rounded px-2 py-1 text-foreground font-medium truncate">
                                <span className="truncate" title={item.cleanFile.name}>{item.cleanFile.name}</span>
                                {!isProcessing && (
                                  <button
                                    onClick={() => updateItem(item.id, { cleanFile: null })}
                                    className="text-muted-foreground hover:text-destructive shrink-0 ml-1.5"
                                  >
                                    ✕
                                  </button>
                                )}
                              </div>
                            ) : (
                              <label className="flex items-center justify-center border-dashed border-2 border-border/80 hover:border-indigo-500 rounded-lg py-2.5 px-3 bg-card hover:bg-muted/10 cursor-pointer transition-all">
                                <Plus className="w-3.5 h-3.5 text-muted-foreground mr-1.5" />
                                <span className="text-[10px] text-muted-foreground font-semibold">Ground Truth (opt)</span>
                                <input
                                  type="file"
                                  accept=".csv,.tsv,.xlsx,.json,.jsonl"
                                  onChange={(e) => {
                                    const files = e.target.files;
                                    if (files && files[0]) {
                                      updateItem(item.id, { cleanFile: files[0] });
                                    }
                                  }}
                                  className="hidden"
                                />
                              </label>
                            )}
                          </td>

                          {/* Ingestion Instructions */}
                          <td className="py-3 px-4 border-b border-r border-r-border/30">
                            <input
                              type="text"
                              value={item.requirements}
                              onChange={(e) => updateItem(item.id, { requirements: e.target.value })}
                              placeholder="E.g. drop duplicate rows, cast age to int..."
                              disabled={isProcessing}
                              className="w-full bg-transparent border-0 hover:bg-muted/20 focus:bg-background focus:ring-1 focus:ring-primary rounded px-2 py-1 text-xs"
                            />
                          </td>

                          {/* Status Badge & Progress */}
                          <td className="py-3 px-4 border-b border-r border-r-border/30">
                            <div className="flex items-center justify-between gap-2">
                              <div className="flex flex-col gap-1 flex-1 min-w-0">
                                {statusBadge}
                                {item.progress > 0 && item.status !== "completed" && item.status !== "failed" && (
                                  <div className="w-full bg-slate-100 rounded-full h-1">
                                    <div
                                      className="bg-primary h-1 rounded-full transition-all duration-500"
                                      style={{ width: `${item.progress}%` }}
                                    />
                                  </div>
                                )}
                              </div>
                              
                              {/* Row Trash Deletion Button */}
                              {item.status !== "uploading" && item.status !== "running" && item.status !== "resuming" && (
                                <button
                                  type="button"
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    removeRow(item.id);
                                  }}
                                  className="p-1 text-muted-foreground hover:text-destructive rounded hover:bg-destructive/5 transition-colors shrink-0"
                                  title="Remove File Row"
                                >
                                  <Trash2 className="w-3.5 h-3.5" />
                                </button>
                              )}
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>

        {/* Right 1 Column: Active Item Inspector & HITL Panel */}
        <div className="flex flex-col min-h-0 bg-card border rounded-xl shadow-sm overflow-hidden">
          <div className="px-4 py-3 border-b bg-muted/10 flex items-center justify-between">
            <h3 className="font-bold text-foreground flex items-center gap-1.5">
              <Settings2 className="w-4.5 h-4.5 text-indigo-500" />
              Active Job Inspector
            </h3>
            {isProcessing && (
              <span className="flex items-center gap-1.5 text-xs text-indigo-600 font-semibold font-sans">
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
                Processing...
              </span>
            )}
          </div>

          <div className="flex-1 overflow-y-auto p-4 custom-scrollbar space-y-6">
            {!activeItem ? (
              <div className="h-full flex flex-col items-center justify-center text-center text-muted-foreground px-4">
                <Database className="w-12 h-12 mb-3 text-muted-foreground/30 stroke-[1.5]" />
                <p className="text-sm font-semibold">No active job.</p>
                <p className="text-xs text-muted-foreground mt-1 max-w-[200px]">
                  Fill details and click "Start Queue" to monitor execution here.
                </p>
              </div>
            ) : (
              <div className="space-y-6">
                {/* Active file summary card */}
                <div className="p-3 bg-muted/20 border rounded-lg">
                  <div className="text-[10px] text-muted-foreground uppercase font-bold tracking-wider">Active Ingestion Job</div>
                  <div className="font-bold text-foreground mt-1.5 truncate" title={activeItem.file?.name || ""}>
                    {activeItem.file?.name}
                  </div>
                  <div className="flex items-center gap-2 mt-2 font-mono text-[10px] text-muted-foreground">
                    <span>Run ID:</span>
                    <span className="bg-muted px-1 py-0.5 rounded text-foreground truncate max-w-[120px]">{activeItem.runId || "Pending Ingestion"}</span>
                  </div>
                </div>

                {/* HITL clarification form */}
                {isAwaitingHitl ? (
                  <div className="border border-amber-300 bg-amber-50/30 rounded-xl p-4 space-y-5 text-left animate-fadeIn">
                    <div className="flex items-start gap-2 border-b border-amber-200/80 pb-3">
                      <AlertCircle className="w-5 h-5 text-amber-600 shrink-0 mt-0.5" />
                      <div>
                        <h4 className="text-sm font-bold text-amber-900">
                          {activeItem.checkpoint.checkpoint_type === "input_validation_clarification"
                            ? "Clarification Request"
                            : activeItem.checkpoint.checkpoint_type === "plan_approval"
                            ? "Execution Plan Approval"
                            : "Validation Review"}
                        </h4>
                        <p className="text-xs text-amber-800/80 mt-0.5">
                          {activeItem.checkpoint.checkpoint_type === "input_validation_clarification"
                            ? "The pipeline requires clarification on data issues. Please answer the questions below to resume."
                            : activeItem.checkpoint.checkpoint_type === "plan_approval"
                            ? "The pipeline has generated a data cleaning plan. Please review and approve it to proceed."
                            : "The pipeline has completed cleaning. Please review the validation results to finalize."}
                        </p>
                      </div>
                    </div>

                    {/* Question body */}
                    <div className="space-y-4 max-h-[35vh] overflow-y-auto custom-scrollbar pr-1">
                      {activeItem.checkpoint.checkpoint_type === "input_validation_clarification" ? (
                        (() => {
                          const payload = activeItem.checkpoint.payload || {};
                          const clarifications = payload.clarifications || {};
                          const categories = ["typecast", "null", "duplicate"] as const;

                          return (
                            <div className="space-y-5">
                              {payload.reasoning && (
                                <div className="text-xs bg-muted/60 p-2.5 rounded border leading-relaxed text-muted-foreground">
                                  <strong>Validator Rationale:</strong> {formatDisplayValue(payload.reasoning)}
                                </div>
                              )}

                              {categories.map((cat) => {
                                const catData = clarifications[cat];
                                if (!catData || Object.keys(catData).length === 0) return null;

                                return (
                                  <div key={cat} className="space-y-4 border rounded-lg bg-card p-3 shadow-xs">
                                    <div className="flex items-center gap-1.5 border-b pb-2">
                                      <span className="px-1.5 py-0.5 rounded text-[9px] font-bold border uppercase bg-indigo-50 border-indigo-200 text-indigo-700">
                                        {cat}
                                      </span>
                                      <span className="text-xs font-bold text-foreground">Questions</span>
                                    </div>
                                    <div className="space-y-5">
                                      {Object.keys(catData).sort().map((qKey, qi) => {
                                        const q = catData[qKey];
                                        if (!q) return null;
                                        const key = `${cat}.${qKey}`;
                                        const selectedVal = mcqAnswers[key] || "";
                                        const isStrategy = q && typeof q === "object" && "options" in q;
                                        let optionsToRender = q.options || [];

                                        if (cat === "null" && qKey.startsWith("Q2_strategy_column_")) {
                                          const colName = qKey.substring("Q2_strategy_column_".length);
                                          
                                          // 1. Filter out keep_null if allow_missing is answered "No"
                                          const q1Key = `null.Q1_allow_missing_column_${colName}`;
                                          const q1Answer = mcqAnswers[q1Key];
                                          if (q1Answer === "No") {
                                            optionsToRender = optionsToRender.filter((opt: any) => opt !== "keep_null");
                                          }

                                          // 2. Filter or add options based on Type Cast decision
                                          const castKey = `typecast.Q1_cast_column_${colName}`;
                                          const castAnswer = mcqAnswers[castKey];
                                          
                                          const typecastData = clarifications.typecast || {};
                                          const hasCastQuestion = `Q1_cast_column_${colName}` in typecastData;
                                          
                                          if (hasCastQuestion) {
                                            let expectedType = "str";
                                            const semProfile = payload.semantic_profile || {};
                                            const colDetail = semProfile.columns?.[colName];
                                            if (colDetail) {
                                              expectedType = colDetail.expected_type || "str";
                                            }

                                            if (castAnswer === "Yes") {
                                              if (expectedType === "int" || expectedType === "float") {
                                                if (!optionsToRender.includes("fill_mean")) optionsToRender.unshift("fill_mean");
                                                if (!optionsToRender.includes("fill_median")) optionsToRender.unshift("fill_median");
                                              } else if (expectedType === "datetime" || expectedType === "date") {
                                                if (!optionsToRender.includes("fill_median")) optionsToRender.unshift("fill_median");
                                              }
                                            } else {
                                              optionsToRender = optionsToRender.filter((opt: any) => opt !== "fill_mean" && opt !== "fill_median");
                                            }
                                          }
                                        }

                                        return (
                                          <div key={qKey} className="space-y-2 text-left">
                                            <p className="text-xs font-semibold text-foreground leading-snug">
                                              {qi + 1}. {formatDisplayValue(q.question)}
                                            </p>
                                            {isStrategy ? (
                                              <div className="space-y-2 pl-1.5">
                                                {optionsToRender.map((opt: any) => {
                                                  const optionLabel = formatDisplayValue(opt);
                                                  const isSelected = selectedVal === optionLabel;
                                                  const optConsequence = getOptionConsequence(q.consequences, optionLabel);

                                                  return (
                                                    <div key={optionLabel} className="space-y-1.5">
                                                      <label className={`flex items-start gap-2 text-xs cursor-pointer rounded px-2.5 py-1.5 border transition-all ${
                                                        isSelected ? "bg-primary/5 border-primary/40 shadow-xs" : "bg-transparent border-border hover:bg-muted/40"
                                                      }`}>
                                                        <input
                                                          type="radio"
                                                          name={key}
                                                          value={optionLabel}
                                                          checked={isSelected}
                                                          onChange={() => setMcqAnswers((prev) => ({ ...prev, [key]: optionLabel }))}
                                                          className="text-primary mt-0.5 shrink-0"
                                                        />
                                                        <span className="leading-snug">{optionLabel}</span>
                                                      </label>
                                                      {isSelected && optConsequence && (
                                                        <div className="ml-5 p-2 bg-indigo-50/50 border border-indigo-100/50 rounded text-[11px] leading-snug text-indigo-950 flex flex-col gap-1.5">
                                                          <div>
                                                            <span className="font-bold">Consequence: </span>
                                                            {formatDisplayValue(optConsequence)}
                                                          </div>
                                                          {optionLabel.includes("Custom strategy") && (
                                                            <input
                                                              type="text"
                                                              value={customInputs[key] || ""}
                                                              onChange={(e) => setCustomInputs((prev) => ({ ...prev, [key]: e.target.value }))}
                                                              onBlur={(e) => {
                                                                const expectedType = getColumnExpectedTypeFromPayload(payload, qKey, mcqAnswers);
                                                                const formatted = tryFormatToISO(e.target.value, expectedType);
                                                                if (formatted !== e.target.value) {
                                                                  setCustomInputs((prev) => ({ ...prev, [key]: formatted }));
                                                                }
                                                              }}
                                                              placeholder="Describe custom behavior..."
                                                              className="w-full text-xs rounded border border-indigo-200 px-2 py-1 bg-white text-foreground focus:outline-none focus:ring-1 focus:ring-indigo-500"
                                                            />
                                                          )}
                                                        </div>
                                                      )}
                                                    </div>
                                                  );
                                                })}
                                              </div>
                                            ) : (
                                              <div className="flex gap-3 pl-1.5">
                                                {["Yes", "No"].map((opt) => (
                                                  <label key={opt} className={`flex items-center gap-1.5 text-xs cursor-pointer rounded px-3 py-1 border transition-all ${
                                                    selectedVal === opt ? "bg-primary/5 border-primary/40" : "bg-transparent border-border"
                                                  }`}>
                                                    <input
                                                      type="radio"
                                                      name={key}
                                                      value={opt}
                                                      checked={selectedVal === opt}
                                                      onChange={() => setMcqAnswers((prev) => ({ ...prev, [key]: opt }))}
                                                      className="text-primary"
                                                    />
                                                    {opt}
                                                  </label>
                                                ))}
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
                          );
                        })()
                      ) : activeItem.checkpoint.checkpoint_type === "plan_approval" ? (
                        <div className="space-y-4">
                          <div className="text-xs font-semibold text-muted-foreground uppercase">Execution Plan summary</div>
                          <div className="p-3 bg-muted/30 border rounded-lg text-xs leading-relaxed text-slate-700">
                            {formatDisplayValue(
                              activeItem.checkpoint.payload?.execution_plan?.plan_summary || 
                              activeItem.checkpoint.message_to_user
                            )}
                          </div>
                          
                          {/* Task list details */}
                          {activeItem.checkpoint.payload?.execution_plan?.task_list && (
                            <div className="space-y-3">
                              <div className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider">
                                Cleaning Task Breakdown
                              </div>
                              <div className="space-y-2.5 max-h-[30vh] overflow-y-auto pr-1 custom-scrollbar">
                                {activeItem.checkpoint.payload.execution_plan.task_list.map((wrapper: any, tIdx: number) => {
                                  const task = wrapper.work_order || wrapper;
                                  if (!task) return null;

                                  const isSkipped = task.skip;
                                  const taskName = task.task_id
                                    ? task.task_id.replace(/_/g, " ").replace(/\b\w/g, (c: string) => c.toUpperCase())
                                    : "Cleaning Step";

                                  return (
                                    <div
                                      key={task.task_id || tIdx}
                                      className={`p-3 rounded-lg border text-xs leading-relaxed transition-all shadow-xs ${
                                        isSkipped
                                          ? "bg-slate-50/50 border-slate-200 text-slate-500"
                                          : "bg-card border-emerald-100 hover:border-emerald-200"
                                      }`}
                                    >
                                      <div className="flex items-center justify-between gap-2 border-b pb-1.5 mb-1.5 border-dashed border-border">
                                        <div className="flex items-center gap-1.5 font-bold">
                                          <span
                                            className={`w-2 h-2 rounded-full ${
                                              isSkipped ? "bg-slate-300" : "bg-emerald-500 animate-pulse"
                                            }`}
                                          />
                                          <span className={isSkipped ? "text-slate-500 line-through" : "text-foreground"}>
                                            {taskName}
                                          </span>
                                        </div>
                                        
                                        <span
                                          className={`px-1.5 py-0.5 rounded text-[9px] font-bold border uppercase tracking-wider ${
                                            isSkipped
                                              ? "bg-slate-100 border-slate-200 text-slate-500"
                                              : "bg-emerald-50 border-emerald-200 text-emerald-700"
                                          }`}
                                        >
                                          {isSkipped ? "Skipped" : "Active"}
                                        </span>
                                      </div>

                                      {task.columns && task.columns.length > 0 && (
                                        <div className="flex flex-wrap gap-1 mb-1.5">
                                          <span className="text-[10px] font-semibold text-muted-foreground mr-1">Columns:</span>
                                          {task.columns.map((col: string) => (
                                            <span
                                              key={col}
                                              className={`px-1 py-0.2 rounded font-mono text-[9px] border ${
                                                isSkipped
                                                  ? "bg-slate-50 border-slate-100 text-slate-400"
                                                  : "bg-slate-100 border-slate-200 text-foreground"
                                              }`}
                                            >
                                              {col}
                                            </span>
                                          ))}
                                        </div>
                                      )}

                                      <p className="text-[11px] text-muted-foreground leading-normal">
                                        {isSkipped
                                          ? `Reason: ${task.skip_reason || "Not required for this dataset."}`
                                          : task.rationale || "Running standard cleanup routine."}
                                      </p>
                                    </div>
                                  );
                                })}
                              </div>
                            </div>
                          )}

                          <div className="text-[11px] text-slate-500 italic">
                            Tip: To automatically process execution plans, toggle "Auto-Approve Plans" at the top of the queue.
                          </div>
                        </div>
                      ) : (
                        <div className="space-y-3">
                          <div className="text-xs font-semibold text-muted-foreground uppercase">Validation Review issues</div>
                          <div className="p-3 bg-card border rounded text-xs leading-relaxed text-foreground whitespace-pre-wrap font-sans">
                            {formatDisplayValue(activeItem.checkpoint.message_to_user)}
                          </div>
                        </div>
                      )}
                    </div>

                    {/* Submit Actions */}
                    <button
                      type="button"
                      onClick={handleResolveClarification}
                      disabled={submittingAnswers}
                      className="w-full inline-flex items-center justify-center gap-1.5 bg-emerald-600 hover:bg-emerald-700 text-white font-bold py-2.5 px-4 rounded-lg text-xs transition-colors shadow-sm disabled:opacity-50"
                    >
                      {submittingAnswers ? (
                        <>
                          <Loader2 className="w-3.5 h-3.5 animate-spin" />
                          Submitting...
                        </>
                      ) : (
                        <>
                          <Check className="w-4 h-4" />
                          {activeItem.checkpoint.checkpoint_type === "input_validation_clarification"
                            ? "Submit Decisions & Resume"
                            : activeItem.checkpoint.checkpoint_type === "plan_approval"
                            ? "Approve Plan & Start Cleaning"
                            : "Accept Results & Finalize"}
                        </>
                      )}
                    </button>
                  </div>
                ) : (
                  <div className="h-40 flex flex-col items-center justify-center text-center text-muted-foreground bg-muted/10 border rounded-lg border-dashed">
                    <CheckCircle2 className="w-8 h-8 mb-2 text-emerald-500" />
                    <p className="text-xs font-semibold">Running automatically...</p>
                    <p className="text-[10px] text-muted-foreground mt-0.5 max-w-[180px]">
                      The pipeline is executing nodes in the background. No action needed.
                    </p>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Bottom Consolidated Executive Report Section */}
      {queue.some((item) => item.status === "completed" && item.report) && (
        <div className="mt-6 flex flex-col bg-card border rounded-xl shadow-sm overflow-hidden text-left">
          <div className="px-4 py-3 border-b bg-muted/10">
            <h3 className="font-bold text-foreground flex items-center gap-1.5">
              <Layers className="w-5 h-5 text-indigo-500" />
              Consolidated Output Report
            </h3>
          </div>
          <div className="p-4 overflow-auto custom-scrollbar max-h-64">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b text-muted-foreground">
                  <th className="py-2 font-semibold">Filename</th>
                  <th className="py-2 font-semibold text-center">Input Rows</th>
                  <th className="py-2 font-semibold text-center">Tracked Cols</th>
                  <th className="py-2 font-semibold text-center">F1 Score</th>
                  <th className="py-2 font-semibold text-center">Precision</th>
                  <th className="py-2 font-semibold text-center">Recall</th>
                  <th className="py-2 font-semibold text-center">Cell Accuracy</th>
                  <th className="py-2 font-semibold">Transformations</th>
                  <th className="py-2 font-semibold text-right">Download Output</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {queue
                  .filter((item) => item.status === "completed" && item.report)
                  .map((item) => {
                    const rep = item.report;
                    const f1 = rep.validation?.metrics?.["F1-Score Evaluation"] || {};
                    const rowsRemoved = rep.issues_fixed || 0;
                    
                    return (
                      <tr key={item.id} className="hover:bg-muted/10">
                        <td className="py-2.5 font-semibold text-foreground max-w-[150px] truncate" title={item.file?.name || ""}>
                          {item.file?.name}
                        </td>
                        <td className="py-2.5 text-center font-mono">
                          {(rep.summary?.input_rows || 0).toLocaleString()}
                        </td>
                        <td className="py-2.5 text-center font-mono">
                          {Object.keys(rep.validation?.column_quality_after || {}).length || "N/A"}
                        </td>
                        <td className="py-2.5 text-center font-mono font-semibold text-primary">
                          {typeof f1.f1_score === "number" ? f1.f1_score.toFixed(2) : "—"}
                        </td>
                        <td className="py-2.5 text-center font-mono">
                          {typeof f1.error_correction_precision === "number" ? f1.error_correction_precision.toFixed(2) : "—"}
                        </td>
                        <td className="py-2.5 text-center font-mono">
                          {typeof f1.error_correction_recall === "number" ? f1.error_correction_recall.toFixed(2) : "—"}
                        </td>
                        <td className="py-2.5 text-center font-mono">
                          {typeof f1.cell_accuracy === "number" ? f1.cell_accuracy.toFixed(2) : "—"}
                        </td>
                        <td className="py-2.5 text-slate-600 max-w-[200px] truncate" title={
                          rep.transformations?.join(", ") || 
                          (rowsRemoved > 0 ? `Deduplication: removed ${rowsRemoved} duplicate rows` : "Normalization applied")
                        }>
                          {rep.transformations?.join(", ") || 
                           (rowsRemoved > 0 ? `Deduplicated (${rowsRemoved} rows)` : "Ingested & structured")}
                        </td>
                        <td className="py-2.5 text-right shrink-0">
                          {item.runId && (
                            <div className="inline-flex gap-2">
                              <button
                                onClick={() => handleDownload(item.runId!, "csv")}
                                className="text-emerald-700 font-semibold hover:underline"
                              >
                                CSV
                              </button>
                              <button
                                onClick={() => handleDownload(item.runId!, "xlsx")}
                                className="text-sky-700 font-semibold hover:underline"
                              >
                                Excel
                              </button>
                              <button
                                onClick={() => handleDownload(item.runId!, "parquet")}
                                className="text-violet-700 font-semibold hover:underline"
                              >
                                Parquet
                              </button>
                            </div>
                          )}
                        </td>
                      </tr>
                    );
                  })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
};

import React from "react";
import { Shield, CheckCircle2, AlertTriangle, Database, Key, Clock, FileText } from "lucide-react";
import { SEVERITY_STYLES } from "./utils";

interface ValidationReviewPanelProps {
  checkpoint: any;
  pipelineState: any;
  validationPassed: boolean | undefined;
  issues: any[];
}

export const ValidationReviewPanel: React.FC<ValidationReviewPanelProps> = ({
  checkpoint,
  pipelineState,
  validationPassed,
  issues,
}) => {
  return (
    <div className="space-y-6">
      {/* 1. Self-Correction Validation Audit Summary */}
      <div className="rounded-xl bg-white border border-slate-200 p-5 shadow-sm">
        <div className="flex items-center justify-between border-b border-slate-100 pb-3 mb-3">
          <h4 className="text-sm font-bold text-slate-800 uppercase tracking-wide flex items-center gap-2">
            <Shield className="h-4 w-4 text-slate-500" />
            Self-Correction Audit Status
          </h4>
          {validationPassed !== undefined ? (
            <span
              className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold uppercase ${
                validationPassed 
                  ? "bg-emerald-50 text-emerald-700 border border-emerald-200" 
                  : "bg-rose-50 text-rose-700 border border-rose-200"
              }`}
            >
              {validationPassed ? (
                <>
                  <CheckCircle2 className="h-3.5 w-3.5 animate-none text-emerald-600" />
                  Passed
                </>
              ) : (
                <>
                  <AlertTriangle className="h-3.5 w-3.5 text-rose-600" />
                  Issues Pending Review
                </>
              )}
            </span>
          ) : (
            <span className="bg-slate-100 text-slate-600 border border-slate-200 px-3 py-1 rounded-full text-xs font-semibold uppercase">
              Awaiting Audit
            </span>
          )}
        </div>
        <p className="text-xs text-slate-600 leading-relaxed whitespace-pre-line text-left">
          {checkpoint.message_to_user || "Please review the execution summary and remaining quality metrics below before approving the data cleaner's results."}
        </p>
      </div>

      {/* 2. Worker Agents Execution Status */}
      <div className="space-y-3">
        <h4 className="text-xs font-bold text-slate-500 uppercase tracking-wider text-left flex items-center gap-1.5">
          <Database className="h-4 w-4" />
          Cleaning Agents Execution Overview
        </h4>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          {[
            {
              name: "Deduplication Agent",
              state: pipelineState?.worker_states?.dedup_agent || { status: "done", retries: 0 },
            },
            {
              name: "Null Imputation Agent",
              state: pipelineState?.worker_states?.null_agent || { status: "done", retries: 0 },
            },
            {
              name: "Type Casting Agent",
              state: pipelineState?.worker_states?.typecast_agent || { status: "done", retries: 0 },
            },
          ].map((w, idx) => (
            <div key={idx} className="bg-white border border-slate-200 rounded-xl p-4 text-left shadow-sm">
              <div className="text-xs font-bold text-slate-800 mb-1">{w.name}</div>
              <div className="flex items-center justify-between text-xs mt-2">
                <span className="text-slate-400">Status</span>
                <span
                  className={`font-semibold uppercase text-[10px] px-2 py-0.5 rounded border ${
                    w.state.status === "done"
                      ? "bg-emerald-50 text-emerald-700 border-emerald-200"
                      : w.state.status === "running"
                        ? "bg-blue-50 text-blue-700 border-blue-200 animate-pulse"
                        : w.state.status === "failed"
                          ? "bg-rose-50 text-rose-700 border-rose-200"
                          : "bg-slate-50 text-slate-500 border-slate-200"
                  }`}
                >
                  {w.state.status}
                </span>
              </div>
              <div className="flex items-center justify-between text-xs mt-1">
                <span className="text-slate-400">Retries Used</span>
                <span className="font-mono text-slate-600 font-semibold">{w.state.retries}</span>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* 3. Deduplication Result details */}
      {(pipelineState?.deduplication_result || pipelineState?.deduplication_result === null) && (
        <div className="space-y-3">
          <h4 className="text-xs font-bold text-slate-500 uppercase tracking-wider text-left flex items-center gap-1.5">
            <Key className="h-4 w-4" />
            Deduplication Metrics Summary
          </h4>
          <div className="bg-white border border-slate-200 rounded-xl overflow-hidden shadow-sm">
            {pipelineState?.deduplication_result ? (
              <div className="p-4 space-y-4">
                <div className="grid grid-cols-2 sm:grid-cols-3 gap-4 text-left">
                  <div>
                    <span className="text-slate-400 text-xs block">Before Row Count</span>
                    <span className="text-lg font-mono font-bold text-slate-800">
                      {pipelineState.deduplication_result.before_row_count?.toLocaleString()}
                    </span>
                  </div>
                  <div>
                    <span className="text-slate-400 text-xs block">After Row Count</span>
                    <span className="text-lg font-mono font-bold text-slate-800">
                      {pipelineState.deduplication_result.after_row_count?.toLocaleString()}
                    </span>
                  </div>
                  <div>
                    <span className="text-slate-400 text-xs block">Dropped Duplicates</span>
                    <span className="text-lg font-mono font-bold text-rose-600">
                      {pipelineState.deduplication_result.dropped_row_count?.toLocaleString()}
                    </span>
                  </div>
                  <div>
                    <span className="text-slate-400 text-xs block">Exact Full-Row Duplicates</span>
                    <span className="text-sm font-mono font-semibold text-slate-700">
                      {pipelineState.deduplication_result.full_row_duplicate_count ?? 0}
                    </span>
                  </div>
                  <div>
                    <span className="text-slate-400 text-xs block">Key-Based Duplicates</span>
                    <span className="text-sm font-mono font-semibold text-slate-700">
                      {pipelineState.deduplication_result.key_duplicate_count ?? 0}
                    </span>
                  </div>
                  <div>
                    <span className="text-slate-400 text-xs block">Kept Strategy</span>
                    <span className="text-sm font-semibold text-slate-700 uppercase">
                      {pipelineState.deduplication_result.keep_strategy || "first"}
                    </span>
                  </div>
                </div>

                {pipelineState.deduplication_result.key_columns?.length > 0 && (
                  <div className="text-left border-t border-slate-100 pt-3">
                    <span className="text-slate-400 text-xs font-semibold block mb-1">Deduplication Keys Verified:</span>
                    <div className="flex flex-wrap gap-1.5">
                      {pipelineState.deduplication_result.key_columns.map((colName: string, idx: number) => (
                        <span key={idx} className="font-mono text-[10px] bg-slate-100 text-slate-700 px-1.5 py-0.5 rounded border border-slate-200">
                          {colName}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                {pipelineState.deduplication_result.notes?.length > 0 && (
                  <div className="text-left border-t border-slate-100 pt-3">
                    <span className="text-slate-400 text-xs font-semibold block mb-1">Audit Notes:</span>
                    <ul className="list-disc pl-5 space-y-1 text-xs text-slate-600">
                      {pipelineState.deduplication_result.notes.map((note: string, idx: number) => (
                        <li key={idx}>{note}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            ) : (
              /* Skeleton / Placeholder when dedup not run or state empty */
              <div className="p-5 text-center text-xs text-slate-400 italic">
                Deduplication was skipped or no keys were defined in plan.
              </div>
            )}
          </div>
        </div>
      )}

      {/* 4. Validation Check History */}
      <div className="space-y-3">
        <h4 className="text-xs font-bold text-slate-500 uppercase tracking-wider text-left flex items-center gap-1.5">
          <Clock className="h-4 w-4" />
          Self-Correction Validation Audit Log
        </h4>
        <div className="bg-white border border-slate-200 rounded-xl overflow-hidden shadow-sm">
          {pipelineState?.validation_results && pipelineState.validation_results.length > 0 ? (
            <div className="overflow-x-auto text-left">
              <table className="w-full text-xs border-collapse">
                <thead>
                  <tr className="bg-slate-50/75 border-b border-slate-200">
                    <th className="p-3 font-semibold text-slate-500 text-left">Agent/Node</th>
                    <th className="p-3 font-semibold text-slate-500 text-center">Result</th>
                    <th className="p-3 font-semibold text-slate-500 text-left">Recommended Action</th>
                    <th className="p-3 font-semibold text-slate-500 text-left">Timestamp</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {pipelineState.validation_results.map((item: any, idx: number) => (
                    <tr key={idx} className="hover:bg-slate-50/25">
                      <td className="p-3 align-top font-semibold text-slate-700">
                        {item.agent} <span className="font-mono text-[10px] text-slate-400 font-normal">({item.task_id})</span>
                      </td>
                      <td className="p-3 align-top text-center">
                        <span
                          className={`inline-flex px-2 py-0.5 rounded text-[10px] font-bold uppercase border ${
                            item.passed
                              ? "bg-emerald-50 text-emerald-700 border-emerald-200"
                              : "bg-rose-50 text-rose-700 border-rose-200"
                          }`}
                        >
                          {item.passed ? "Passed" : "Failed"}
                        </span>
                      </td>
                      <td className="p-3 align-top text-slate-600 font-mono text-[10px]">
                        {item.recommended_next_action || "pass"}
                      </td>
                      <td className="p-3 align-top text-slate-400 text-[10px]">
                        {item.timestamp ? new Date(item.timestamp).toLocaleTimeString() : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            /* Skeleton / Placeholder */
            <div className="p-5 text-center text-xs text-slate-400 italic">
              No validation checks logged yet.
            </div>
          )}
        </div>
      </div>

      {/* 5. Diagnostic Quality Issues */}
      {issues.length > 0 && (
        <div className="space-y-3">
          <h4 className="text-xs font-bold text-slate-500 uppercase tracking-wider text-left flex items-center gap-1.5">
            <FileText className="h-4 w-4" />
            Detected Quality Issues ({issues.length})
          </h4>
          <div className="rounded-xl bg-white border border-slate-200 shadow-sm overflow-hidden text-left">
            <div className="divide-y divide-slate-100 max-h-[300px] overflow-y-auto custom-scrollbar">
              {issues.map((issue: any, i: number) => (
                <div key={i} className="px-4 py-3 flex items-start gap-3 hover:bg-slate-50/20">
                  <span
                    className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase shrink-0 ${
                      SEVERITY_STYLES[issue.severity] || SEVERITY_STYLES.info
                    }`}
                  >
                    {issue.severity}
                  </span>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <code className="text-xs font-mono bg-slate-100 text-slate-800 px-1.5 py-0.5 rounded border border-slate-200">
                        {issue.column}
                      </code>
                      <span className="text-xs text-slate-400 font-medium">
                        {issue.issue_type}
                      </span>
                    </div>
                    <p className="text-xs text-slate-600 mt-1 leading-relaxed">
                      {issue.description}
                    </p>
                    {issue.affected_rows > 0 && (
                      <span className="text-[10px] text-slate-400 font-semibold block mt-1">
                        {issue.affected_rows.toLocaleString()} rows affected
                      </span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

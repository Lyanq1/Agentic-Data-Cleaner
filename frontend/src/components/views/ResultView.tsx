import React, { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { pipelineApi } from '../../api/services';
import {
  Download,
  RotateCcw,
  CheckCircle2,
  AlertCircle,
  ChevronDown,
  ChevronUp,
  FileJson,
  Shield,
  Layers,
  Database,
} from 'lucide-react';

interface ResultViewProps {
  runId: string;
  onStartOver: () => void;
}

const SEVERITY_STYLES: Record<string, string> = {
  error: 'bg-red-100 text-red-700 border-red-200 dark:bg-red-950/40 dark:text-red-300 dark:border-red-900',
  warning: 'bg-amber-100 text-amber-800 border-amber-200 dark:bg-amber-950/40 dark:text-amber-200 dark:border-amber-900',
  info: 'bg-blue-100 text-blue-700 border-blue-200 dark:bg-blue-950/40 dark:text-blue-300 dark:border-blue-900',
};

function humanizeMetricKey(key: string): string {
  return key
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

/** Flatten nested metric values to one readable path per line (e.g. col.accuracy.passed: true). */
function flattenMetricLines(value: unknown, path = ''): string[] {
  if (value === null || value === undefined) {
    return path ? [`${path}: —`] : [];
  }
  if (typeof value === 'boolean' || typeof value === 'number') {
    return [path ? `${path}: ${value}` : String(value)];
  }
  if (typeof value === 'string') {
    const s = value.length > 280 ? `${value.slice(0, 280)}…` : value;
    return [path ? `${path}: ${s}` : s];
  }
  if (Array.isArray(value)) {
    if (value.length === 0) return [path ? `${path}: (empty)` : '(empty)'];
    return value.flatMap((item, i) => flattenMetricLines(item, path ? `${path}[${i}]` : `[${i}]`));
  }
  if (typeof value === 'object') {
    const entries = Object.entries(value as Record<string, unknown>);
    if (entries.length === 0) return [path ? `${path}: (empty)` : '(empty)'];
    return entries.flatMap(([k, v]) => {
      const next = path ? `${path}.${k}` : k;
      return flattenMetricLines(v, next);
    });
  }
  return [path ? `${path}: ${String(value)}` : String(value)];
}

function getColumnCount(report: Record<string, any> | undefined): number | 'N/A' {
  if (!report) return 'N/A';
  const after = report.validation?.column_quality_after;
  if (after && typeof after === 'object' && Object.keys(after).length > 0) {
    return Object.keys(after).length;
  }
  const wr = report.worker_results;
  if (!Array.isArray(wr) || wr.length === 0) return 'N/A';
  const names = new Set<string>();
  for (const r of wr) {
    const cols = r?.columns;
    if (Array.isArray(cols)) cols.forEach((c: string) => names.add(c));
  }
  return names.size > 0 ? names.size : 'N/A';
}

function getRowsProcessed(report: Record<string, any> | undefined): number | 'N/A' {
  if (!report) return 'N/A';
  const n = report.summary?.input_rows ?? report.profile?.row_count;
  if (typeof n === 'number' && !Number.isNaN(n)) return n;
  return 'N/A';
}

function buildTransformationLines(report: Record<string, any> | undefined): string[] {
  if (!report) return [];
  const legacy = report.transformations;
  if (Array.isArray(legacy) && legacy.length > 0) return legacy.map(String);
  const wr = report.worker_results;
  if (!Array.isArray(wr) || wr.length === 0) return [];
  const lines: string[] = [];
  for (const r of wr) {
    const id = r.task_id ?? 'task';
    if (typeof r.rows_removed === 'number' && r.rows_removed > 0) {
      lines.push(`Deduplication (${id}): removed ${r.rows_removed.toLocaleString()} duplicate rows (${r.strategy ?? 'strategy n/a'})`);
    }
    if (Array.isArray(r.columns) && r.columns.length > 0) {
      lines.push(`Null & type handling (${id}): columns ${r.columns.join(', ')}`);
    }
  }
  return lines.length > 0 ? lines : ['Worker tasks completed — see raw report for details'];
}

function formatGMT7(dateStr: string): string {
  try {
    const d = new Date(dateStr);
    if (isNaN(d.getTime())) return dateStr;
    return new Intl.DateTimeFormat('en-GB', {
      timeZone: 'Asia/Bangkok', // GMT+7
      year: 'numeric',
      month: 'short',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false
    }).format(d).replace(',', '');
  } catch {
    return dateStr;
  }
}

export const ResultView: React.FC<ResultViewProps> = ({ runId, onStartOver }) => {
  const [showRawJson, setShowRawJson] = useState(false);

  const { data: report, isLoading, error } = useQuery({
    queryKey: ['pipeline-report', runId],
    queryFn: () => pipelineApi.getReport(runId),
  });

  const rowsProcessed = useMemo(() => getRowsProcessed(report), [report]);
  const columnCount = useMemo(() => getColumnCount(report), [report]);
  const transformationLines = useMemo(() => buildTransformationLines(report), [report]);

  const validation = report?.validation as Record<string, any> | undefined;
  const hasValidation = validation && Object.keys(validation).length > 0;
  const validationPassed = hasValidation ? validation.passed === true : true;
  const validationIssues: any[] = Array.isArray(validation?.issues) ? validation.issues : [];

  const handleDownload = () => {
    window.location.href = pipelineApi.getDownloadUrl(runId);
  };

  /** Outer fills main; inner scroll region gets flex-1 min-h-0 so it scrolls under h-screen + overflow-hidden. */
  return (
    <div className="w-full max-w-4xl mx-auto flex flex-col flex-1 min-h-0 text-left self-center">
      <div className="flex-1 min-h-0 overflow-y-auto overscroll-y-contain pt-8 pb-4 custom-scrollbar">
        {isLoading ? (
          <div className="text-center py-12 text-muted-foreground">Loading report...</div>
        ) : error ? (
          <div className="text-center py-12 text-destructive border rounded-xl bg-destructive/5 px-4">
            Failed to load the final report. The pipeline may not have generated a report yet.
          </div>
        ) : (
          <>
            <div className="mb-8 text-center flex flex-col items-center">
            <div
              className={`w-16 h-16 rounded-full flex items-center justify-center mb-4 ${
                validationPassed
                  ? 'bg-green-100 dark:bg-green-900/30 text-green-600'
                  : 'bg-amber-100 dark:bg-amber-900/30 text-amber-700'
              }`}
            >
              {validationPassed ? (
                <CheckCircle2 className="w-8 h-8" />
              ) : (
                <AlertCircle className="w-8 h-8" />
              )}
            </div>
            <h1 className="text-3xl font-bold tracking-tight mb-2">
              {validationPassed ? 'Pipeline Completed' : 'Pipeline Completed — Validation Notes'}
            </h1>
            <p className="text-muted-foreground max-w-lg">
              {report?.filename ? (
                <>
                  Output for <span className="font-medium text-foreground">{report.filename}</span>
                  {report?.completed_at ? (
                    <span className="block text-sm mt-1">Completed at {formatGMT7(report.completed_at)}</span>
                  ) : null}
                </>
              ) : (
                'Your data has been processed by the agentic pipeline.'
              )}
            </p>
            {!validationPassed && (
              <p className="text-sm text-amber-700 dark:text-amber-400 mt-3 max-w-lg">
                Validation did not fully pass. Review the summary below and the issue list — you can still download the output.
              </p>
            )}
          </div>

          <div className="rounded-xl border bg-card text-card-foreground shadow mb-6 overflow-hidden">
            <div className="p-6 border-b bg-muted/20">
              <h2 className="text-xl font-semibold flex items-center gap-2">
                <Database className="w-5 h-5 text-muted-foreground" />
                Processing Summary
              </h2>
            </div>
            <div className="p-6 space-y-8">
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <div className="border rounded-lg p-4 bg-muted/20">
                  <div className="text-xs text-muted-foreground mb-1">Rows (input)</div>
                  <div className="text-2xl font-bold tabular-nums">
                    {typeof rowsProcessed === 'number' ? rowsProcessed.toLocaleString() : rowsProcessed}
                  </div>
                </div>
                <div className="border rounded-lg p-4 bg-muted/20">
                  <div className="text-xs text-muted-foreground mb-1">Columns (tracked)</div>
                  <div className="text-2xl font-bold tabular-nums">
                    {typeof columnCount === 'number' ? columnCount.toLocaleString() : columnCount}
                  </div>
                </div>
                <div className="border rounded-lg p-4 bg-muted/20">
                  <div className="text-xs text-muted-foreground mb-1">Tokens used</div>
                  <div className="text-2xl font-bold tabular-nums">
                    {(report?.summary?.total_tokens_used ?? 0).toLocaleString()}
                  </div>
                </div>
                <div className="border rounded-lg p-4 bg-muted/20">
                  <div className="text-xs text-muted-foreground mb-1">Retry cycles</div>
                  <div className="text-2xl font-bold tabular-nums">{report?.summary?.retry_cycles ?? 0}</div>
                </div>
              </div>

              {typeof report?.issues_fixed === 'number' && (
                <div className="rounded-lg border bg-muted/10 px-4 py-3 text-sm">
                  <span className="text-muted-foreground">Rows affected by deduplication (approx.): </span>
                  <span className="font-semibold">{report.issues_fixed.toLocaleString()}</span>
                </div>
              )}

              <div>
                <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide mb-3">
                  Applied transformations
                </h3>
                <ul className="list-disc pl-5 text-sm space-y-1.5 text-foreground">
                  {transformationLines.map((line, i) => (
                    <li key={i}>{line}</li>
                  ))}
                </ul>
              </div>

              {hasValidation && (
                <div
                  className={`rounded-2xl border-2 overflow-hidden ${
                    validationPassed ? 'border-emerald-200 dark:border-emerald-900' : 'border-amber-200 dark:border-amber-900'
                  }`}
                >
                  <div
                    className={`px-5 py-4 flex items-center gap-3 ${
                      validationPassed
                        ? 'bg-gradient-to-r from-emerald-500 to-teal-600'
                        : 'bg-gradient-to-r from-amber-500 to-orange-600'
                    }`}
                  >
                    <div className="w-10 h-10 rounded-full bg-white/20 flex items-center justify-center">
                      <Shield className="w-5 h-5 text-white" />
                    </div>
                    <div>
                      <h3 className="text-lg font-bold text-white">Validation</h3>
                      <p className="text-white/85 text-sm">
                        {validationPassed ? 'All checks passed.' : `${validationIssues.length} issue(s) reported.`}
                      </p>
                    </div>
                    <span className="ml-auto text-xs font-semibold uppercase tracking-wider text-white/90 bg-white/20 rounded-full px-2.5 py-1">
                      {validationPassed ? 'Passed' : 'Review'}
                    </span>
                  </div>
                  <div className="p-5 bg-card space-y-4">
                    {validation?.metrics && Object.keys(validation.metrics).length > 0 && (
                      <div className="space-y-4">
                        <h4 className="text-sm font-semibold text-muted-foreground">Validation metrics</h4>
                        {Object.entries(validation.metrics).map(([k, v]) => {
                          const lines = flattenMetricLines(v);
                          return (
                            <div key={k} className="rounded-lg border border-border bg-muted/15 overflow-hidden">
                              <div className="px-3 py-2 border-b border-border/80 bg-muted/30 text-xs font-semibold text-foreground">
                                {humanizeMetricKey(k)}
                              </div>
                              <div className="px-3 py-2 font-mono text-[11px] leading-relaxed text-foreground max-h-[320px] overflow-y-auto">
                                {lines.map((line, i) => (
                                  <div key={i} className="break-words whitespace-pre-wrap py-0.5">
                                    {line}
                                  </div>
                                ))}
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    )}
                    {validationIssues.length > 0 && (
                      <div className="rounded-xl border shadow-sm overflow-hidden">
                        <div className="px-4 py-3 border-b bg-muted/30 flex items-center gap-2">
                          <Layers className="w-4 h-4 text-muted-foreground" />
                          <span className="text-sm font-semibold">Issues ({validationIssues.length})</span>
                        </div>
                        <div className="divide-y max-h-[280px] overflow-auto">
                          {validationIssues.map((issue: any, i: number) => (
                            <div key={i} className="px-4 py-3 flex items-start gap-3">
                              <span
                                className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase shrink-0 ${
                                  SEVERITY_STYLES[issue.severity] || SEVERITY_STYLES.info
                                }`}
                              >
                                {issue.severity ?? 'info'}
                              </span>
                              <div className="flex-1 min-w-0">
                                <div className="flex items-center gap-2 flex-wrap">
                                  <code className="text-xs font-mono bg-muted px-1.5 py-0.5 rounded">{issue.column}</code>
                                  <span className="text-xs text-muted-foreground">{issue.issue_type}</span>
                                </div>
                                <p className="text-sm text-foreground mt-1">{issue.description}</p>
                                {issue.affected_rows > 0 && (
                                  <span className="text-xs text-muted-foreground">
                                    {issue.affected_rows.toLocaleString()} rows affected
                                  </span>
                                )}
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              )}

              <div className="border-t pt-6">
                <button
                  type="button"
                  onClick={() => setShowRawJson(!showRawJson)}
                  className="flex items-center gap-2 text-sm font-medium text-muted-foreground hover:text-foreground transition-colors w-full sm:w-auto"
                >
                  <FileJson className="w-4 h-4 shrink-0" />
                  {showRawJson ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                  {showRawJson ? 'Hide' : 'Show'} raw report JSON
                </button>
                {showRawJson && (
                  <div className="mt-3 bg-slate-950 text-slate-300 rounded-lg p-4 font-mono text-[11px] leading-relaxed overflow-auto max-h-[min(420px,50vh)] border border-slate-800">
                    <pre className="whitespace-pre-wrap break-words">{JSON.stringify(report, null, 2)}</pre>
                  </div>
                )}
              </div>
            </div>
          </div>
          </>
        )}
      </div>

      <div className="flex-shrink-0 flex flex-col sm:flex-row justify-center gap-3 sm:gap-4 pt-4 pb-2 border-t border-border/60 bg-background">
        <button
          onClick={handleDownload}
          className="inline-flex items-center justify-center whitespace-nowrap rounded-md text-sm font-medium transition-colors bg-primary text-primary-foreground hover:bg-primary/90 h-11 px-8"
        >
          <Download className="mr-2 h-4 w-4" />
          Download Data
        </button>
        <button
          onClick={onStartOver}
          className="inline-flex items-center justify-center whitespace-nowrap rounded-md text-sm font-medium transition-colors border border-input bg-background hover:bg-accent hover:text-accent-foreground h-11 px-8"
        >
          <RotateCcw className="mr-2 h-4 w-4" />
          Process Another File
        </button>
      </div>
    </div>
  );
};

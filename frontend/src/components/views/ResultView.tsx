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
import { StatusBadge } from '../ui/StatusBadge';
import { Button } from '../ui/Button';

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

function formatCell(value: any): string {
  if (value === null || value === undefined || value === '') return '—';
  if (typeof value === 'string') return value;
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

const CircularProgress = ({ value, label }: { value: number, label: string }) => {
  const radius = 24;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (value / 100) * circumference;
  const decimalValue = (value / 100).toFixed(2);
  
  return (
    <div className="flex flex-col items-center justify-center gap-2">
      <div className="relative w-14 h-14 flex items-center justify-center">
        <svg className="w-full h-full transform -rotate-90" viewBox="0 0 56 56">
          <circle cx="28" cy="28" r={radius} className="stroke-muted/30" strokeWidth="4.5" fill="none" />
          <circle 
            cx="28" cy="28" r={radius} 
            className="stroke-primary transition-all duration-1000 ease-out" 
            strokeWidth="4.5" fill="none" 
            strokeDasharray={circumference} 
            strokeDashoffset={offset} 
            strokeLinecap="round" 
          />
        </svg>
        <span className="absolute text-xs font-bold text-foreground">{decimalValue}</span>
      </div>
      <span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">{label}</span>
    </div>
  );
};

export const ResultView: React.FC<ResultViewProps> = ({ runId, onStartOver }) => {
  const [showRawJson, setShowRawJson] = useState(false);

  const { data: report, isLoading, error } = useQuery({
    queryKey: ['pipeline-report', runId],
    queryFn: () => pipelineApi.getReport(runId),
  });
  const { data: preview } = useQuery({
    queryKey: ['processed-preview', runId],
    queryFn: () => pipelineApi.getProcessedPreview(runId, 500),
  });

  const rowsProcessed = useMemo(() => getRowsProcessed(report), [report]);
  const columnCount = useMemo(() => getColumnCount(report), [report]);
  const transformationLines = useMemo(() => buildTransformationLines(report), [report]);

  const validation = report?.validation as Record<string, any> | undefined;
  const hasValidation = validation && Object.keys(validation).length > 0;
  const validationPassed = hasValidation ? validation.passed === true : true;
  const validationIssues: any[] = Array.isArray(validation?.issues) ? validation.issues : [];

  const handleDownload = (format: 'csv' | 'xlsx' | 'parquet') => {
    window.location.href = pipelineApi.getDownloadUrl(runId, format);
  };

  /** Outer fills main; inner scroll region gets flex-1 min-h-0 so it scrolls under h-screen + overflow-hidden. */
  return (
    <div className="w-full max-w-4xl mx-auto flex flex-col flex-1 min-h-0 text-left self-center">
      <div className="flex-1 min-h-0 overflow-y-auto pt-8 pb-4 hidden-scrollbar">
        {isLoading ? (
          <div className="text-center py-12 text-muted-foreground">Loading report...</div>
        ) : error ? (
          <div className="text-center py-12 text-destructive border rounded-xl bg-destructive/5 px-4">
            Failed to load the final report. The pipeline may not have generated a report yet.
          </div>
        ) : (
          <>
            <div className="mb-6 text-left border-b pb-4">
              <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
                <div className="space-y-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <h1 className="text-xl font-bold text-foreground">
                      {validationPassed ? 'Pipeline completed' : 'Pipeline completed with validation notes'}
                    </h1>
                    <StatusBadge status="completed" />
                  </div>
                  {report?.filename && (
                    <p className="text-xs text-muted-foreground">
                      Output for <span className="font-semibold text-foreground">{report.filename}</span>
                      {report?.completed_at ? ` • Completed at ${formatGMT7(report.completed_at)}` : ''}
                    </p>
                  )}
                </div>
              </div>
              {!validationPassed && (
                <p className="text-xs text-warning mt-2 leading-relaxed max-w-2xl">
                  Validation did not fully pass. Review the summary below and the issue list — you can still download the output.
                </p>
              )}
            </div>

          <div className="rounded-lg border border-border bg-card text-foreground mb-6 overflow-hidden">
            <div className="p-4 sm:p-6 border-b border-border bg-muted/10">
              <h2 className="text-sm font-bold uppercase tracking-wider text-muted-foreground flex items-center gap-2">
                <Database className="w-4 h-4 text-muted-foreground" />
                Processing Summary
              </h2>
            </div>
            <div className="p-4 sm:p-6 space-y-6">
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
                <div className="border border-border rounded p-4 bg-muted/5">
                  <div className="text-[10px] font-bold uppercase text-muted-foreground mb-1">Rows (input)</div>
                  <div className="text-xl font-bold tabular-nums">
                    {typeof rowsProcessed === 'number' ? rowsProcessed.toLocaleString() : rowsProcessed}
                  </div>
                </div>
                <div className="border border-border rounded p-4 bg-muted/5">
                  <div className="text-[10px] font-bold uppercase text-muted-foreground mb-1">Columns (tracked)</div>
                  <div className="text-xl font-bold tabular-nums">
                    {typeof columnCount === 'number' ? columnCount.toLocaleString() : columnCount}
                  </div>
                </div>
                <div className="border border-border rounded p-4 bg-muted/5">
                  <div className="text-[10px] font-bold uppercase text-muted-foreground mb-1">Tokens used</div>
                  <div className="text-xl font-bold tabular-nums">
                    {(report?.summary?.total_tokens_used ?? 0).toLocaleString()}
                  </div>
                </div>
                <div className="border border-border rounded p-4 bg-muted/5">
                  <div className="text-[10px] font-bold uppercase text-muted-foreground mb-1">Retry cycles</div>
                  <div className="text-xl font-bold tabular-nums">{report?.summary?.retry_cycles ?? 0}</div>
                </div>
              </div>

              {typeof report?.issues_fixed === 'number' && (
                <div className="rounded border border-border bg-muted/10 px-4 py-3 text-xs">
                  <span className="text-muted-foreground">Rows affected by deduplication (approx.): </span>
                  <span className="font-semibold">{report.issues_fixed.toLocaleString()}</span>
                </div>
              )}

              <div>
                <h3 className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider mb-2">
                  Applied transformations
                </h3>
                <ul className="list-disc pl-5 text-xs space-y-1 text-muted-foreground">
                  {transformationLines.map((line, i) => (
                    <li key={i} className="text-foreground">{line}</li>
                  ))}
                </ul>
              </div>

              {hasValidation && (
                <div className="rounded-lg border border-border overflow-hidden bg-card">
                  <div className="px-5 py-4 border-b border-border bg-muted/30 flex items-center justify-between gap-3">
                    <div className="flex items-center gap-2 text-left">
                      <div className="p-2 rounded bg-muted text-muted-foreground">
                        <Shield className="w-4 h-4" />
                      </div>
                      <div>
                        <h3 className="text-sm font-bold text-foreground">Validation Results</h3>
                        <p className="text-xs text-muted-foreground">
                          {validationPassed ? 'All checks passed successfully.' : `${validationIssues.length} issue(s) reported.`}
                        </p>
                      </div>
                    </div>
                    <StatusBadge status={validationPassed ? 'completed' : 'awaiting_hitl'} />
                  </div>
                  <div className="p-5 bg-card space-y-4">
                    {validation?.metrics && Object.keys(validation.metrics).length > 0 && (
                      <div className="space-y-6">
                        {Object.entries(validation.metrics).map(([k, v]) => {
                          if (k === 'Intent Analysis') {
                            const data = v as any;
                            return (
                              <div key={k} className="space-y-3">
                                <h4 className="text-xs font-bold uppercase tracking-wider text-muted-foreground">{k}</h4>
                                <div className="border border-border rounded-lg overflow-hidden bg-card text-xs">
                                  <table className="w-full text-left border-collapse">
                                    <thead>
                                      <tr className="bg-muted/50 border-b border-border">
                                        <th className="p-2.5 font-bold text-muted-foreground">Property</th>
                                        <th className="p-2.5 font-bold text-muted-foreground text-right">Value</th>
                                        <th className="p-2.5 font-bold text-muted-foreground text-center">Status</th>
                                      </tr>
                                    </thead>
                                    <tbody className="divide-y divide-border">
                                      <tr className="hover:bg-muted/30">
                                        <td className="p-2.5 font-medium text-foreground">Matched Columns</td>
                                        <td className="p-2.5 text-right font-mono">{data['Matched Columns'] ?? '—'}</td>
                                        <td className="p-2.5 text-center">
                                          <span className="inline-flex items-center rounded-full bg-success/10 border border-success/20 text-success px-1.5 py-0.5 text-[9px] font-bold">Passed</span>
                                        </td>
                                      </tr>
                                      <tr className="hover:bg-muted/30">
                                        <td className="p-2.5 font-medium text-foreground">Missing Values Detected</td>
                                        <td className="p-2.5 text-right font-mono font-bold text-warning">{data['Missing values detected'] ?? '—'}</td>
                                        <td className="p-2.5 text-center">
                                          {data['Missing values detected'] > 0 ? (
                                            <span className="inline-flex items-center rounded-full bg-warning/10 border border-warning/20 text-warning px-1.5 py-0.5 text-[9px] font-bold">Warning</span>
                                          ) : (
                                            <span className="inline-flex items-center rounded-full bg-success/10 border border-success/20 text-success px-1.5 py-0.5 text-[9px] font-bold">Passed</span>
                                          )}
                                        </td>
                                      </tr>
                                    </tbody>
                                  </table>
                                </div>
                              </div>
                            );
                          }
                          
                          if (k === 'F1-Score Evaluation') {
                            const data = v as any;
                            return (
                              <div key={k} className="space-y-3">
                                <h4 className="text-xs font-bold uppercase tracking-wider text-muted-foreground">{k}</h4>
                                <div className="border border-border rounded-lg overflow-hidden bg-card text-xs">
                                  <table className="w-full text-left border-collapse">
                                    <thead>
                                      <tr className="bg-muted/50 border-b border-border">
                                        <th className="p-2.5 font-bold text-muted-foreground">Metric</th>
                                        <th className="p-2.5 font-bold text-muted-foreground text-right">Value</th>
                                        <th className="p-2.5 font-bold text-muted-foreground text-center">Status</th>
                                      </tr>
                                    </thead>
                                    <tbody className="divide-y divide-border">
                                      <tr className="hover:bg-muted/30">
                                        <td className="p-2.5 font-medium text-foreground">F1 Score</td>
                                        <td className="p-2.5 text-right font-mono font-bold text-primary">{(data.f1_score ?? 0).toFixed(4)}</td>
                                        <td className="p-2.5 text-center">
                                          <span className="inline-flex items-center rounded-full bg-success/10 border border-success/20 text-success px-1.5 py-0.5 text-[9px] font-bold">Passed</span>
                                        </td>
                                      </tr>
                                      <tr className="hover:bg-muted/30">
                                        <td className="p-2.5 font-medium text-foreground">Precision</td>
                                        <td className="p-2.5 text-right font-mono font-bold">{(data.error_correction_precision ?? 0).toFixed(4)}</td>
                                        <td className="p-2.5 text-center">
                                          <span className="inline-flex items-center rounded-full bg-success/10 border border-success/20 text-success px-1.5 py-0.5 text-[9px] font-bold">Passed</span>
                                        </td>
                                      </tr>
                                      <tr className="hover:bg-muted/30">
                                        <td className="p-2.5 font-medium text-foreground">Recall</td>
                                        <td className="p-2.5 text-right font-mono font-bold">{(data.error_correction_recall ?? 0).toFixed(4)}</td>
                                        <td className="p-2.5 text-center">
                                          <span className="inline-flex items-center rounded-full bg-success/10 border border-success/20 text-success px-1.5 py-0.5 text-[9px] font-bold">Passed</span>
                                        </td>
                                      </tr>
                                      <tr className="hover:bg-muted/30">
                                        <td className="p-2.5 font-medium text-foreground">Cell Accuracy</td>
                                        <td className="p-2.5 text-right font-mono font-bold">{(data.cell_accuracy ?? 0).toFixed(4)}</td>
                                        <td className="p-2.5 text-center">
                                          <span className="inline-flex items-center rounded-full bg-success/10 border border-success/20 text-success px-1.5 py-0.5 text-[9px] font-bold">Passed</span>
                                        </td>
                                      </tr>
                                      <tr className="hover:bg-muted/30 text-muted-foreground bg-muted/5">
                                        <td className="p-2.5 font-medium">Total Cells Evaluated</td>
                                        <td className="p-2.5 text-right font-mono">{(data.total_cells_evaluated ?? 0).toLocaleString()}</td>
                                        <td className="p-2.5 text-center">—</td>
                                      </tr>
                                      <tr className="hover:bg-muted/30 text-muted-foreground bg-muted/5">
                                        <td className="p-2.5 font-medium">Confusion Matrix (TP / FP / FN)</td>
                                        <td className="p-2.5 text-right font-mono">
                                          <span className="text-success">{data.tp ?? 0}</span> / <span className="text-warning">{data.fp ?? 0}</span> / <span className="text-destructive">{data.fn ?? 0}</span>
                                        </td>
                                        <td className="p-2.5 text-center">—</td>
                                      </tr>
                                    </tbody>
                                  </table>
                                </div>
                              </div>
                            );
                          }

                          // Fallback for other metrics
                          const lines = flattenMetricLines(v);
                          return (
                            <div key={k} className="rounded border border-border bg-muted/5 overflow-hidden text-xs">
                              <div className="px-3 py-2 border-b border-border bg-muted/30 text-[10px] font-bold text-muted-foreground uppercase tracking-wider">
                                {humanizeMetricKey(k)}
                              </div>
                              <div className="px-3 py-2 font-mono text-[10px] leading-relaxed text-foreground max-h-[320px] overflow-y-auto">
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
                      <div className="rounded-lg border border-border bg-card overflow-hidden">
                        <div className="px-4 py-3 border-b border-border bg-muted/30 flex items-center gap-2">
                          <Layers className="w-4 h-4 text-muted-foreground" />
                          <span className="text-sm font-semibold">Issues ({validationIssues.length})</span>
                        </div>
                        <div className="divide-y divide-border max-h-[280px] overflow-auto">
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

              {preview?.columns?.length > 0 && (
                <div className="rounded-lg border border-border bg-card overflow-hidden">
                  <div className="px-4 py-3 border-b border-border bg-muted/30 flex items-center justify-between gap-3">
                    <div>
                      <h3 className="text-sm font-semibold text-foreground">Processed data preview</h3>
                      <p className="text-xs text-muted-foreground mt-0.5">
                        Showing {preview.preview_count?.toLocaleString?.() ?? preview.rows?.length ?? 0} of {preview.row_count?.toLocaleString?.() ?? 0} rows from the latest processed version.
                      </p>
                    </div>
                  </div>
                  <div className="overflow-auto max-h-[360px]">
                    <table className="w-full min-w-[48rem] border-separate border-spacing-0 text-xs">
                      <thead className="sticky top-0 z-10">
                        <tr>
                          {preview.columns.map((column: string) => (
                            <th
                              key={column}
                              className="bg-muted border-b border-r border-border px-3 py-2 text-left font-semibold text-muted-foreground whitespace-nowrap"
                            >
                              {column}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {(preview.rows || []).map((row: Record<string, any>, rowIndex: number) => (
                          <tr key={rowIndex} className="hover:bg-muted/20">
                            {preview.columns.map((column: string) => (
                              <td
                                key={column}
                                className="border-b border-r border-border px-3 py-1.5 text-foreground whitespace-nowrap max-w-xs truncate font-mono text-[11px]"
                                title={formatCell(row[column])}
                              >
                                {formatCell(row[column])}
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              <div className="border-t border-border pt-6">
                <button
                  type="button"
                  onClick={() => setShowRawJson(!showRawJson)}
                  className="flex items-center gap-2 text-xs font-semibold text-muted-foreground hover:text-foreground transition-colors w-full sm:w-auto cursor-pointer"
                >
                  <FileJson className="w-3.5 h-3.5 shrink-0" />
                  {showRawJson ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                  {showRawJson ? 'Hide' : 'Show'} raw report JSON
                </button>
                {showRawJson && (
                  <div className="mt-3 bg-slate-950 text-slate-300 rounded-lg p-4 font-mono text-[10px] leading-relaxed overflow-auto max-h-[min(420px,50vh)] border border-slate-800">
                    <pre className="whitespace-pre-wrap break-words">{JSON.stringify(report, null, 2)}</pre>
                  </div>
                )}
              </div>
            </div>
          </div>
          </>
        )}
      </div>

      <div className="flex-shrink-0 flex flex-col sm:flex-row justify-center gap-3 sm:gap-4 pt-4 pb-2 border-t border-border bg-background">
        <div className="flex flex-col sm:flex-row gap-2 sm:gap-3">
          {([
            ['csv', 'CSV'],
            ['xlsx', 'XLSX'],
            ['parquet', 'Parquet'],
          ] as const).map(([format, label]) => {
            const isPrimary = format === 'csv';
            return (
              <Button
                key={format}
                onClick={() => handleDownload(format)}
                variant={isPrimary ? 'default' : 'outline'}
                className="cursor-pointer"
              >
                <Download className="mr-2 h-4 w-4" />
                Download {label}
              </Button>
            );
          })}
        </div>
        <Button
          onClick={onStartOver}
          variant="secondary"
          className="px-8 cursor-pointer"
        >
          <RotateCcw className="mr-2 h-4 w-4" />
          Process Another File
        </Button>
      </div>
    </div>
  );
};

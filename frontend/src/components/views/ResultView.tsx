import React, { memo, useEffect, useMemo, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { pipelineApi } from '../../api/services';
import { MermaidDiagram } from '../MermaidDiagram';
import {
  Download,
  RotateCcw,
  CheckCircle2,
  AlertCircle,
  ChevronDown,
  ChevronUp,
  FileJson,
  FileText,
  GitBranch,
  MessageSquare,
  Send,
  Shield,
  Layers,
  Database,
  ArrowRightLeft,
  X,
  Sparkles,
} from 'lucide-react';

interface ResultViewProps {
  runId: string;
  onStartOver: () => void;
}

interface ComparePreview {
  available?: boolean;
  reason?: string;
  columns?: string[];
  before_rows?: Record<string, any>[];
  after_rows?: Record<string, any>[];
  before_row_count?: number;
  after_row_count?: number;
  preview_count?: number;
  changed_cells?: Array<{
    row_index: number;
    column: string;
    before: any;
    after: any;
  }>;
  changed_cell_count?: number;
  truncated?: boolean;
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
  const tracked = report.summary?.tracked_columns;
  if (typeof tracked === 'number' && !Number.isNaN(tracked)) return tracked;
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
  const n = report.summary?.output_rows ?? report.summary?.input_rows ?? report.profile?.row_count;
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

function buildEvidenceContexts(report: Record<string, any> | undefined): Array<{ id: string; label: string; available: boolean; evidence: string }> {
  const contexts = report?.answer_contexts;
  if (Array.isArray(contexts) && contexts.length > 0) {
    return contexts.map((item: any, index: number) => ({
      id: String(item.id || item.label || index),
      label: String(item.label || item.id || 'Context'),
      available: Boolean(item.available),
      evidence: String(item.evidence || ''),
    }));
  }
  return [
    { id: 'summary', label: 'Run summary', available: Boolean(report?.summary), evidence: 'Rows, columns, retries, tokens' },
    { id: 'planning', label: 'Planning decisions', available: Boolean(report?.execution_plan_summary?.tasks?.length), evidence: 'Tasks, skipped steps, rationale' },
    { id: 'workers', label: 'Worker execution', available: Boolean(report?.worker_results && Object.keys(report.worker_results).length), evidence: 'Agent outputs and affected rows' },
    { id: 'validation', label: 'Validation approval', available: Boolean(report?.validation), evidence: 'Checks, issues, pass/fail' },
    { id: 'lineage', label: 'Lineage versions', available: Boolean(report?.lineage?.versions?.length), evidence: 'Version history and producing agents' },
  ];
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

function buildChangedCellLookup(comparePreview: ComparePreview | undefined): Map<string, NonNullable<ComparePreview['changed_cells']>[number]> {
  const lookup = new Map<string, NonNullable<ComparePreview['changed_cells']>[number]>();
  for (const cell of comparePreview?.changed_cells || []) {
    lookup.set(`${cell.row_index}::${cell.column}`, cell);
  }
  return lookup;
}

const DatasetComparePreview = memo(({ comparePreview }: { comparePreview?: ComparePreview }) => {
  const rootRef = useRef<HTMLDivElement | null>(null);
  const [selectedCell, setSelectedCell] = useState<{ rowIndex: number; column: string; side: 'before' | 'after' } | null>(null);
  const changedLookup = useMemo(() => buildChangedCellLookup(comparePreview), [comparePreview]);
  const columns = comparePreview?.columns || [];
  const beforeRows = comparePreview?.before_rows || [];
  const afterRows = comparePreview?.after_rows || [];

  const handleCellSelect = (rowIndex: number, column: string, side: 'before' | 'after') => {
    const counterpartSide = side === 'before' ? 'after' : 'before';
    setSelectedCell({ rowIndex, column, side });
    window.setTimeout(() => {
      const selector = `[data-compare-cell="${CSS.escape(`${counterpartSide}::${rowIndex}::${column}`)}"]`;
      const target = rootRef.current?.querySelector<HTMLElement>(selector);
      target?.scrollIntoView({ behavior: 'smooth', block: 'center', inline: 'center' });
    }, 0);
  };

  const renderTable = (label: string, rows: Record<string, any>[], side: 'before' | 'after') => (
    <div className="min-w-0 rounded-lg border bg-background overflow-hidden">
      <div className="flex items-center justify-between gap-3 border-b bg-muted/25 px-4 py-3">
        <div>
          <h4 className="text-sm font-semibold">{label}</h4>
          <p className="text-xs text-muted-foreground">{rows.length.toLocaleString()} preview row(s)</p>
        </div>
        <span className="rounded-full border bg-background px-2.5 py-1 text-[11px] font-medium text-muted-foreground">
          {side === 'before' ? 'Left: Input' : 'Right: Cleaned'}
        </span>
      </div>
      <div className="max-h-[640px] overflow-auto">
        <table className="w-full min-w-[72rem] border-separate border-spacing-0 text-xs">
          <thead className="sticky top-0 z-10">
            <tr>
              <th className="sticky left-0 z-20 bg-slate-50 border-b border-r px-3 py-2 text-left font-semibold text-slate-600">#</th>
              {columns.map((column) => (
                <th key={column} className="bg-slate-50 border-b border-r px-3 py-2 text-left font-semibold text-slate-600 whitespace-nowrap">
                  {column}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, rowIndex) => (
              <tr key={rowIndex} className="hover:bg-muted/20">
                <td className="sticky left-0 bg-background border-b border-r px-3 py-1.5 text-slate-500 tabular-nums">{rowIndex + 1}</td>
                {columns.map((column) => {
                  const change = changedLookup.get(`${rowIndex}::${column}`);
                  const changed = Boolean(change);
                  const selected = selectedCell?.rowIndex === rowIndex && selectedCell.column === column;
                  const selectedOrigin = selected && selectedCell.side === side;
                  const title = changed
                    ? `Before: ${formatCell(change?.before)} -> After: ${formatCell(change?.after)}`
                    : formatCell(row[column]);
                  return (
                    <td
                      key={column}
                      data-compare-cell={`${side}::${rowIndex}::${column}`}
                      onClick={() => handleCellSelect(rowIndex, column, side)}
                      className={`cursor-pointer border-b border-r px-3 py-1.5 whitespace-nowrap max-w-xs truncate ${
                        selected
                          ? selectedOrigin
                            ? 'bg-blue-100 text-blue-950 ring-2 ring-inset ring-blue-500'
                            : 'bg-cyan-100 text-cyan-950 ring-2 ring-inset ring-cyan-500'
                          : changed
                            ? 'bg-amber-100 text-amber-950 ring-1 ring-inset ring-amber-300'
                            : 'text-slate-700'
                      }`}
                      title={title}
                    >
                      {formatCell(row[column])}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );

  if (comparePreview && comparePreview.available === false) {
    return (
      <div className="rounded-xl border border-dashed bg-muted/10 p-5 text-sm text-muted-foreground">
        Before/after preview is not available yet. {comparePreview.reason}
      </div>
    );
  }

  if (!columns.length) {
    return (
      <div className="rounded-xl border border-dashed bg-muted/10 p-5 text-sm text-muted-foreground">
        Loading before/after dataset comparison...
      </div>
    );
  }

  return (
    <div ref={rootRef} className="rounded-xl border shadow-sm overflow-hidden">
      <div className="flex flex-col gap-3 border-b bg-muted/30 px-4 py-4 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <h3 className="flex items-center gap-2 text-base font-semibold">
            <ArrowRightLeft className="h-4 w-4 text-muted-foreground" />
            Before / After Dataset Comparison
          </h3>
          <p className="mt-1 text-xs text-muted-foreground">
            Showing {comparePreview?.truncated ? 'the first ' : ''}
            {comparePreview?.preview_count?.toLocaleString?.() ?? beforeRows.length.toLocaleString()} row(s). Changed cells are highlighted; click any cell to jump to the same row and column in the other table.
          </p>
        </div>
        <div className="flex flex-wrap gap-2 text-xs">
          <span className="rounded-full border bg-background px-3 py-1">
            Before: {(comparePreview?.before_row_count ?? beforeRows.length).toLocaleString()} rows
          </span>
          <span className="rounded-full border bg-background px-3 py-1">
            After: {(comparePreview?.after_row_count ?? afterRows.length).toLocaleString()} rows
          </span>
          <span className="rounded-full border border-amber-300 bg-amber-100 px-3 py-1 text-amber-900">
            {(comparePreview?.changed_cell_count ?? 0).toLocaleString()} changed cells in preview
          </span>
        </div>
      </div>
      <div className="grid grid-cols-1 gap-4 p-4 lg:grid-cols-2">
        {renderTable('Original dataset', beforeRows, 'before')}
        {renderTable('Cleaned dataset', afterRows, 'after')}
      </div>
    </div>
  );
});

DatasetComparePreview.displayName = 'DatasetComparePreview';

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

interface ReportChatPanelProps {
  runId: string;
}

const ReportChatPanel = memo(({ runId }: ReportChatPanelProps) => {
  const [isOpen, setIsOpen] = useState(false);
  const [question, setQuestion] = useState('');
  const [messages, setMessages] = useState<any[]>([]);
  const [isAsking, setIsAsking] = useState(false);
  const transcriptEndRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!isOpen) return;
    transcriptEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [isOpen, messages.length, isAsking]);

  useQuery({
    queryKey: ['report-chat-history', runId],
    queryFn: async () => {
      const history = await pipelineApi.getReportChatHistory(runId);
      setMessages(history.messages || []);
      return history;
    },
  });

  const handleAsk = async () => {
    const trimmed = question.trim();
    if (!trimmed) return;
    setIsAsking(true);
    setQuestion('');
    setMessages((prev) => [
      ...prev,
      {
        role: 'user',
        content: trimmed,
        created_at: new Date().toISOString(),
      },
    ]);
    try {
      const result = await pipelineApi.askReport(runId, trimmed);
      const history = result.history || [];
      if (history.length > 0 && result.reasoning_summary) {
        const lastIndex = history.length - 1;
        setMessages(history.map((message: any, index: number) => (
          index === lastIndex
            ? { ...message, reasoning_summary: result.reasoning_summary, answer_mode: result.answer_mode }
            : message
        )));
      } else {
        setMessages(history);
      }
    } finally {
      setIsAsking(false);
    }
  };

  if (!isOpen) {
    return (
      <button
        type="button"
        onClick={() => setIsOpen(true)}
        className="fixed bottom-6 right-6 z-50 inline-flex h-14 w-14 items-center justify-center rounded-full border bg-primary text-primary-foreground shadow-lg transition hover:bg-primary/90"
        aria-label="Ask Report Agent"
        title="Ask Report Agent"
      >
        <MessageSquare className="h-5 w-5" />
      </button>
    );
  }

  return (
    <div className="fixed bottom-6 right-6 z-50 flex h-[min(72vh,680px)] w-[min(92vw,420px)] flex-col overflow-hidden rounded-xl border bg-card text-card-foreground shadow-2xl">
      <div className="px-5 py-4 border-b bg-muted/30 flex items-center gap-2">
        <MessageSquare className="w-4 h-4 text-muted-foreground" />
        <span className="text-sm font-semibold">Ask the Report Agent</span>
        <button
          type="button"
          onClick={() => setIsOpen(false)}
          className="ml-auto inline-flex h-8 w-8 items-center justify-center rounded-md text-muted-foreground transition hover:bg-muted hover:text-foreground"
          aria-label="Close Report Agent"
        >
          <X className="h-4 w-4" />
        </button>
      </div>
      <div className="flex min-h-0 flex-1 flex-col">
        <div className="flex-1 overflow-y-auto bg-muted/5 px-5 py-5">
          <div className="mx-auto flex max-w-full flex-col gap-4">
            {messages.length === 0 && !isAsking && (
              <div className="rounded-lg border border-dashed bg-background px-4 py-6 text-sm text-muted-foreground">
                Ask about changed columns, before/after values, planner decisions, worker results, approval evidence, validation metrics, lineage, tokens, or next transformations.
              </div>
            )}
            {messages.map((message, index) => {
              const isUser = message.role === 'user';
              return (
                <div key={message.id || index} className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
                  <div
                    className={`max-w-[86%] rounded-xl border px-4 py-3 text-sm shadow-sm ${
                      isUser
                        ? 'border-primary/20 bg-primary/10 text-foreground'
                        : 'bg-background text-foreground'
                    }`}
                  >
                    <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground mb-1">
                      {isUser ? 'You' : 'Report Agent'}
                    </div>
                    {!isUser && (
                      <div className="mb-2 flex items-center justify-between gap-2">
                        {(message.answer_mode === 'llm_synthesis' || message.answer_mode === 'scope_guard') && (
                          <span className="rounded-full border bg-muted/40 px-2 py-0.5 text-[10px] font-medium text-muted-foreground">
                            {message.answer_mode === 'llm_synthesis' ? 'LLM synthesis' : 'Out of scope'}
                          </span>
                        )}
                      </div>
                    )}
                    <div className="prose prose-sm dark:prose-invert max-w-none text-sm leading-relaxed [&_ul]:list-disc [&_ul]:pl-4 [&_ol]:list-decimal [&_ol]:pl-4 [&_p]:mb-2 [&_p:last-child]:mb-0 [&_strong]:font-semibold [&_li]:my-0.5">
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>
                        {message.content}
                      </ReactMarkdown>
                    </div>
                    {message.sources?.length > 0 && (
                      <div className="mt-3 flex flex-wrap gap-1.5">
                        {message.sources.map((source: string) => (
                          <span key={source} className="rounded-full border bg-muted/40 px-2 py-0.5 text-[10px] font-medium text-muted-foreground">
                            {source}
                          </span>
                        ))}
                      </div>
                    )}
                    {message.reasoning_summary && (
                      <div className="mt-3 rounded-lg border border-primary/15 bg-primary/5 px-3 py-2 text-xs leading-relaxed text-muted-foreground">
                        <span className="font-semibold text-foreground">Analysis checked: </span>
                        {message.reasoning_summary}
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
            {isAsking && (
              <div className="flex justify-start">
                <div className="max-w-[86%] rounded-xl border bg-background px-4 py-3 text-sm shadow-sm">
                  <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground mb-1">
                    Report Agent
                  </div>
                  <div className="flex items-center gap-2 text-muted-foreground">
                    <span className="inline-flex h-2 w-2 animate-pulse rounded-full bg-primary" />
                    <span>Checking report, planner, workers, validation, lineage, metrics, and recent chat...</span>
                  </div>
                </div>
              </div>
            )}
            <div ref={transcriptEndRef} />
          </div>
        </div>
        <div className="border-t bg-background p-4">
          <div className="mx-auto max-w-full">
            <div className="flex flex-col sm:flex-row gap-2">
              <input
                value={question}
                onChange={(event) => setQuestion(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter') void handleAsk();
                }}
                placeholder="Ask what changed, why it was approved, which worker ran, or what to transform next..."
                disabled={isAsking}
                className="flex-1 rounded-md border bg-background px-3 py-3 text-sm outline-none focus:ring-2 focus:ring-primary/30"
              />
              <button
                type="button"
                disabled={isAsking || !question.trim()}
                onClick={() => void handleAsk()}
                className="inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-md bg-primary text-primary-foreground disabled:opacity-50"
                aria-label="Send message"
                title="Send message"
              >
                <Send className="h-4 w-4" />
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
});

ReportChatPanel.displayName = 'ReportChatPanel';

export const ResultView: React.FC<ResultViewProps> = ({ runId, onStartOver }) => {
  const [showRawJson, setShowRawJson] = useState(false);
  const [showDiagram, setShowDiagram] = useState(true);

  const { data: report, isLoading, error } = useQuery({
    queryKey: ['pipeline-report', runId],
    queryFn: () => pipelineApi.getReport(runId),
  });
  const {
    data: lineageDiagram,
    isLoading: isDiagramLoading,
    error: diagramError,
  } = useQuery({
    queryKey: ['report-diagram', runId, 'lineage'],
    queryFn: () => pipelineApi.getReportDiagram(runId, 'lineage'),
  });
  const { data: comparePreview } = useQuery<ComparePreview>({
    queryKey: ['dataset-compare-preview', runId],
    queryFn: () => pipelineApi.getDatasetComparePreview(runId, 100, true),
  });

  const rowsProcessed = useMemo(() => getRowsProcessed(report), [report]);
  const columnCount = useMemo(() => getColumnCount(report), [report]);
  const transformationLines = useMemo(() => buildTransformationLines(report), [report]);
  const evidenceContexts = useMemo(() => buildEvidenceContexts(report), [report]);

  const validation = report?.validation as Record<string, any> | undefined;
  const hasValidation = validation && Object.keys(validation).length > 0;
  const validationPassed = hasValidation ? validation.passed === true : true;
  const validationIssues: any[] = Array.isArray(validation?.issues) ? validation.issues : [];

  const handleDownload = (format: 'csv' | 'xlsx' | 'parquet') => {
    window.location.href = pipelineApi.getDownloadUrl(runId, format);
  };

  const handleReportExport = (format: 'json' | 'md' | 'html') => {
    window.location.href = pipelineApi.getReportExportUrl(runId, format);
  };

  /** Outer fills main; inner scroll region gets flex-1 min-h-0 so it scrolls under h-screen + overflow-hidden. */
  return (
    <div className="w-full max-w-none flex flex-col flex-1 min-h-0 text-left self-stretch">
      <div className="flex-1 min-h-0 overflow-y-auto px-4 pt-6 pb-4 sm:px-6 lg:px-8 hidden-scrollbar">
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
            <h1 className="text-2xl sm:text-3xl font-bold tracking-tight mb-2">
              {validationPassed ? 'Pipeline Completed' : 'Pipeline Completed — Validation Notes'}
            </h1>
            <p className="text-muted-foreground max-w-2xl">
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
              <p className="text-sm text-amber-700 dark:text-amber-400 mt-3 max-w-2xl">
                Validation did not fully pass. Review the summary below and the issue list — you can still download the output.
              </p>
            )}
          </div>

          <div className="rounded-xl border bg-card text-card-foreground shadow mb-6 overflow-hidden">
            <div className="p-4 sm:p-6 border-b bg-muted/20">
              <h2 className="text-lg sm:text-xl font-semibold flex items-center gap-2">
                <Database className="w-5 h-5 text-muted-foreground" />
                Processing Summary
              </h2>
            </div>
            <div className="p-4 sm:p-6 space-y-8">
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
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

              <div className="rounded-xl border bg-muted/10 p-4">
                <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide mb-3">
                  Cleaning Summary
                </h3>
                <div className="grid grid-cols-1 gap-3 text-sm md:grid-cols-2 xl:grid-cols-4">
                  <div className="rounded-lg border bg-background px-4 py-3">
                    <div className="text-xs text-muted-foreground mb-1">Original rows</div>
                    <div className="font-semibold tabular-nums">
                      {(comparePreview?.before_row_count ?? report?.summary?.input_rows ?? 0).toLocaleString()}
                    </div>
                  </div>
                  <div className="rounded-lg border bg-background px-4 py-3">
                    <div className="text-xs text-muted-foreground mb-1">Cleaned rows</div>
                    <div className="font-semibold tabular-nums">
                      {(comparePreview?.after_row_count ?? report?.summary?.output_rows ?? 0).toLocaleString()}
                    </div>
                  </div>
                  <div className="rounded-lg border bg-background px-4 py-3">
                    <div className="text-xs text-muted-foreground mb-1">Changed cells</div>
                    <div className="font-semibold tabular-nums">
                      {(comparePreview?.changed_cell_count ?? 0).toLocaleString()}
                    </div>
                  </div>
                  <div className="rounded-lg border bg-background px-4 py-3">
                    <div className="text-xs text-muted-foreground mb-1">Outcome</div>
                    <div className="font-semibold">
                      {validationPassed ? 'Validated output' : 'Completed with notes'}
                    </div>
                  </div>
                </div>
                <ul className="mt-3 list-disc pl-5 text-sm leading-relaxed text-muted-foreground">
                  <li>{transformationLines.length.toLocaleString()} cleaning step(s) are documented for this run.</li>
                  <li>{(report?.lineage?.version_count ?? 0).toLocaleString()} approved lineage version(s) are available for inspection.</li>
                  <li>The before/after tables below link matching cells across the original and cleaned datasets.</li>
                </ul>
              </div>

              <div>
                <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide mb-3">
                  Report Agent evidence map
                </h3>
                <div className="grid grid-cols-1 gap-2 text-sm md:grid-cols-2 xl:grid-cols-5">
                  {evidenceContexts.map((context) => (
                    <div
                      key={context.id}
                      className={`rounded-lg border px-3 py-2 ${
                        context.available ? 'bg-background' : 'bg-muted/20 text-muted-foreground'
                      }`}
                    >
                      <div className="flex items-center gap-2">
                        <span
                          className={`h-2 w-2 rounded-full ${
                            context.available ? 'bg-emerald-500' : 'bg-slate-300'
                          }`}
                        />
                        <span className="font-medium">{context.label}</span>
                      </div>
                      <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{context.evidence}</p>
                    </div>
                  ))}
                </div>
              </div>

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

              <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
                <div className="xl:col-span-2 rounded-xl border bg-muted/10 p-4">
                  <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide mb-2">
                    Dataset documentation
                  </h3>
                  <p className="text-sm leading-relaxed text-foreground">
                    {report?.semantic_summary?.table_summary || 'No semantic table summary was produced for this run.'}
                  </p>
                </div>
                <div className="rounded-xl border bg-muted/10 p-4">
                  <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide mb-3">
                    Profile highlights
                  </h3>
                  <div className="space-y-2 text-sm">
                    <div className="flex justify-between gap-3">
                      <span className="text-muted-foreground">Initial rows</span>
                      <span className="font-medium tabular-nums">{report?.profile_summary?.total_rows?.toLocaleString?.() ?? 'â€”'}</span>
                    </div>
                    <div className="flex justify-between gap-3">
                      <span className="text-muted-foreground">Initial columns</span>
                      <span className="font-medium tabular-nums">{report?.profile_summary?.total_columns?.toLocaleString?.() ?? 'â€”'}</span>
                    </div>
                    <div className="flex justify-between gap-3">
                      <span className="text-muted-foreground">Missing values</span>
                      <span className="font-medium tabular-nums">{report?.profile_summary?.missing_values_detected?.toLocaleString?.() ?? 'â€”'}</span>
                    </div>
                    <div className="flex justify-between gap-3">
                      <span className="text-muted-foreground">Duplicate rows</span>
                      <span className="font-medium tabular-nums">{report?.profile_summary?.duplicate_rows?.toLocaleString?.() ?? 'â€”'}</span>
                    </div>
                  </div>
                </div>
              </div>

              {report?.lineage?.versions?.length > 0 && (
                <div className="rounded-xl border shadow-sm overflow-hidden">
                  <div className="px-4 py-3 border-b bg-muted/30 flex items-center gap-2">
                    <GitBranch className="w-4 h-4 text-muted-foreground" />
                    <span className="text-sm font-semibold">Data lineage</span>
                    <span className="ml-auto text-xs text-muted-foreground">
                      {report.lineage.version_count} approved version(s)
                    </span>
                  </div>
                  <div className="divide-y">
                    {report.lineage.versions.map((version: any) => (
                      <div key={version.version} className="px-4 py-3 text-sm">
                        <div className="flex flex-col gap-2 lg:flex-row lg:items-center">
                          <div className="flex min-w-0 flex-1 items-center gap-2">
                            <span className="font-semibold">v{version.version}</span>
                            <span className="truncate text-muted-foreground">{version.agent_name}</span>
                          </div>
                          <div className="flex flex-wrap gap-1.5">
                            {(['csv', 'xlsx', 'parquet'] as const).map((format) => (
                              <button
                                key={format}
                                type="button"
                                onClick={() => {
                                  window.location.href = pipelineApi.getVersionDownloadUrl(runId, version.version, format);
                                }}
                                className="inline-flex h-7 items-center rounded-md border bg-background px-2 text-[11px] font-medium uppercase text-muted-foreground hover:bg-muted/30 hover:text-foreground"
                              >
                                <Download className="mr-1 h-3 w-3" />
                                {format}
                              </button>
                            ))}
                          </div>
                        </div>
                        {version.description && (
                          <p className="text-xs text-muted-foreground mt-1">{version.description}</p>
                        )}
                      </div>
                    ))}
                  </div>
                  <button
                    type="button"
                    onClick={() => setShowDiagram(!showDiagram)}
                    className="w-full border-t px-4 py-2 text-left text-xs font-medium text-muted-foreground hover:text-foreground hover:bg-muted/20"
                  >
                    {showDiagram ? 'Hide' : 'Show'} Mermaid lineage diagram
                  </button>
                  {showDiagram && (
                    <div className="m-4">
                      {isDiagramLoading ? (
                        <div className="flex min-h-40 items-center justify-center rounded-lg border bg-muted/10 p-4 text-sm text-muted-foreground">
                          Loading diagram...
                        </div>
                      ) : diagramError ? (
                        <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">
                          Failed to load the lineage diagram.
                        </div>
                      ) : (
                        <MermaidDiagram definition={lineageDiagram?.diagram || ''} />
                      )}
                    </div>
                  )}
                </div>
              )}

              {hasValidation && (
                <div
                  className={`rounded-2xl border-2 overflow-hidden ${
                    validationPassed ? 'border-emerald-200 dark:border-emerald-900' : 'border-amber-200 dark:border-amber-900'
                  }`}
                >
                  <div
                    className={`px-5 py-4 flex items-center gap-3 ${
                      validationPassed
                        ? 'bg-emerald-600'
                        : 'bg-amber-600'
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
                      <div className="space-y-6">
                        {Object.entries(validation.metrics).map(([k, v]) => {
                          if (k === 'Intent Analysis') {
                            const data = v as any;
                            return (
                              <div key={k} className="space-y-3">
                                <h4 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider">{k}</h4>
                                <div className="grid grid-cols-2 gap-3">
                                  <div className="rounded-xl border bg-card p-4 shadow-sm flex flex-col justify-center items-center text-center">
                                    <span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider mb-2">Matched Columns</span>
                                    <span className="text-2xl font-bold text-foreground">{data['Matched Columns'] ?? '—'}</span>
                                  </div>
                                  <div className="rounded-xl border bg-card p-4 shadow-sm flex flex-col justify-center items-center text-center">
                                    <span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider mb-2">Missing Values Detected</span>
                                    <span className="text-2xl font-bold text-amber-600">{data['Missing values detected'] ?? '—'}</span>
                                  </div>
                                </div>
                              </div>
                            );
                          }
                          
                          if (k === 'F1-Score Evaluation') {
                            const data = v as any;
                            return (
                              <div key={k} className="space-y-3">
                                <h4 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider">{k}</h4>
                                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                                  <div className="rounded-xl border bg-card p-4 shadow-sm flex justify-center items-center">
                                    <CircularProgress value={(data.f1_score ?? 0) * 100} label="F1 Score" />
                                  </div>
                                  <div className="rounded-xl border bg-card p-4 shadow-sm flex justify-center items-center">
                                    <CircularProgress value={(data.error_correction_precision ?? 0) * 100} label="Precision" />
                                  </div>
                                  <div className="rounded-xl border bg-card p-4 shadow-sm flex justify-center items-center">
                                    <CircularProgress value={(data.error_correction_recall ?? 0) * 100} label="Recall" />
                                  </div>
                                  <div className="rounded-xl border bg-card p-4 shadow-sm flex justify-center items-center">
                                    <CircularProgress value={(data.cell_accuracy ?? 0) * 100} label="Accuracy" />
                                  </div>
                                </div>
                                <div className="grid grid-cols-4 gap-3">
                                  <div className="col-span-4 sm:col-span-1 rounded-xl border bg-card px-4 py-3 shadow-sm flex flex-col justify-center">
                                    <span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider mb-1">Total Cells</span>
                                    <span className="text-lg font-bold text-foreground">{data.total_cells_evaluated?.toLocaleString() ?? '—'}</span>
                                  </div>
                                  <div className="col-span-4 sm:col-span-3 rounded-xl border bg-card px-4 py-3 shadow-sm flex items-center justify-around">
                                    <div className="flex flex-col items-center">
                                      <span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider mb-1">True Positive</span>
                                      <span className="text-sm font-bold text-emerald-600">{data.tp?.toLocaleString() ?? '—'}</span>
                                    </div>
                                    <div className="flex flex-col items-center">
                                      <span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider mb-1">False Positive</span>
                                      <span className="text-sm font-bold text-amber-600">{data.fp?.toLocaleString() ?? '—'}</span>
                                    </div>
                                    <div className="flex flex-col items-center">
                                      <span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider mb-1">False Negative</span>
                                      <span className="text-sm font-bold text-rose-600">{data.fn?.toLocaleString() ?? '—'}</span>
                                    </div>
                                  </div>
                                </div>
                              </div>
                            );
                          }

                          // Fallback for other metrics
                          const lines = flattenMetricLines(v);
                          return (
                            <div key={k} className="rounded-lg border border-border bg-muted/15 overflow-hidden">
                              <div className="px-3 py-2 border-b border-border/80 bg-muted/30 text-xs font-semibold text-foreground uppercase tracking-wider">
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

              <DatasetComparePreview comparePreview={comparePreview} />

              <ReportChatPanel
                runId={runId}
              />

              {report?.next_actions?.length > 0 && (
                <div className="rounded-xl border bg-muted/10 px-4 py-3">
                  <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide mb-3">
                    Recommended next actions
                  </h3>
                  <ul className="list-disc pl-5 text-sm leading-relaxed text-foreground space-y-1">
                    {report.next_actions.map((action: string, index: number) => (
                      <li key={index}>{action}</li>
                    ))}
                  </ul>
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

              <div className="border-t pt-6">
                <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap">
                  <button
                    onClick={() => handleReportExport('json')}
                    className="inline-flex h-11 items-center justify-center whitespace-nowrap rounded-md border border-input bg-background px-4 text-sm font-medium transition-colors hover:bg-accent hover:text-accent-foreground"
                  >
                    <FileText className="mr-2 h-4 w-4" />
                    Report JSON
                  </button>
                  {([
                    ['csv', 'CSV'],
                    ['xlsx', 'XLSX'],
                    ['parquet', 'Parquet'],
                  ] as const).map(([format, label]) => (
                    <button
                      key={format}
                      onClick={() => handleDownload(format)}
                      className="inline-flex h-11 items-center justify-center whitespace-nowrap rounded-md bg-primary px-5 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
                    >
                      <Download className="mr-2 h-4 w-4" />
                      Download {label}
                    </button>
                  ))}
                  <button
                    onClick={onStartOver}
                    className="inline-flex h-11 items-center justify-center whitespace-nowrap rounded-md border border-input bg-background px-8 text-sm font-medium transition-colors hover:bg-accent hover:text-accent-foreground"
                  >
                    <RotateCcw className="mr-2 h-4 w-4" />
                    Process Another File
                  </button>
                </div>
              </div>
            </div>
          </div>
          </>
        )}
      </div>
    </div>
  );
};

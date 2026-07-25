import React, { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  AlertCircle,
  ArrowLeftRight,
  CheckCircle2,
  ChevronDown,
  Download,
  FileJson,
  FileText,
  Gauge,
  GitBranch,
  RotateCcw,
  ShieldCheck,
} from 'lucide-react';
import { pipelineApi } from '../../api/services';
import { MermaidDiagram } from '../MermaidDiagram';
import { DatasetComparePreview, ReportChatPanel } from './ResultView';

interface ResultViewProps {
  runId: string;
  onStartOver: () => void;
}

interface ComparePreview {
  available?: boolean;
  reason?: string;
  columns?: string[];
  before_rows?: Record<string, unknown>[];
  after_rows?: Record<string, unknown>[];
  before_row_count?: number;
  after_row_count?: number;
  preview_count?: number;
  changed_cells?: Array<{
    row_index: number;
    column: string;
    before: unknown;
    after: unknown;
  }>;
  changed_cell_count?: number;
  truncated?: boolean;
}

interface ReportSummary {
  input_rows?: number;
  output_rows?: number;
  tracked_columns?: number;
  retry_cycles?: number;
  total_tokens_used?: number;
}

interface F1Metrics {
  f1_score?: number;
  error_correction_precision?: number;
  error_correction_recall?: number;
  cell_accuracy?: number;
  total_cells_evaluated?: number;
  tp?: number;
  fp?: number;
  fn?: number;
}

interface LineageVersion {
  version: number | string;
  agent_name?: string;
  description?: string;
  created_at?: string;
}

interface ReportContract {
  filename?: string;
  completed_at?: string;
  summary?: ReportSummary;
  profile_summary?: {
    total_rows?: number;
    total_columns?: number;
    missing_values_detected?: number;
    duplicate_rows?: number;
  };
  semantic_summary?: {
    table_summary?: string;
  };
  execution_plan_summary?: {
    active_task_count?: number;
    skipped_task_count?: number;
  };
  worker_results?: Record<string, unknown>;
  validation?: {
    passed?: boolean;
    issue_count?: number;
  };
  lineage?: {
    versions?: LineageVersion[];
    version_count?: number;
    latest_version?: number | string;
  };
  metrics?: {
    f1_metrics?: F1Metrics;
    token_metrics?: {
      total_tokens?: number;
    };
  };
  transformations?: string[];
  next_actions?: string[];
}

type ResultTab = 'summary' | 'lineage' | 'compare';

const RESULT_TABS: Array<{
  id: ResultTab;
  label: string;
  icon: React.ComponentType<{ className?: string; 'aria-hidden'?: boolean }>;
}> = [
  { id: 'summary', label: 'Summary', icon: ShieldCheck },
  { id: 'lineage', label: 'Data lineage', icon: GitBranch },
  { id: 'compare', label: 'Before & after', icon: ArrowLeftRight },
];

function formatDate(dateValue?: string): string {
  if (!dateValue) return '';
  const date = new Date(dateValue);
  if (Number.isNaN(date.getTime())) return dateValue;
  return new Intl.DateTimeFormat('en-GB', {
    timeZone: 'Asia/Bangkok',
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(date);
}

function formatNumber(value: number | undefined): string {
  return typeof value === 'number' && Number.isFinite(value) ? value.toLocaleString() : '—';
}

function formatScore(value: number | undefined): string {
  return typeof value === 'number' && Number.isFinite(value)
    ? `${(value * 100).toFixed(1)}%`
    : '—';
}

function download(url: string): void {
  window.location.assign(url);
}

function normalizeMetric(value: number | undefined): number | null {
  if (typeof value !== 'number' || !Number.isFinite(value)) return null;
  return Math.max(0, Math.min(1, value));
}

const BenchmarkMetricBar: React.FC<{
  label: string;
  description: string;
  value?: number;
}> = ({ label, description, value }) => {
  const normalizedValue = normalizeMetric(value);
  const barStyle = {
    '--benchmark-bar-scale': normalizedValue ?? 0,
  } as React.CSSProperties;

  return (
    <div
      className="space-y-2"
      role="img"
      aria-label={`${label}: ${formatScore(value)}. ${description}`}
    >
      <div className="flex items-end justify-between gap-4">
        <div>
          <p className="text-sm font-medium">{label}</p>
          <p className="text-xs text-muted-foreground">{description}</p>
        </div>
        <span className="shrink-0 text-sm font-semibold tabular-nums">
          {formatScore(value)}
        </span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-muted">
        <div
          className="benchmark-metric-bar h-full w-full origin-left rounded-full bg-primary"
          style={barStyle}
        />
      </div>
    </div>
  );
};

const BenchmarkMetricsVisualization: React.FC<{ metrics: F1Metrics }> = ({ metrics }) => {
  const normalizedF1 = normalizeMetric(metrics.f1_score);
  const gaugeValue = (normalizedF1 ?? 0) * 100;
  const gaugeStyle = {
    '--benchmark-gauge-value': gaugeValue,
  } as React.CSSProperties;
  const gaugeTicks = [0, 25, 50, 75, 100].map((value) => {
    const angle = Math.PI - (value / 100) * Math.PI;
    return {
      value,
      x: 90 + 70 * Math.cos(angle),
      y: 92 - 70 * Math.sin(angle),
    };
  });
  const evidenceItems = [
    ['Evaluated cells', metrics.total_cells_evaluated],
    ['True positives', metrics.tp],
    ['False positives', metrics.fp],
    ['False negatives', metrics.fn],
  ] as const;

  return (
    <section
      className="overflow-hidden rounded-xl border border-primary/15 bg-gradient-to-br from-primary/[0.06] via-background to-background"
      aria-labelledby="benchmark-quality-title"
    >
      <div className="flex flex-col gap-3 border-b border-primary/10 px-4 py-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-start gap-3">
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
            <Gauge className="h-4 w-4" aria-hidden="true" />
          </span>
          <div>
            <h2 id="benchmark-quality-title" className="text-base font-semibold">
              Benchmark quality
            </h2>
            <p className="mt-0.5 text-xs text-muted-foreground">
              Performance against the supplied clean ground-truth dataset.
            </p>
          </div>
        </div>
        <span className="w-fit rounded-full border border-primary/20 bg-background/80 px-2.5 py-1 text-xs font-medium text-primary">
          Ground-truth evaluation
        </span>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[minmax(15rem,0.8fr)_minmax(0,1.2fr)]">
        <div className="flex flex-col items-center justify-center border-b p-5 lg:border-b-0 lg:border-r">
          <div
            className="w-full max-w-[16rem]"
            role="img"
            aria-label={`F1 score: ${formatScore(metrics.f1_score)}. Composite balance of precision and recall.`}
          >
            <svg
              viewBox="0 0 180 112"
              className="h-auto w-full overflow-visible"
              aria-hidden="true"
            >
              <path
                d="M 20 92 A 70 70 0 0 1 160 92"
                pathLength="100"
                fill="none"
                className="stroke-muted"
                strokeWidth="12"
                strokeLinecap="round"
              />
              <path
                d="M 20 92 A 70 70 0 0 1 160 92"
                pathLength="100"
                fill="none"
                className="benchmark-gauge-progress stroke-primary"
                strokeWidth="12"
                strokeLinecap="round"
                style={gaugeStyle}
              />
              {gaugeTicks.map((tick) => (
                <circle
                  key={tick.value}
                  cx={tick.x}
                  cy={tick.y}
                  r="2.2"
                  className="fill-background stroke-border"
                  strokeWidth="1"
                />
              ))}
              <text
                x="90"
                y="77"
                textAnchor="middle"
                className="fill-foreground text-[23px] font-semibold tabular-nums"
              >
                {formatScore(metrics.f1_score)}
              </text>
              <text
                x="90"
                y="91"
                textAnchor="middle"
                className="fill-muted-foreground text-[8px] font-semibold tracking-[0.18em]"
              >
                F1 SCORE
              </text>
              <text x="15" y="108" className="fill-muted-foreground text-[8px]">0</text>
              <text x="154" y="108" className="fill-muted-foreground text-[8px]">100</text>
            </svg>
          </div>
          <p className="mt-1 text-center text-xs text-muted-foreground">
            Composite balance of precision and recall
          </p>
        </div>

        <div className="space-y-5 p-5">
          <BenchmarkMetricBar
            label="Precision"
            description="How often proposed fixes were correct"
            value={metrics.error_correction_precision}
          />
          <BenchmarkMetricBar
            label="Recall"
            description="How many required fixes were recovered"
            value={metrics.error_correction_recall}
          />
          <BenchmarkMetricBar
            label="Cell accuracy"
            description="Share of all evaluated cells that match"
            value={metrics.cell_accuracy}
          />
        </div>
      </div>

      {evidenceItems.some(([, value]) => typeof value === 'number') && (
        <dl className="grid grid-cols-2 border-t bg-background/45 sm:grid-cols-4">
          {evidenceItems.map(([label, value], index) => (
            <div
              key={label}
              className={`px-4 py-3 ${
                index % 2 === 0 ? 'border-r' : ''
              } sm:border-r sm:last:border-r-0`}
            >
              <dt className="text-[11px] text-muted-foreground">{label}</dt>
              <dd className="mt-1 text-sm font-semibold tabular-nums">
                {formatNumber(value)}
              </dd>
            </div>
          ))}
        </dl>
      )}
    </section>
  );
};

export const ResultView: React.FC<ResultViewProps> = ({ runId, onStartOver }) => {
  const [activeTab, setActiveTab] = useState<ResultTab>('summary');
  const [showDiagram, setShowDiagram] = useState(false);

  const {
    data: report,
    isLoading,
    error,
  } = useQuery<ReportContract>({
    queryKey: ['pipeline-report', runId],
    queryFn: () => pipelineApi.getReport(runId),
  });

  const {
    data: comparePreview,
    isLoading: isCompareLoading,
    error: compareError,
    refetch: refetchCompare,
  } = useQuery<ComparePreview>({
    queryKey: ['dataset-compare-preview', runId, 100],
    queryFn: () => pipelineApi.getDatasetComparePreview(runId, 100, false),
  });

  const {
    data: lineageDiagram,
    isLoading: isDiagramLoading,
    error: diagramError,
  } = useQuery<{ diagram?: string }>({
    queryKey: ['report-diagram', runId, 'lineage'],
    queryFn: () => pipelineApi.getReportDiagram(runId, 'lineage'),
    enabled: activeTab === 'lineage' && showDiagram,
  });

  const lineageVersions = useMemo(
    () => report?.lineage?.versions || [],
    [report?.lineage?.versions],
  );
  const transformations = useMemo(
    () => report?.transformations || [],
    [report?.transformations],
  );

  const handleTabKeyDown = (
    event: React.KeyboardEvent<HTMLButtonElement>,
    currentIndex: number,
  ) => {
    let nextIndex: number | null = null;
    if (event.key === 'ArrowRight' || event.key === 'ArrowDown') {
      nextIndex = (currentIndex + 1) % RESULT_TABS.length;
    } else if (event.key === 'ArrowLeft' || event.key === 'ArrowUp') {
      nextIndex = (currentIndex - 1 + RESULT_TABS.length) % RESULT_TABS.length;
    } else if (event.key === 'Home') {
      nextIndex = 0;
    } else if (event.key === 'End') {
      nextIndex = RESULT_TABS.length - 1;
    }

    if (nextIndex === null) return;
    event.preventDefault();
    const nextTab = RESULT_TABS[nextIndex];
    setActiveTab(nextTab.id);
    window.requestAnimationFrame(() => {
      document.getElementById(`result-tab-${nextTab.id}`)?.focus();
    });
  };

  if (isLoading) {
    return (
      <div className="result-page-surface w-full flex-1 px-4 py-6 sm:px-6 lg:px-8" aria-busy="true" aria-live="polite">
        <span className="sr-only">Loading result</span>
        <div className="mx-auto w-full max-w-7xl space-y-6 animate-pulse motion-reduce:animate-none">
          <div className="h-48 rounded-2xl border bg-card/80 shadow-sm" />
          <div className="h-16 rounded-2xl border bg-card/70 shadow-sm" />
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <div className="h-40 rounded-2xl border bg-card/70 shadow-sm sm:col-span-2" />
            <div className="h-40 rounded-2xl border bg-card/70 shadow-sm" />
          </div>
        </div>
      </div>
    );
  }

  if (error || !report) {
    return (
      <div className="flex flex-1 items-center justify-center p-6">
        <div className="max-w-lg rounded-xl border border-destructive/30 bg-destructive/5 p-5 text-sm text-destructive">
          The final result is not available yet. Return to the pipeline and try again when reporting is complete.
        </div>
      </div>
    );
  }

  const validationPassed = report.validation?.passed !== false;
  const changedCellCount = comparePreview?.changed_cell_count;
  const latestVersion = report.lineage?.latest_version;
  const f1Metrics = report.metrics?.f1_metrics;
  const visibleTransformations = transformations.slice(0, 4);
  const remainingTransformations = transformations.slice(4);

  return (
    <div className="result-page-surface min-h-0 w-full flex-1 overflow-y-auto px-4 py-5 sm:px-6 sm:py-7 lg:px-8">
      <main className="mx-auto w-full max-w-7xl space-y-6">
        <header className="result-surface-enter relative isolate overflow-hidden rounded-2xl border border-primary/15 bg-card/95 p-5 text-card-foreground shadow-sm sm:p-6">
          <div className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-primary/60 to-transparent" aria-hidden="true" />
          <div className="pointer-events-none absolute -right-16 -top-24 h-64 w-64 rounded-full bg-primary/[0.07] blur-3xl" aria-hidden="true" />

          <div className="relative flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
            <div className="flex min-w-0 items-start gap-4">
              <div
                className={`result-success-pop flex h-12 w-12 shrink-0 items-center justify-center rounded-full ring-8 ring-background/70 ${
                  validationPassed
                    ? 'bg-emerald-100 text-emerald-700 shadow-sm dark:bg-emerald-950/60 dark:text-emerald-300'
                    : 'bg-amber-100 text-amber-800 dark:bg-amber-950/50 dark:text-amber-200'
                }`}
              >
                {validationPassed ? (
                  <CheckCircle2 className="h-5 w-5" aria-hidden="true" />
                ) : (
                  <AlertCircle className="h-5 w-5" aria-hidden="true" />
                )}
              </div>
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">
                    Cleaning complete
                  </h1>
                  <span className="rounded-full border border-primary/15 bg-primary/[0.06] px-2.5 py-1 text-xs font-medium text-foreground">
                    {validationPassed ? 'Validated' : 'Review needed'}
                  </span>
                </div>
                <p className="mt-2 break-words text-sm text-muted-foreground">
                  {report.filename || 'Dataset'}
                  {report.completed_at ? ` · ${formatDate(report.completed_at)}` : ''}
                </p>
              </div>
            </div>

            <div className="grid w-full grid-cols-1 gap-2 sm:flex sm:w-auto sm:flex-wrap">
              <button
                type="button"
                onClick={() => download(pipelineApi.getDownloadUrl(runId, 'csv'))}
                className="result-interactive inline-flex min-h-11 w-full cursor-pointer items-center justify-center rounded-lg bg-primary px-4 text-sm font-medium text-primary-foreground shadow-sm hover:bg-primary/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 sm:w-auto"
              >
                <Download className="mr-2 h-4 w-4" aria-hidden="true" />
                Download CSV
              </button>

              <details className="group relative w-full sm:w-auto">
                <summary className="result-interactive inline-flex min-h-11 w-full cursor-pointer list-none items-center justify-center rounded-lg border bg-background/80 px-4 text-sm font-medium shadow-sm hover:bg-muted/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2">
                  More downloads
                  <ChevronDown className="ml-2 h-4 w-4 transition-transform duration-200 group-open:rotate-180 motion-reduce:transition-none" aria-hidden="true" />
                </summary>
                <div className="result-menu-enter mt-2 flex w-full flex-wrap gap-2 rounded-xl border bg-popover p-3 text-popover-foreground shadow-lg sm:absolute sm:right-0 sm:z-20 sm:w-[24rem]">
                  {(['xlsx', 'parquet'] as const).map((format) => (
                    <button
                      key={format}
                      type="button"
                      onClick={() => download(pipelineApi.getDownloadUrl(runId, format))}
                      className="result-interactive inline-flex min-h-11 cursor-pointer items-center rounded-lg border bg-background px-3 text-sm font-medium uppercase hover:bg-muted/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    >
                      <Download className="mr-2 h-4 w-4" aria-hidden="true" />
                      {format}
                    </button>
                  ))}
                  {(['json', 'md', 'html'] as const).map((format) => (
                    <button
                      key={format}
                      type="button"
                      onClick={() => download(pipelineApi.getReportExportUrl(runId, format))}
                      className="result-interactive inline-flex min-h-11 cursor-pointer items-center rounded-lg border bg-background px-3 text-sm font-medium uppercase hover:bg-muted/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    >
                      <FileText className="mr-2 h-4 w-4" aria-hidden="true" />
                      Report {format}
                    </button>
                  ))}
                </div>
              </details>

              <button
                type="button"
                onClick={onStartOver}
                className="result-interactive inline-flex min-h-11 w-full cursor-pointer items-center justify-center rounded-lg border bg-background/80 px-4 text-sm font-medium shadow-sm hover:bg-muted/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 sm:w-auto"
              >
                <RotateCcw className="mr-2 h-4 w-4" aria-hidden="true" />
                New file
              </button>
            </div>
          </div>

          <dl className="result-stagger relative mt-6 grid grid-cols-2 gap-3 border-t pt-5 sm:grid-cols-4">
            {[
              ['Input rows', report.summary?.input_rows],
              ['Output rows', report.summary?.output_rows],
              ['Preview changes', changedCellCount],
              ['Latest version', latestVersion == null ? undefined : `v${latestVersion}`],
            ].map(([label, value]) => (
              <div key={String(label)} className="min-w-0 rounded-xl border bg-background/70 px-3 py-3 shadow-sm">
                <dt className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">{label}</dt>
                <dd className="mt-1.5 truncate text-lg font-semibold tabular-nums">
                  {typeof value === 'number' ? formatNumber(value) : value || '—'}
                </dd>
              </div>
            ))}
          </dl>
        </header>

        <section className="result-surface-enter overflow-hidden rounded-2xl border bg-card/95 shadow-sm [animation-delay:70ms]">
          <nav
            className="grid grid-cols-1 gap-1 border-b bg-muted/20 p-2 sm:grid-cols-3"
            role="tablist"
            aria-label="Result sections"
          >
            {RESULT_TABS.map((tab, index) => {
              const selected = activeTab === tab.id;
              const Icon = tab.icon;
              return (
                <button
                  key={tab.id}
                  id={`result-tab-${tab.id}`}
                  type="button"
                  role="tab"
                  aria-selected={selected}
                  aria-controls={`result-panel-${tab.id}`}
                  tabIndex={selected ? 0 : -1}
                  onClick={() => setActiveTab(tab.id)}
                  onKeyDown={(event) => handleTabKeyDown(event, index)}
                  className={`result-interactive inline-flex min-h-11 cursor-pointer items-center justify-center gap-2 rounded-lg border px-4 text-sm font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring ${
                    selected
                      ? 'border-border bg-background text-foreground shadow-sm'
                      : 'border-transparent text-muted-foreground hover:bg-background/60 hover:text-foreground'
                  }`}
                >
                  <Icon className={`h-4 w-4 transition-colors duration-200 motion-reduce:transition-none ${selected ? 'text-primary' : ''}`} aria-hidden={true} />
                  {tab.label}
                </button>
              );
            })}
          </nav>

          {activeTab === 'summary' && (
            <div
              id="result-panel-summary"
              role="tabpanel"
              aria-labelledby="result-tab-summary"
              className="result-panel-enter space-y-6 p-4 outline-none sm:p-6"
            >
              <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1.4fr)_minmax(18rem,0.6fr)]">
                <section>
                  <h2 className="text-lg font-semibold">What changed</h2>
                  <p className="mt-1 text-sm text-muted-foreground">
                    The main transformations applied to this dataset.
                  </p>
                  {visibleTransformations.length > 0 ? (
                    <ul className="mt-4 space-y-3">
                      {visibleTransformations.map((transformation, index) => (
                        <li key={`${transformation}-${index}`} className="flex gap-3 rounded-xl border bg-background/60 p-3 text-sm leading-relaxed transition-colors duration-200 hover:border-primary/20 hover:bg-primary/[0.025] motion-reduce:transition-none">
                          <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-emerald-100 text-emerald-700 dark:bg-emerald-950/60 dark:text-emerald-300">
                            <CheckCircle2 className="h-3.5 w-3.5" aria-hidden="true" />
                          </span>
                          <span>{transformation}</span>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="mt-4 rounded-lg border border-dashed p-4 text-sm text-muted-foreground">
                      No transformation summary was recorded.
                    </p>
                  )}
                  {remainingTransformations.length > 0 && (
                    <details className="group mt-3">
                      <summary className="inline-flex min-h-11 cursor-pointer list-none items-center text-sm font-medium text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
                        Show {remainingTransformations.length} more
                        <ChevronDown className="ml-2 h-4 w-4 transition-transform duration-200 group-open:rotate-180 motion-reduce:transition-none" aria-hidden="true" />
                      </summary>
                      <ul className="space-y-2 border-l pl-4 text-sm text-muted-foreground">
                        {remainingTransformations.map((transformation, index) => (
                          <li key={`${transformation}-${index}`}>{transformation}</li>
                        ))}
                      </ul>
                    </details>
                  )}
                </section>

                <section className="relative overflow-hidden rounded-xl border border-primary/15 bg-gradient-to-br from-primary/[0.07] via-background to-background p-4">
                  <div className="pointer-events-none absolute -right-10 -top-12 h-28 w-28 rounded-full bg-primary/10 blur-2xl" aria-hidden="true" />
                  <div className="flex items-center gap-2">
                    <ShieldCheck className="h-4 w-4 text-primary" aria-hidden="true" />
                    <h2 className="text-sm font-semibold">Quality at a glance</h2>
                  </div>
                  <dl className="relative mt-4 space-y-3 text-sm">
                    {[
                      ['Validation', validationPassed ? 'Passed' : 'Review needed'],
                      ['Missing values detected', formatNumber(report.profile_summary?.missing_values_detected)],
                      ['Duplicate rows detected', formatNumber(report.profile_summary?.duplicate_rows)],
                      ['Tracked columns', formatNumber(report.summary?.tracked_columns)],
                    ].map(([label, value]) => (
                      <div key={String(label)} className="flex items-start justify-between gap-4 border-b border-border/70 pb-3 last:border-0 last:pb-0">
                        <dt className="text-muted-foreground">{label}</dt>
                        <dd className="text-right font-medium">{value}</dd>
                      </div>
                    ))}
                  </dl>
                </section>
              </div>

              {f1Metrics && <BenchmarkMetricsVisualization metrics={f1Metrics} />}

              <details className="group overflow-hidden rounded-xl border bg-background/50">
                <summary className="flex min-h-12 cursor-pointer list-none items-center justify-between gap-3 px-4 text-sm font-medium transition-colors duration-200 hover:bg-muted/30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring motion-reduce:transition-none">
                  Technical details
                  <ChevronDown className="h-4 w-4 transition-transform duration-200 group-open:rotate-180 motion-reduce:transition-none" aria-hidden="true" />
                </summary>
                <div className="result-details-enter space-y-5 border-t p-4">
                  <p className="max-w-4xl text-sm leading-relaxed text-muted-foreground">
                    {report.semantic_summary?.table_summary || 'No semantic table summary was recorded.'}
                  </p>

                  <dl className="grid grid-cols-2 gap-4 sm:grid-cols-4">
                    {[
                      ['Active tasks', report.execution_plan_summary?.active_task_count],
                      ['Skipped tasks', report.execution_plan_summary?.skipped_task_count],
                      ['Worker outputs', Object.keys(report.worker_results || {}).length],
                      ['LLM tokens', report.metrics?.token_metrics?.total_tokens ?? report.summary?.total_tokens_used],
                    ].map(([label, value]) => (
                      <div key={String(label)}>
                        <dt className="text-xs text-muted-foreground">{label}</dt>
                        <dd className="mt-1 font-semibold tabular-nums">
                          {typeof value === 'number' ? formatNumber(value) : '—'}
                        </dd>
                      </div>
                    ))}
                  </dl>

                  <details className="group">
                    <summary className="inline-flex min-h-11 cursor-pointer list-none items-center text-sm font-medium text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
                      <FileJson className="mr-2 h-4 w-4" aria-hidden="true" />
                      Raw report JSON
                      <ChevronDown className="ml-2 h-4 w-4 transition-transform duration-200 group-open:rotate-180 motion-reduce:transition-none" aria-hidden="true" />
                    </summary>
                    <pre className="mt-2 max-h-[28rem] overflow-auto whitespace-pre-wrap break-words rounded-lg border border-slate-800 bg-slate-950 p-4 text-xs leading-relaxed text-slate-300">
                      {JSON.stringify(report, null, 2)}
                    </pre>
                  </details>
                </div>
              </details>
            </div>
          )}

          {activeTab === 'lineage' && (
            <div
              id="result-panel-lineage"
              role="tabpanel"
              aria-labelledby="result-tab-lineage"
              className="result-panel-enter space-y-5 p-4 outline-none sm:p-6"
            >
              <div>
                <h2 className="text-lg font-semibold">Dataset versions</h2>
                <p className="mt-1 text-sm text-muted-foreground">
                  Each saved version shows which agent produced it and what changed.
                </p>
              </div>

              {lineageVersions.length > 0 ? (
                <ol className="space-y-3">
                  {lineageVersions.map((version) => {
                    const isLatest = String(version.version) === String(latestVersion);
                    return (
                      <li
                        key={String(version.version)}
                        className={`rounded-xl border p-4 transition-[border-color,box-shadow,transform] duration-200 motion-reduce:transition-none ${
                          isLatest
                            ? 'border-primary/25 bg-primary/[0.035] shadow-sm'
                            : 'bg-background/60 hover:-translate-y-0.5 hover:border-primary/20 hover:shadow-sm motion-reduce:hover:translate-y-0'
                        }`}
                      >
                        <div className="flex flex-col gap-3 sm:flex-row sm:items-start">
                          <div className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-full border font-semibold ${
                            isLatest ? 'border-primary/25 bg-primary/10 text-primary' : 'bg-muted/20'
                          }`}>
                            v{version.version}
                          </div>
                          <div className="min-w-0 flex-1">
                            <div className="flex flex-wrap items-center gap-2">
                              <h3 className="font-medium">{version.agent_name || 'Unknown agent'}</h3>
                              {isLatest && (
                                <span className="rounded-full border border-primary/20 bg-primary/[0.07] px-2 py-0.5 text-xs font-medium text-primary">
                                  Latest
                                </span>
                              )}
                            </div>
                            <p className="mt-1 text-sm leading-relaxed text-muted-foreground">
                              {version.description || 'No version description was recorded.'}
                            </p>
                            {version.created_at && (
                              <p className="mt-2 text-xs text-muted-foreground">{formatDate(version.created_at)}</p>
                            )}
                          </div>
                          <details className="group shrink-0">
                            <summary className="result-interactive inline-flex min-h-11 cursor-pointer list-none items-center rounded-lg border bg-background px-3 text-sm font-medium shadow-sm hover:bg-muted/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
                              <Download className="mr-2 h-4 w-4" aria-hidden="true" />
                              Download
                              <ChevronDown className="ml-2 h-4 w-4 transition-transform duration-200 group-open:rotate-180 motion-reduce:transition-none" aria-hidden="true" />
                            </summary>
                            <div className="result-menu-enter mt-2 flex flex-wrap gap-2 sm:justify-end">
                              {(['csv', 'xlsx', 'parquet'] as const).map((format) => (
                                <button
                                  key={format}
                                  type="button"
                                  onClick={() => download(pipelineApi.getVersionDownloadUrl(runId, Number(version.version), format))}
                                  className="result-interactive inline-flex min-h-11 cursor-pointer items-center rounded-lg border bg-background px-3 text-xs font-medium uppercase hover:bg-muted/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                                >
                                  {format}
                                </button>
                              ))}
                            </div>
                          </details>
                        </div>
                      </li>
                    );
                  })}
                </ol>
              ) : (
                <div className="rounded-xl border border-dashed p-5 text-sm text-muted-foreground">
                  No persisted lineage versions are available for this run.
                </div>
              )}

              <div className="border-t pt-5">
                <button
                  type="button"
                  aria-expanded={showDiagram}
                  onClick={() => setShowDiagram((current) => !current)}
                  className="result-interactive inline-flex min-h-11 cursor-pointer items-center rounded-lg border bg-background px-4 text-sm font-medium shadow-sm hover:bg-muted/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  <GitBranch className="mr-2 h-4 w-4" aria-hidden="true" />
                  {showDiagram ? 'Hide lineage diagram' : 'Show lineage diagram'}
                </button>
                {showDiagram && (
                  <div className="result-details-enter mt-4">
                    {isDiagramLoading ? (
                      <div className="rounded-xl border p-5 text-sm text-muted-foreground">
                        Loading lineage diagram…
                      </div>
                    ) : diagramError ? (
                      <div className="rounded-xl border border-destructive/30 bg-destructive/5 p-5 text-sm text-destructive">
                        The lineage diagram could not be loaded.
                      </div>
                    ) : (
                      <MermaidDiagram definition={lineageDiagram?.diagram || ''} />
                    )}
                  </div>
                )}
              </div>
            </div>
          )}

          {activeTab === 'compare' && (
            <div
              id="result-panel-compare"
              role="tabpanel"
              aria-labelledby="result-tab-compare"
              className="result-panel-enter p-4 outline-none sm:p-6"
            >
              {compareError ? (
                <div
                  className="flex flex-col gap-4 rounded-xl border border-destructive/30 bg-destructive/5 p-5 sm:flex-row sm:items-center sm:justify-between"
                  role="alert"
                >
                  <div>
                    <h2 className="text-sm font-semibold text-destructive">
                      The before-and-after preview could not be loaded
                    </h2>
                    <p className="mt-1 text-sm text-muted-foreground">
                      The comparison endpoint returned an error. Retry after the backend has restarted.
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => void refetchCompare()}
                    className="result-interactive inline-flex min-h-11 shrink-0 cursor-pointer items-center justify-center rounded-lg border bg-background px-4 text-sm font-medium shadow-sm hover:bg-muted/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  >
                    <RotateCcw className="mr-2 h-4 w-4" aria-hidden="true" />
                    Retry comparison
                  </button>
                </div>
              ) : isCompareLoading ? (
                <div className="space-y-3" aria-busy="true" aria-live="polite">
                  <span className="sr-only">Loading the before-and-after preview</span>
                  <div className="h-16 animate-pulse rounded-xl bg-muted/50 motion-reduce:animate-none" />
                  <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
                    <div className="h-72 animate-pulse rounded-xl bg-muted/40 motion-reduce:animate-none" />
                    <div className="h-72 animate-pulse rounded-xl bg-muted/40 motion-reduce:animate-none" />
                  </div>
                </div>
              ) : (
                <DatasetComparePreview comparePreview={comparePreview} />
              )}
            </div>
          )}
        </section>
      </main>

      <ReportChatPanel runId={runId} />
    </div>
  );
};

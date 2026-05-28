import React, { useMemo, useState } from 'react';
import { ChevronDown, ChevronUp, FileText, ListChecks, AlertTriangle } from 'lucide-react';

export interface RequirementSummaryProps {
  userRequirementsText?: string;
  spec?: Record<string, any> | null;
  validation?: Record<string, any> | null;
  compact?: boolean;
}

const CASE_LABELS: Record<string, string> = {
  upper: 'UPPERCASE',
  lower: 'lowercase',
  title: 'Title Case',
  none: 'unchanged',
};

function formatImputation(imp: any): string {
  if (!imp) return '—';
  const s = imp.strategy || '—';
  if (s === 'constant' && imp.fill_value != null) {
    return `constant (${String(imp.fill_value)})`;
  }
  return s;
}

export const RequirementSummaryPanel: React.FC<RequirementSummaryProps> = ({
  userRequirementsText,
  spec,
  validation,
  compact = false,
}) => {
  const [showRaw, setShowRaw] = useState(false);

  const summary = useMemo(() => {
    if (!spec) return null;

    const mappings = spec.columns_mapping || [];
    const rules = spec.column_rules || [];
    const dedup = spec.deduplication;
    const columnsToDrop = spec.columns_to_drop || [];
    const touchedColumns = new Set([
      ...mappings.map((m: any) => m.original_name),
      ...rules.map((r: any) => r.column_name),
      ...columnsToDrop,
    ]);

    return {
      datasetName: spec.dataset_name,
      specVersion: spec.spec_version,
      mappingCount: mappings.length,
      ruleCount: rules.length,
      dropCount: columnsToDrop.length,
      columnsToDrop,
      touchedCount: touchedColumns.size,
      dedupLabel: dedup
        ? `Yes — keep ${dedup.keep_strategy || 'first'}${
            dedup.subset_columns?.length
              ? ` on [${dedup.subset_columns.join(', ')}]`
              : ' (full row)'
          }`
        : 'No deduplication in spec',
      openQuestions: spec.open_questions || [],
      conflicts: spec.conflicts_detected_by_parser || [],
      mappings,
      rules,
    };
  }, [spec]);

  if (!spec && !userRequirementsText) {
    return (
      <div className="rounded-xl border border-dashed bg-muted/20 p-4 text-sm text-muted-foreground">
        Requirement summary will appear after the Input Validator runs.
      </div>
    );
  }

  const blocking = validation?.blocking;
  const isValid = validation?.is_valid;

  return (
    <div className="rounded-xl border bg-white shadow-sm overflow-hidden">
      <div className="px-5 py-4 border-b bg-gradient-to-r from-slate-50 to-indigo-50/40 flex items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          <div className="w-9 h-9 rounded-lg bg-indigo-100 flex items-center justify-center shrink-0">
            <ListChecks className="w-5 h-5 text-indigo-700" />
          </div>
          <div>
            <h3 className="text-base font-semibold text-foreground">LLM Requirement Summary</h3>
            <p className="text-xs text-muted-foreground mt-0.5">
              Structured interpretation (StructuredCleaningSpec) — what the system will plan against
            </p>
          </div>
        </div>
        {validation && (
          <span
            className={`text-[10px] font-bold uppercase px-2 py-1 rounded-full shrink-0 ${
              blocking
                ? 'bg-amber-100 text-amber-800'
                : isValid
                  ? 'bg-emerald-100 text-emerald-800'
                  : 'bg-red-100 text-red-800'
            }`}
          >
            {blocking ? 'Needs review' : isValid ? 'Valid' : 'Invalid'}
          </span>
        )}
      </div>

      <div className={`p-5 space-y-5 ${compact ? 'text-sm' : ''}`}>
        {userRequirementsText?.trim() && (
          <section>
            <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-2">
              <FileText className="w-3.5 h-3.5" />
              Your original text
            </div>
            <p className="text-sm text-foreground whitespace-pre-wrap rounded-lg bg-muted/40 border p-3 leading-relaxed">
              {userRequirementsText.trim()}
            </p>
          </section>
        )}

        {summary && (
          <>
            <section className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              <Stat label="Columns mapped" value={String(summary.mappingCount)} />
              <Stat label="Column rules" value={String(summary.ruleCount)} />
              <Stat label="Columns touched" value={String(summary.touchedCount)} />
              <Stat
                label="Parser questions"
                value={String(summary.openQuestions.length)}
              />
            </section>

            <section className="text-sm space-y-1">
              <Row label="Dataset" value={summary.datasetName} mono />
              <Row label="Spec version" value={summary.specVersion} mono />
              <Row label="Deduplication" value={summary.dedupLabel} />
              {summary.dropCount > 0 && (
                <Row
                  label="Columns to drop"
                  value={summary.columnsToDrop.join(', ')}
                  mono
                />
              )}
            </section>

            {summary.conflicts.length > 0 && (
              <section className="rounded-lg bg-amber-50 border border-amber-200 p-3">
                <div className="flex items-center gap-2 text-amber-900 text-sm font-semibold mb-2">
                  <AlertTriangle className="w-4 h-4" />
                  Parser detected conflicts
                </div>
                <ul className="list-disc pl-5 text-sm text-amber-950 space-y-1">
                  {summary.conflicts.map((c: string, i: number) => (
                    <li key={i}>{c}</li>
                  ))}
                </ul>
              </section>
            )}

            {summary.openQuestions.length > 0 && (
              <section>
                <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-2">
                  LLM still unsure about
                </h4>
                <ul className="list-disc pl-5 text-sm space-y-1">
                  {summary.openQuestions.map((q: string, i: number) => (
                    <li key={i}>{q}</li>
                  ))}
                </ul>
              </section>
            )}

            {summary.mappings.length > 0 && (
              <section>
                <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-2">
                  Column mapping (physical → target)
                </h4>
                <div className="border rounded-lg overflow-hidden max-h-48 overflow-y-auto">
                  <table className="w-full text-xs">
                    <thead className="bg-muted/50 sticky top-0">
                      <tr>
                        <th className="text-left p-2 font-semibold">Original</th>
                        <th className="text-left p-2 font-semibold">Target</th>
                        <th className="text-left p-2 font-semibold">Type</th>
                        <th className="text-left p-2 font-semibold">Nullable</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y">
                      {summary.mappings.map((m: any, i: number) => (
                        <tr key={i} className="hover:bg-muted/30">
                          <td className="p-2 font-mono">{m.original_name}</td>
                          <td className="p-2 font-mono text-indigo-700">{m.target_name}</td>
                          <td className="p-2">{m.target_type}</td>
                          <td className="p-2">{m.nullable ? 'yes' : 'no'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>
            )}

            {summary.rules.length > 0 && (
              <section>
                <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-2">
                  Per-column cleaning rules
                </h4>
                <div className="border rounded-lg overflow-hidden max-h-56 overflow-y-auto">
                  <table className="w-full text-xs">
                    <thead className="bg-muted/50 sticky top-0">
                      <tr>
                        <th className="text-left p-2 font-semibold">Column</th>
                        <th className="text-left p-2 font-semibold">Whitespace</th>
                        <th className="text-left p-2 font-semibold">Case</th>
                        <th className="text-left p-2 font-semibold">Imputation</th>
                        <th className="text-left p-2 font-semibold">Outliers</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y">
                      {summary.rules.map((r: any, i: number) => (
                        <tr key={i} className="hover:bg-muted/30">
                          <td className="p-2 font-mono font-medium">{r.column_name}</td>
                          <td className="p-2">{r.strip_whitespace ? 'trim' : '—'}</td>
                          <td className="p-2">{CASE_LABELS[r.case_transformation] || r.case_transformation}</td>
                          <td className="p-2">{formatImputation(r.imputation)}</td>
                          <td className="p-2">
                            {r.outliers?.method && r.outliers.method !== 'none'
                              ? `${r.outliers.method} → ${r.outliers.action}`
                              : '—'}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>
            )}

            {summary.mappingCount > 0 && summary.ruleCount === 0 && (
              <p className="text-xs text-amber-700 bg-amber-50 border border-amber-100 rounded-lg p-3">
                LLM mapped columns but did not attach explicit column rules — planner may infer actions
                from your original text only.
              </p>
            )}
          </>
        )}

        <button
          type="button"
          onClick={() => setShowRaw(!showRaw)}
          className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground"
        >
          {showRaw ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
          {showRaw ? 'Hide' : 'Show'} raw StructuredCleaningSpec JSON
        </button>
        {showRaw && spec && (
          <pre className="bg-slate-950 text-slate-300 rounded-lg p-4 text-[11px] overflow-auto max-h-64">
            {JSON.stringify(spec, null, 2)}
          </pre>
        )}
      </div>
    </div>
  );
};

const Stat: React.FC<{ label: string; value: string }> = ({ label, value }) => (
  <div className="rounded-lg border bg-muted/20 p-3 text-center">
    <div className="text-lg font-bold text-foreground">{value}</div>
    <div className="text-[10px] uppercase tracking-wide text-muted-foreground mt-1">{label}</div>
  </div>
);

const Row: React.FC<{ label: string; value: string; mono?: boolean }> = ({
  label,
  value,
  mono,
}) => (
  <div className="flex gap-2">
    <span className="text-muted-foreground min-w-[7rem]">{label}:</span>
    <span className={mono ? 'font-mono text-foreground' : 'text-foreground'}>{value}</span>
  </div>
);

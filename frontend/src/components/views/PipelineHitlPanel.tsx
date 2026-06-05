import React, { useState, useMemo, useEffect } from 'react';
import { RequirementSummaryPanel } from './RequirementSummaryPanel';
import {
  AlertCircle,
  Loader2,
  CheckCircle2,
  XCircle,
  Columns3,
  Layers,
  Zap,
  Shield,
  MessageSquare,
  ChevronDown,
  ChevronUp,
} from 'lucide-react';

/* ── Helpers ────────────────────────────────────────────────────────────── */

const ROLE_META: Record<string, { label: string; color: string; icon: React.ReactNode }> = {
  duplicate_handler: { label: 'Deduplication', color: 'bg-violet-500/10 text-violet-600 border-violet-200', icon: <Layers className="w-4 h-4" /> },
  null_type_handler: { label: 'Null & Type Fix', color: 'bg-sky-500/10 text-sky-600 border-sky-200', icon: <Zap className="w-4 h-4" /> },
  validator: { label: 'Validation', color: 'bg-emerald-500/10 text-emerald-600 border-emerald-200', icon: <Shield className="w-4 h-4" /> },
  planner: { label: 'Planner', color: 'bg-amber-500/10 text-amber-600 border-amber-200', icon: <Columns3 className="w-4 h-4" /> },
};

export function roleMeta(role: string) {
  return ROLE_META[role] ?? { label: role, color: 'bg-gray-100 text-gray-600 border-gray-200', icon: <Zap className="w-4 h-4" /> };
}

function getOptionConsequence(consequences: any, optionText: string): string | null {
  if (!consequences) return null;

  // Case 1: consequences is a dictionary
  if (typeof consequences === 'object' && !Array.isArray(consequences)) {
    // Exact match
    if (consequences[optionText]) {
      return consequences[optionText];
    }
    // Case-insensitive key check
    const lowerOpt = optionText.toLowerCase();
    for (const key of Object.keys(consequences)) {
      if (key.toLowerCase() === lowerOpt) {
        return consequences[key];
      }
      // Substring check (e.g. if key is "Option A" and optionText contains "Option A" or vice versa)
      if (lowerOpt.includes(key.toLowerCase()) || key.toLowerCase().includes(lowerOpt)) {
        return consequences[key];
      }
    }
  }

  // Case 2: consequences is a string
  if (typeof consequences === 'string') {
    const lines = consequences.split('\n');
    const cleanOpt = optionText.replace(/^\([^)]+\)\s*/, '').toLowerCase().trim(); // strip (Recommended) etc
    
    for (const line of lines) {
      if (line.toLowerCase().includes(cleanOpt) || cleanOpt.includes(line.toLowerCase())) {
        return line.trim();
      }
    }
    return consequences;
  }

  return null;
}

const ERROR_TYPE_LABELS: Record<string, string> = {
  duplicate: 'Duplicate rows',
  null: 'Null values',
  type_cast: 'Type casting',
  format: 'Format issues',
};

/* ── Task Card ──────────────────────────────────────────────────────────── */

export const TaskCard: React.FC<{ task: any; index: number; phase: string }> = ({ task, index: _index, phase }) => {
  const meta = roleMeta(task.agent_role);
  return (
    <div className="group rounded-lg border bg-card p-4 hover:shadow-md transition-all duration-200">
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium ${meta.color}`}>
            {meta.icon}
            {meta.label}
          </span>
          <span className="text-xs text-muted-foreground font-mono">{task.task_id}</span>
        </div>
        <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/60">{phase}</span>
      </div>

      {task.error_type && (
        <div className="text-sm text-muted-foreground mb-2">
          <span className="font-medium text-foreground">Fixes:</span>{' '}
          {ERROR_TYPE_LABELS[task.error_type] ?? task.error_type}
        </div>
      )}

      {task.target_columns?.length > 0 && (
        <div className="mb-2">
          <div className="text-xs font-medium text-muted-foreground mb-1">Target columns</div>
          <div className="flex flex-wrap gap-1.5">
            {task.target_columns.map((col: string) => (
              <span key={col} className="inline-block rounded bg-primary/8 border border-primary/15 px-2 py-0.5 text-xs font-mono text-primary">
                {col}
              </span>
            ))}
          </div>
        </div>
      )}

      {task.instructions && (
        <details className="mt-2 text-xs">
          <summary className="cursor-pointer text-muted-foreground hover:text-foreground transition-colors select-none">
            View instructions
          </summary>
          <pre className="mt-1.5 whitespace-pre-wrap bg-muted/50 rounded p-2 text-[11px] leading-relaxed max-h-40 overflow-auto">
            {typeof task.instructions === 'string' ? task.instructions : JSON.stringify(task.instructions, null, 2)}
          </pre>
        </details>
      )}
    </div>
  );
};

/* ── HITL Checkpoint Panel ──────────────────────────────────────────────── */

const SEVERITY_STYLES: Record<string, string> = {
  error: 'bg-red-100 text-red-700 border-red-200',
  warning: 'bg-amber-100 text-amber-700 border-amber-200',
  info: 'bg-blue-100 text-blue-700 border-blue-200',
};

/* ── Input Validation Clarification Content Component ─────────────────── */

export const InputValidationClarificationContent: React.FC<{
  payload: any;
  isAwaiting: boolean;
  onDecision: (
    d: 'approve' | 'reject' | 'modify',
    fb?: string,
    disambiguationAnswers?: Record<string, string | string[]>
  ) => void;
  isPending: boolean;
  runId: string;
}> = ({ payload, isAwaiting, onDecision, isPending, runId }) => {
  const clarifications = payload.clarifications || {};
  const categories = ['null', 'duplicate', 'typecast'] as const;

  // Initialize answers from localStorage if present
  const [answers, setAnswers] = useState<Record<string, string>>(() => {
    const saved = localStorage.getItem(`hitl_answers_${runId}`);
    if (saved) {
      try {
        const parsed = JSON.parse(saved);
        return parsed.answers || {};
      } catch (e) {
        return {};
      }
    }
    return {};
  });

  const handleSelectAnswer = (key: string, val: string) => {
    setAnswers((prev) => ({ ...prev, [key]: val }));
  };

  // Check if all questions are answered
  const totalQuestions = useMemo(() => {
    let count = 0;
    categories.forEach((cat) => {
      const catData = clarifications[cat];
      if (catData) {
        count += Object.keys(catData).length;
      }
    });
    return count;
  }, [clarifications]);

  const answeredCount = useMemo(() => {
    let count = 0;
    categories.forEach((cat) => {
      const catData = clarifications[cat];
      if (catData) {
        Object.keys(catData).forEach((qKey) => {
          if (answers[`${cat}.${qKey}`]) {
            count += 1;
          }
        });
      }
    });
    return count;
  }, [clarifications, answers]);

  const allAnswered = answeredCount === totalQuestions;

  const handleSubmit = () => {
    // Save full questions + answers under run ID
    const fullLog = {
      runId,
      submittedAt: new Date().toISOString(),
      questions: clarifications,
      answers: answers,
    };
    localStorage.setItem(`hitl_answers_${runId}`, JSON.stringify(fullLog));
    localStorage.setItem(`hitl_submitted_${runId}`, 'true');

    // Notify parent view to mutate/decision
    onDecision('approve', 'User resolved all clarifications', answers);
  };

  return (
    <div className="space-y-6">
      {/* Reasoning summary from agent */}
      {payload.reasoning && (
        <div className="rounded-xl border bg-muted/30 p-4 text-sm leading-relaxed text-muted-foreground">
          <strong className="text-foreground block mb-1">Reasoning:</strong>
          {payload.reasoning}
        </div>
      )}

      {/* Questions list */}
      <div className="space-y-6">
        {categories.map((cat) => {
          const catData = clarifications[cat];
          if (!catData || Object.keys(catData).length === 0) return null;

          const title = cat === 'null' ? 'Null Value Resolutions' : cat === 'duplicate' ? 'Duplicate Row Resolutions' : 'Type Casting Resolutions';
          const badgeColor = cat === 'null' ? 'bg-sky-50 text-sky-700 border-sky-200' : cat === 'duplicate' ? 'bg-violet-50 text-violet-700 border-violet-200' : 'bg-amber-50 text-amber-700 border-amber-200';

          return (
            <div key={cat} className="rounded-xl border bg-card/60 backdrop-blur-md shadow-sm overflow-hidden text-left">
              <div className={`px-4 py-3 border-b flex items-center justify-between bg-muted/20`}>
                <h4 className="text-sm font-semibold flex items-center gap-2">
                  <span className={`px-2 py-0.5 rounded text-xs border ${badgeColor}`}>
                    {cat.toUpperCase()}
                  </span>
                  {title}
                </h4>
              </div>
              <div className="p-4 space-y-6 divide-y divide-border/40">
                {Object.keys(catData).sort().map((qKey, qi) => {
                  const q = catData[qKey];
                  const key = `${cat}.${qKey}`;
                  const selectedVal = answers[key] || '';
                  const isStrategy = 'options' in q;

                  return (
                    <div key={qKey} className={`pt-4 ${qi === 0 ? 'pt-0' : ''} text-left`}>
                      <p className="text-sm font-medium text-foreground mb-3 leading-snug">
                        {qi + 1}. {q.question}
                      </p>

                      {isStrategy ? (
                        /* Strategy MCQ */
                        <div className="space-y-3">
                          <div className="space-y-3 pl-2">
                            {(q.options || []).map((opt: string) => {
                              const isSelected = selectedVal === opt;
                              const optConsequence = getOptionConsequence(q.consequences, opt);
                              return (
                                <div key={opt} className="space-y-2">
                                  <label
                                    className={`flex items-start gap-2.5 text-sm cursor-pointer rounded-lg px-3 py-2.5 border transition-all ${
                                      isSelected
                                        ? 'bg-primary/5 border-primary/40 shadow-sm'
                                        : 'bg-transparent border-border/60 hover:bg-muted/30'
                                    }`}
                                  >
                                    <input
                                      type="radio"
                                      name={key}
                                      value={opt}
                                      checked={isSelected}
                                      onChange={() => handleSelectAnswer(key, opt)}
                                      disabled={!isAwaiting}
                                      className="text-primary mt-0.5 shrink-0"
                                    />
                                    <span className="leading-snug">{opt}</span>
                                  </label>
                                  {isSelected && optConsequence && (
                                    <div className="ml-6 p-3 rounded-lg bg-indigo-50/40 border border-indigo-100/50 text-xs text-indigo-950/90 leading-relaxed flex items-start gap-2 animate-fadeIn">
                                      <AlertCircle className="w-4 h-4 text-indigo-500 shrink-0 mt-0.5" />
                                      <div>
                                        <strong className="font-semibold text-indigo-900 block mb-0.5">Consequence:</strong>
                                        {optConsequence}
                                      </div>
                                    </div>
                                  )}
                                </div>
                              );
                            })}
                          </div>
                        </div>
                      ) : (
                        /* Insight YES/NO */
                        <div className="space-y-3">
                          {q.insight && (
                            <div className="text-xs bg-muted/40 p-2.5 rounded border border-border/40 text-muted-foreground italic mb-2 leading-relaxed">
                              💡 {q.insight}
                            </div>
                          )}
                          <div className="flex gap-4 pl-2">
                            {['Yes', 'No'].map((opt) => (
                              <label
                                key={opt}
                                className={`flex items-center gap-2 text-sm cursor-pointer rounded-lg px-4 py-2 border transition-all ${
                                  selectedVal === opt
                                    ? 'bg-primary/5 border-primary/40 shadow-sm'
                                    : 'bg-transparent border-border/60 hover:bg-muted/30'
                                }`}
                              >
                                <input
                                  type="radio"
                                  name={key}
                                  value={opt}
                                  checked={selectedVal === opt}
                                  onChange={() => handleSelectAnswer(key, opt)}
                                  disabled={!isAwaiting}
                                  className="text-primary"
                                />
                                {opt}
                              </label>
                            ))}
                          </div>
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

      {/* Progress & Submission */}
      {isAwaiting && (
        <div className="sticky bottom-0 z-[5] -mx-6 px-6 py-4 bg-gradient-to-t from-background via-background to-background/90 border-t flex flex-col sm:flex-row items-center gap-4 justify-between">
          <div className="text-xs text-muted-foreground font-medium">
            Answered {answeredCount} of {totalQuestions} questions
          </div>
          <button
            type="button"
            onClick={handleSubmit}
            disabled={isPending || !allAnswered}
            className="w-full sm:w-auto inline-flex items-center justify-center gap-2 bg-gradient-to-r from-emerald-500 to-emerald-600 hover:from-emerald-600 hover:to-emerald-700 text-white px-6 py-2.5 rounded-lg text-sm font-semibold transition-all shadow-sm shadow-emerald-500/10 hover:shadow-md disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Confirm Answers
          </button>
        </div>
      )}
    </div>
  );
};

export const HITLCheckpointPanel: React.FC<{
  checkpoint: any;
  userRequirementsText?: string;
  feedback: string;
  onFeedbackChange: (v: string) => void;
  onDecision: (
    d: 'approve' | 'reject' | 'modify',
    fb?: string,
    disambiguationAnswers?: Record<string, string | string[]>
  ) => void;
  isPending: boolean;
  isAwaiting: boolean;
}> = ({ checkpoint, userRequirementsText, feedback, onFeedbackChange, onDecision, isPending, isAwaiting }) => {
  const payload = checkpoint.payload || {};
  const isRequirementApproval = checkpoint.checkpoint_type === 'requirement_approval';
  const isPlanApproval = checkpoint.checkpoint_type === 'plan_approval';
  const isInputValidationClarification = checkpoint.checkpoint_type === 'input_validation_clarification';
  const modifyCount = isRequirementApproval
    ? (payload.requirement_modify_count ?? 0)
    : (payload.modify_count ?? 0);
  const maxModify = payload.max_modify_cycles as number | undefined;
  const canModify =
    isRequirementApproval ? true : maxModify == null || modifyCount < maxModify;

  const plan = payload.plan || {};
  const colSelection = payload.column_selection || {};
  const [showRawJson, setShowRawJson] = useState(false);
  const [mcqAnswers, setMcqAnswers] = useState<Record<string, string>>({});
  const [mcqClarifyText, setMcqClarifyText] = useState<Record<string, string>>({});

  useEffect(() => {
    setMcqAnswers({});
    setMcqClarifyText({});
  }, [checkpoint?.checkpoint_id]);

  const isClarifyValue = (value: string) =>
    value === 'clarify' || value.toLowerCase().startsWith('clarify:');

  const isClarifySelected = (questionId: string) => {
    const raw = mcqAnswers[questionId] || '';
    if (raw === 'clarify' || raw.toLowerCase().startsWith('clarify:')) return true;
    return raw.split(',').some((v) => isClarifyValue(v.trim()));
  };

  const hasColumnSelection = (questionId: string) => {
    const raw = mcqAnswers[questionId] || '';
    return raw
      .split(',')
      .map((v) => v.trim())
      .some((v) => v && !isClarifyValue(v));
  };

  const disambiguationQuestions: any[] =
    payload.disambiguation_questions ||
    payload.requirement_validation?.disambiguation_questions ||
    [];
  const comparisonNotes: any[] =
    payload.comparison_notes ||
    payload.requirement_validation?.comparison_notes ||
    [];

  const questionAllowsMultiple = (q: any) => {
    if (q?.allow_multiple === true) return true;
    if (q?.allow_multiple === false) return false;
    return ['column_select', 'imputation_target', 'column_drop', 'general'].includes(
      q?.category
    );
  };

  const requiredMcqIds = disambiguationQuestions
    .filter((q: any) => q.required !== false)
    .map((q: any) => q.question_id);
  const allMcqAnswered =
    requiredMcqIds.length === 0 ||
    requiredMcqIds.every((id: string) => {
      const q = disambiguationQuestions.find((x: any) => x.question_id === id);
      if (isClarifySelected(id)) {
        return Boolean(mcqClarifyText[id]?.trim());
      }
      if (questionAllowsMultiple(q)) {
        return hasColumnSelection(id);
      }
      return Boolean(mcqAnswers[id]?.trim());
    });

  const toggleMultiMcq = (questionId: string, value: string, checked: boolean) => {
    const isClarify = isClarifyValue(value);
    setMcqAnswers((prev) => {
      if (isClarify) {
        if (!checked) {
          setMcqClarifyText((t) => {
            const next = { ...t };
            delete next[questionId];
            return next;
          });
        }
        return { ...prev, [questionId]: checked ? value : '' };
      }
      const current = prev[questionId]
        ? prev[questionId].split(',').map((s) => s.trim()).filter(Boolean)
        : [];
      const withoutClarify = current.filter((v) => !isClarifyValue(v));
      const next = checked
        ? [...new Set([...withoutClarify, value])]
        : withoutClarify.filter((v) => v !== value);
      return { ...prev, [questionId]: next.join(',') };
    });
  };

  const buildMcqPayload = () => {
    const answers: Record<string, string | string[]> = {};
    const feedbackParts: string[] = [];

    for (const q of disambiguationQuestions) {
      const qid = q.question_id;
      const raw = mcqAnswers[qid] || '';
      const clarifyText = mcqClarifyText[qid]?.trim() || '';

      if (isClarifySelected(qid)) {
        const tokens: string[] = [];
        if (hasColumnSelection(qid)) {
          raw
            .split(',')
            .map((s) => s.trim())
            .filter((v) => v && !isClarifyValue(v))
            .forEach((v) => tokens.push(v));
        }
        if (clarifyText) {
          tokens.push(`clarify:${clarifyText}`);
          feedbackParts.push(`${q.prompt}\n${clarifyText}`);
        }
        if (tokens.length) {
          answers[qid] = tokens;
        }
        continue;
      }

      if (!raw.trim()) continue;

      if (questionAllowsMultiple(q)) {
        const parts = raw.includes(',')
          ? raw.split(',').map((s) => s.trim()).filter(Boolean)
          : [raw.trim()];
        answers[qid] = parts;
      } else {
        answers[qid] = raw;
      }
    }

    const feedback =
      feedbackParts.length > 0 ? feedbackParts.join('\n\n') : undefined;
    return {
      answers: Object.keys(answers).length ? answers : undefined,
      feedback,
    };
  };

  const submitWithMcq = (decision: 'approve' | 'reject' | 'modify', fb?: string) => {
    const { answers, feedback: clarifyFeedback } = buildMcqPayload();
    const mergedFeedback = [fb, clarifyFeedback].filter(Boolean).join('\n\n') || undefined;
    onDecision(decision, mergedFeedback, answers);
  };

  const allTasks = useMemo(() => {
    const tasks: { task: any; phase: string }[] = [];
    (plan.sequential_tasks || []).forEach((t: any) => tasks.push({ task: t, phase: 'Sequential' }));
    (plan.parallel_task_groups || []).forEach((group: any[], gi: number) =>
      group.forEach((t: any) => tasks.push({ task: t, phase: `Parallel #${gi + 1}` }))
    );
    return tasks;
  }, [plan]);

  // Safely extract from nested payload structures
  const issues: any[] = payload.issues || payload.validation_result?.issues || [];
  const metrics = payload.metrics || payload.validation_result?.metrics || {};
  const validationPassed = payload.validation_result?.passed;

  const spec = payload.structured_cleaning_spec || {};
  const reqErrors: string[] = payload.errors || payload.requirement_validation?.errors || [];
  const reqWarnings: string[] = payload.warnings || payload.requirement_validation?.warnings || [];
  const openQuestions: string[] = payload.open_questions || spec.open_questions || [];

  const requirementConfirmDisabled =
    isRequirementApproval && disambiguationQuestions.length > 0 && !allMcqAnswered;

  const headerConfig = isInputValidationClarification
    ? { title: 'Input Validator Clarifications', subtitle: 'Please answer the following clarification questions about your dataset', gradient: 'from-purple-500 to-indigo-500', border: 'border-purple-400/40', bg: 'from-purple-50/80 via-white to-indigo-50/40' }
    : isRequirementApproval
    ? { title: 'Confirm requirements', subtitle: 'Review the interpretation below, answer any prompts, then confirm or cancel', gradient: 'from-indigo-500 to-violet-500', border: 'border-indigo-400/40', bg: 'from-indigo-50/80 via-white to-violet-50/40' }
    : isPlanApproval
    ? { title: 'Plan Review Required', subtitle: 'The AI has generated a cleaning plan for your approval', gradient: 'from-amber-500 to-orange-500', border: 'border-amber-400/40', bg: 'from-amber-50/80 via-white to-orange-50/40' }
    : { title: 'Validation Review Required', subtitle: 'Persistent quality issues were found after processing', gradient: 'from-rose-500 to-pink-500', border: 'border-rose-400/40', bg: 'from-rose-50/80 via-white to-pink-50/40' };

  return (
    <div className={`mb-8 rounded-2xl border-2 ${headerConfig.border} bg-gradient-to-br ${headerConfig.bg} shadow-lg overflow-hidden`}>
      {/* Header */}
      <div className={`bg-gradient-to-r ${headerConfig.gradient} px-6 py-4`}>
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-full bg-white/20 backdrop-blur-sm flex items-center justify-center">
            <AlertCircle className="w-5 h-5 text-white" />
          </div>
          <div>
            <h3 className="text-lg font-bold text-white">{headerConfig.title}</h3>
            <p className="text-white/80 text-sm">{headerConfig.subtitle}</p>
          </div>
          {modifyCount > 0 && (
            <span className="ml-auto text-xs bg-white/20 text-white rounded-full px-2.5 py-1 font-medium">
              {isRequirementApproval
                ? `Clarifications: ${modifyCount}`
                : `Revision ${modifyCount}${maxModify != null ? `/${maxModify}` : ''}`}
            </span>
          )}
        </div>
      </div>

      <div className="p-6 space-y-6 relative">
        {isPending && (
          <div className="absolute inset-0 z-10 bg-white/80 backdrop-blur-[2px] flex flex-col items-center justify-center rounded-b-2xl">
            <Loader2 className="w-10 h-10 text-primary animate-spin mb-4" />
            <div className="text-base font-bold text-foreground">Processing your decision...</div>
            <div className="text-sm text-muted-foreground mt-1">Please wait while the agents resume...</div>
          </div>
        )}

        {/* ── Input Validation Clarification Content ───────────────────── */}
        {isInputValidationClarification && (
          <InputValidationClarificationContent
            payload={payload}
            isAwaiting={isAwaiting}
            onDecision={onDecision}
            isPending={isPending}
            runId={checkpoint.checkpoint_id}
          />
        )}

        {/* ── Requirement Approval Content ───────────────────────────── */}
        {isRequirementApproval && (
          <>
            <RequirementSummaryPanel
              userRequirementsText={userRequirementsText}
              spec={spec}
              validation={payload.requirement_validation}
              compact
            />

            {checkpoint.message_to_user && (
              <p className="text-sm text-muted-foreground whitespace-pre-line rounded-lg border bg-muted/30 p-3">
                {checkpoint.message_to_user}
              </p>
            )}

            {openQuestions.length > 0 && disambiguationQuestions.length === 0 && (
              <div className="rounded-xl bg-amber-50 border border-amber-200 p-4">
                <h4 className="text-sm font-semibold text-amber-800 mb-2">Questions for you</h4>
                <ul className="list-disc pl-5 space-y-1 text-sm text-amber-900">
                  {openQuestions.map((q: string, i: number) => (
                    <li key={i}>{q}</li>
                  ))}
                </ul>
              </div>
            )}

            {reqErrors.length > 0 && (
              <div className="rounded-xl bg-red-50 border border-red-200 p-4">
                <h4 className="text-sm font-semibold text-red-800 mb-2">Blocking issues</h4>
                <ul className="list-disc pl-5 space-y-1 text-sm text-red-900">
                  {reqErrors.map((e: string, i: number) => (
                    <li key={i}>{e}</li>
                  ))}
                </ul>
              </div>
            )}

            {comparisonNotes.length > 0 && (
              <div className="rounded-xl bg-white border p-4 shadow-sm">
                <h4 className="text-sm font-semibold text-muted-foreground mb-2">Requirement vs EDA</h4>
                <ul className="space-y-2 text-sm">
                  {comparisonNotes.map((n: any, i: number) => (
                    <li key={i} className="flex gap-2">
                      <span className={`text-[10px] font-bold uppercase px-1.5 py-0.5 rounded ${SEVERITY_STYLES[n.severity] || SEVERITY_STYLES.info}`}>
                        {n.severity}
                      </span>
                      <span>{n.message}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {disambiguationQuestions.length > 0 && (
              <div className="rounded-xl bg-indigo-50/50 border border-indigo-200 p-4 space-y-3">
                <h4 className="text-sm font-semibold text-indigo-900">
                  Your choices
                </h4>
                {disambiguationQuestions.map((q: any) => {
                  const multi = questionAllowsMultiple(q);
                  const qid = q.question_id;
                  const selectedValues = mcqAnswers[qid]
                    ? mcqAnswers[qid].split(',').map((s: string) => s.trim())
                    : [];
                  const clarifySelected = isClarifySelected(qid);
                  const clarifyOnly =
                    clarifySelected && !hasColumnSelection(qid);
                  return (
                    <div
                      key={qid}
                      role="group"
                      aria-labelledby={`mcq-label-${qid}`}
                      className="rounded-lg border border-indigo-100 bg-white p-4 flex flex-col gap-4"
                    >
                      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 lg:gap-6 items-start">
                        <div id={`mcq-label-${qid}`}>
                          <p className="text-sm font-medium text-foreground leading-snug">
                            {q.prompt}
                          </p>
                          {multi && !clarifyOnly && (
                            <p className="text-xs font-normal text-indigo-600 mt-1">
                              Select one or more
                            </p>
                          )}
                        </div>
                        <div className="space-y-1 lg:border-l lg:border-indigo-100 lg:pl-5 min-w-0">
                          {(q.options || []).map((opt: any) => (
                            <label
                              key={opt.option_id}
                              className="flex items-start gap-2.5 text-sm cursor-pointer rounded-md px-2 py-1.5 hover:bg-indigo-50/80"
                            >
                              <input
                                type={multi ? 'checkbox' : 'radio'}
                                name={qid}
                                value={opt.value}
                                checked={
                                  multi
                                    ? selectedValues.includes(opt.value)
                                    : mcqAnswers[qid] === opt.value
                                }
                                onChange={() =>
                                  multi
                                    ? toggleMultiMcq(
                                        qid,
                                        opt.value,
                                        !selectedValues.includes(opt.value)
                                      )
                                    : setMcqAnswers((prev) => {
                                        if (isClarifyValue(opt.value)) {
                                          setMcqClarifyText((t) => {
                                            const next = { ...t };
                                            delete next[qid];
                                            return next;
                                          });
                                        }
                                        return { ...prev, [qid]: opt.value };
                                      })
                                }
                                disabled={!isAwaiting}
                                className="text-indigo-600 mt-0.5 shrink-0"
                              />
                              <span className="leading-snug">{opt.label}</span>
                            </label>
                          ))}
                        </div>
                      </div>
                      {clarifySelected && (
                        <div className="w-full border-t border-indigo-100 pt-3">
                          <label
                            htmlFor={`clarify-${qid}`}
                            className="block text-xs font-semibold text-indigo-900 mb-1.5"
                          >
                            Describe what you need
                          </label>
                          <textarea
                            id={`clarify-${qid}`}
                            value={mcqClarifyText[qid] || ''}
                            onChange={(e) =>
                              setMcqClarifyText((prev) => ({
                                ...prev,
                                [qid]: e.target.value,
                              }))
                            }
                            disabled={!isAwaiting}
                            placeholder="Type your clarification here — we will re-check your requirements after you confirm."
                            className="w-full min-h-[4.5rem] max-h-[40vh] sm:max-h-[12rem] resize-y rounded-lg border border-indigo-200 bg-white px-3 py-2.5 text-sm leading-relaxed placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400 disabled:opacity-60"
                          />
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}

            {isAwaiting && (
              <div className="sticky bottom-0 z-[5] -mx-6 px-6 py-4 bg-gradient-to-t from-white via-white to-white/90 border-t flex flex-col sm:flex-row gap-3">
                <button
                  type="button"
                  onClick={() => submitWithMcq('approve')}
                  disabled={isPending || requirementConfirmDisabled}
                  title={
                    requirementConfirmDisabled
                      ? 'Select options or type a clarification for each prompt'
                      : undefined
                  }
                  className="flex-1 inline-flex items-center justify-center gap-2 bg-gradient-to-r from-emerald-500 to-emerald-600 hover:from-emerald-600 hover:to-emerald-700 text-white px-5 py-3 rounded-lg text-sm font-semibold transition-all shadow-sm hover:shadow-md disabled:opacity-50"
                >
                  Confirm
                </button>
                <button
                  type="button"
                  onClick={() => submitWithMcq('reject')}
                  disabled={isPending}
                  className="flex-1 inline-flex items-center justify-center gap-2 border-2 border-slate-200 bg-white hover:bg-slate-50 text-slate-700 px-5 py-3 rounded-lg text-sm font-semibold transition-all disabled:opacity-50"
                >
                  Cancel
                </button>
              </div>
            )}

            {!isAwaiting && (
              <div className="flex items-center justify-center py-2 px-4 bg-emerald-50 border border-emerald-100 rounded-lg text-emerald-700 text-sm font-medium gap-2">
                <CheckCircle2 className="w-4 h-4" />
                Decision recorded. Pipeline is proceeding.
              </div>
            )}

            {reqWarnings.length > 0 && (
              <div className="rounded-xl bg-white border p-4 shadow-sm">
                <h4 className="text-sm font-semibold text-muted-foreground mb-2">Warnings</h4>
                <ul className="list-disc pl-5 space-y-1 text-sm text-foreground">
                  {reqWarnings.map((w: string, i: number) => (
                    <li key={i}>{w}</li>
                  ))}
                </ul>
              </div>
            )}

            {(spec.columns_mapping?.length > 0) && (
              <div className="rounded-xl bg-white border p-4 shadow-sm">
                <h4 className="text-sm font-semibold mb-2">Column mappings ({spec.columns_mapping.length})</h4>
                <div className="flex flex-wrap gap-1.5">
                  {spec.columns_mapping.slice(0, 24).map((m: any) => (
                    <span key={m.original_name} className="inline-block rounded-md bg-indigo-50 border border-indigo-200 px-2 py-0.5 text-xs font-mono text-indigo-700">
                      {m.original_name} → {m.target_name}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </>
        )}

        {/* ── Plan Approval Content ──────────────────────────────────── */}
        {isPlanApproval && (
          <>
            {/* Plan Summary */}
            <div className="rounded-xl bg-white border p-5 shadow-sm">
              <h4 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide mb-2">Plan Summary</h4>
              <p className="text-foreground leading-relaxed">{plan.summary || checkpoint.message_to_user}</p>
            </div>

            {/* Column Selection */}
            {(colSelection.target_columns?.length > 0 || colSelection.skipped_columns?.length > 0) && (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                {colSelection.target_columns?.length > 0 && (
                  <div className="rounded-xl bg-white border p-4 shadow-sm">
                    <div className="flex items-center gap-2 mb-3">
                      <div className="w-6 h-6 rounded-full bg-emerald-100 flex items-center justify-center">
                        <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
                      </div>
                      <h4 className="text-sm font-semibold">Target Columns</h4>
                      <span className="ml-auto text-xs bg-emerald-100 text-emerald-700 rounded-full px-2 py-0.5 font-medium">
                        {colSelection.target_columns.length}
                      </span>
                    </div>
                    <div className="flex flex-wrap gap-1.5">
                      {colSelection.target_columns.map((col: string) => (
                        <span key={col} className="inline-block rounded-md bg-emerald-50 border border-emerald-200 px-2 py-0.5 text-xs font-mono text-emerald-700">
                          {col}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
                {colSelection.skipped_columns?.length > 0 && (
                  <div className="rounded-xl bg-white border p-4 shadow-sm">
                    <div className="flex items-center gap-2 mb-3">
                      <div className="w-6 h-6 rounded-full bg-gray-100 flex items-center justify-center">
                        <XCircle className="w-3.5 h-3.5 text-gray-400" />
                      </div>
                      <h4 className="text-sm font-semibold text-muted-foreground">Skipped Columns</h4>
                      <span className="ml-auto text-xs bg-gray-100 text-gray-500 rounded-full px-2 py-0.5 font-medium">
                        {colSelection.skipped_columns.length}
                      </span>
                    </div>
                    <div className="flex flex-wrap gap-1.5">
                      {colSelection.skipped_columns.map((col: string) => (
                        <span key={col} className="inline-block rounded-md bg-gray-50 border border-gray-200 px-2 py-0.5 text-xs font-mono text-gray-500">
                          {col}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* Tasks */}
            {allTasks.length > 0 && (
              <div>
                <h4 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide mb-3">
                  Execution Steps ({allTasks.length})
                </h4>
                <div className="space-y-3">
                  {allTasks.map(({ task, phase }, i) => (
                    <TaskCard key={task.task_id || i} task={task} index={i} phase={phase} />
                  ))}
                </div>
              </div>
            )}
          </>
        )}

        {/* ── Result Approval Content ────────────────────────────────── */}
        {!isPlanApproval && !isRequirementApproval && !isInputValidationClarification && (
          <>
            {/* Message */}
            <div className="rounded-xl bg-white border p-5 shadow-sm">
              <div className="flex items-center justify-between mb-2">
                <h4 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide">Validation Summary</h4>
                {validationPassed !== undefined && (
                  <span className={`inline-flex items-center gap-1 text-[10px] font-semibold px-2 py-0.5 rounded-full uppercase ${validationPassed ? 'bg-emerald-100 text-emerald-700' : 'bg-rose-100 text-rose-700'}`}>
                    {validationPassed ? <CheckCircle2 className="w-3 h-3" /> : <XCircle className="w-3 h-3" />}
                    {validationPassed ? 'Passed' : 'Failed'}
                  </span>
                )}
              </div>
              <p className="text-foreground leading-relaxed whitespace-pre-line">{checkpoint.message_to_user}</p>
            </div>

            {/* Metrics */}
            {metrics.total_rows && (
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                <div className="rounded-xl bg-white border p-4 shadow-sm text-center">
                  <div className="text-2xl font-bold text-foreground">{metrics.total_rows?.toLocaleString()}</div>
                  <div className="text-xs text-muted-foreground mt-1">Total Rows</div>
                </div>
                <div className="rounded-xl bg-white border p-4 shadow-sm text-center">
                  <div className="text-2xl font-bold text-foreground">{metrics.target_columns_checked ?? 0}</div>
                  <div className="text-xs text-muted-foreground mt-1">Columns Checked</div>
                </div>
                <div className="rounded-xl bg-white border p-4 shadow-sm text-center">
                  <div className="text-2xl font-bold text-red-600">{issues.filter((i: any) => i.severity === 'error').length}</div>
                  <div className="text-xs text-muted-foreground mt-1">Errors Found</div>
                </div>
              </div>
            )}

            {/* Issues Table */}
            {issues.length > 0 && (
              <div className="rounded-xl bg-white border shadow-sm overflow-hidden">
                <div className="px-4 py-3 border-b bg-muted/30">
                  <h4 className="text-sm font-semibold">Quality Issues ({issues.length})</h4>
                </div>
                <div className="divide-y max-h-[300px] overflow-auto">
                  {issues.map((issue: any, i: number) => (
                    <div key={i} className="px-4 py-3 flex items-start gap-3">
                      <span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase ${SEVERITY_STYLES[issue.severity] || SEVERITY_STYLES.info}`}>
                        {issue.severity}
                      </span>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <code className="text-xs font-mono bg-muted px-1.5 py-0.5 rounded">{issue.column}</code>
                          <span className="text-xs text-muted-foreground">{issue.issue_type}</span>
                        </div>
                        <p className="text-sm text-foreground mt-1">{issue.description}</p>
                        {issue.affected_rows > 0 && (
                          <span className="text-xs text-muted-foreground">{issue.affected_rows.toLocaleString()} rows affected</span>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </>
        )}

        {/* Raw JSON toggle (shared) */}
        <button
          type="button"
          onClick={() => setShowRawJson(!showRawJson)}
          className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors"
        >
          {showRawJson ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
          {showRawJson ? 'Hide' : 'Show'} raw JSON
        </button>
        {showRawJson && (
          <pre className="bg-slate-950 text-slate-300 rounded-lg p-4 text-xs font-mono overflow-auto max-h-[250px] whitespace-pre-wrap break-words">
            {JSON.stringify(payload, null, 2)}
          </pre>
        )}

        {/* Feedback + Actions (plan / result checkpoints only) */}
        {!isRequirementApproval && !isInputValidationClarification && (
        <div className="rounded-xl bg-white border p-5 shadow-sm space-y-4">
          <div className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
            <MessageSquare className="w-4 h-4" />
            Feedback {isAwaiting ? (canModify ? '(required for Modify)' : '(optional)') : '(submitted)'}
          </div>
          <textarea
            className="flex min-h-[80px] w-full rounded-lg border border-input bg-muted/30 px-4 py-3 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring transition-all resize-none disabled:opacity-70"
            placeholder={isRequirementApproval
              ? "Clarify requirements or correct column names..."
              : isPlanApproval
              ? "Describe how you'd like the plan to change..."
              : "Provide guidance on how to fix the remaining issues..."
            }
            value={feedback}
            onChange={(e) => onFeedbackChange(e.target.value)}
            disabled={!isAwaiting}
          />

          {isAwaiting ? (
            <div className="flex flex-col sm:flex-row gap-3 pt-1">
              <button
                onClick={() => submitWithMcq('approve', feedback)}
                disabled={isPending || (isRequirementApproval && !allMcqAnswered)}
                title={isRequirementApproval && !allMcqAnswered ? 'Answer all required questions first' : ''}
                className="flex-1 inline-flex items-center justify-center gap-2 bg-gradient-to-r from-emerald-500 to-emerald-600 hover:from-emerald-600 hover:to-emerald-700 text-white px-5 py-2.5 rounded-lg text-sm font-semibold transition-all shadow-sm hover:shadow-md disabled:opacity-50"
              >
                {isRequirementApproval ? 'Approve Requirements' : isPlanApproval ? 'Approve Plan' : 'Accept Results'}
              </button>
              <button
                onClick={() => submitWithMcq('modify', feedback)}
                disabled={
                  isPending ||
                  (!feedback.trim() && !allMcqAnswered) ||
                  !canModify
                }
                title={!canModify ? `Maximum ${maxModify} modifications reached` : ''}
                className="flex-1 inline-flex items-center justify-center gap-2 bg-gradient-to-r from-amber-500 to-amber-600 hover:from-amber-600 hover:to-amber-700 text-white px-5 py-2.5 rounded-lg text-sm font-semibold transition-all shadow-sm hover:shadow-md disabled:opacity-50"
              >
                {canModify
                  ? isRequirementApproval
                    ? 'Clarify requirements'
                    : maxModify != null
                      ? `Modify (${maxModify - modifyCount} left)`
                      : 'Modify'
                  : 'Max Modifications Reached'}
              </button>
              <button
                onClick={() => submitWithMcq('reject', feedback)}
                disabled={isPending}
                className="flex-1 inline-flex items-center justify-center gap-2 bg-gradient-to-r from-red-500 to-red-600 hover:from-red-600 hover:to-red-700 text-white px-5 py-2.5 rounded-lg text-sm font-semibold transition-all shadow-sm hover:shadow-md disabled:opacity-50"
              >
                {isRequirementApproval ? 'Cancel Run' : isPlanApproval ? 'Reject' : 'Reject (Export As-Is)'}
              </button>
            </div>
          ) : (
            <div className="flex items-center justify-center py-2 px-4 bg-emerald-50 border border-emerald-100 rounded-lg text-emerald-700 text-sm font-medium gap-2">
              <CheckCircle2 className="w-4 h-4" />
              Decision recorded. Pipeline is proceeding.
            </div>
          )}
        </div>
        )}
      </div>
    </div>
  );
};

export const ResolvedValidationPlanPanel: React.FC<{
  validationResult: any;
  runId: string;
  onGeneratePlan: () => void;
  isGenerating: boolean;
}> = ({ validationResult, runId, onGeneratePlan, isGenerating }) => {
  const reasoning = validationResult.reasoning || '';
  const actionPlan = validationResult.action_plan || {};
  const resolvedByUser = validationResult.resolved_by_user || [];

  // Read saved answers from localStorage if available
  const savedAnswers = useMemo(() => {
    const saved = localStorage.getItem(`hitl_answers_${runId}`);
    if (saved) {
      try {
        const parsed = JSON.parse(saved);
        return parsed.answers || {};
      } catch (e) {
        return null;
      }
    }
    return null;
  }, [runId]);

  return (
    <div className="mb-8 rounded-2xl border-2 border-emerald-400/40 bg-gradient-to-br from-emerald-50/80 via-white to-teal-50/40 shadow-lg overflow-hidden text-left animate-fadeIn">
      {/* Header */}
      <div className="bg-gradient-to-r from-emerald-500 to-teal-600 px-6 py-4">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-full bg-white/20 backdrop-blur-sm flex items-center justify-center">
            <CheckCircle2 className="w-5 h-5 text-white" />
          </div>
          <div>
            <h3 className="text-lg font-bold text-white">Validation Resolution Plan</h3>
            <p className="text-white/80 text-sm">The AI Agent has integrated your answers and compiled the cleaning rules</p>
          </div>
        </div>
      </div>

      <div className="p-6 space-y-6">
        {/* Reasoning */}
        {reasoning && (
          <div className="rounded-xl border bg-muted/40 p-4 text-sm leading-relaxed text-muted-foreground">
            <strong className="text-foreground block mb-1.5">Decision Reasoning:</strong>
            {reasoning}
          </div>
        )}

        {/* Action Plan */}
        <div className="space-y-4">
          <h4 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider">
            Generated Cleaning Instructions
          </h4>
          
          <div className="grid grid-cols-1 gap-4">
            {['null', 'duplicate', 'typecast'].map((issue) => {
              const planText = actionPlan[issue];
              if (!planText) return null;

              const title = issue === 'null' ? 'Null Handling Plan' : issue === 'duplicate' ? 'Deduplication Plan' : 'Type Casting Plan';
              const iconColor = issue === 'null' ? 'text-sky-500 bg-sky-50 border-sky-100' : issue === 'duplicate' ? 'text-violet-500 bg-violet-50 border-violet-100' : 'text-amber-500 bg-amber-50 border-amber-100';

              return (
                <div key={issue} className="flex gap-4 p-4 rounded-xl border bg-card/60 backdrop-blur-md shadow-sm">
                  <div className={`w-8 h-8 rounded-lg border flex items-center justify-center shrink-0 ${iconColor}`}>
                    <Zap className="w-4 h-4" />
                  </div>
                  <div>
                    <h5 className="text-sm font-bold text-foreground mb-1">{title}</h5>
                    <p className="text-xs text-muted-foreground leading-relaxed whitespace-pre-line">
                      {planText}
                    </p>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Resolved issues */}
        {resolvedByUser.length > 0 && (
          <div className="rounded-xl border p-4 bg-white shadow-sm">
            <h4 className="text-sm font-semibold text-muted-foreground mb-3">Resolved Column Issues</h4>
            <div className="flex flex-wrap gap-2">
              {resolvedByUser.map((item: string, i: number) => (
                <span key={i} className="inline-block px-3 py-1 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
                  {item}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* User answers summary */}
        {savedAnswers && Object.keys(savedAnswers).length > 0 && (
          <details className="mt-4 text-xs font-semibold">
            <summary className="cursor-pointer text-muted-foreground hover:text-foreground font-medium select-none transition-colors">
              View your submitted answers
            </summary>
            <div className="mt-2.5 rounded-xl border bg-muted/30 p-4 space-y-2.5 divide-y divide-border/40">
              {Object.entries(savedAnswers).map(([key, value]: [string, any]) => {
                const parts = key.split('.');
                const cat = parts[0];
                const qKey = parts[1];
                return (
                  <div key={key} className="pt-2 first:pt-0">
                    <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground/60 block mb-0.5">
                      {cat} - {qKey}
                    </span>
                    <p className="text-xs text-foreground font-medium">{value}</p>
                  </div>
                );
              })}
            </div>
          </details>
        )}

        {/* Proceed to plan button */}
        <div className="pt-4 border-t border-slate-100 flex justify-end">
          <button
            type="button"
            onClick={onGeneratePlan}
            disabled={isGenerating}
            className="inline-flex items-center gap-2 px-5 py-2.5 bg-gradient-to-r from-emerald-500 to-teal-600 hover:from-emerald-600 hover:to-teal-700 text-white rounded-xl text-sm font-semibold transition-all shadow-sm hover:shadow-md disabled:opacity-50"
          >
            {isGenerating ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                Generating Cleaning Plan...
              </>
            ) : (
              <>
                <Layers className="w-4 h-4" />
                Tiến hành tạo plan
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
};

export const ExecutionPlanPanel: React.FC<{
  executionPlan: any;
  onApprove: () => void;
  isApproving: boolean;
}> = ({ executionPlan, onApprove, isApproving }) => {
  const metadata = executionPlan.metadata || {};
  const assumptions = executionPlan.assumptions || [];
  const globalConstraints = executionPlan.global_constraints || {};
  const taskList = executionPlan.task_list || [];

  return (
    <div className="mb-8 rounded-2xl border-2 border-indigo-400/40 bg-gradient-to-br from-indigo-50/80 via-white to-violet-50/40 shadow-lg overflow-hidden text-left animate-fadeIn">
      {/* Header */}
      <div className="bg-gradient-to-r from-indigo-500 to-violet-600 px-6 py-4">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-full bg-white/20 backdrop-blur-sm flex items-center justify-center">
            <Columns3 className="w-5 h-5 text-white" />
          </div>
          <div>
            <h3 className="text-lg font-bold text-white">Execution Plan</h3>
            <p className="text-white/80 text-sm">Generated cleaning DAG and worker strategies</p>
          </div>
        </div>
      </div>

      <div className="p-6 space-y-6">
        {/* Metadata & Global Constraints */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="rounded-xl border bg-white p-4 shadow-sm text-xs space-y-2">
            <h4 className="font-bold text-foreground uppercase tracking-wider mb-2">Plan Details</h4>
            <div><span className="text-muted-foreground">Plan ID:</span> <code className="bg-muted px-1.5 py-0.5 rounded font-mono">{metadata.plan_id}</code></div>
            <div><span className="text-muted-foreground">Version:</span> {metadata.plan_version}</div>
            <div><span className="text-muted-foreground">Created At:</span> {metadata.created_at}</div>
          </div>
          <div className="rounded-xl border bg-white p-4 shadow-sm text-xs space-y-2">
            <h4 className="font-bold text-foreground uppercase tracking-wider mb-2">Global Constraints</h4>
            <div><span className="text-muted-foreground">Max Retries:</span> {globalConstraints.max_retries_per_task}</div>
            <div>
              <span className="text-muted-foreground block mb-1">Preserve Columns:</span>
              <div className="flex flex-wrap gap-1">
                {globalConstraints.preserve_columns?.length > 0 ? (
                  globalConstraints.preserve_columns.map((col: string) => (
                    <span key={col} className="px-1.5 py-0.5 bg-slate-100 rounded text-[10px] font-mono text-slate-700">
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

        {/* Assumptions */}
        {assumptions.length > 0 && (
          <div className="rounded-xl border bg-muted/20 p-4">
            <h4 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider mb-2">Plan Assumptions</h4>
            <ul className="list-disc pl-5 space-y-1 text-xs text-foreground">
              {assumptions.map((asm: string, i: number) => (
                <li key={i}>{asm}</li>
              ))}
            </ul>
          </div>
        )}

        {/* Summary */}
        <div className="rounded-xl bg-white border p-5 shadow-sm">
          <h4 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider mb-2">Plan Summary</h4>
          <p className="text-xs text-foreground leading-relaxed leading-5">{executionPlan.plan_summary}</p>
        </div>

        {/* Tasks List */}
        <div className="space-y-4">
          <h4 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider">
            Work Orders ({taskList.length})
          </h4>
          
          <div className="space-y-4">
            {taskList.map((item: any, i: number) => {
              const task = item.work_order || {};
              const title = task.task_id === 'deduplication' ? 'Exact & Fuzzy Deduplication' : task.task_id === 'null_handling' ? 'Null & Disguised Value Imputation' : 'Strict Type Casting';
              const agentLabel = task.agent;
              const isSkipped = task.skip;
              
              return (
                <div key={i} className={`rounded-xl border bg-card p-4 shadow-sm transition-all duration-200 ${isSkipped ? 'opacity-60 bg-muted/10' : 'hover:shadow-md'}`}>
                  <div className="flex items-start justify-between mb-3 flex-wrap gap-2">
                    <div className="flex items-center gap-2">
                      <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-semibold ${
                        isSkipped 
                          ? 'bg-slate-100 text-slate-500 border-slate-200' 
                          : task.task_id === 'deduplication' 
                            ? 'bg-violet-500/10 text-violet-600 border-violet-200' 
                            : task.task_id === 'null_handling'
                              ? 'bg-sky-500/10 text-sky-600 border-sky-200'
                              : 'bg-amber-500/10 text-amber-600 border-amber-200'
                      }`}>
                        {title}
                      </span>
                      <span className="text-xs text-muted-foreground font-mono">({agentLabel})</span>
                    </div>
                    {isSkipped && (
                      <span className="text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 bg-gray-100 text-gray-500 rounded border border-gray-200">
                        Skipped
                      </span>
                    )}
                  </div>

                  {isSkipped ? (
                    <p className="text-xs text-slate-500 italic">Reason: {task.skip_reason}</p>
                  ) : (
                    <div className="space-y-3 mt-2 text-xs">
                      {task.rationale && (
                        <p className="text-slate-600 leading-relaxed"><strong className="text-foreground">Rationale:</strong> {task.rationale}</p>
                      )}
                      
                      {task.columns?.length > 0 && (
                        <div>
                          <span className="font-semibold text-foreground mr-2">Target columns:</span>
                          <div className="inline-flex flex-wrap gap-1">
                            {task.columns.map((col: string) => (
                              <span key={col} className="px-1.5 py-0.5 bg-indigo-50 border border-indigo-100 rounded text-[10px] font-mono text-indigo-600">
                                {col}
                              </span>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Display strategy depending on task_id */}
                      {task.strategy && (
                        <div className="bg-muted/30 border rounded-lg p-3">
                          <span className="font-bold text-foreground block mb-2 text-[11px] uppercase tracking-wider text-muted-foreground/80">Strategy Configuration</span>
                          {task.task_id === 'deduplication' && (
                            <div className="space-y-1">
                              <div>Tier level: {task.strategy.tier}</div>
                              <div>Primary keys: {task.strategy.primary_keys?.join(', ')}</div>
                              {task.strategy.fuzzy_columns && Object.keys(task.strategy.fuzzy_columns).length > 0 && (
                                <div>
                                  Fuzzy matching:
                                  <ul className="list-disc pl-4 mt-0.5">
                                    {Object.entries(task.strategy.fuzzy_columns).map(([col, cfg]: [string, any]) => (
                                      <li key={col}>{col}: {cfg.method} (threshold {cfg.threshold})</li>
                                    ))}
                                  </ul>
                                </div>
                              )}
                            </div>
                          )}
                          {task.task_id === 'null_handling' && task.strategy.per_column && (
                            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                              {Object.entries(task.strategy.per_column).map(([col, cfg]: [string, any]) => (
                                <div key={col} className="bg-white border rounded p-2 text-[11px]">
                                  <span className="font-mono font-bold text-foreground block">{col}</span>
                                  <span className="text-muted-foreground">Imputation: {cfg.strategy} {cfg.fill_value !== null ? `(${cfg.fill_value})` : ''}</span>
                                </div>
                              ))}
                            </div>
                          )}
                          {task.task_id === 'type_casting' && task.strategy.per_column && (
                            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                              {Object.entries(task.strategy.per_column).map(([col, cfg]: [string, any]) => (
                                <div key={col} className="bg-white border rounded p-2 text-[11px]">
                                  <span className="font-mono font-bold text-foreground block">{col}</span>
                                  <span className="text-muted-foreground">Cast expected: {cfg.expected_type} {cfg.parse_format ? `(Format: ${cfg.parse_format})` : ''}</span>
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                      )}

                      {task.verification?.pandera_checks?.length > 0 && (
                        <div>
                          <span className="font-semibold text-foreground block mb-1">Validation rules:</span>
                          <div className="flex flex-wrap gap-1.5">
                            {task.verification.pandera_checks.map((rule: string, ri: number) => (
                              <span key={ri} className="px-2 py-0.5 bg-emerald-50 border border-emerald-100 rounded-md text-[10px] font-mono text-emerald-700">
                                {rule}
                              </span>
                            ))}
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

        {/* Action Button */}
        <div className="pt-4 border-t border-slate-100 flex justify-end">
          <button
            type="button"
            onClick={onApprove}
            disabled={isApproving}
            className="inline-flex items-center gap-2 px-6 py-3 bg-gradient-to-r from-indigo-500 to-violet-600 hover:from-indigo-600 hover:to-violet-700 text-white rounded-xl text-sm font-semibold transition-all shadow-md hover:shadow-lg disabled:opacity-50"
          >
            {isApproving ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                Executing Pipeline...
              </>
            ) : (
              <>
                <CheckCircle2 className="w-4 h-4" />
                Approve & Execute Cleaning
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
};

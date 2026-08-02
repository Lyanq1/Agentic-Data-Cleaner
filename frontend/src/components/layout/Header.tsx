import React from 'react';
import { Database } from 'lucide-react';
import { motion } from 'framer-motion';
import type { AppStep } from '../../lib/pipelineSession';

export interface HeaderProps {
  step: AppStep;
  runId: string | null;
  onNavigateStep: (step: AppStep) => void;
  onHomeReset: () => void;
}

const STEPS: { id: AppStep; label: string }[] = [
  { id: 'upload', label: 'Upload' },
  { id: 'profile', label: 'Profile' },
  { id: 'pipeline', label: 'Pipeline' },
  { id: 'result', label: 'Results' },
];

export const Header: React.FC<HeaderProps> = ({
  step,
  runId,
  onNavigateStep,
  onHomeReset,
}) => {
  const canProfile = Boolean(runId);
  const canPipeline = Boolean(runId);
  const canResult = Boolean(runId);

  const canNavigateTo = (target: AppStep) => {
    if (target === 'upload') return true;
    if (target === 'profile') return canProfile;
    if (target === 'pipeline') return canPipeline;
    if (target === 'result') return canResult;
    return false;
  };

  return (
    <header className="sticky top-0 z-50 w-full pt-4 pb-2 px-4 pointer-events-none flex justify-center">
      <div className="w-full max-w-[1400px] grid grid-cols-1 md:grid-cols-3 gap-4 items-center pointer-events-auto">
        
        {/* Left: Rounded Logo badge */}
        <div className="flex justify-start">
        <button
          type="button"
          onClick={onHomeReset}
          className="glass-panel px-4 py-2 flex items-center gap-3 hover:bg-white/70 dark:hover:bg-black/40 transition-colors"
          title="Start over — new upload session"
        >
          <div className="bg-primary/10 text-primary p-1.5 rounded-lg">
            <Database className="h-5 w-5 shrink-0" />
          </div>
          <span className="hidden font-bold sm:inline-block text-foreground whitespace-nowrap">Agentic Data Cleaner</span>
        </button>

        </div>

        {/* Middle: Glass segmented control / Steps Pill */}
        <div className="hidden md:flex justify-center">
          <nav
            className="glass-panel items-center p-1.5 rounded-[2rem] relative flex shadow-lg shadow-primary/5"
            aria-label="Pipeline steps"
          >
          {STEPS.map((s) => {
            const isCurrent = step === s.id;
            const isEnabled = canNavigateTo(s.id);

            return (
              <button
                key={s.id}
                type="button"
                className={`relative px-6 py-2 rounded-full text-sm font-semibold transition-colors z-10 overflow-hidden ${
                  isCurrent
                    ? 'text-white'
                    : isEnabled
                    ? 'text-foreground/70 hover:text-foreground'
                    : 'text-muted-foreground/30 cursor-not-allowed'
                }`}
                disabled={!isEnabled}
                onClick={() => {
                  if (s.id === 'upload') onHomeReset();
                  else if (isEnabled) onNavigateStep(s.id);
                }}
              >
                {isCurrent && (
                  <motion.div
                    layoutId="header-active-step"
                    className="absolute inset-0 bg-primary/90 dark:bg-primary rounded-full -z-10 shadow-[0_0_15px_rgba(var(--color-primary),0.5)]"
                    transition={{ type: 'spring', stiffness: 500, damping: 30 }}
                  />
                )}
                {s.label}
              </button>
            );
          })}
          </nav>
        </div>

        {/* Right: Run ID badge */}
        <div className="flex justify-end">
          <div className="glass-panel px-4 py-2 flex items-center opacity-90 h-10 min-w-[80px] justify-center">
          {runId ? (
            <span className="text-[12px] text-muted-foreground font-mono truncate max-w-[150px]" title={runId}>
              {runId.split('-')[0]}...
            </span>
          ) : (
            <span className="text-[12px] text-muted-foreground">New Session</span>
          )}
          </div>
        </div>
        
      </div>
    </header>
  );
};

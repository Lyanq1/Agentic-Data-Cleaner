import React from 'react';
import { ChevronRight, Database, Home } from 'lucide-react';
import type { AppStep } from '../../lib/pipelineSession';

export interface HeaderProps {
  step: AppStep;
  runId: string | null;
  onNavigateStep: (step: AppStep) => void;
  /** Full reset (logo): clears run and returns to upload. */
  onHomeReset: () => void;
}

const STEP_LABEL: Record<AppStep, string> = {
  upload: 'Upload',
  profile: 'Statistical Profile',
  pipeline: 'Pipeline',
  // input_validator: 'Human Input' for later use
  result: 'Results',
};

export const Header: React.FC<HeaderProps> = ({
  step,
  runId,
  onNavigateStep,
  onHomeReset,
}) => {
  const canProfile = Boolean(runId);
  const canPipeline = Boolean(runId);
  const canResult = Boolean(runId);

  const crumbClass = (_target: AppStep, enabled: boolean, isCurrent: boolean) =>
    [
      'text-sm font-medium transition-colors rounded-md px-2 py-1 -mx-2',
      isCurrent
        ? 'text-foreground bg-muted/80 cursor-default'
        : enabled
          ? 'text-muted-foreground hover:text-foreground hover:bg-muted/50 cursor-pointer'
          : 'text-muted-foreground/40 cursor-not-allowed',
    ].join(' ');

  return (
    <header className="sticky top-0 z-50 w-full border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60 text-left">
      <div className="max-w-[1400px] flex h-14 items-center mx-auto px-4 w-full gap-4 flex-wrap">
        <button
          type="button"
          onClick={onHomeReset}
          className="mr-2 flex items-center space-x-2 rounded-md px-1 py-1 text-left hover:bg-muted/60 transition-colors"
          title="Start over — new upload session"
        >
          <Database className="h-6 w-6 shrink-0" />
          <span className="hidden font-bold sm:inline-block">Agentic Data Pipeline</span>
        </button>

        <nav
          className="flex items-center gap-1 min-w-0 flex-1 text-muted-foreground"
          aria-label="Pipeline steps"
        >
          <span className="hidden sm:inline text-muted-foreground/50" aria-hidden>
            <Home className="w-3.5 h-3.5" />
          </span>
          <ChevronRight className="w-4 h-4 shrink-0 text-muted-foreground/50 hidden sm:block" aria-hidden />

          <button
            type="button"
            className={crumbClass('upload', true, step === 'upload')}
            onClick={onHomeReset}
            title="Start over — new upload session"
          >
            {STEP_LABEL.upload}
          </button>

          <ChevronRight className="w-4 h-4 shrink-0 text-muted-foreground/50" aria-hidden />

          <button
            type="button"
            className={crumbClass('profile', canProfile, step === 'profile')}
            disabled={!canProfile}
            onClick={() => canProfile && onNavigateStep('profile')}
            title={!canProfile ? 'Upload a file first' : 'Open statistical profile'}
          >
            {STEP_LABEL.profile}
          </button>

          <ChevronRight className="w-4 h-4 shrink-0 text-muted-foreground/50" aria-hidden />

          <button
            type="button"
            className={crumbClass('pipeline', canPipeline, step === 'pipeline')}
            disabled={!canPipeline}
            onClick={() => canPipeline && onNavigateStep('pipeline')}
            title={!canPipeline ? 'Run a file first' : 'Open pipeline view'}
          >
            {STEP_LABEL.pipeline}
          </button>

          <ChevronRight className="w-4 h-4 shrink-0 text-muted-foreground/50" aria-hidden />

          <button
            type="button"
            className={crumbClass('result', canResult, step === 'result')}
            disabled={!canResult}
            onClick={() => canResult && onNavigateStep('result')}
            title={!canResult ? 'Run a file first' : 'Open results'}
          >
            {STEP_LABEL.result}
          </button>
        </nav>

        {runId && (
          <div className="hidden md:block text-[11px] text-muted-foreground font-mono truncate max-w-[200px] lg:max-w-xs shrink-0" title={runId}>
            Run ID: {runId}
          </div>
        )}
      </div>
    </header>
  );
};

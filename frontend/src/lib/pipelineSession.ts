/** Pipeline flow: URL query is the single source of truth. */

export type AppStep = 'upload' | 'profile' | 'pipeline' | 'result';

export function parsePipelineSearch(search: string): { step: AppStep; runId: string | null } {
  const params = new URLSearchParams(search.startsWith('?') ? search.slice(1) : search);
  const stepRaw = params.get('step');
  const run = params.get('run');

  const step: AppStep =
    stepRaw === 'profile' || stepRaw === 'pipeline' || stepRaw === 'result' ? stepRaw : 'upload';
  const runId = run && run.trim().length > 0 ? run.trim() : null;

  if ((step === 'profile' || step === 'pipeline' || step === 'result') && !runId) {
    return { step: 'upload', runId: null };
  }
  return { step, runId };
}

function hasRouteQuery(search: string): boolean {
  const p = new URLSearchParams(search.startsWith('?') ? search.slice(1) : search);
  return p.has('step') || p.has('run');
}

export function buildPipelineSearch(step: AppStep, runId: string | null): string {
  const p = new URLSearchParams();
  p.set('step', step);
  if (runId) p.set('run', runId);
  return p.toString();
}

export function applyPipelineRoute(
  step: AppStep,
  runId: string | null,
  mode: 'push' | 'replace'
): void {
  const qs = buildPipelineSearch(step, runId);
  const url = `${window.location.pathname}?${qs}`;
  const state = { step, runId };
  if (mode === 'push') {
    window.history.pushState(state, '', url);
  } else {
    window.history.replaceState(state, '', url);
  }
}

/** Use in useState initializer: restore from URL only. */
export function getInitialRouteState(): { step: AppStep; runId: string | null } {
  const search = window.location.search;
  if (hasRouteQuery(search)) {
    return parsePipelineSearch(search);
  }
  return { step: 'upload', runId: null };
}

import { useCallback, useEffect, useLayoutEffect, useMemo, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { Header } from './components/layout/Header';
import { UploadView } from './components/views/UploadView';
import { PipelineView } from './components/views/PipelineView';
import { ResultView } from './components/views/ResultView';
import type { AppStep } from './lib/pipelineSession';
import {
  applyPipelineRoute,
  getInitialRouteState,
  parsePipelineSearch,
} from './lib/pipelineSession';

function App() {
  const queryClient = useQueryClient();
  const initialRoute = useMemo(() => getInitialRouteState(), []);
  const [currentStep, setCurrentStep] = useState<AppStep>(initialRoute.step);
  const [runId, setRunId] = useState<string | null>(initialRoute.runId);
  const [sessionKey, setSessionKey] = useState(0);

  // Bare "/" with restored session: mirror ?step=&run= into the address bar without adding a history entry.
  useLayoutEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (!params.has('step')) {
      if (initialRoute.runId || initialRoute.step !== 'upload') {
        applyPipelineRoute(initialRoute.step, initialRoute.runId, 'replace');
      }
    }
  }, [initialRoute.step, initialRoute.runId]);

  useEffect(() => {
    const onPop = () => {
      const { step, runId: r } = parsePipelineSearch(window.location.search);
      setCurrentStep(step);
      setRunId(r);
    };
    window.addEventListener('popstate', onPop);
    return () => window.removeEventListener('popstate', onPop);
  }, []);

  const resetSession = useCallback(() => {
    if (runId) {
      queryClient.removeQueries({ queryKey: ['pipeline-state', runId] });
      queryClient.removeQueries({ queryKey: ['hitl-checkpoint', runId] });
    }
    setRunId(null);
    setCurrentStep('upload');
    setSessionKey((k) => k + 1);
    applyPipelineRoute('upload', null, 'replace');
  }, [queryClient, runId]);

  const handleNavigateStep = useCallback(
    (step: AppStep) => {
      if (step === 'upload') {
        resetSession();
        return;
      }
      if (!runId) return;
      setCurrentStep(step);
      applyPipelineRoute(step, runId, 'push');
    },
    [runId, resetSession]
  );

  const handleProfileLoaded = useCallback((loadedRunId: string) => {
    setRunId(loadedRunId);
    setCurrentStep('profile');
    applyPipelineRoute('profile', loadedRunId, 'replace');
  }, []);

  const handleClearProfile = useCallback(() => {
    resetSession();
  }, [resetSession]);

  const handleUploadSuccess = (newRunId: string) => {
    setRunId(newRunId);
    setCurrentStep('pipeline');
    applyPipelineRoute('pipeline', newRunId, 'push');
  };

  const handlePipelineComplete = () => {
    if (!runId) return;
    setCurrentStep('result');
    applyPipelineRoute('result', runId, 'push');
  };

  const handleStartOver = () => {
    resetSession();
  };

  /** Logo / app title: full reset — clears run, cache, and upload form state. */
  const handleHomeReset = () => {
    resetSession();
  };

  return (
    <div className="h-screen overflow-hidden bg-background font-sans antialiased flex flex-col items-center">
      <Header
        step={currentStep}
        runId={runId}
        onNavigateStep={handleNavigateStep}
        onHomeReset={handleHomeReset}
      />
      <main className="flex-1 min-h-0 overflow-hidden w-full max-w-[1400px] px-6 py-6 flex flex-col">
        {(currentStep === 'upload' || currentStep === 'profile') && (
          <UploadView
            key={sessionKey}
            onUploadSuccess={handleUploadSuccess}
            onProfileLoaded={handleProfileLoaded}
            onClearProfile={handleClearProfile}
            initialRunId={currentStep === 'profile' ? runId : null}
          />
        )}
        {currentStep === 'pipeline' && runId && (
          <PipelineView runId={runId} onComplete={handlePipelineComplete} />
        )}
        {currentStep === 'result' && runId && (
          <ResultView runId={runId} onStartOver={handleStartOver} />
        )}
      </main>
    </div>
  );
}

export default App;
export type { AppStep } from './lib/pipelineSession';

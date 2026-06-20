import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useState,
} from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Header } from "./components/layout/Header";
import { UploadView } from "./components/views/UploadView";
import { PipelineView } from "./components/views/PipelineView";
import { ResultView } from "./components/views/ResultView";
import type { AppStep } from "./lib/pipelineSession";
import {
  applyPipelineRoute,
  getInitialRouteState,
  parsePipelineSearch,
} from "./lib/pipelineSession";
import { MassUploadView } from "./components/views/MassUploadView";
import { Database } from "lucide-react";

function App() {
  const queryClient = useQueryClient();
  const initialRoute = useMemo(() => getInitialRouteState(), []);
  const [currentStep, setCurrentStep] = useState<AppStep>(initialRoute.step);
  const [runId, setRunId] = useState<string | null>(initialRoute.runId);
  const [sessionKey, setSessionKey] = useState(0);
  const [autoCompletedRunId, setAutoCompletedRunId] = useState<string | null>(
    initialRoute.step === "result" ? initialRoute.runId : null,
  );

  // Bare "/" with restored session: mirror ?step=&run= into the address bar without adding a history entry.
  useLayoutEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (!params.has("step")) {
      if (initialRoute.runId || initialRoute.step !== "upload") {
        applyPipelineRoute(initialRoute.step, initialRoute.runId, "replace");
      }
    }
  }, [initialRoute.step, initialRoute.runId]);

  useEffect(() => {
    const onPop = () => {
      const { step, runId: r } = parsePipelineSearch(window.location.search);
      setCurrentStep(step);
      setRunId(r);
    };
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  const resetSession = useCallback(() => {
    // Clear React Query cache
    if (runId) {
      queryClient.removeQueries({ queryKey: ["pipeline-state", runId] });
      queryClient.removeQueries({ queryKey: ["hitl-checkpoint", runId] });
    }
    queryClient.clear();

    setRunId(null);
    setAutoCompletedRunId(null);
    setCurrentStep("upload");
    setSessionKey((k) => k + 1);
    applyPipelineRoute("upload", null, "replace");
  }, [queryClient, runId]);

  const handleNavigateStep = useCallback(
    (step: AppStep) => {
      if (step === "upload") {
        resetSession();
        return;
      }
      if (!runId) return;
      setCurrentStep(step);
      applyPipelineRoute(step, runId, "push");
    },
    [runId, resetSession],
  );

  const handleProfileLoaded = useCallback((loadedRunId: string) => {
    setRunId(loadedRunId);
    setCurrentStep("profile");
    applyPipelineRoute("profile", loadedRunId, "replace");
  }, []);

  const handleClearProfile = useCallback(() => {
    resetSession();
  }, [resetSession]);

  const handleUploadSuccess = (newRunId: string) => {
    setRunId(newRunId);
    setAutoCompletedRunId(null);
    setCurrentStep("pipeline");
    applyPipelineRoute("pipeline", newRunId, "push");
  };

  const handlePipelineComplete = () => {
    if (!runId) return;
    if (autoCompletedRunId === runId) return;
    setAutoCompletedRunId(runId);
    setCurrentStep("result");
    applyPipelineRoute("result", runId, "push");
  };

  const handleStartOver = () => {
    resetSession();
  };

  /** Logo / app title: full reset — clears run, cache, and upload form state. */
  const handleHomeReset = () => {
    resetSession();
  };

  const isMassUpload = window.location.pathname === "/massupload" || window.location.pathname === "/massupload/";

  if (isMassUpload) {
    return (
      <div className="h-dvh overflow-hidden bg-background font-sans antialiased flex flex-col items-center">
        <header className="sticky top-0 z-50 w-full border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60 text-left flex-none">
          <div className="max-w-[1400px] flex h-14 items-center mx-auto px-4 w-full gap-4 justify-between">
            <a
              href="/"
              className="flex items-center space-x-2 rounded-md px-1 py-1 text-left hover:bg-muted/60 transition-colors font-bold text-foreground"
            >
              <Database className="h-6 w-6 shrink-0 text-violet-600" />
              <span>Agentic Data Cleaner</span>
            </a>
            <div className="flex items-center gap-3">
              <span className="inline-flex items-center gap-1.5 text-xs font-semibold px-2.5 py-1 rounded-full bg-violet-100 text-violet-800 border border-violet-200">
              Mass Ingestion Console
              </span>
              <a
                href="/"
                className="text-xs font-medium text-muted-foreground hover:text-foreground hover:bg-muted px-3 py-1.5 rounded-lg border transition-colors"
              >
                Back to Single Ingestion
              </a>
            </div>
          </div>
        </header>
        <main className="flex-1 min-h-0 overflow-hidden w-full max-w-[1400px] px-3 py-4 sm:px-4 md:px-6 md:py-6 flex flex-col">
          <MassUploadView />
        </main>
      </div>
    );
  }

  return (
    <div className="h-dvh overflow-hidden bg-background font-sans antialiased flex flex-col items-center">
      <Header
        step={currentStep}
        runId={runId}
        onNavigateStep={handleNavigateStep}
        onHomeReset={handleHomeReset}
      />
      <main className="flex-1 min-h-0 overflow-hidden w-full max-w-[1400px] px-3 py-4 sm:px-4 md:px-6 md:py-6 flex flex-col">
        {(currentStep === "upload" || currentStep === "profile") && (
          <UploadView
            key={sessionKey}
            onUploadSuccess={handleUploadSuccess}
            onProfileLoaded={handleProfileLoaded}
            onClearProfile={handleClearProfile}
            initialRunId={currentStep === "profile" ? runId : null}
          />
        )}
        {currentStep === "pipeline" && runId && (
          <PipelineView
            runId={runId}
            onComplete={handlePipelineComplete}
            onOpenProfile={() => handleNavigateStep("profile")}
          />
        )}
        {currentStep === "result" && runId && (
          <ResultView runId={runId} onStartOver={handleStartOver} />
        )}
      </main>
    </div>
  );
}

export default App;
export type { AppStep } from "./lib/pipelineSession";

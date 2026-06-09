# Changelog: `hmq-log-streaming` Branch

This document provides a clean, factual summary of the changes introduced in the `hmq-log-streaming` branch based strictly on the git history and code diffs.

## 1. Backend: Real-Time Log Streaming via WebSockets
*(Commit: `637fb2b`)*

Replaced the synchronous LangGraph execution approach with an asynchronous streaming model to provide real-time visibility into the pipeline's progress without polluting the database.

* **`app/services/pipeline.py`**:
  * Transitioned from using `graph.ainvoke()` to `graph.astream_events()`.
  * Filtered specific LangGraph events (`on_chain_start`, `on_tool_start`, `on_tool_end`) to extract meaningful, human-readable progress logs (e.g., "Starting step...", "Calling tool...").
  * Integrated a broadcasting mechanism to send these logs live as they happen.
* **`app/core/websocket_manager.py` & `app/api/v1/websocket.py`**:
  * Implemented a FastAPI WebSocket endpoint (`/ws/{run_id}`).
  * Created a `ConnectionManager` class to handle connections, disconnections, and broadcasting JSON payload logs to all active clients subscribed to a specific `run_id`.
* **`app/api/v1/pipeline.py` & `app/api/v1/router.py`**:
  * Shifted pipeline execution (`run_pipeline`) to FastAPI `BackgroundTasks` to prevent HTTP request blocking while the graph streams events.
  * Registered the new WebSocket endpoints in the router.
* **`logging_flow_analysis.md`**:
  * Added documentation outlining the technical flow and analysis of the new log streaming architecture.

## 2. Frontend & Agent Nodes: UX Fixes & Read-Only Review Flow
*(Commit: `09bc792`)*

Resolved UI redirect bugs, enhanced the accuracy of agent state logging, and implemented a comprehensive post-completion review interface.

* **`app/graphs/nodes.py`**:
  * Updated agent nodes (profiler, input_validator, planner, dedup_agent, null_agent, typecast_agent) to append a discrete `"Running..."` log to the state dictionary right before their `"Completed..."` log. This ensures the frontend polling fallback accurately displays state transitions even if a WebSocket event is missed or the page is refreshed.
* **`frontend/src/components/views/PipelineView.tsx`**:
  * **Redirect Loop Fix**: Implemented a `sessionStorage` mechanism (`pipeline_completed_{runId}`) to prevent infinite auto-redirect loops. If a user manually navigates back to the Pipeline view after completion, the system detects the flag and halts the redirect to the Results view, safely ignoring stale-to-fresh React Query cache transitions.
  * **Completed Pipeline Review**: Created the `CompletedPipelineReviewPanel` component. This allows users to inspect the full pipeline journey (Statistical Profile, Requirements, Validation Plan, and Execution Plan) in a read-only state after the run has finished.
* **`frontend/src/components/views/pipelinepanel/ResolvedValidationPlanPanel.tsx`**:
  * Removed the fake 2-second timeout mock.
  * Tied the "Start Plan" button directly to the backend's `state.execution_plan`. It now correctly displays a disabled spinner ("Generating plan...") until the graph produces the execution plan, at which point it becomes a functional "View Execution Plan" button.
* **`frontend/src/components/views/pipelinepanel/ExecutionPlanPanel.tsx`**:
  * Added a `readOnly` prop to adapt the component for the new post-completion review interface, hiding action buttons when simply reviewing past results.
* **`frontend/src/App.tsx`**:
  * Updated navigation/routing logic to cleanly accommodate the revised flow between the Pipeline and Result steps.

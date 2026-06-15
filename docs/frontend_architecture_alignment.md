# Frontend Architecture & Backend API Alignment Plan

This document details the architectural structure, API mappings, data flow models, and optimization strategies for the **Agentic Data Cleaner** frontend system, ensuring it integrates with the LangGraph-based backend.

---

## 1. Proposed Frontend Structure

The frontend is structured as a modern React + TypeScript application powered by Vite, TailwindCSS, and ShadCN UI components:

```
frontend/
├── src/
│   ├── api/
│   │   ├── client.ts         # Axios client config (baseURL set to /api/v1)
│   │   └── services.ts       # API service functions & TypeScript models (Aligned)
│   ├── components/
│   │   ├── layout/
│   │   │   └── Header.tsx    # Header & Step navigation bar
│   │   └── views/
│   │       ├── UploadView.tsx              # Dataset Upload & Profiling Screen
│   │       ├── PipelineView.tsx            # Multi-agent Pipeline Logs & Progress
│   │       ├── PipelineHitlPanel.tsx       # Human-In-The-Loop review (Modular)
│   │       ├── RequirementSummaryPanel.tsx # LLM summary interpretation
│   │       └── ResultView.tsx              # Final clean report & download
│   ├── lib/
│   │   └── pipelineSession.ts # URL state serialization & route management
│   ├── App.tsx               # Main SPA Router & Coordinator
│   └── main.tsx              # Vite app entry point
```

---

## 2. UI Screen to Backend API Mappings

| UI Screen | User Action | Backend Endpoint | Request Payload | Response / Impact |
| :--- | :--- | :--- | :--- | :--- |
| **Upload View** | Drag/Drop & Submit dataset | `POST /api/v1/pipeline/run` | `file` (Multipart), `user_prompt` (Form Data) | Starts LangGraph execution; returns `run_id` and initial validation. |
| **Upload View** | Load Profile details | `GET /api/v1/pipeline/{run_id}/state` | `run_id` (Path parameter) | Fetches completed profiling state & detailed numeric histograms. |
| **Pipeline View** | Monitor live progress / logs | `GET /api/v1/pipeline/{run_id}/state` | `run_id` (Path parameter) | Polls the latest graph checkpoint to extract `completed_steps` and `errors`. |
| **Result View** | Review data metrics & issues | `GET /api/v1/pipeline/{run_id}/state` | `run_id` (Path parameter) | Renders token usage stats, data quality metrics, and validation reports. |
| **Result View** | Download Parquet file | `GET /api/v1/pipeline/{run_id}/state` | `run_id` (Path parameter) | Downloads the clean canonical data file. |

---

## 3. Data Flow: UI $\rightarrow$ API $\rightarrow$ UI

```mermaid
sequenceDiagram
    autonumber
    actor User as Graduate Student
    participant UI as React Frontend
    participant API as Axios Client
    participant BE as FastAPI Backend
    participant Graph as LangGraph Engine

    User->>UI: Selects file & enters prompt, clicks "Upload"
    UI->>API: pipelineApi.uploadFile(file, user_prompt)
    API->>BE: POST /api/v1/pipeline/run
    BE->>Graph: Initiates thread_id (run_id)
    BE-->>API: Returns { run_id, validation_result }
    API-->>UI: Updates currentStep to "pipeline"

    Note over UI, BE: Processing Phase (State Polling)
    loop Every 3 seconds (or via WebSocket)
        UI->>API: pipelineApi.getFullState(runId)
        API->>BE: GET /api/v1/pipeline/{run_id}/state
        BE-->>API: Returns global state values (data_profile, validation_result, completed_steps)
        API-->>UI: Maps to transformed UI schemas (agent_logs, status, spec)
        UI-->>User: Visualizes active agent terminal & step completions
    end

    Note over UI, BE: Processing Completed
    UI->>User: Switches to "result" step on 'completed' status
    User->>UI: Clicks "Download Data"
    UI->>API: Redirects to download URL
    API->>BE: GET /api/v1/pipeline/{run_id}/state (returns parquet)
    BE-->>User: Clean Parquet download starts
```

---

## 4. Software Architecture & Optimization Thinking

### 🚀 Performance Optimization
- **Lazy Loading Components**: Utilizing React `Suspense` and `lazy` imports for heavy panels (like Excel parser sheets and JSON renderers) ensures faster Initial Page Load times.
- **Smart React Query Caching**: Configured `@tanstack/react-query` to automatically suspend polling when a pipeline is in terminal states (`completed` or `failed`) to save server bandwidth.

### 🎨 User Experience (UX)
- **State Serialization**: Saves current state to URL parameters (`?step=...&runId=...`). When refreshing, the user does not lose their progress during a long ETL execution.
- **Dynamic Graphical Profiles**: Replaces boring textual tables with detailed interactive SVG histograms for numeric fields and relative bar charts for categories.

### 🔒 Robust Clean Code & Architecture
- **API Mapping Layer**: The Axios service acts as an abstraction model translating graph state outputs into components expectations. This isolates UI files from potential backend schema changes.
- **Micro-Animations**: Uses subtle fade-in transitions and loaders to provide reassurance while LLM operations are executing in the background.

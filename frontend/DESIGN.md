# Design System & UI Documentation — Agentic Data Cleaner

This document defines the design guidelines, standards, and reusable component patterns established during the UI/UX redesign of the Agentic Data Cleaner application.

---

## 1. Design Principles

- **Visual Restraint:** Avoid colorful "rainbow dashboards". Use muted gray borders and backgrounds as the baseline. Colors (green, amber, red, blue) are reserved strictly for semantic feedback (success, warning, error, info).
- **Efficiency and Density:** Design tables, lists, and forms to be compact. Reduce large font sizes and wide empty paddings. Avoid large floating cards, centering content only when there is a clear semantic purpose.
- **Micro-interactions:** Interactive elements (buttons, row selections, dropdowns) must have subtle transitions (`transition-all duration-200`) and standard focus indicators.
- **Immediate Context:** High-priority items (like pending Human-in-the-Loop checkpoints) must be placed at the top of the viewport or highlighted using sticky regions (e.g. `Sticky Run Strip` and `Sticky Action Bar`).

---

## 2. Colors & Typography

We use Tailwind v4 dynamic colors synced with the system state:
- `--color-primary` / `--color-primary-foreground`
- `--color-muted` / `--color-muted-foreground`
- `--color-success` / `--color-success-foreground`
- `--color-warning` / `--color-warning-foreground`
- `--color-destructive` / `--color-destructive-foreground`
- `--color-info` / `--color-info-foreground`

### Borders and Radius Scaling
- **Controls & Input badges:** `rounded` (4px) or `rounded-md` (6px).
- **Cards, Rows, & Tables:** `rounded-lg` (8px).
- **Outer Shell Elements:** `rounded-xl` (12px) max. Avoid excessive corner rounding.
- **Borders:** Thin, uniform `1px border-border` lines. Do not use colored thick borders unless highlighting critical alerts.

---

## 3. Standard Shared UI Components

### `StatusBadge` (src/components/ui/StatusBadge.tsx)
Unified 6-state status mapping used across `PipelineView` and `MassUploadView`:
- **`queued`** (Muted): Pipeline waiting in queue.
- **`running`** (Info, pulse): Actively processing.
- **`awaiting_hitl`** (Warning): Stopped, awaiting user decisions/approval.
- **`completed`** (Success): Executed successfully.
- **`failed`** (Destructive): Encountered an unrecoverable error.
- **`cancelled`** (Muted): Process stopped by user.

### `Panel` (src/components/ui/Panel.tsx)
Used as the standard card layout. Automatically handles borders, background (`bg-card`), text colors (`text-card-foreground`), and subtle styling.

### `Button` (src/components/ui/Button.tsx)
Restructured button element accepting:
- `variant`: `default` | `secondary` | `outline` | `ghost` | `destructive`
- `size`: `default` | `sm` | `lg` | `icon`

### `StickyActionBar` (src/components/ui/StickyActionBar.tsx)
Affixed to the bottom of long panels to keep CTA actions (Approve, Submit, Resume) visible without scrolling.

---

## 4. Feature Redesign Specifications

### 4.1 Left-Aligned Upload View
The centered marketing hero is removed. When starting, the user sees a left-aligned, standard `Upload dataset` header next to a flat drag-and-drop zone using a thin `border border-dashed border-border` style.

### 4.2 Muted Profile Metadata Badges
Vibrant violet, blue, and orange chips in `StatisticalProfilePanel` and `SemanticProfilePanel` are replaced with a single, unified mono tag style:
```html
bg-muted border border-border text-muted-foreground font-mono rounded text-[10px] px-1.5 py-0.5
```

### 4.3 Tabular Results (Great Expectations Style)
Rather than displaying separate round gauge cards for F1-score evaluation metrics, `ResultView` displays a clean tabular report summarizing properties, values, and status checks:
- **Metrics Table:** Displays `F1 Score`, `Precision`, `Recall`, `Cell Accuracy` and confusion counts.
- **Passed/Warning badges:** Inline pills next to each metric row.

### 4.4 Mass Ingestion Console
- Status badges are mapped to the common `StatusBadge` component.
- Left-border selection side stripes are replaced with a full-row focus background (`bg-muted ring-1 ring-inset ring-primary`).
- Dashboard cards are combined into a single compact divider-split metric row.

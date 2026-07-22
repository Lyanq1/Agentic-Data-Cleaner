# Frontend UI Redesign Brief

**Ngày:** 2026-07-18  
**Phạm vi:** `frontend/src/` (SPA React + Tailwind)  
**Constraint cứng:** Nghiêm cấm mọi dạng gradient (`bg-gradient-*`, `from-*`/`to-*` làm nền, gradient text, mesh, aurora).  
**Mục tiêu:** UI chuyên nghiệp, dễ theo dõi pipeline/HITL, không còn cảm giác “AI generated”.

---

## 0. Design Read

> Reading this as: **product console UI** cho data engineer / analyst theo dõi pipeline làm sạch dữ liệu và HITL, với ngôn ngữ **restrained ops-tool** (Linear / Airbyte / dbt Cloud), leaning toward **Tailwind + semantic tokens + dense information layout**. Không phải marketing landing.

| Dial | Giá trị | Lý do |
| --- | --- | --- |
| `DESIGN_VARIANCE` | **3** | Tool UI cần predictable grid, alignment ổn định |
| `MOTION_INTENSITY` | **2** | Chỉ feedback trạng thái (150–250ms), không choreography |
| `VISUAL_DENSITY` | **7** | Pipeline, log, bảng, checkpoint cần dense và scannable |

**Register:** Product (design SERVES the product), không phải brand landing.

**Đã có:** `PRODUCT.md` (init xong). **Handoff agent:** `docs/FRONTEND_UI_AGENT_HANDOFF.md` (file feed Cursor). `DESIGN.md` tạo sau Phase A/D bằng `/impeccable document`.

---

## 1. Tham chiếu sản phẩm thực tế (use case tương đương)

Học pattern từ các tool cùng loại việc (upload → profile → run → review → export), **không copy skin marketing**.

| Sản phẩm | Use case gần với ta | Pattern nên học |
| --- | --- | --- |
| [Airbyte](https://airbyte.com/) Connections / Sync History | Job chạy dài, status, logs | Status pill 1 màu semantic; timeline run; log monospace; header mỏng + run metadata |
| [dbt Cloud](https://www.getdbt.com/product/dbt-cloud) Run details | Artifact + step results | Left summary / right detail; step list với pass/fail; không banner màu full-bleed |
| [Prefect](https://www.prefect.io/) / [Dagster](https://dagster.io/) Run UI | Graph/pipeline + logs | Sticky run toolbar; filter log; state = text + icon, không rainbow badge |
| [Great Expectations / GX Cloud](https://greatexpectations.io/) | Validation report | Expectation result table; severity column; metrics dạng bảng, không “hero metric cards” |
| [OpenRefine](https://openrefine.org/) / [Cleanlab Studio](https://cleanlab.ai/) | HITL sửa dữ liệu | Facet/filter cột; selection rõ; approve/reject sát nội dung đang review |
| [Linear](https://linear.app/) Issues | Density + keyboard + trạng thái | Một accent; border 1px; typography system-ui/Inter; tránh decorative shadow |
| [Stripe Dashboard](https://dashboard.stripe.com/) | Ops console tin cậy | Neutral surface; semantic color chỉ cho state; bảng + detail panel |

**Nguyên tắc lấy từ các sản phẩm trên**

1. **Một accent** cho primary action / selection; semantic colors chỉ cho state (running, waiting, failed, success).
2. **Status = label + icon nhỏ**, không “celebration banner” xanh full-width trừ khi thực sự là terminal success screen.
3. **Log / table / checklist** là hero của màn hình pipeline, không phải icon tròn lớn giữa trang.
4. **HITL** đặt quyết định (Approve / Modify / Reject) gần nội dung cần đọc, sticky footer hoặc sidebar action, không chôn dưới stack card.
5. **Density trước decoration:** `border` + khoảng trắng có nhịp > `shadow-lg` + `rounded-2xl` + pill rainbow.

---

## 2. Chẩn đoán hiện trạng (AI-slop & UX)

### 2.1 Detector (Impeccable)

| Antipattern | File | Ghi chú |
| --- | --- | --- |
| `ai-color-palette` (violet) | `PipelineView.tsx` | Violet trên heading / badge / ping |
| `gray-on-color` | `StatisticalProfilePanel.tsx` | `text-slate-500` trên `bg-amber-50` |

### 2.2 Tín hiệu “AI generated” đang có trong code

| Tín hiệu | Ví dụ vị trí | Vì sao sai với product UI |
| --- | --- | --- |
| Violet / indigo / purple làm brand accent | `Header.tsx` Mass Ingestion link; `App.tsx` mass header; `MassUploadView`, `PipelineView`, `ResolvedValidationPlanPanel` | Palette mặc định của LLM; ops tools dùng neutral + 1 accent |
| Rainbow status pills (`animate-ping`) | `MassUploadView`, `PipelineView` worker cards | Mỗi state một màu pastel + pulse = dashboard toy, khó scan |
| Hero celebration (icon tròn lớn, centered) | `ResultView.tsx` | Giống onboarding marketing, không giống run report |
| Colored section banners (`bg-emerald-600` header bar) | `ResultView` Validation; `CompletedPipelineReviewPanel`; `ResolvedValidationPlanPanel` | “Success confetti panel”; dbt/GX dùng border + text status |
| Numbered circle steps (`bg-indigo-600`) | `PipelineView` `ReviewSection` | Section-number scaffolding; dùng heading + nội dung |
| Uppercase tracking eyebrows dày đặc | Nhiều panel | Product: tối đa rất thưa; label thường sentence-case |
| Nested cards + `shadow-sm` / `shadow-lg` mọi nơi | Hầu hết views | Elevation không mang hierarchy thật |
| Side-stripe selection (`border-l-2 border-l-primary`) | `MassUploadView` queue | Absolute ban của Impeccable; dùng `bg-muted` + ring hoặc `aria-current` style |
| Emoji trong UI (`🤖`) | `ResolvedValidationPlanPanel` | Thay bằng icon library hoặc text thuần |
| Em-dash trong copy | `ResultView` title có `—` | Đổi thành `-` hoặc tách câu |
| Glass / blur trang trí | Header `backdrop-blur`; một số panel `backdrop-blur-md` | Header solid border đủ; blur chỉ khi cần overlay modal |
| Default shadcn blue primary + violet satellite | `index.css` + violet utilities | Hai hệ màu cạnh tranh |

### 2.3 Vấn đề theo dõi / usability (không chỉ thẩm mỹ)

| Vấn đề | Hậu quả | Hướng sửa |
| --- | --- | --- |
| Pipeline: status + logs + HITL + profile lẫn layout card | Khó biết “đang chờ tôi” vs “đang chạy” | Sticky **run strip** (status, WS, run id, primary action) luôn visible |
| HITL panels quá cao, CTA dưới cùng | Scroll mất nút Approve | Sticky action bar trong panel review |
| Mass upload: 6+ màu status + ping | Không đọc được queue nhanh | 1 vocabulary status chuẩn (xem §4) |
| Result: metrics dạng circular progress + metric cards | Hero-metric template | Bảng metrics / definition list dạng GX |
| Profile tabs nằm trong card toolbar | OK về cấu trúc, nhưng visual còn “marketing card” | Toolbar flat, content flush với border |

---

## 3. Hệ thống thiết kế mục tiêu (không gradient)

### 3.1 Color strategy: **Restrained**

Chọn **một** accent (đề xuất: giữ blue primary hiện có **hoặc** chuyển sang teal/emerald muted cho “data quality”, nhưng **chỉ một**). Loại bỏ hoàn toàn `violet-*`, `purple-*`, `indigo-*` khỏi brand/chrome.

**Token đề xuất (OKLCH hoặc HSL tương đương, flat solid only):**

| Token | Vai trò | Quy tắc |
| --- | --- | --- |
| `--background` | App canvas | Off-white / zinc-50 family, **không** cream beige |
| `--surface` / `--card` | Panel | Trắng / zinc-100 dark |
| `--border` | Phân tách | 1px, dùng thay shadow |
| `--foreground` | Ink | Zinc-900 / zinc-50 |
| `--muted-foreground` | Secondary text | Contrast ≥ 4.5:1 trên background |
| `--primary` | CTA / selection | 1 accent, saturation < 80% |
| `--success` | completed / passed | Semantic only |
| `--warning` | awaiting_hitl / review | Semantic only |
| `--destructive` | failed / reject | Semantic only |
| `--info` | running / queued | Semantic only (cùng hue với primary hoặc slate) |

**Cấm**

- Mọi `bg-gradient-*`, `from-X to-Y` làm nền section/button/badge
- Neon glow, outer glow shadow màu
- Pastel rainbow cho từng agent role (gom role vào 1 badge neutral + label text)

### 3.2 Typography

- **Một family:** `system-ui` / Inter / Geist (product được phép Inter). Không display font, không serif.
- Scale chặt: `text-xs` → `text-sm` → `text-base` → `text-lg` (hiếm `text-2xl`/`text-3xl`).
- Data / run id / JSON: `font-mono` + `tabular-nums`.
- Bỏ hầu hết `uppercase tracking-wider` trên section headers; giữ sentence case.

### 3.3 Shape & elevation

| Quy tắc | Giá trị |
| --- | --- |
| Radius | Một scale: `6–8px` controls, `8–10px` panels. Không `rounded-2xl` + `rounded-full` lẫn lộn trừ avatar/status dot 6px |
| Shadow | Mặc định **không**. Modal/dropdown mới được soft shadow tinted |
| Cards | Chỉ khi là interactive container hoặc panel có scroll riêng. Không card-in-card |
| Dividers | `border-b` một chiều giữa rows |

### 3.4 Motion

- `transition-colors` / `opacity` 150–200ms.
- Spinner chỉ khi không có skeleton.
- **Cấm** `animate-ping` trên badge thường; live indicator tối đa **một** chấm nhỏ cạnh “Running”.
- Tôn trọng `prefers-reduced-motion`.

### 3.5 Icon

- Hiện dùng `lucide-react` (đã có trong project): **giữ một family**, không thêm Phosphor lẫn lộn trừ khi migrate cả repo.
- Không emoji trong production UI.

---

## 4. Status vocabulary (thống nhất toàn app)

Áp dụng giống Airbyte / Prefect: **một mapping**, mọi màn hình dùng chung.

| State | Label | Color | Motion |
| --- | --- | --- | --- |
| `queued` | Queued | muted | none |
| `running` | Running | info/primary | optional 1 dot pulse |
| `awaiting_hitl` | Needs review | warning | none (đây là state quan trọng nhất: nhấn bằng **bold + left placement**, không rainbow) |
| `completed` | Completed | success | none |
| `failed` | Failed | destructive | none |
| `cancelled` | Cancelled | muted | none |

**UI component đề xuất:** `<StatusBadge status={...} />` dùng chung (`PipelineView`, `MassUploadView`, Header nếu cần).

Mass upload hiện map quá nhiều màu (blue / indigo / amber / purple / emerald / rose + ping). Collapse về bảng trên.

---

## 5. Chỉnh sửa theo màn hình

### 5.1 Shell & Header — `App.tsx`, `Header.tsx`

| # | Việc cần làm | Chi tiết |
| --- | --- | --- |
| H1 | Solid header | Bỏ `backdrop-blur` / translucent; `bg-background border-b`, height 56px |
| H2 | Brand mark | Icon + tên app; bỏ màu violet trên Database icon (mass upload) |
| H3 | Step nav | Giữ breadcrumb/stepper nhưng style Linear: current = `font-medium text-foreground`, others muted; không pill nền dày |
| H4 | Mass Ingestion link | Secondary ghost/outline **neutral**, không `bg-violet-50` |
| H5 | Run ID | Giữ mono; có thể thêm copy-to-clipboard (ops habit) |
| H6 | Mass upload layout | Cùng shell với app chính (một header system), tránh header fork màu khác |

### 5.2 Upload / Profile — `UploadView.tsx` + profile panels

| # | Việc cần làm | Chi tiết |
| --- | --- | --- |
| U1 | Bỏ centered marketing hero | Khi chưa có file: left-aligned title `text-xl font-semibold` + 1 câu phụ ≤ 20 từ |
| U2 | Form layout | Max-width form OK, nhưng không “card floating giữa void”; align với grid app (`max-w-6xl` content) |
| U3 | Dropzone | Border dashed 1px, `hover:border-foreground/30`, **không** scale icon; icon nhỏ 20px |
| U4 | Primary CTA | Full-width trong form OK; bỏ `shadow-md`; loading = spinner + disable, không đổi layout |
| U5 | Post-upload toolbar | Flat bar: tabs segmented (đã có) + “Continue to Pipeline”; bỏ nested `shadow-sm` thừa |
| U6 | `StatisticalProfilePanel` | Sửa gray-on-amber; metrics dạng table/definition list thay vì nhiều mini-cards nếu trùng pattern Result |
| U7 | `SemanticProfilePanel` | Giảm violet/indigo chips; column tags = `bg-muted font-mono text-xs` |
| U8 | `TablePreviewPanel` | Giữ sticky header; giảm shadow; zebra optional rất nhẹ |

### 5.3 Pipeline — `PipelineView.tsx` + `pipelinepanel/*`

Đây là màn hình quan trọng nhất để “dễ theo dõi”.

#### Layout mục tiêu (tham Airbyte sync / Prefect run)

```
┌─ Sticky run strip: Status | WS | elapsed | [Open profile] [Cancel?] ─┐
├─ Main (flex) ──────────────────────────────┬─ Context (optional) ───┤
│  A. HITL / Plan / Clarification (priority) │  Requirement summary   │
│  B. Execution progress / task list         │  or format anomalies   │
│  C. Logs (mono, filterable)                │                        │
└────────────────────────────────────────────┴────────────────────────┘
```

| # | Việc cần làm | Chi tiết |
| --- | --- | --- |
| P1 | Sticky run strip | Gộp status badge + WS indicator + run meta; luôn trên cùng viewport nội dung |
| P2 | Ưu tiên HITL | Khi `awaiting_hitl`, panel checkpoint **trên cùng**, highlight bằng `border-warning` (1px), không banner xanh/tím |
| P3 | Xóa `ReviewSection` numbered circles | Heading `text-sm font-semibold` + description muted |
| P4 | Xóa / redesign Completed review emerald banner | Read-only accordion theo stage; header trắng + badge “Read-only” |
| P5 | Logs | Monospace; severity color chỉ trên prefix; bỏ parse markdown violet bullets nếu có thể plain text |
| P6 | Worker / task cards | Một list row denser (như Dagster step): role label, columns, status; expand instructions |
| P7 | Modal log | Overlay OK; scrim solid `bg-black/40` **không** blur bắt buộc; panel `rounded-lg border` |
| P8 | `HITLCheckpointPanel` | Sticky footer: Approve / Modify / Reject; disable states rõ; progress modify_count dạng text `2 of 5` không progress bar track đầy |
| P9 | `ExecutionPlanPanel` / `TaskCard` | Role badge **một style** (muted + text); bỏ color-per-role nếu đang rainbow |
| P10 | `FormatAnomaliesPanel` | Palette chip cột: dùng **một** accent + opacity, hoặc hash → limited 3 neutrals; bỏ purple/indigo/violet list |
| P11 | `ResolvedValidationPlanPanel` | Bỏ emoji; bỏ violet “Auto-Resolved”; list `divide-y`; CTA primary solid flat |
| P12 | `ValidationResolutionPendingPanel` | Thay `border-2` + `shadow-lg` + round icon glass bằng alert inline: icon + text + border |

### 5.4 Result — `ResultView.tsx`

| # | Việc cần làm | Chi tiết |
| --- | --- | --- |
| R1 | Bỏ centered hero icon 64px | Header trái: title + filename + timestamp; status badge cạnh title |
| R2 | Sửa em-dash trong title | `Pipeline completed` / `Pipeline completed with validation notes` |
| R3 | Summary metrics | Giữ 4 số nhưng **không** “hero metric”; style definition list hoặc compact toolbar stats (Airbyte) |
| R4 | Validation block | **Không** full-bleed `bg-emerald-600` / `bg-amber-600`. Dùng header row: Shield icon + title + `StatusBadge` |
| R5 | F1 circular gauges | Đổi sang bảng số `tabular-nums` (F1, Precision, Recall, Accuracy) như GX; circular optional secondary |
| R6 | Download actions | Primary = format mặc định; secondary outline cho csv/xlsx/parquet; group rõ |
| R7 | Raw JSON | Collapsible mono panel, không card shadow |
| R8 | Preview table | Cùng component vocabulary với `TablePreviewPanel` |

### 5.5 Mass Ingestion — `MassUploadView.tsx`

| # | Việc cần làm | Chi tiết |
| --- | --- | --- |
| M1 | Bỏ violet/indigo accents | Icon + links dùng foreground / primary |
| M2 | Queue status | Map về §4 vocabulary; bỏ `animate-ping` hàng loạt |
| M3 | Selected row | `bg-muted` hoặc `ring-1 ring-primary`, **cấm** `border-l-2` side stripe |
| M4 | Top stats | 4 ô hiện tại → compact strip (label nhỏ + số), không 4 card shadow ngang |
| M5 | Auto-approve toggle | Switch/checkbox chuẩn, label rõ; không badge tím |
| M6 | Detail pane HITL | Đồng bộ component với single-run HITL (reuse panels), cùng CTA style |
| M7 | Progress bar | Track `bg-muted`, fill `bg-primary` solid (đây không phải gradient nếu 1 màu) |

---

## 6. Component inventory cần chuẩn hóa

Tạo (hoặc extract) các primitive dùng chung trước khi polish từng màn:

| Component | Props chính | Thay thế hiện tại |
| --- | --- | --- |
| `StatusBadge` | `status` | Copy STATUS_CONFIG rải rác |
| `Button` | `variant: primary \| secondary \| ghost \| danger`, `size`, `loading` | Class string lặp lại emerald/red/primary |
| `Panel` | `title`, `description?`, `actions?`, `flush?` | `rounded-xl border shadow-sm` mọi nơi |
| `Alert` | `tone: info \| warning \| success \| danger` | Banner emerald/amber full color |
| `Tabs` | controlled | Segmented control copy-paste |
| `EmptyState` | title, action | Text “nothing” / spinner giữa trang |
| `DataTable` | sticky header, mono cells | Preview tables lệch style |
| `StickyActionBar` | children | CTA chôn cuối HITL |

**Không** cần shadcn full install nếu chưa muốn; nhưng nếu adopt shadcn: **customize tokens**, không để default violet theme.

---

## 7. Copy & microcopy

| Hiện tại (ví dụ) | Đề xuất |
| --- | --- |
| “Provide your data file and specific requirements for the AI agent to process.” | “Upload a file and optional cleaning requirements.” |
| “🤖 Auto-Resolved Decisions” | “Auto-resolved decisions” |
| “Pipeline Completed — Validation Notes” | “Pipeline completed with validation notes” |
| “Mass Ingestion Console” pill | Bỏ pill; hoặc text muted “Batch” |

Tone: **ops / factual**, không “agentic magic” marketing.

---

## 8. Accessibility & quality gates

- [ ] Mọi text body ≥ 4.5:1; không gray trên amber/emerald tint
- [ ] Focus ring `ring-2 ring-primary` visible trên button/input
- [ ] HITL: keyboard được Approve/Reject (không chỉ mouse)
- [ ] `prefers-reduced-motion`: tắt ping/spin không cần thiết
- [ ] Không em-dash (`—` / `–`) trên UI
- [ ] **Zero** gradient utilities trong `frontend/src`
- [ ] **Zero** `violet-` / `purple-` / brand-`indigo-` ngoài chart data (nếu chart cần màu, document riêng)
- [ ] Detector: `node …/detect.mjs --json frontend/src` sạch `ai-color-palette`

---

## 9. Lộ trình thực hiện (ưu tiên)

### Phase A — Foundation (1–2 ngày)

1. Khóa token màu trong `index.css` (bỏ dual violet; semantic tokens).
2. Thêm `StatusBadge`, `Button`, `Panel`, `Alert`.
3. Sweep global: xóa violet/purple/indigo brand; xóa gradient nếu phát sinh; thay side-stripe.

### Phase B — Pipeline & HITL (ưu tiên UX theo dõi)

4. Sticky run strip + reorder HITL-first.
5. Redesign HITL panels + sticky actions.
6. Flatten Completed review / Resolved validation banners.

### Phase C — Upload / Result / Mass

7. Upload form denser, left-aligned.
8. Result report kiểu GX/dbt (bảng metrics, bỏ celebration + colored banner).
9. Mass queue status vocabulary + selection style.

### Phase D — Polish

10. Skeleton loading; empty states; copy pass.
11. `/impeccable audit frontend` + `/impeccable polish`.
12. Ghi `DESIGN.md` từ code sau khi ổn định.

---

## 10. Definition of Done (visual)

Một reviewer quen Linear/Airbyte nhìn vào sẽ:

1. Trong **3 giây** biết run đang `Running` hay `Needs review`.
2. Không đoán “template AI SaaS tím”.
3. Không thấy gradient, celebration banner, hay ping rainbow.
4. Approve HITL không cần scroll tìm nút.
5. Result đọc được như validation report, không như landing “Success!”.

---

## 11. File đụng chạm chính (checklist PR)

- [ ] `frontend/src/index.css`
- [ ] `frontend/src/App.tsx`
- [ ] `frontend/src/components/layout/Header.tsx`
- [ ] `frontend/src/components/views/UploadView.tsx`
- [ ] `frontend/src/components/views/PipelineView.tsx`
- [ ] `frontend/src/components/views/ResultView.tsx`
- [ ] `frontend/src/components/views/MassUploadView.tsx`
- [ ] `frontend/src/components/views/StatisticalProfilePanel.tsx`
- [ ] `frontend/src/components/views/SemanticProfilePanel.tsx`
- [ ] `frontend/src/components/views/TablePreviewPanel.tsx`
- [ ] `frontend/src/components/views/RequirementSummaryPanel.tsx`
- [ ] `frontend/src/components/views/pipelinepanel/*` (HITL, Execution, Validation, FormatAnomalies, TaskCard, …)
- [ ] (mới) `frontend/src/components/ui/*` primitives

---

## 12. Ngoài phạm vi brief này

- Thay đổi backend API / WebSocket protocol
- Marketing landing page
- Dark mode overhaul bắt buộc (nên giữ parity token, nhưng có thể phase sau)
- Viết lại toàn bộ copy tiếng Việt (hiện UI chủ yếu English)

---

*Brief này là backlog thiết kế/implement. Không thay code cho đến khi được yêu cầu implement theo Phase A→D.*

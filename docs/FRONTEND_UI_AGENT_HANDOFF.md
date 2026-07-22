# Frontend UI Makeover — Agent Handoff

**Branch:** `uimakeover`  
**Mục đích:** Một file duy nhất để `@` vào Cursor khi implement. Không đổi nghiệp vụ / API / flow; chỉ nâng UI.

---

## Cách dùng trong Cursor

1. Mở chat Agent trên branch `uimakeover`.
2. Attach (hoặc `@`) **file này**:
   ```
   @docs/FRONTEND_UI_AGENT_HANDOFF.md
   ```
3. (Khuyến nghị) cũng attach:
   ```
   @PRODUCT.md
   ```
4. Paste prompt theo phase bên dưới. **Một phase / một PR hoặc một session**, đừng làm cả A→D một lần nếu context dài.

**Nguồn sự thật**

| File | Vai trò | Khi nào đọc |
| --- | --- | --- |
| `PRODUCT.md` | Who / why / principles / anti-references | Luôn |
| `docs/FRONTEND_UI_AGENT_HANDOFF.md` (file này) | What to build, order, DoD, prompts | Luôn khi code UI |
| `docs/frontend-ui-redesign-brief.md` | Chi tiết dài, bảng tham chiếu sản phẩm | Khi cần sâu hơn |
| `DESIGN.md` | Visual tokens sau khi ổn định | Chưa có — tạo bằng `/impeccable document` sau Phase A hoặc D |

Không cần “tung thêm” nhiều file. Handoff + PRODUCT là đủ để agent làm việc.

---

## Non-negotiables (đọc trước khi sửa)

1. **Giữ nguyên flow:** upload → profile → pipeline → HITL → result. Mass ingestion tồn tại nhưng **không ưu tiên**.
2. **Cấm gradient** mọi dạng (`bg-gradient-*`, `from-*`/`to-*` nền, gradient text, mesh).
3. **Cấm AI SaaS chrome:** violet / purple / brand-indigo, glow, glass/blur trang trí, celebration banner full màu.
4. **Register:** product console (ops), không marketing landing.
5. **Personality:** calm, precise, trustworthy. Copy ops/factual, không “AI magic”.
6. **A11y:** WCAG AA; tôn trọng `prefers-reduced-motion`.
7. **Stack:** React + Tailwind trong `frontend/`; giữ `lucide-react`; không đổi backend.

### Dials

| Dial | Value |
| --- | --- |
| DESIGN_VARIANCE | 3 |
| MOTION_INTENSITY | 2 |
| VISUAL_DENSITY | 7 |

### Visual references (học pattern, không copy skin)

- Pipeline theo dõi: **Airbyte + dbt Cloud**
- Density / chrome: **Linear + Stripe Dashboard**
- Màn Result / validation: **Great Expectations / Cleanlab**

---

## Product snapshot (từ PRODUCT.md)

- **Users:** primary data engineer/analyst; secondary domain expert.
- **Success:** (1) biết ngay Running vs Needs review; (2) profile/EDA đọc được trước khi quyết định.
- **Principles:** preserve the job; state before decoration; inspectability; HITL gần quyết định; calm ops console.

---

## Target design system (tóm tắt)

### Color (restrained, flat only)

- Một accent = giữ `--primary` blue hiện có trong `index.css` (hoặc đổi 1 lần sang teal muted — **không** giữ violet song song).
- Semantic: `--success`, `--warning`, `--destructive`, `--info` chỉ cho state.
- Sweep: xóa mọi `violet-*`, `purple-*`, brand-`indigo-*` khỏi chrome.
- Surface: border 1px thay shadow; không cream/beige body.

### Type / shape / motion

- Một sans (`system-ui` / Inter / Geist). Mono cho run id / JSON / metrics số.
- Radius: controls 6–8px, panels 8–10px. Shadow mặc định off.
- Motion 150–200ms; cấm `animate-ping` hàng loạt (tối đa 1 live dot cho Running).
- Không emoji trong UI; không em-dash (`—`/`–`).

### Status vocabulary (bắt buộc dùng chung)

| State | Label | Tone |
| --- | --- | --- |
| `queued` | Queued | muted |
| `running` | Running | info/primary (+ optional 1 dot) |
| `awaiting_hitl` | Needs review | warning |
| `completed` | Completed | success |
| `failed` | Failed | destructive |
| `cancelled` | Cancelled | muted |

Component: `StatusBadge`.

### Primitives cần tạo (`frontend/src/components/ui/`)

`StatusBadge`, `Button`, `Panel`, `Alert`, `Tabs` (reuse nếu đã có), `StickyActionBar`, (sau) `EmptyState` / table shared.

---

## Work plan (làm theo thứ tự)

### Phase A — Foundation

**Mục tiêu:** token + primitives + sweep màu AI.

- [ ] `frontend/src/index.css` — semantic tokens; primary duy nhất; không violet dual
- [ ] `frontend/src/components/ui/*` — StatusBadge, Button, Panel, Alert, StickyActionBar
- [ ] Sweep toàn `frontend/src`: bỏ violet/purple/indigo brand, gradient, side-stripe `border-l-2`, emoji
- [ ] `Header.tsx` / `App.tsx` — solid header, Mass link neutral

**Prompt Cursor (Phase A):**

```
@PRODUCT.md @docs/FRONTEND_UI_AGENT_HANDOFF.md

Implement Phase A only (Foundation) on branch uimakeover.
- Lock tokens in frontend/src/index.css (no gradients, no violet dual brand).
- Add ui primitives: StatusBadge, Button, Panel, Alert, StickyActionBar.
- Global sweep: remove violet/purple/brand-indigo, decorative blur, side-stripe selection, emoji.
- Update Header + App mass shell to match.
Do not redesign Pipeline/Result layouts yet. No backend changes.
```

### Phase B — Pipeline & HITL (ưu tiên theo dõi)

**Mục tiêu:** 3 giây biết Running vs Needs review; Approve không phải scroll tìm.

- [ ] Sticky run strip (status, WS, run meta, actions)
- [ ] Khi `awaiting_hitl`: checkpoint panel trên cùng + `border-warning` 1px
- [ ] HITL sticky Approve / Modify / Reject
- [ ] Bỏ numbered indigo circles; bỏ emerald celebration banners
- [ ] Logs mono; task list denser; role badge một style

**Files:** `PipelineView.tsx`, `pipelinepanel/*`

**Prompt Cursor (Phase B):**

```
@PRODUCT.md @docs/FRONTEND_UI_AGENT_HANDOFF.md

Implement Phase B only (Pipeline & HITL).
Follow the sticky run-strip layout and HITL-first rules in the handoff.
Reuse Phase A primitives. No gradients. No violet. No celebration banners.
Do not change Upload/Result/Mass beyond shared components.
```

### Phase C — Upload / Result / Mass

- [ ] Upload: left-aligned, flat dropzone, no marketing hero
- [ ] Profile panels: fix gray-on-amber; muted mono tags
- [ ] Result: report layout (GX-style metrics table); no 64px hero; no full-bleed green/amber header
- [ ] Mass: status vocabulary §; selection `bg-muted`/`ring`; không ưu tiên polish sâu

**Prompt Cursor (Phase C):**

```
@PRODUCT.md @docs/FRONTEND_UI_AGENT_HANDOFF.md

Implement Phase C (Upload, Result, light Mass pass).
Result must read like a validation report, not a success landing.
Mass: only status vocabulary + selection style + kill violet; no feature work.
```

### Phase D — Polish

- [ ] Skeleton / empty states / copy pass (bảng microcopy trong brief)
- [ ] `/impeccable audit frontend` + fix
- [ ] `/impeccable document` → tạo `DESIGN.md` từ code đã ổn
- [ ] Detector sạch `ai-color-palette`

**Prompt Cursor (Phase D):**

```
@PRODUCT.md @docs/FRONTEND_UI_AGENT_HANDOFF.md

Phase D polish: loading/empty states, copy cleanup per handoff, a11y pass.
Then summarize remaining gaps. Do not invent new features.
```

---

## Screen checklist (ID → file)

| ID | Việc | File chính |
| --- | --- | --- |
| H1–H6 | Shell / header | `App.tsx`, `Header.tsx` |
| U1–U8 | Upload + profile | `UploadView.tsx`, `*ProfilePanel.tsx`, `TablePreviewPanel.tsx` |
| P1–P12 | Pipeline + HITL | `PipelineView.tsx`, `pipelinepanel/*` |
| R1–R8 | Result | `ResultView.tsx` |
| M1–M7 | Mass (light) | `MassUploadView.tsx` |

Chi tiết từng hàng: `docs/frontend-ui-redesign-brief.md` §5.

---

## Definition of Done

Reviewer quen Linear/Airbyte nhìn vào sẽ:

1. Trong 3 giây biết `Running` vs `Needs review`.
2. Không đoán “AI SaaS tím”.
3. Zero gradient; zero celebration banner; zero rainbow ping.
4. HITL Approve không cần scroll tìm nút.
5. Result giống validation report, không giống landing “Success!”.
6. Flow nghiệp vụ không đổi; API/WS không đổi.

**Gates**

- [ ] Không `—` / `–` trên UI
- [ ] Không `violet-` / `purple-` / brand-`indigo-` trong chrome
- [ ] Contrast body ≥ 4.5:1
- [ ] `detect.mjs --json frontend/src` không còn `ai-color-palette`

---

## Out of scope

- Backend, WebSocket protocol, agent logic
- Marketing landing
- Mass ingestion feature expansion
- Dark mode overhaul bắt buộc (parity token OK, polish sau)
- Đổi copy sang tiếng Việt toàn bộ

---

## Gợi ý session đầu tiên

Chỉ cần paste:

```
@PRODUCT.md @docs/FRONTEND_UI_AGENT_HANDOFF.md

Start Phase A only. Confirm plan in 5 bullets, then implement.
```

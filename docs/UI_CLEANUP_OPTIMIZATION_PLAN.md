# UI Cleanup & Optimization Plan — Centinelas PR frontend

> **Scope.** This plan covers the diagnostic frontend at `frontend/` (React 18 +
> Vite + Tailwind + shadcn/ui). Per [ADR 0001](../README.md), this surface is a
> **development / diagnostic tool for this producer only** — the supported
> product surface is the hub app (`thehub-pr/server/frontend`). That framing
> shapes every recommendation below: the goal is a *lean, consistent, fast
> diagnostic console*, not a consumer product. Where a change would only matter
> for a public-facing app, it is called out as **defer**.

**Status:** Draft for review · **Owner:** frontend · **Date:** 2026-07-13

---

## 1. Executive summary

The frontend works and is reasonably componentized, but it carries three kinds of
drag:

1. **Consistency debt** — the UI is accidentally bilingual (Spanish core, English
   Pipeline), every page re-implements the same fetch/loading/empty scaffolding,
   and two different filter idioms coexist.
2. **Dead / unused surface** — an unrouted legacy legislative layer, ~40 unused
   shadcn primitives, and several heavy dependencies (`moment`, `jspdf`,
   `html2canvas`, `canvas-confetti`, Stripe, dnd) that a diagnostic console does
   not need.
3. **Under-used platform** — `@tanstack/react-query` is installed and wired
   (`lib/query-client.js`) but **no page uses it**; `next-themes` + a full `.dark`
   palette exist but there is **no theme toggle**; `lib/app-params.js` can read
   URL params but filters never sync to the URL.

The plan is organized into six workstreams, sequenced so that foundational
refactors (data layer, shared primitives) land before the surface polish that
depends on them. Each item lists concrete files and an effort estimate
(S ≈ <½ day, M ≈ ½–1 day, L ≈ 1–2 days).

---

## 2. Current-state map

| Area | Files | Notes |
|---|---|---|
| Routing | `src/App.jsx` | 18 routes; legacy legislative + auth routes retained |
| Layout | `components/Layout.jsx`, `Header.jsx`, `Footer.jsx` | Sticky header, 7-item nav, no theme control |
| Core surfaces | `pages/Monitor.jsx`, `Signals.jsx`, `Matters.jsx`, `MatterDetail.jsx`, `Sources.jsx`, `Handoff.jsx`, `Pipeline.jsx`, `PipelineItemDetail.jsx` | The diagnostic workflow |
| Legacy surfaces | `pages/LawTable.jsx`, `LawDetail.jsx`, `Authors.jsx`, `AuthorDetail.jsx`, `Profile.jsx` + `components/laws/*` | Only `/tabla` is reachable from nav |
| Domain components | `components/monitor/*`, `components/lifecycle/*`, `components/pipeline/*` | Badges, cards, timeline — the good, reusable core |
| Design tokens | `src/index.css`, `tailwind.config.js` | HSL token system, light + `.dark`, Bebas Neue / Montserrat |
| Data | `api/appClient.js` (localStorage entities), `api/pipelineClient.js` (FastAPI) | Two backends behind one UI |

---

## 3. Workstream A — Data & state layer (foundation)

**Problem.** Six pages (`Monitor`, `Signals`, `Matters`, `MatterDetail`,
`Sources`, `Handoff`) each hand-roll the *same* pattern: a local `safeList()`
copy, a `useEffect` with an `active` cancellation flag, `useState` for
rows + `loading`, and a legacy-`Law` fallback fetch that **always runs even when
the primary list returns data**. React Query is configured but bypassed.

### A1. Adopt React Query for all reads · **M**
- Replace the per-page `safeList` + `useEffect` blocks with a small set of query
  hooks in a new `src/hooks/queries.js`, e.g. `useSignals()`, `useMatters()`,
  `useSources()`, `usePipelineItems(domain)`, `usePipelineStatus()`.
- Centralize the `entity.list()` try/catch (today copy-pasted 6×) inside one
  `listEntity(name, sort, limit)` helper.
- **Wins:** request dedup + caching across pages (Monitor and Signals both fetch
  `Signal`), automatic retry/stale handling from `query-client.js`, and deletion
  of ~20 lines of boilerplate per page.

### A2. Fix the always-on legacy fallback · **S**
- Today Monitor/Signals/Matters/Handoff fetch legacy `Law` rows on **every**
  load to use only if the primary list is empty. Make the fallback lazy: fetch
  `Law` only when the primary query resolves empty (React Query `enabled` flag),
  or fold the fallback into the query hook so callers don't repeat it.

### A3. URL-synced filters · **S–M**
- `Signals` (query + status), `Sources` (query), and `Pipeline` (domain) hold
  filter state in `useState`, so a filtered view can't be shared or restored on
  reload. Sync them to search params (`react-router` `useSearchParams`, or the
  existing `lib/app-params.js`). Bonus: Pipeline currently **refetches from the
  server on every domain click** — with URL state + React Query cache, most
  domain switches become instant client-side reads.

---

## 4. Workstream B — Shared UI primitives (kill the copy-paste)

**Problem.** The same markup is duplicated across nearly every page:
`div.max-w-7xl mx-auto px-4 py-8 space-y-6`, the loading line
`<p className="rounded-xl border p-6 text-muted-foreground">Cargando…</p>`, the
empty-state variant of the same, and the page `<h1>` + subtitle block.

### B1. Layout & state primitives · **M**
Introduce four tiny components in `components/common/`:
- `PageContainer` — the `max-w-7xl` wrapper (one place to tune width/padding).
- `PageHeader` — title + description + optional action slot (Monitor, Signals,
  Matters, Sources, Handoff, Pipeline all repeat this).
- `LoadingState` / `EmptyState` — replace the inline `<p className="rounded-xl
  border p-6 …">` clones; give them `role="status"` for a11y.

### B2. Unify the card idiom · **S**
- `SignalCard` and `PipelineItemCard` (inline in `Pipeline.jsx`) solve the same
  problem — title + source + badge row — with different structure. Extract the
  badge-row and title-with-source header into shared bits so the two cards read
  as one system.

### B3. One filter idiom · **S**
- `Signals` uses a native `<select>`; `Pipeline` uses pill buttons. Pick one
  (pills read better for ≤6 options; the `ToggleGroup` primitive already exists)
  and apply to both.

---

## 5. Workstream C — Interaction & workflow polish

The Handoff and Pipeline flows are the interactive heart of the tool; they have
the sharpest rough edges.

### C1. Handoff: real feedback instead of raw state strings · **M**
- `Handoff.jsx` renders machine status like `accept_ok` and
  `accept_failed: <error.message>` directly to the user. The `<Toaster />` is
  mounted in `App.jsx` but unused. Route action results through `toast()` with
  human copy (success / error), and clear the inline string.
- **Destructive actions need confirmation.** "Rechazar" and "Aceptar / crear
  registro" fire immediately. Wrap them in the existing `alert-dialog` primitive.
- After a successful accept/reject, **invalidate the matters query** so the list
  reflects the new state instead of going stale.

### C2. Optimistic + guarded pipeline filtering · **S**
- With A1/A3 in place, keep the full item set in cache and filter by domain
  client-side; only hit the server when the cache is cold.

### C3. Global command palette (optional) · **M** · *defer-friendly*
- `cmdk` is already a dependency and the `command` primitive exists. A ⌘K palette
  to jump to a matter/signal/source id would fit the "diagnostic console" framing
  well. Low priority; list as a stretch item.

### C4. Consistent detail-page back-nav · **S**
- `PipelineItemDetail` has a "Back to pipeline" link; `MatterDetail` has none.
  Add a shared `BackLink` and use it on all detail pages.

---

## 6. Workstream D — Internationalization / copy consistency

**Problem (highest-visibility).** The product is bilingual by accident:
- Spanish: Header, Home, Monitor, Signals, Matters, Sources, Handoff, all
  lifecycle badges.
- English: `Pipeline.jsx` and `PipelineItemDetail.jsx` end-to-end ("Universal
  intake", "Loading items…", "Backend not reachable", "Back to pipeline",
  "domain-routed"), plus the nav label "Pipeline" and "Handoff".

### D1. Pick one primary language · **M**
- Recommendation: **Spanish** for all user-facing surfaces (it's the majority and
  the domain is Puerto Rico public info). Translate the two Pipeline pages.
- Keep code identifiers, domain slugs, and repo names (`thehub-pr`) in English.

### D2. Extract strings to a lightweight dictionary · **M** · *defer for diagnostic-only*
- A full i18n framework is overkill here. A single `src/i18n/es.js` string map
  (or even co-located constants) makes future audits trivial and prevents the
  drift from recurring. Mark as optional given the diagnostic scope.

---

## 7. Workstream E — Theming, design tokens & accessibility

### E1. Wire up the dark theme (or delete it) · **S–M**
- `index.css` ships a complete `.dark` palette and `next-themes` is a dependency,
  but nothing toggles `.dark` and there is no `ThemeProvider`. Either add a
  header toggle (`next-themes` + a `sun/moon` button — both icon and lib already
  available) **or** remove the dead `.dark` block. Recommendation: wire it — it's
  cheap and useful for a console people stare at.

### E2. Accessibility pass · **M**
- Loading spinner in `App.jsx` needs `role="status"` + visually-hidden label.
- Status is currently conveyed by color alone in several badges; ensure every
  badge pairs color with text (most already do — audit `ConfidenceBadge`,
  `HandoffStatusBadge`, `DomainBadge`, dispatch chips for contrast in both
  themes).
- Verify focus-visible rings on the custom (non-shadcn) `<button>`/`<Link>`
  controls in `Header`, `Pipeline` pills, and hero CTAs.
- Add a single top-level **error boundary** so a render throw doesn't blank the
  whole app.

### E3. Font loading · **S**
- `index.css` pulls Bebas Neue + 5 Montserrat weights via a blocking
  `@import url(fonts.googleapis…)` and then forces them with `!important`.
  Move to `<link rel="preconnect">` + `<link rel="stylesheet">` in `index.html`
  (non-blocking) and drop the `!important` overrides by fixing specificity.

---

## 8. Workstream F — Dependency & bundle diet

**Problem.** `frontend/package.json` and `components/ui/` carry far more than the
diagnostic surface uses. 49 UI primitives exist; the app imports roughly a dozen
(`card`, `badge`, `button`, `toaster`/`toast`). Several heavy libs appear unused
by the current pages.

### F1. Prune unused shadcn primitives · **M**
- Audit `components/ui/*` against actual imports; remove the unreferenced ones
  (candidates: `carousel`, `drawer`, `input-otp`, `resizable`, `sidebar`,
  `navigation-menu`, `context-menu`, `menubar`, `chart`, `pagination`,
  `breadcrumb`, `hover-card`, `aspect-ratio`, …). Each removal also drops its
  Radix/embla dep.

### F2. Retire redundant / heavy deps · **M**
- **Date libs:** both `moment` **and** `date-fns` are present. Standardize on
  `date-fns` (tree-shakeable) and drop `moment`.
- **Likely-unused in the diagnostic surface** (verify with a grep, then remove):
  `jspdf`, `html2canvas`, `canvas-confetti`, `@stripe/*`, `@hello-pangea/dnd`,
  `input-otp`, `embla-carousel-react`, `framer-motion`, `lodash` (replace stray
  uses with native/`clsx`).
- Each removal is gated on "no imports remain" — do it as a verified sweep, not a
  blind delete.

### F3. Decide the legacy legislative layer's fate · **L**
- `pages/LawDetail`, `LawTable`, `Authors`, `AuthorDetail`, `Profile` and most of
  `components/laws/*` (`VoteButtons`, `CommentSection`, `WeeklyVoteChart`,
  `LawCalendar`, `CategorySubscription`, `LawTimeline`, `LawDashboard`,
  `LawFilters`) are the pre-federation legislative UI. Only `/tabla` is linked
  from nav; several `laws/*` components appear entirely unrouted.
- **Options:** (a) prune to the minimal MoneySweep bridge the routing comment
  describes and delete the rest; (b) move the whole legacy layer behind a single
  `/legacy` route and stop shipping it in the main bundle. Recommendation: (a),
  after confirming nothing the hub relies on imports these.

---

## 9. Suggested sequencing

```
Phase 1 (foundation)   A1 A2  →  B1 B2 B3            # data layer + shared primitives
Phase 2 (workflow)     C1 C4  →  A3 C2               # feedback, guards, URL state
Phase 3 (consistency)  D1     →  E1 E2 E3            # one language, theme, a11y
Phase 4 (diet)         F1 F2  →  F3                  # prune deps & legacy (verified sweep)
Optional / stretch     C3 D2                          # command palette, string dictionary
```

Rationale: Phases 1–2 are pure refactors that make every later change smaller;
D/E are user-visible polish; F is deletion, safest last once the surface is
settled.

---

## 10. Guardrails & acceptance criteria

- **No behavior regressions:** each phase keeps `npm run lint`, `npm run
  typecheck`, and `npm run build` green.
- **Verified deletions only:** F1–F3 removals must be preceded by a repo-wide
  import grep showing zero references.
- **Bundle target:** report `vite build` bundle size before/after; F-phase should
  measurably shrink it.
- **Diagnostic-first:** no item adds consumer-product scope (payments, social,
  gamification) to a surface ADR 0001 defines as diagnostic-only.
- **Federation-safe:** confirm nothing under `frontend/` that the hub imports is
  removed (check `thehub-pr` consumption before pruning shared shapes).

---

## 11. Out of scope (explicitly deferred)

- A full design-system rebuild or visual rebrand — tokens in `index.css` are fine.
- Server/API changes in `server/backend` or `api/*` beyond what A1's query hooks
  need.
- Building the consumer product surface — that lives in `thehub-pr`.

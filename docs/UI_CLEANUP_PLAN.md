# UI Cleanup & Optimization Plan

> Scope: the **diagnostic-only frontend** in `frontend/` (ADR 0001, Phase 2).
> This is Centinelas' internal development/diagnostic surface — not the
> federation's product UI (that is `thehub-pr`). The goal here is a lean,
> consistent, correctly-branded diagnostic tool, **not** a full public product.
> This plan tightens what exists; it does not add product scope.

A leverage-ordered ledger for bringing the frontend from "works, but drifting"
to "clean, consistent, and cheap to maintain." Findings below are from an audit
of `frontend/src` on branch `claude/centinelas-pr-ui-cleanup-ingcws`.

---

## Executive summary

The frontend is a working Vite + React 18 + Tailwind + Radix/shadcn app that was
migrated from a prior "MoneySweep / legislative" template. The migration is
**~70% done**: the new `Signal → Matter → Handoff` model and the `/pipeline`
surface are in place, but three kinds of debt remain layered on top:

1. **Branding & vocabulary drift** — legacy `Law / vote / author` pages, routes,
   and nav links still ship alongside the new model, and `MoneySweep` naming
   leaks into UI copy. This directly blocks the README's **Branding release
   gate** ("100 percent Centinelas naming, metadata, routes, and visual
   identity").
2. **Template bloat** — ~2/3 of the shadcn primitives and a long tail of heavy
   dependencies (Stripe, three.js, Leaflet, jsPDF, three separate toast systems)
   are unused Base44-era scaffolding.
3. **Inconsistent design & workflow plumbing** — no shared page shell, status
   colors hardcoded instead of tokenized, a dead dark theme, a render-blocking
   font import, and the same data-loading helper copy-pasted across six pages.

None of this is a rewrite. It is deletion, extraction, and tokenization — the
work is mechanical and low-risk, and most of it shrinks the codebase.

---

## Current-state map

| Surface | Data source | State |
|---|---|---|
| `/`, `/monitor`, `/signals`, `/matters`, `/matters/:id`, `/sources`, `/handoff` | `appClient` (localStorage, seeded) | New model — **keep, polish** |
| `/pipeline`, `/pipeline/:id` | `pipelineClient` (FastAPI) | New model — **keep, polish** |
| `/tabla`, `/ley/:id`, `/autores`, `/autor/:id`, `/perfil` | `appClient` legacy `Law`/`Author` | Legacy — **retire or convert** |

**Component inventory**
- `components/laws/`: 9 files. **5 are dead code** (`LawCard`, `LawFilters`,
  `LawDashboard`, `LawCalendar`, `WeeklyVoteChart` — zero importers). The other 4
  (`VoteButtons`, `CommentSection`, `CategorySubscription`, `LawTimeline`) are
  imported **only** by the legacy `LawDetail`/`Profile` pages.
- `components/ui/`: 49 shadcn primitives; **~16 are actually imported** by app
  code. The rest (`accordion`, `carousel`, `sidebar`, `menubar`, `command`,
  `drawer`, `chart`, `table`, `pagination`, `resizable`, `context-menu`, …) are
  unused.
- `components/lifecycle/`, `components/monitor/`, `components/pipeline/`: the
  real, current design language — small, focused, reused.

---

## Findings & actions

### P0 — Branding & vocabulary (blocks the Branding release gate)

**Findings**
- `Header.jsx:12` still links `/tabla` as "Legislativo"; the logo subtitle
  (`Header.jsx:39`) reads "Señal temprana → MoneySweep".
- `"MoneySweep"` appears **24×** in JSX. Some are legitimate (it is the named
  sibling system), but UI chrome and CTAs ("Ver handoff MoneySweep") mix product
  branding with a sibling-system name.
- Legacy routes are live and cross-linked: `/tabla`, `/ley/:id`, `/autores`,
  `/autor/:id`, `/perfil` (`App.jsx:63-68`), with internal `Link`s in
  `LawTable`, `Authors`, `AuthorDetail`, `Profile`, `LawDetail`.
- Two vocabularies coexist in the UI: `Law / voto / autor` (MoneySweep-era) vs
  `Signal / Matter / Entity` (the intended model, per README "UI priorities").
- Language mix: nav labels are Spanish (`Señales`, `Asuntos`, `Fuentes`) but
  `Monitor`, `Pipeline`, `Handoff` stay English, and the entire `/pipeline`
  surface is English while the rest is Spanish.

**Actions**
1. **Decide the fate of the legacy legislative surface** (see Open Questions).
   Recommended: **convert, don't delete** — `LawTable → Signals table view`,
   `Authors/AuthorDetail → Entity profiles`, retire `Profile`'s vote history.
   Until converted, remove `/tabla` ("Legislativo") from the primary nav so the
   default experience is 100% the new model; keep the routes reachable only as
   an explicit "legacy/diagnostic" link.
2. **Contain `MoneySweep` naming** to where it means the sibling system (handoff
   target, lifecycle stages 4–6). Replace product-chrome uses. Add a lint guard
   (a `ruff`-equivalent grep in CI, or an eslint `no-restricted-syntax` rule)
   asserting no bare `MoneySweep` in headings/logo/titles.
3. **Pick one UI language** (Spanish is dominant and the product is PR-civic).
   Localize the `/pipeline` surface and the residual English nav labels, or
   introduce a tiny i18n string map so the choice is centralized rather than
   scattered.
4. **Unify vocabulary** on `Signal / Matter / Entity / Source / Handoff`; purge
   `vote`/`voto`/`author`/`autor` from any surface that survives.

### P0 — Design-system consistency

**Findings**
- **Render-blocking font import**: `index.css:1` pulls Google Fonts over the
  network at the top of the stylesheet, with `Bebas Neue` applied to all headings
  via `!important` (`index.css:44-45`). This blocks first paint, causes FOUT, and
  adds an external dependency to an otherwise self-contained diagnostic tool.
- **Dead dark theme**: a full `.dark` palette exists (`index.css:47-68`) but
  there is **no `ThemeProvider`/toggle wired** (`next-themes` is a dependency but
  only referenced by the unused `sonner` primitive), and only **2 `dark:`
  utilities** exist in the entire app. The dark theme can never activate.
- **Alarm-red monochrome palette**: every token hue is `0°` (red), including
  `background`, `border`, `card`, `muted`. A civic *early-warning* monitor reads
  as permanently in an error state, and red primary on red-tinted surfaces is a
  contrast risk.
- **No shared page shell**: `max-w-7xl mx-auto px-4 py-8` is hardcoded in **10
  pages**; section/hero markup is copy-pasted.
- **Hardcoded status colors**: `text-emerald / text-red / text-slate` literals
  appear **43×** for confidence/dispatch/handoff tones instead of semantic
  tokens — inconsistent across pages and not theme-aware.

**Actions**
1. **Self-host the fonts** (or drop to a system stack) and remove the
   `@import` + `!important`. Move heading font to a Tailwind `fontFamily` token.
2. **Either wire dark mode or delete it.** For a diagnostic tool, recommend
   deleting the `.dark` block and `next-themes` unless a toggle is actually
   wanted; if wanted, add a `ThemeProvider` + toggle and audit contrast.
3. **Re-evaluate the palette**: keep red as the *alert/urgency* accent, but move
   the neutral surfaces (`background`, `card`, `border`, `muted`) to true
   neutrals. Introduce **semantic status tokens** (`--status-ok`,
   `--status-warn`, `--status-risk`, `--status-neutral`) and map the 43 hardcoded
   color usages onto them.
4. **Extract a `<PageShell>`** (max-width, padding, optional hero/eyebrow/title)
   and a `<PageHero>`; migrate the 10 pages onto it.

### P1 — Interactive workflow

**Findings**
- **`safeList` is copy-pasted across 6 pages** (`Monitor`, `Signals`, `Matters`,
  `Handoff`, `Sources`, `MatterDetail`), each re-implementing the same
  "list entity, fall back to legacy `Law` mapping, swallow errors → `[]`"
  pattern.
- **Silent failure**: because `safeList` catches and returns `[]`, a broken data
  layer is visually indistinguishable from "no data." Only `/pipeline` surfaces a
  real "backend not reachable" state (`Pipeline.jsx:113`); the localStorage pages
  cannot fail visibly.
- **Duplicated loading/empty markup**: the inline
  `rounded-xl border p-6 text-muted-foreground` "Cargando…/No hay…" block appears
  **14×**; the `skeleton` primitive exists but is never used.
- **Ad-hoc, inconsistent filtering**: `Signals` uses raw `<input>`/`<select>`;
  `Pipeline` uses pill buttons; `Matters`/`Sources` differ again. No shared
  filter/search primitive, so behavior (debounce, empty-state copy, clering) is
  inconsistent.
- **Disconnected surfaces**: the localStorage legislative model and the FastAPI
  pipeline model share a nav bar but no conceptual bridge — a user cannot tell
  they are two systems or how they relate.

**Actions**
1. **Extract a `useEntityList(entityName, opts)` hook** (or `lib/appQuery.js`)
   that centralizes list + legacy fallback + a real `error` state, and adopt
   `@tanstack/react-query` (already a dependency) for caching/refetch instead of
   per-page `useEffect`.
2. **Add explicit `error` / `empty` / `loading` states** everywhere; distinguish
   "data layer failed" from "no rows." Reuse across pages via a shared
   `<AsyncBoundary>` / `<ListState>` component built on `skeleton`.
3. **Build one `<FilterBar>` primitive** (search + faceted selects/pills) and
   adopt it in `Signals`, `Matters`, `Sources`, `Pipeline`.
4. **Add a one-line orientation** on `/monitor` (or a small "how the two
   surfaces relate" affordance) so the localStorage vs pipeline split is legible.

### P1 — Dependency & primitive diet

**Findings**
- **Unused heavy dependencies** (Base44-template residue), verified 0-import in
  `frontend/src`: `@stripe/*` (2), `three`, `react-leaflet`, `jspdf`,
  `html2canvas`, `canvas-confetti`, `@hello-pangea/dnd`. Also **redundant**
  libraries: `moment` (use the already-present `date-fns`), and **three** toast
  systems (`react-hot-toast`, `sonner`, `@radix-ui/react-toast`) — pick one.
- **Do NOT remove without first retiring the consuming UI** (these are *not*
  unused): `input-otp` backs `components/ui/input-otp`, which the **live
  `/register` route** imports (`pages/Register.jsx:8`); `embla-carousel-react`
  backs `components/ui/carousel` and can only be dropped **together with** that
  primitive (same coupling as `react-day-picker`/`calendar` ↔ the dead
  `LawCalendar`). Prune the primitive first, then the package.
- **~33 of 49 `components/ui` primitives** are never imported.
- **5 dead `components/laws` components** and (pending the P0 decision) up to 4
  more once legacy pages are retired.

**Actions**
1. **Delete the 5 dead `laws/` components** now (zero importers, zero risk).
2. **Prune unused `ui/` primitives** — keep only the ~16 imported plus a small
   reserve; deletion is safe since each is self-contained.
3. **Remove unused dependencies** from `package.json`; consolidate to **one**
   date library and **one** toast system. Verify with `npm run build` +
   `depcheck`.
4. Track bundle size before/after (`vite build` reports it) as the success
   metric for this section.

### P2 — Accessibility (blocks the WCAG AA release gate)

**Findings**
- **Color-only status encoding**: confidence bands, dispatch status, and handoff
  status are conveyed by color alone (the 43 hardcoded tones). Fails WCAG 1.4.1.
- **Contrast risk**: red primary/foreground on red-tinted `background`/`card`.
- **Focus & semantics**: raw `<input>`/`<select>` in `Signals` lack associated
  error/`aria` states; the 7-item nav has no active indicator beyond font weight
  (weight-only is not a sufficient non-color cue for some users).

**Actions**
1. Pair every status color with a **text label or icon** (the
   `lifecycle/*Badge` components already do this — extend the pattern to
   dispatch/handoff tones).
2. Run an automated pass (`axe`/Lighthouse) and fix contrast on the new palette;
   add a Playwright + `axe-core` smoke check to CI (aligns with the README's QA
   gate).
3. Add visible focus rings (the `--ring` token exists — apply it) and an
   `aria-current` active-route indicator in the nav.

---

## Phasing & sequencing

| Phase | Theme | Risk | Net LOC |
|---|---|---|---|
| **1. Delete** | Remove 5 dead `laws/` components, unused `ui/` primitives, unused deps | Very low | **−−** |
| **2. Tokenize** | Semantic status tokens, page shell, self-host fonts, kill/adopt dark mode | Low | ≈0 |
| **3. Debloat data layer** | `useEntityList` hook, real error states, shared `FilterBar`/`ListState` | Low–med | **−** |
| **4. Rebrand** | Legacy-page decision, purge `MoneySweep`/`vote`/`author` chrome, language unification | Med (product call) | varies |
| **5. A11y** | Non-color status cues, contrast, focus, `axe` CI check | Low | **+** |

Phases 1–3 are pure hygiene and can land as small, independent PRs immediately.
Phase 4 needs the product decision below. Phase 5 closes the WCAG gate.

---

## Success metrics

- **Branding gate**: zero `MoneySweep` in product chrome; zero `/tabla`,
  `vote`, `author` in the default nav/flow (grep-enforced in CI).
- **Bundle**: measurable drop in `vite build` output and `node_modules` after the
  dependency diet.
- **Consistency**: one page shell, one filter primitive, one loading/empty
  component, one date lib, one toast system.
- **A11y**: `axe` clean at WCAG AA on core flows; no color-only status.
- **Maintainability**: `safeList` defined once, not six times.

---

## Open questions (need a product decision)

1. **Legacy legislative surface** (`/tabla`, `/ley/:id`, `/autores`, `/perfil`):
   **convert** to the Signal/Entity model, **hide** behind a diagnostic-only
   link, or **delete** outright? (Recommendation: hide from primary nav now,
   convert `LawTable`→signals-table and `Authors`→entity-profiles later; delete
   the vote/comment/subscription legacy components once nothing imports them.)
2. **UI language**: standardize on **Spanish** (recommended, matches the
   PR-civic product), or keep the pipeline surface English?
3. **Dark mode**: wire a real toggle, or delete the dead `.dark` palette and
   `next-themes`? (Recommendation: delete for a diagnostic tool.)
4. **Palette**: is the all-red identity intentional brand, or should neutrals go
   truly neutral with red reserved for alert/urgency? (Recommendation: the
   latter.)

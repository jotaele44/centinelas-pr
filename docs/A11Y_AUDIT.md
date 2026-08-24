# Accessibility (a11y) Audit — centinelas-pr

**Date:** 2026-08-24
**Scope:** Follow-up pass to the GUI-controls audit (`docs/GUI_AUDIT.md`, merged), collecting live axe-core results plus a design-system-usage inventory for the PRII federation rollup.

## Overview

centinelas-pr's frontend (`frontend/`) is a single-page app: 13 routed pages plus a catch-all 404, built on React 18 + react-router-dom, shadcn/ui (`new-york` style) local primitives, and `@pr-federation/react` v0.3.0 for the shared federation design tokens/components. This audit ran the shared federation a11y runner (Playwright + axe-core) live against the running app and separately inventoried which control implementation (shadcn, Federation, or hand-rolled) backs each interactive surface.

**Overall result:** every scanned route fails automated axe checks on **one recurring, systemic finding** — a color-contrast bug in the `@pr-federation/react` v0.3.0 CSS layer itself (`.fd-status[data-status="warning"|"caution"]`), not something local to any one page. Beyond that, touch-target sizing is inconsistent (header icon buttons and the `/pipeline` domain-filter chips fall short of 44px), and `/pipeline` has a mobile-viewport horizontal-overflow bug. Keyboard focus visibility passed cleanly everywhere tested.

## Method

- **Runner:** shared `/home/user/.a11y-runner` harness — Playwright `1.62.1`, `@axe-core/playwright` `4.12.1` (axe-core `4.12.1`), explicit Chromium `chromium-1194` executable (no `playwright install` run; shared directory untouched).
- **Viewports:** `390x844` (mobile-compact) and `1280x800` (desktop), both from the harness's two fixed projects.
- **Theme:** light only for the automated axe/keyboard/overflow/touch-target checks (the runner does not toggle theme). Dark-mode *reachability* and visual appearance were verified separately via screenshots (see Design-System Usage below) — dark mode was not run back through axe.
- **Route sample:** 5 of 14 page files — the app's primary route (`/`) plus `/monitor`, `/pipeline`, `/handoff`, and `/signals`, chosen as the highest-traffic entries from `Header.jsx`'s nav and the manifest's `e2e_routes`. The remaining 9 (`/matters`, `/matters/:id`, `/sources`, `/pipeline/:itemId`, `/water-disruption`, `/tabla`, `/entidades`, `/entidad/:slug`, 404 catch-all) were **not** scanned — see Scope Limitations.
- **Per-route checks** (from `federation-smoke.spec.js`, run unmodified): axe scan filtered to `critical`/`serious` impact, keyboard-focus-visible on first Tab, document horizontal-overflow check, and a `<button>` bounding-box sweep for the WCAG 2.5.5 44×44px touch-target target.
- **Environment:** backend on `127.0.0.1:8106` (uv-managed venv, `desktop/seed.py` replay of 266 signal items from the committed ledgers), frontend on `127.0.0.1:5306` (`vite --strictPort`). CORS was temporarily widened to allow `:5306` for this session and **reverted** before the final commit (see Cleanup below) — `server/backend/main.py` matches `origin/main` again.
- Per the prior GUI audit, the water-disruption "shadow console" links that resolve to raw JSON (not real HTML) were left out of scope entirely; they aren't reachable from the frontend router anyway (`/water-disruption/console` is a backend-only implicit route per `.federation/gui-capabilities.json`, not one of the `react-router-dom` routes in `App.jsx`).

## Per-Route Results

| Route | axe smoke (critical/serious) | Keyboard focus | Horizontal overflow | Touch targets ≥44px |
|---|---|---|---|---|
| `/` | ✅ pass | ✅ pass (both viewports) | ✅ pass | ❌ fail (2 header controls, both viewports) |
| `/monitor` | ❌ fail — `color-contrast`, 2 nodes (`data-status="warning"`) | ✅ pass | ✅ pass | ❌ fail (2 header controls) |
| `/pipeline` | ❌ fail — `color-contrast`, 140 nodes (`data-status="caution"`) | ✅ pass | ❌ fail (**mobile only**) | ❌ fail (10–11 controls: 2 header + 7 domain-filter chips, ×2 on mobile) |
| `/handoff` | ❌ fail — `color-contrast` (`caution` + `warning` tones) | ✅ pass | ✅ pass | ❌ fail (268× "Entregar" buttons @ 36px + 2 header controls) |
| `/signals` | ❌ fail — `color-contrast`, `data-status="warning"` | ✅ pass | ✅ pass | ❌ fail (2 header controls) |

All results identical between the mobile-compact and desktop-1280 projects unless noted.

## Findings (prioritized)

### 1. [Serious, systemic] `federationTone()` "warning"/"caution" tones fail WCAG 2 AA color contrast
- **Rule:** axe `color-contrast`, impact `serious`. Present on every route that renders a `ConfidenceBadge` or `HandoffStatusBadge` (`/monitor`, `/pipeline`, `/handoff`, `/signals` all hit it; `/` doesn't because it renders none of those badges).
- **Root cause, precisely located:** `node_modules/@pr-federation/react/dist/federation.css`, lines 53 and 58:
  ```css
  .fd-status[data-status="warning"]{color:var(--fd-st-warning-fg); ...}
  .fd-status[data-status="caution"]{color:var(--fd-st-caution-fg); ...}
  ```
  with `--fd-st-warning-fg:#b45309` and `--fd-st-caution-fg:#a16207` against the badge's own tinted background. This is **upstream, in the federation design-system package** (`thehub-pr`), not a centinelas-pr-local bug — every sibling repo importing `@pr-federation/react` v0.3.0 and using these two tones will reproduce it.
- **Local impact:** `ConfidenceBadge.jsx` maps its `medium`→`warning` and `low`→`caution` confidence bands directly onto these tones (`frontend/src/components/lifecycle/ConfidenceBadge.jsx`); `HandoffStatusBadge.jsx` maps `watching`→`warning` (`frontend/src/components/lifecycle/HandoffStatusBadge.jsx`). On `/pipeline` alone this produces **140 failing nodes** (one per visible pipeline-item confidence badge) — the single highest-volume violation found in this audit.
- **Recommendation:** file upstream against `@pr-federation/react` to darken `--fd-st-warning-fg`/`--fd-st-caution-fg` (or lighten the tint background) to meet 4.5:1; track as a cross-repo fix since it affects every PRII frontend consuming these tones, not just centinelas-pr.

### 2. [Moderate] Header icon buttons undersized for touch (36px vs. 44px target)
- The language toggle ("ES"/"EN") and theme toggle in `Header.jsx` are both `h-9` (36px) — present and failing identically on **every single route scanned**, both viewports.
- **Fix:** bump to `h-11 w-11` (44px) or add invisible touch-padding via a larger hit-slop wrapper; low-risk, single-file change (`frontend/src/components/Header.jsx`).

### 3. [Moderate] `/pipeline` domain-filter chips are 30px tall
- The 7 domain filter buttons ("All", "Environmental", "Financial", "Political", "Geo/Geology", "Anomalous", "Military/Aerospace", "Unclassified") plus the header controls fail touch-target sizing on both viewports — worst offender on the route.
- **Fix:** same pattern as #2, scoped to the filter-bar component in `Pipeline.jsx`.

### 4. [Moderate] `/handoff` "Entregar" button undersized at scale
- The shadcn `Button` used for "Entregar" renders at 36px height across **268 instances** on this route (one per handoff-eligible item) — the only place shadcn's `Button` primitive is actually used in this app, and it's still short of the touch target by 8px. Because shadcn's default button height (`h-9`) is the culprit, this is very likely to recur wherever `Button` gets adopted more broadly later.
- **Fix:** override to `size="lg"` / `h-11` for this action, or adjust the shadcn `button.jsx` default size token repo-wide.

### 5. [Moderate] `/pipeline` mobile horizontal overflow
- `document.documentElement.scrollWidth > clientWidth` at 390px width on `/pipeline` only (not reproduced at 1280px, not reproduced on any other route). Given the volume of domain-filter chips (7, plus "All"), this is consistent with the filter bar not wrapping/scrolling within the mobile viewport.
- **Fix:** constrain the filter bar to `overflow-x-auto` with a scroll container, or wrap onto multiple lines below the `md` breakpoint.

### 6. [Positive] Keyboard focus visibility passes everywhere tested
- First-Tab focus produced a visible (`outline-style !== 'none'`) focus ring on all 5 routes × 2 viewports — Tailwind's `focus-visible:ring-2 focus-visible:ring-ring` convention (seen in `Header.jsx` and elsewhere) appears to be applied consistently. No action needed.

### 7. [Info] Version-skew — `@pr-federation/react` pinned to v0.3.0
- `frontend/package.json` resolves the dependency from a fixed GitHub-release tarball (`federation-design-v0.3.0`). This version's `package.json` `exports` map (`.`, `./styles.css`, `./tokens.json`, `./package.json`) does not ship a `test-harness.contract.json` export at all — a repo on this pin cannot resolve that contract regardless of local code changes. It's also missing roughly a dozen components this audit was briefed to look for as the "current" federation surface (`FederationIconButton`, `FederationSemanticBadge`, `FederationEvidenceTierBadge`, `FederationConfidenceBadge`, `FederationLoadingState`/`ErrorState`/`OfflineState`/etc.) — none of those exist in the installed v0.3.0 `src/index.jsx`. See `docs/design-system-usage.json` for the full detail.

## Design-System Usage Summary

Full machine-readable detail lives in `docs/design-system-usage.json`. Highlights:

- **Federation package:** v0.3.0 pin, no test-harness contract, exports only `FederationThemeProvider`, `useFederationTheme`, `FederationButton`, `FederationPanel`, `federationStatusRole`/`federationTone`, `FederationStatusBadge`, `FederationEmptyState`, `FederationStatCard`. This repo imports exactly two of those symbols: `federationTone` (4 call sites) and `FederationEmptyState` (1 call site, wrapped by `ListState.jsx`). `FederationButton` and `FederationStatusBadge` are both available but unused.
- **shadcn:** `components.json` present, `new-york` style, `neutral` base color, 9 local primitives under `frontend/src/components/ui/` (`badge`, `button`, `card`, `input`, `label`, `skeleton`, `toast`, `toaster`, `use-toast`). Notably absent: `dialog`, `toggle`, `switch`, `tabs`, `select`, `dropdown-menu`.
- **Control sourcing** (button / dialog / badge / toggle / empty-state):
  - **Button:** shadcn `Button` used in exactly one place (`Handoff.jsx`); every other button in the app is a raw hand-styled `<button>`.
  - **Dialog:** does not exist anywhere in this app — no shadcn dialog primitive, no other modal pattern found by a repo-wide grep. No screenshot evidence could be captured for this reason (not a bug — a genuine absence).
  - **Badge:** split lineage. `DomainBadge`/`EvidenceTierBadge` wrap shadcn's `Badge`; `ConfidenceBadge`/`HandoffStatusBadge` bypass it and consume `federationTone()`'s raw CSS classes directly via a `<span>`.
  - **Toggle:** no dedicated toggle/switch primitive anywhere (shadcn or Federation); the theme/language toggles in `Header.jsx` are raw buttons without `aria-pressed`.
  - **Empty state:** `FederationEmptyState`, the one Federation *component* actually rendered anywhere in the app, via the shared `ListState.jsx` wrapper.
- **Theme support:** light (default) and dark both fully reachable via the header's real toggle button, which flips both the Tailwind `.dark` class and `data-theme` attribute the federation CSS keys off of. Preference persists to `localStorage` (`centinelas_theme`). Screenshots confirm the visual result in both themes at both viewports for the header, `/handoff`, `/pipeline`, and `/monitor`.
- **Screenshot evidence:** 16 PNGs under `docs/a11y-evidence/` (`screenshot-manifest.json` indexes all of them) — button, badge, and toggle are each covered light+dark × both viewports across 4 routes; dialog has no evidence because no dialog exists in the app.

## Scope Limitations

- **5 of 14 routes scanned** (`/`, `/monitor`, `/pipeline`, `/handoff`, `/signals`). Not scanned: `/matters`, `/matters/:id`, `/sources`, `/pipeline/:itemId`, `/water-disruption`, `/tabla`, `/entidades`, `/entidad/:slug`, and the 404 catch-all. These are reasonable next-pass candidates, particularly `/water-disruption` (distinct data shape from the other domains) and the two detail routes (`/matters/:id`, `/pipeline/:itemId`), which weren't scanned live but do use the same `ConfidenceBadge`/`EvidenceTierBadge` components implicated in Finding #1 and would very likely reproduce it.
- **2 viewports, light theme only** for the automated axe pass — dark theme was visually spot-checked via screenshots but not re-run through axe, so any contrast regressions specific to the dark token set (`[data-theme="dark"]` block in `federation.css`, which defines separate `-fg` values) are not covered by this audit's automated results.
- The touch-target check only inspects `<button>` elements per the shared runner's implementation; native `<a>`-tag navigation links (e.g. the header's `NavLink`s) were not measured for tap-target size.
- `/pipeline`'s 140-node and `/handoff`'s 268-node violation counts scale with the seeded demo dataset (266 signal items); production data volumes will change the exact counts but not the underlying per-badge/per-button contrast or sizing defect.

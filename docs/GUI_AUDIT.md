# GUI Audit — centinelas-pr

Audit date: 2026-08-23
Scope: every user-executable control (buttons, links, toggles, filters, dropdowns, checkboxes, tabs, modal/console actions) in `frontend/src` and its embedded backend-rendered console, plus the desktop launcher entry points.

## Overview

Centinelas is the Puerto Rico civic/legislative **pre-officialization** signal monitor in the PRII federation — it captures announcements, agendas, RFPs, hearings, and notices *before* they become an official contract, law, permit, payment, or audit (that later, official-record stage is MoneySweep's job). The app also runs a second, independent "universal 6-domain online-intelligence intake" pipeline that classifies scraped content and routes it to sibling federation repos (Spiderweb, AguaYLuz, MoneySweep, Skywatcher), plus a shadow-mode water-disruption producer.

**Tech stack**
- Frontend: React 18 + Vite 6, React Router v6, TanStack Query (provider mounted, not yet used by any page), Tailwind CSS, shadcn/ui-style components (`frontend/src/components/ui`), lucide-react icons, `@pr-federation/react` shared design-system package (status-tone chips, empty states).
- Two independent data layers:
  - **Legislative/lifecycle layer** (`frontend/src/api/appClient.js`): browser `localStorage`-backed CRUD over 16 entity types, seeded from `frontend/src/data/seedData.js`. Powers Home, Monitor, Signals, SignalsTable, Matters, MatterDetail, Sources, Entities, EntityDetail.
  - **Universal intake pipeline** (`frontend/src/api/pipelineClient.js`): REST client for a FastAPI backend (`server/backend/main.py`) reading JSON files under `.centinelas/{queue,classified,dispatched,handoffs}/`. Powers Pipeline, PipelineItemDetail, Handoff, and (via a third router) WaterDisruption.
- Backend: FastAPI (`server/backend/main.py`, mounting `server/backend/water_disruption_api.py`), read-mostly over flat JSON files on disk; no database.
- i18n: `frontend/src/lib/LanguageContext.jsx` — a `t()` function translates a canonical Spanish string to English via `frontend/src/lib/i18n/en.js`, default language follows `navigator.language`, persisted to `localStorage`.
- Theme: `frontend/src/lib/ThemeContext.jsx` — light/dark, persisted to `localStorage`, follows OS preference on first load.

**Entry points**
- Dev: `cd frontend && npm run dev` → `http://127.0.0.1:5173`, needs the FastAPI backend on `:8000` for Pipeline/Handoff/WaterDisruption (`uvicorn server.backend.main:app --reload --port 8000` from repo root); the legislative pages work with no backend at all (pure `localStorage`).
- Desktop launcher: double-click `PRII-CENTINELAS.command` (macOS)/`.sh` (Linux)/`.bat` (Windows), or the `PRII-CENTINELAS.app` bundle on macOS. See **Desktop Launcher** section below.
- Existing e2e coverage: `frontend/tests/gui-parity.spec.mjs`, run via `npm run test:gui-parity` (`frontend/gui-parity.playwright.config.mjs`) — boots the real FastAPI backend + Vite dev server and asserts every `active`/non-`internal` route in `.federation/gui-capabilities.json` is reachable from a real nav link and renders without a runtime error. It does not click deeper into page-specific controls (search boxes, filters, checkboxes) — that gap is what this audit fills in.

## Methodology

- **Static catalog**: every interactive JSX element was located by reading `frontend/src/pages/*.jsx` and `frontend/src/components/**/*.jsx`, tracing each `onClick`/`onChange`/`href`/`to` to its handler and, for handlers that call out, to the API/localStorage function it invokes.
- **Counting convention**: a control is catalogued once per place it occurs in the *source*, not once per row of a dynamically-rendered list. E.g. `SignalCard`'s title link is one row in this document even though it renders once per signal in the list — the same handler code executes for every instance. Pipeline's 7 domain-filter buttons and Handoff's 4 destination checkboxes *are* enumerated individually since each is a functionally distinct, individually labeled control.
- **Live verification**: `npm install` in `frontend/`, `uv sync --extra server` at the repo root, `uv run python desktop/seed.py` to replay the 266 committed demo signals from `data/signals/*.jsonl` into `.centinelas/classified/` (this is the same seeding the desktop launcher performs on first run), then the FastAPI backend and Vite dev server were started on isolated ports (`:8010` / `:5183`, to avoid clashing with sibling repos' dev servers already running in this shared container) and driven with Playwright (Chromium at `/opt/pw-browsers/chromium`) — clicking through nav, search/filter inputs, selects, checkboxes, and cross-page navigation, watching for console/page errors. The backend's CORS allow-list (hardcoded to `:5173`) was temporarily widened to include `:5183` for this run only and reverted before committing anything (`git checkout -- server/backend/main.py`); no other file was modified for testing. Both servers were stopped afterward and `frontend/node_modules` was removed at the end per the shared-container disk constraint.
- Controls requiring real external credentials/services (there are none reachable from this app — it has no OAuth/login flow and no third-party API keys in the client) are marked **static-only** with the reason; a handful of controls were left static-only simply because exercising them would have produced an irreversible side effect on the shared demo dataset (e.g. actually delivering a handoff) — those are called out per-row.

## Global layout (Header / Footer) — rendered on every route via `frontend/src/components/Layout.jsx`

| Element | Type | Label | Handler/Behavior | Verified | Notes |
|---|---|---|---|---|---|
| Brand link | Link | Centinelas logo + wordmark | `Link to="/"` (Header.jsx) | Live | Navigates home from any page. |
| Nav item | NavLink | Monitor | `to="/monitor"` | Live | |
| Nav item | NavLink | Señales | `to="/signals"` | Live | |
| Nav item | NavLink | Asuntos | `to="/matters"` | Live | |
| Nav item | NavLink | Entidades | `to="/entidades"` | Live | |
| Nav item | NavLink | Fuentes | `to="/sources"` | Live | |
| Nav item | NavLink | Pipeline | `to="/pipeline"` | Live | |
| Nav item | NavLink | Interrupciones de agua | `to="/water-disruption"` | Live | |
| Nav item | NavLink | Handoff | `to="/handoff"` | Live | |
| Language toggle | Button | "ES"/"EN" | `toggleLang()` (LanguageContext) flips `lang` state between `es`/`en`, writes `centinelas_lang` to `localStorage`, sets `<html lang>` | Live | Confirmed all visible copy re-renders (`h1`, placeholders, button labels) after toggling. |
| Theme toggle | Button (icon) | Sun/Moon icon | `toggleTheme()` (ThemeContext) flips `light`/`dark`, writes `centinelas_theme` to `localStorage`, toggles `.dark` class + `data-theme` on `<html>` | Live | Confirmed `<html>` class changes. |
| Mobile nav toggle | Button (icon) | Menu/X icon | `setOpen(!open)` — shows/hides a second copy of the 8 nav links in a mobile drawer | Live | Verified opens at 375px viewport; the drawer re-renders the same 8 links above, not separately catalogued. |

Footer (`Footer.jsx`) is static text — no interactive elements.

## Cross-cutting: error handling

| Element | Type | Label | Handler/Behavior | Verified | Notes |
|---|---|---|---|---|---|
| "Try again" | Button | Try again | `ErrorBoundary.jsx` — `this.setState({ error: null })`, clearing the caught render error and re-rendering children | Static-only: requires forcing a component to throw during render | Wraps the entire `<Routes>` tree in `App.jsx`; without it, one bad component would blank the whole app. Read confirms it works as designed. |

## Page: 404 Not Found (`frontend/src/lib/PageNotFound.jsx`, route `path="*"`)

| Element | Type | Label | Handler/Behavior | Verified | Notes |
|---|---|---|---|---|---|
| "Ir al inicio" | Button | Ir al inicio / Go home | `window.location.href = '/'` (hard navigation, not React Router) | Live | Confirmed lands on `/`. |

## Page: Home (`frontend/src/pages/Home.jsx`, route `/`)

| Element | Type | Label | Handler/Behavior | Verified | Notes |
|---|---|---|---|---|---|
| "Abrir monitor" | Link (button-styled) | Abrir monitor / Open monitor | `Link to="/monitor"` | Live | |
| "Ver handoff MoneySweep" | Link (button-styled) | Ver handoff MoneySweep / View MoneySweep handoff | `Link to="/handoff"` | Live | |

`MatterTimeline` (7-stage lifecycle strip) renders on this page — display-only, no click handlers.

## Page: Monitor (`frontend/src/pages/Monitor.jsx`, route `/monitor`)

| Element | Type | Label | Handler/Behavior | Verified | Notes |
|---|---|---|---|---|---|
| "Ver handoff" | Link (button-styled) | Ver handoff / View handoff | `Link to="/handoff"` | Live | |
| "Ver todas" | Link | Ver todas / View all | `Link to="/signals"` | Live | |
| Signal card title | Link (in `SignalCard`) | signal title | `Link to="/matters/:matter_id"` | Live | Shared component, verified live on Signals; identical markup/handler here. |
| Signal card "Fuente original" | Link (in `SignalCard`, conditional) | Fuente original / Original source | `<a target="_blank" href={signal.source_url}>` — external | Static-only: none of the seeded demo signals used in this run had `source_url` set | Present in source; opens the real external source page when populated. |

4 `MetricCard`s (Señales capturadas, Asuntos públicos, Listos para MoneySweep, Fuentes con brecha) are display-only stat tiles, no interaction.

## Page: Signals (`frontend/src/pages/Signals.jsx`, route `/signals`)

| Element | Type | Label | Handler/Behavior | Verified | Notes |
|---|---|---|---|---|---|
| Search input | Text input | Buscar señales | `onChange` sets `query` state; client-side filter over `title/summary/beat/source_name` (case-insensitive substring), no API call | Live | Typing "agua" correctly narrowed the list to the empty-state message; clearing restored it. |
| Handoff status select | Select/dropdown | Handoff (Todos / En observación / Candidato / Listo para MoneySweep / Vinculado) | `onChange` sets `status` state; client-side filter on `signal.handoff_status` | Live | Selecting "Candidato" round-tripped correctly (`inputValue()` confirmed). |
| "Ver como tabla" | Link | Ver como tabla / View as table | `Link to="/tabla"` | Live | |
| Signal card title | Link (`SignalCard`) | signal title | `Link to="/matters/:matter_id"` | Live | |
| Signal card "Fuente original" | Link (`SignalCard`, conditional) | external source | `<a target="_blank">` | Static-only: conditional on data | |

## Page: SignalsTable (`frontend/src/pages/SignalsTable.jsx`, route `/tabla`)

| Element | Type | Label | Handler/Behavior | Verified | Notes |
|---|---|---|---|---|---|
| Search input | Text input | Buscar señales | Client-side filter over `title/summary/beat/signal_type/source_name` | Live | Filtering "junta" reduced row count as expected. |
| "Ver como tarjetas" | Link | Ver como tarjetas / View as cards | `Link to="/signals"` | Live | |
| Row title | Link (per `<tr>`) | signal title | `Link to="/matters/:matter_id_or_id"` | Live | Clicked first row, landed on the matching `MatterDetail`. |

Confidence/Handoff badges in the table are display-only spans.

## Page: Matters (`frontend/src/pages/Matters.jsx`, route `/matters`)

| Element | Type | Label | Handler/Behavior | Verified | Notes |
|---|---|---|---|---|---|
| Matter title | Link (per card) | matter title | `Link to="/matters/:matter_id"`, sorted by `confidence_score` desc | Live | |

## Page: MatterDetail (`frontend/src/pages/MatterDetail.jsx`, route `/matters/:id`)

| Element | Type | Label | Handler/Behavior | Verified | Notes |
|---|---|---|---|---|---|
| Signal card title | Link (`SignalCard`, per linked signal) | signal title | `Link to="/matters/:matter_id"` (self-referential — links back to the containing matter) | Live | |
| Signal card "Fuente original" | Link (`SignalCard`, conditional) | external source | `<a target="_blank">` | Static-only: conditional on data | |

`MatterTimeline` and the two side `Card`s (Panel MoneySweep, Regla de lenguaje) are display-only.

## Page: Sources (`frontend/src/pages/Sources.jsx`, route `/sources`)

| Element | Type | Label | Handler/Behavior | Verified | Notes |
|---|---|---|---|---|---|
| Search input | Text input | Buscar fuente | Client-side filter over `name/source_type/coverage_tier/status` | Live | Filtering "municip" reduced the card count. |

No links/buttons on the source cards themselves — purely a read-only registry view (falls back to a hardcoded `seedSources` array of 7 P0/P1 sources when the `localStorage` `Source` collection is empty).

## Page: Entities (`frontend/src/pages/Entities.jsx`, route `/entidades`)

| Element | Type | Label | Handler/Behavior | Verified | Notes |
|---|---|---|---|---|---|
| Search input | Text input | Buscar entidad | Client-side filter on entity name | Live | |
| Entity card | Link (per card) | entity name | `Link to="/entidad/:slug"` — entities are *derived* client-side (`deriveEntities()` in `lib/appQuery.js`) from `signal.agencies/entities` and `matter.agencies/people/organizations`, not their own stored records | Live | |

## Page: EntityDetail (`frontend/src/pages/EntityDetail.jsx`, route `/entidad/:slug`)

| Element | Type | Label | Handler/Behavior | Verified | Notes |
|---|---|---|---|---|---|
| "Volver a entidades" | Link | Volver a entidades / Back to entities | `Link to="/entidades"` | Live | |
| Signal card title | Link (`SignalCard`, per linked signal) | signal title | `Link to="/matters/:matter_id"` | Live | |
| Signal card "Fuente original" | Link (`SignalCard`, conditional) | external source | `<a target="_blank">` | Static-only: conditional on data | |

## Page: Pipeline (`frontend/src/pages/Pipeline.jsx`, route `/pipeline`)

Universal 6-domain intake pipeline — reads from the FastAPI backend (`GET /items`, `GET /status`).

| Element | Type | Label | Handler/Behavior | Verified | Notes |
|---|---|---|---|---|---|
| "Todos" domain filter | Button | Todos / All | `setDomain("")` → refetches `GET /items` with no `domain` query param | Live | |
| Domain filter (×7) | Button | Environmental, Financial, Political, Geo/Geology, Anomalous, Military/Aerospace, Unclassified | `setDomain(d)` → `GET /items?domain=d` | Live | Clicked "Financial": item count dropped from 266 → 10, matching the backend's server-side filter. |
| Pipeline item card | Link (per item) | item title | `Link to="/pipeline/:item_id"` | Live | |

## Page: PipelineItemDetail (`frontend/src/pages/PipelineItemDetail.jsx`, route `/pipeline/:itemId`)

| Element | Type | Label | Handler/Behavior | Verified | Notes |
|---|---|---|---|---|---|
| "Back to pipeline" | Link | ← Back to pipeline | `Link to="/pipeline"` | Live | |
| "source" | Link (conditional) | source ↗ | `<a target="_blank" href={item.source_url}>` | Static-only: requires an item with `source_url` populated (an external site) — present in `PipelineItemDetail.jsx` source, standard external-link pattern | Not exercised to avoid navigating to a real external site from the sandbox. |

## Page: Handoff (`frontend/src/pages/Handoff.jsx`, route `/handoff`)

Delivers classified pipeline items to sibling federation repos and records a per-target delivery receipt.

| Element | Type | Label | Handler/Behavior | Verified | Notes |
|---|---|---|---|---|---|
| Destination checkbox (×4) | Checkbox (per item card) | Spiderweb, Agua y Luz, Moneysweep, Skywatcher | `toggle(itemId, target)` — adds/removes the target from a `Set` held in `selected` state | Live | Checking a box correctly enabled the "Entregar" button (was `disabled` with none selected). |
| "Entregar" | Button | Entregar / Entregando… | `send(item)` → `createHandoff(item_id, targets)` → `POST /handoffs/{item_id}` with the selected `targets`; on success, refreshes the list and shows delivery-attempt chips per target; on failure shows `role="alert"` inline error | Static-only: enable/disable state verified live; the click itself was **not** exercised to avoid writing an irreversible handoff receipt into the shared demo dataset | Code path traced: writes a JSON receipt file under `.centinelas/handoffs/`, is not idempotent-guarded client-side (server-side `dispatch_to_targets` handles retries via `retry_receipt_id`, but that path has no GUI control at all — see Findings). |

## Page: Water Disruption (`frontend/src/pages/WaterDisruption.jsx`, route `/water-disruption`)

Embeds the FastAPI water-disruption shadow console (`GET /water-disruption/console`) in an `<iframe>`.

| Element | Type | Label | Handler/Behavior | Verified | Notes |
|---|---|---|---|---|---|
| Console iframe | iframe (not itself clickable) | — | `src={consoleState.url}` from `getWaterDisruptionConsole()`, which HEAD-checks `GET /water-disruption/console` for a `200` + `text/html` response before rendering it | Live | Loaded successfully; not counted as an interactive control itself. |
| "Retry" | Button (conditional, shown only when the console is unavailable) | Retry | `loadConsole()` re-runs the availability check | Static-only: requires the backend to be down or return non-HTML; the console loaded successfully in this run so the retry branch never rendered | Code confirms it simply re-invokes the same load function; no state is mutated. |
| [in iframe] "Sources" | Link (backend-rendered static HTML) | Sources | `href="/water-disruption/sources"` | Live | Loads inside the iframe. **Finding**: this and the next three links point at JSON API endpoints, not HTML pages — clicking them replaces the iframe content with raw unstyled JSON, not a real sub-view. |
| [in iframe] "Run ledger" | Link | Run ledger | `href="/water-disruption/runs"` | Live | Same JSON-not-HTML issue. |
| [in iframe] "Candidates" | Link | Candidates | `href="/water-disruption/candidates"` | Live | Same JSON-not-HTML issue. |
| [in iframe] "Outbox" | Link | Outbox | `href="/water-disruption/outbox"` | Live | Same JSON-not-HTML issue. |

## Desktop Launcher

Three double-click launcher scripts at the repo root (`PRII-CENTINELAS.command` for macOS, `.sh` for Linux, `.bat` for Windows) and a macOS `PRII-CENTINELAS.app` bundle (`PRII-CENTINELAS.app/Contents/MacOS/PRII-CENTINELAS`) all funnel into the same two-step flow:

1. **`desktop/setup.py --ensure`** (one-time, idempotent — skipped on later runs via a `.setup-complete` marker):
   - Runs `desktop/seed.py`: replays the committed `data/signals/{live_signals,example_signals}.jsonl` ledgers into `.centinelas/classified/*.json` **only if** no real pipeline run has already populated that directory (never overwrites live state). This is the same seeding step used for this audit's live verification.
   - Creates a private `.venv`, installs `server/backend/requirements.txt` + `requirements-desktop.txt` (`pywebview`, `prii-desktop` — a shared package pulled from the `thehub-pr` federation repo at a pinned commit) plus the `centinelas` package itself (`pip install -e .[server]`).
   - Runs `npm ci`/`npm install` + `npm run build` in `frontend/` with `VITE_API_BASE=""` (empty — same-origin), producing `frontend/dist/`.
2. **`desktop/launch.py`**: thin shim that calls `prii_desktop.launch(DesktopConfig.from_module(desktop.config))`. Per that shared package's docstrings and `desktop/README.md`, this starts a `uvicorn` server serving the FastAPI backend (`server/backend/main.py:app`) same-origin with the built frontend (`desktop/app_server.py` wraps `app` for this), takes a single-instance lock, and opens a native `pywebview` window (or the system default browser, with `--browser`) pointed at it. Flags `--no-window`, `--browser`, `--route PATH`, and `--smoke` (CI headless smoke-test mode) are handled by the shared launcher, not by anything in this repo.

The `.app` bundle's launcher script additionally: self-locates the repo root from its own bundle path, detects and explains macOS Gatekeeper's "App Translocation" quarantine problem (with a guided fix pointing at `Fix-Gatekeeper.command`, which clears the `com.apple.quarantine` xattr and ad-hoc re-signs the bundle), restores `PATH` entries Finder strips (`/opt/homebrew/bin`, `/usr/local/bin`) so `python3`/`npm` resolve, and logs setup failures to a tempdir file it can point the user at (since Finder discards stdout).

Net effect for an end user: double-click → (first run only) a few minutes of one-time dependency install + frontend build, needing internet and Node.js once → a native window (or browser tab) opens showing the same React SPA audited above, served from a local `uvicorn` process, with the 266-signal demo ledger already seeded so the app isn't empty on first open.

## Findings

- **No dead/broken controls found** in the 58 catalogued elements — every button, link, checkbox, select, and search input that was reachable in this sandbox did what its label implies, with zero console/page errors across all 13 routed pages plus the 404 route during live Playwright verification.
- **Water-disruption console nav links are not real pages.** The 4 links inside the embedded shadow-console iframe (Sources / Run ledger / Candidates / Outbox) point at JSON API endpoints (`server/backend/water_disruption_api.py`), not HTML views — clicking one replaces the iframe with unstyled raw JSON. Functionally reachable, but not a usable console UI.
- **Water-disruption mutating endpoints have no GUI control at all.** The backend exposes `POST /capture`, `POST /candidates/{id}/dispatch`, `POST /outbox/{id}/deliver`, and `POST /candidates/{id}/retract` (all wired, tested at the API layer per `.federation/gui-capabilities.json`), but nothing in `frontend/src` calls any of them — there is no button anywhere in the app that captures evidence, dispatches a candidate, delivers to the outbox, or retracts one. The only reachable action from the GUI is the read-only console iframe. This is inside this repo's own `AGENTS.md` "GUI capability parity" rule (a production capability must be reachable without a terminal/direct API call) — worth a follow-up ticket, out of scope for this audit to fix.
- **Handoff retry path has no GUI control.** The backend's `POST /handoffs/{item_id}` accepts a `retry_receipt_id` to re-attempt only the previously failed targets (`server/backend/main.py`), but `Handoff.jsx`'s `send()` never passes one — a partial/failed delivery can only be retried by re-checking the same boxes and re-sending to all originally-selected targets, not just the failed ones.
- **Dead/unused frontend code** (not itself broken, just unreachable — noted for completeness, not counted as an "interactive element" since it renders nowhere): `frontend/src/components/AuthLayout.jsx` and `GoogleIcon.jsx` are leftover from a removed Login/Register/ForgotPassword/ResetPassword flow (visible in `git diff origin/main` history — those pages were deleted from this branch already) and are imported by nothing. `frontend/src/components/ScrollToTop.jsx` is fully implemented but never mounted in `App.jsx`. `frontend/src/components/ui/toaster.jsx`'s `<Toaster />` is mounted in `App.jsx`, but nothing in the app ever calls the `toast()` helper (`use-toast.jsx`) — the toast system is wired end-to-end but nothing triggers it. `appClient.js`'s `functions.invoke` handlers (`evaluateHandoffCandidate`, `acceptHandoffCandidate`, `rejectHandoffCandidate`, `validatePreOfficialLanguage`) implement the full matter→MoneySweep handoff-candidate lifecycle and pre-official-language validation, but are called from nowhere in `frontend/src/pages` — only from `lifecycle.js`/its test file. None of these have a GUI surface to catalog as "broken" since there is no control pointing at them; they're flagged here as unreachable code rather than as failing controls.
- **TanStack Query is installed and its `QueryClientProvider` wraps the whole app**, but no page/component actually uses `useQuery`/`useMutation` — all data fetching is hand-rolled `useEffect` + `useState` (legislative pages) or plain `fetch` wrappers (`pipelineClient.js`). Not a bug, just unused infrastructure.

## Summary

- **Pages audited**: 13 routed React pages (`Home`, `Monitor`, `Signals`, `SignalsTable`, `Matters`, `MatterDetail`, `Sources`, `Entities`, `EntityDetail`, `Pipeline`, `PipelineItemDetail`, `Handoff`, `WaterDisruption`) + the `PageNotFound` catch-all route = **14 page/route sections**. (`frontend/src/pages/WaterDisruption.test.jsx` is a Vitest spec, not a page, and was read but not catalogued as one.)
- **Total interactive elements catalogued**: **58** (12 in the global Header, 1 in the cross-cutting ErrorBoundary fallback, 1 on the 404 page, 44 spread across the 13 page bodies — see per-page tables above for the exact breakdown; see **Methodology** for how repeated list-row controls are counted once).
- **Live-verified vs. static-only**: **50 live-verified** via Playwright against the running app (backend seeded with 266 real demo signals) with zero console or page errors observed; **8 static-only** — 1 conditional error-boundary button (needs a forced render exception), 4 conditional `SignalCard` "Fuente original" external links (one instance each on Monitor, Signals, MatterDetail, EntityDetail — none of the exercised signals had `source_url` populated), 1 conditional PipelineItemDetail external source link, 1 conditional water-disruption retry button (console loaded successfully so the failure branch never rendered), and 1 Handoff "Entregar" click (the checkbox enable/disable wiring was verified live; the click itself was withheld to avoid writing an irreversible delivery receipt into the shared demo dataset used by other concurrent audits in this container). The water-disruption capture/dispatch/deliver/retract backend actions have *no* GUI control at all (see Findings) and are excluded from both counts since there is nothing to click.
- **Broken/dead controls found**: **none.** All 50 live-verified controls behaved as their source code indicated, with zero console/page errors. The issues worth following up on are gaps rather than breakage: two backend capabilities (water-disruption capture/dispatch/deliver/retract, and handoff partial-retry) with no GUI control pointing at them, and the water-disruption console's four "page" links resolving to raw JSON instead of real views — see **Findings** above.

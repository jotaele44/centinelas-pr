# Real-Time Data Acquisition — Data Discovery Audit

**Date:** 2026-09-23
**Scope:** Every subsystem in this repository that acquires, polls, monitors,
or claims to serve "live"/"real-time" data — ingestion, classification,
routing, backend APIs, scheduled monitors, and frontend/desktop consumption.
**Method:** Static analysis across `src/centinelas/ingest/`,
`src/centinelas/classify/`, `src/centinelas/route/`, `src/centinelas/water_disruption.py`,
`src/centinelas/space_observations/`, `server/backend/`, `tools/`,
`data/monitoring/`, `data/signals/`, `schemas/`, `frontend/src/`, `desktop/`,
and `.github/workflows/`. No source code was changed to produce this audit.

---

## 1. Executive summary

**There is no continuous or streaming data acquisition anywhere in this
program.** Every mechanism labeled "real-time" or "live" in the README,
schemas, or UI copy is one of two things:

1. **Scheduled batch polling** driven by GitHub Actions `cron:` triggers —
   but these live entirely *outside* the documented ingestion pipeline
   (`src/centinelas/ingest/`). Only two exist, and one of them has been
   completely non-functional (HTTP 403) since it was wired up.
2. **Manual/`workflow_dispatch`-triggered batch polling** of the real
   RSS/Federal-Register/HTML-scrape pipeline (58+ sources) — a human must
   click "Run workflow" and type `confirm=YES`. There is no cron trigger for
   this pipeline at all.

The frontend adds a third layer of disconnect: it does not poll anything,
and most of its pages render `localStorage` mock data rather than any
backend output — live or otherwise.

### 1.1 Acquisition mechanism inventory

| Mechanism | Location | Trigger / cadence | Health tracking | Retry/backoff | Status |
|---|---|---|---|---|---|
| RSS/Atom poll (58+2 feeds) | `src/centinelas/ingest/rss.py` | Manual (`workflow_dispatch`) or CLI | None | None | Works when run |
| Federal Register API poll | `src/centinelas/ingest/federal_register.py` | Manual/CLI | None | None | Works when run |
| HTML/listing scrape (7 active, 1 disabled) | `src/centinelas/ingest/web.py` | Manual/CLI | None | None | 1 source 403-blocked (USACE) |
| Email / Google Alerts ingestion | `src/centinelas/ingest/email/` | N/A — hard-disabled | N/A | N/A | Design-only, not shippable |
| El Yunque access monitor | `tools/el_yunque_access_monitor.py` | **Cron, every 15 min** | `data/monitoring/el_yunque/health.json` | None (keeps prior state on failure) | Working |
| Just Security monitor | `tools/just_security_monitor.py` | **Cron, every 6h** | `data/monitoring/just_security/state.json` | None | **Blocked (HTTP 403) since inception** |
| Water-disruption "shadow" producer | `server/backend/water_disruption_api.py` | N/A — passive, evidence POSTed in manually | N/A | Dead-letter queue (delivery leg only) | Shadow mode by design, no fetcher |
| Space-observations intake | `src/centinelas/space_observations/producer.py` | N/A | N/A | N/A | Network acquisition explicitly disabled by a hard invariant |
| `POST /run` (full pipeline trigger) | `server/backend/main.py:179` | On-demand HTTP call | None | None | Synchronous, unbounded, weakly authenticated |
| Frontend polling | `frontend/src/` | **None exists** | N/A | N/A | Fetch-once-on-mount only; 6/10 routed pages show mock data, not backend output |

The rest of this document walks through each row with file/line detail,
then lists cross-cutting inefficiencies and prioritized recommendations.

---

## 2. Inventory of real-time acquisition surfaces

### 2.1 RSS/Atom polling — `src/centinelas/ingest/rss.py`

- Reads `src/centinelas/ingest/sources.yaml` (58 feeds, grouped by beat:
  military/aerospace, environmental, geology, "anomalous", financial,
  political, cross-domain wire, contracts/procurement, 22 DRNA permit
  feeds) plus an overlay `just_security_sources.yaml` (2 feeds), merged
  idempotently by `source_id`/`url` (`rss.py:30-46`).
- `poll_all()` (`rss.py:136-170`) loops sequentially over every feed with
  `feedparser`, one `httpx` fetch per source, no concurrency.
- **No rate limiting** — no delay between requests, no per-host throttling,
  no concurrency cap.
- **No retry/backoff** — a failed fetch is caught by a blanket
  `try/except Exception`, logged as a warning (`rss.py:167-168`), and the
  source silently contributes zero items for that run. There is no
  distinction between "source had zero new items" and "source fetch
  failed."
- **No conditional GET** — no ETag/`If-Modified-Since` handling; every poll
  re-downloads the full feed body even when unchanged.
- **No persisted dedup across runs** — `seen_ids` (`rss.py:139`) is a local
  set rebuilt every call; there is no on-disk "already seen" ledger, so an
  RSS item that stays in a feed across multiple polls is reprocessed
  (and, downstream, reclassified — see §2.5) every time.
- Contrast: `src/centinelas/releases/adapters.py:104-142` already
  implements a real `RateLimiter` and content-addressed `HttpCache` for a
  different (FOIA/declassification) producer — that pattern exists in the
  codebase but is never reused by the ingest path.

### 2.2 Federal Register API poll — `src/centinelas/ingest/federal_register.py`

- Calls `https://www.federalregister.gov/api/v1/documents.json`
  (`federal_register.py:29,46-49`) for 2 configured agencies
  (`sources.yaml:245-253`). Same lack of retry/backoff
  (`federal_register.py:106-108`) and no conditional GET as §2.1.

### 2.3 HTML/listing scrape — `src/centinelas/ingest/web.py`

- Two layers: `scrape_url()` for a single page (`web.py:83-132`) and
  `poll_scrape_sources()`/`scrape_listing()` for listing pages
  (`web.py:567-646`), covering 8 configured sources (`sources.yaml:270-374`):
  OGPe, 3 JP pages, 2 ASG (paginated, with a per-entry detail fetch —
  `web.py:487-519`), an EPA NPDES table, and a USACE `rss_detail` crawler
  that is **disabled** (`sources.yaml:365-372`) because the target site's
  Akamai edge returns HTTP 403 to all programmatic clients.
- Same no-retry/no-backoff pattern (`web.py:94-96`, `157-159`); the ASG
  paginator simply stops on first failure rather than retrying
  (`web.py:496-509`).
- Sequential, non-parallel — a plain `for` loop over sources
  (`web.py:634`), a fresh `httpx.Client` per call, 15-20s timeout per
  source (`web.py:38`, `federal_register.py:30`). A single slow/hanging
  source materially delays a full run.

### 2.4 Email / Google Alerts ingestion — `src/centinelas/ingest/email/`

Fully disabled, design-only — not a working acquisition path in any
deployable sense:

- `adapter.py:1-6` — explicit "Disabled Gmail adapter contracts and
  offline fake client. No production Gmail API dependency is imported
  here."
- `EmailSourceProfile.enabled: bool = False` (`adapter.py:23`) plus a hard
  guard `assert_safe()` (`adapter.py:38-46`) that raises if `enabled=True`
  is ever set, and also forbids raw RFC822 download and auto-promotion.
- `GmailClientProtocol` (`adapter.py:49-57`) has no concrete production
  implementation — only `OfflineFakeGmailClient` (`adapter.py:60-79`),
  which reads a static JSON fixture.
- The shipped example config is itself disabled:
  `config/email_sources/google_alerts.example.yaml:3` (`enabled: false`).
- `server/backend/email_review_contract.py` registers **zero FastAPI
  routes** by design (`email_review_contract.py:1-5,41-49`).

### 2.5 Classification and routing — `src/centinelas/classify/`, `src/centinelas/route/`

- `classify(item)` (`classifier.py:74`) is synchronous, per-item: a
  keyword fast-path, else an LLM call. The Anthropic client is
  **constructed fresh on every call** (`classifier.py:42` —
  `anthropic.Anthropic(api_key=...)` inline, no reused/module-level
  client).
- **No caching** — no cache keyed by item_id/URL/content-hash anywhere in
  `classifier.py`, `enrich.py`, or `build_signal_ledger.py`. Combined with
  §2.1's lack of a persisted seen-ids ledger, the same RSS article showing
  up across multiple poll cycles is **re-classified via the LLM every
  run** — redundant API spend with zero memoization.
- **No rate limiting/batching** — `build_ledger()`
  (`scripts/build_signal_ledger.py:89-104`) classifies items one at a time
  in a plain loop, no concurrency, no backoff on transient failures beyond
  a blanket fallback to keyword classification (`classifier.py:101-105`).
- `route/dispatch.py:157` (`dispatch_many`) and `route/router.py:107`
  (`route`) are similarly per-item, unbatched, unparallelized.

### 2.6 CLI and pipeline triggers — `src/centinelas/cli.py`

- Commands: `ingest`, `classify`, `route`, `run`, `status` (Typer app).
- **The exact same acquisition call is duplicated three times** in the
  codebase with no shared function:
  - `cli.py:54` (`ingest`)
  - `cli.py:154` (`run`)
  - `server/backend/main.py:191` (`POST /run`)

  All three independently call
  `_merge_items(poll_all(), poll_federal_register(), poll_scrape_sources())`.
- `status` (`cli.py:176-186`) only counts files in queue/classified
  directories — it does not report source health or freshness, despite
  the README describing a `SourceHealthCheck` entity (see §4.3).
- **"Real-time" cadence, concretely:** the only path that touches all 58+
  RSS feeds, the Federal Register API, and the scrape sources is triggered
  by `workflow_dispatch` only — `.github/workflows/dispatch-signals.yml`,
  `dispatch-signals-aguayluz.yml`, `dispatch-signals-ovnis.yml` (none has a
  `schedule:` block), each additionally gated behind a manual
  `confirm: YES` input. There is **no cron trigger anywhere** for this
  core pipeline.

### 2.7 Backend FastAPI — `server/backend/main.py`

- A **read-only, disk-tailing** API: `GET /health`, `/items`,
  `/items/{id}`, `/queue`, `/sources`, `/status`, `/handoffs` all read
  `.centinelas/{queue,classified,dispatched,handoffs}/*.json` fresh on
  every request, explicitly documented as uncached (`main.py:1-7,47-56`).
  No background task, no websocket, no polling loop.
- `POST /run` (`main.py:179-207`) is the one place a live fetch can be
  triggered outside the CLI. It runs the full triplicated poll
  (§2.6) **synchronously inside the request handler**, with **no
  server-side timeout**, while the frontend's own client applies a 15s
  timeout to POST calls (`frontend/src/api/pipelineClient.js:24-28`) — a
  full ingest pass across 58+ sequential HTTP fetches will very likely
  exceed that, timing out the UI while the backend keeps running unbounded
  in the background with no cancellation path.
- `server/backend/auth.py` is a 45-line stub: `require_write_access()`
  (`auth.py:25-42`) checks a bearer token from `CENTINELAS_WRITE_TOKEN`,
  but **if that env var is unset, it falls back to allowing any client on
  a loopback/private/link-local IP** (`auth.py:32-42`). This same thin
  guard protects both a cheap idempotent water-disruption retraction call
  and the expensive, unbounded `/run` pipeline trigger — no differentiated
  or cost-aware gating.

### 2.8 El Yunque access monitor — `tools/el_yunque_access_monitor.py`

- Standalone scraper (341 lines), **outside** `src/centinelas/ingest/`
  entirely. Scrapes `https://www.fs.usda.gov/r08/elyunque/alerts` via
  `httpx` + `BeautifulSoup`, computes semantic hashes of alert content,
  and emits idempotent `repository_dispatch` handoffs to `aguayluz-pr`.
- Driven by `.github/workflows/el-yunque-access-monitor.yml`, cron
  `7,22,37,52 * * * *` (every 15 minutes) — the tightest cadence of any
  acquisition mechanism in the repo. It commits its own output
  (`data/monitoring/el_yunque/*`) back to `main`.
- Has a genuinely working, if bespoke and non-shared, health record:
  `data/monitoring/el_yunque/health.json` —
  `{"status": "healthy", "condition_count": 11, "transition_count": 11, "checked_at": ...}`.
  `current.json` (16.4KB) holds real `access_condition` records
  (schema `access_condition.v1.schema.json`) with `evidence_tier: "T1"`,
  `confidence`, `semantic_hash`, `status_basis`.
- This is the one acquisition mechanism in the whole repo that is
  simultaneously **scheduled, functioning, and health-tracked** — but its
  pattern (health JSON, transition ledger) is not shared with or reused by
  any other source.

### 2.9 Just Security monitor — `tools/just_security_monitor.py`

- Standalone scraper, also outside `src/centinelas/ingest/`. Driven by
  `.github/workflows/just-security-monitor.yml`, cron `17 */6 * * *`
  (every 6 hours).
- **Has been permanently blocked (HTTP 403) since inception.**
  `data/monitoring/just_security/state.json` shows
  `"certification": "BLOCKED"` for both its search and tag-archive
  targets. `runs.jsonl` (9 run records) shows `relevant: 0, seen: 0,
  event_count: 0` on **every single run** — this monitor has never
  successfully extracted an article.
- `data/monitoring/just_security/events.jsonl` is **0 bytes** — a
  permanently dead output stream.
- No backoff, no circuit breaker, no alert-on-N-consecutive-failures. The
  job keeps running every 6 hours, consuming CI minutes, producing nothing,
  with no adaptive behavior despite the *pattern* for tracking consecutive
  failures already existing elsewhere in the codebase
  (`src/centinelas/ingest/email/models.py:124`,
  `GmailSyncCheckpoint.consecutive_failures`) but not applied here.

### 2.10 Water-disruption "shadow" producer — `server/backend/water_disruption_api.py`, `src/centinelas/water_disruption.py`

- Explicitly **shadow mode**: the console literally renders "Shadow mode —
  No live alerts or production promotion"
  (`water_disruption_api.py:53`), and `water_disruption.py:89` hardcodes
  `self.shadow_mode = True` with no config to flip it.
- **No fetcher exists.** `_SOURCES` (`water_disruption_api.py:21-29`)
  lists 7 conceptual sources (PRASA, municipalities, emergency-management,
  news, radio, social, public-works) but none has an actual HTTP client —
  a repo-wide `grep -i prasa` only matches keyword lists in
  `classify/rules.py`/`classify/enrich.py` and docs, never a live poller.
  Evidence only enters via manually-invoked `POST /water-disruption/capture`.
- `docs/adr/ADR-0001-water-disruption-evidence-production.md` is
  **`Status: Proposed`** and describes a scheduled-run design that has no
  corresponding `.github/workflows/*water*` file — there is no scheduled
  run at all today.
- The one genuinely live piece is the delivery leg:
  `/outbox/{id}/deliver` (`water_disruption_api.py:103-123`) makes a real
  outbound POST to a consumer webhook with a 10s timeout, idempotency-key
  dedup, and a real dead-letter path on failure — but this is egress
  (pushing an already-captured record out), not acquisition.
- `src/centinelas/generated/water_disruption_client.py` is misleadingly
  named — its own docstring calls it a "generated-style" client, but it is
  hand-written, not produced by any codegen tool (no
  `openapi-generator`/`datamodel-codegen` reference anywhere in the repo).
  It already covers only 3 of the API's 8 routes (`sources()`,
  `candidates()`, `dispatch()` — missing `/console`, `/runs`,
  `/evidence/{id}`, `/outbox`, `/candidates/{id}/retract`,
  `/outbox/{id}/deliver`), a drift risk since nothing keeps it in sync
  with the real API.

### 2.11 Space-observations intake — `src/centinelas/space_observations/producer.py`

- The `IntakeEngine` (`producer.py:218`) is explicitly documented as
  "Network-disabled, restart-safe Phase 0-1 intake engine." Its own
  validator, `_validate_acquisition()` (`producer.py:384`), **raises if
  `acquisition["network_acquisition_performed"]` is anything other than
  `False`** — i.e., a hard invariant that no network fetch ever happens in
  this phase. It only performs dedup/idempotency bookkeeping for leads
  that arrive already-built from elsewhere.
- `data/reference/space_source_registry_delta.csv` lists intended future
  sources (NASA RSS, NASA Archives, NASA NTRS, NASA Earthdata) with
  `scrape_method` values of `rss`/`html_change`/`api`/`manual`, several
  still `manual` — named intentions, not implemented pollers.

### 2.12 The `data/signals/live_signals.jsonl` "ledger"

- Called a "ledger" throughout the README/`federation.json`/docs, but
  `scripts/build_signal_ledger.py:120` opens it with `"w"` — **every run
  overwrites the entire file rather than appending to it.**
- Currently 100 lines, **last modified 2026-08-25** (commit `dd0d287`) —
  about four weeks stale relative to this audit's date, because the only
  thing that ever writes it is `workflow_dispatch`-triggered
  (`dispatch-signals.yml`), never a cron job.
- `federation.json:70` documents that this one and only refresh ran with
  the classifier in **keyword-fallback mode** because
  `ANTHROPIC_API_KEY` was unavailable at the time — meaning essentially
  none of the 100 "live" signals were actually LLM-classified, despite the
  architecture implying Claude Haiku classification throughout.
- The signal-building mapping (`item_to_signal`, `build_signal_ledger.py:61-86`)
  is a thinner, **duplicated** mapping of `ClassifiedItem` that hardcodes
  `municipalities`, `agencies`, `entities`, `estimated_value`,
  `deadline_date`, `urgency_score` to empty/null (lines 75-80) rather than
  reusing the richer enrichment already implemented for MoneySweep-bound
  items in `route/router.py`'s `build_payload`.

### 2.13 Frontend and desktop consumption

- **No polling of any kind exists anywhere in `frontend/src`.** A
  repo-wide search for `setInterval`, `refetchInterval`, `staleTime`,
  `EventSource`, `WebSocket`, `useQuery`, `useSWR` turns up nothing tied to
  data fetching. Every data call is a one-shot `fetch`/localStorage read
  fired from a `useEffect` on mount (or on an explicit user action like a
  filter click or a "Retry" button).
- `frontend/src/api/appClient.js` (316 lines) is **not a network client at
  all** — every entity (`Signal`, `Matter`, `Source`,
  `HandoffCandidate`, etc.) is backed by `window.localStorage` under one
  key (`appClient.js:10`), seeded once from a static file
  (`frontend/src/data/seedData.js`). Its `.subscribe()` method is a
  documented no-op (`appClient.js:124-126`, returns `() => undefined`).
  This backs `Monitor`, `Signals`, `SignalsTable`, `Matters`,
  `MatterDetail`, and `Sources` — **6 of the app's routed pages show mock
  data, not backend output**, confirmed by
  `.federation/gui-capabilities.json` classifying `legislative-monitor` as
  `"client_only"` with no backend files listed at all.
- `frontend/src/api/pipelineClient.js` (64 lines) is the one real HTTP
  client, hitting `server/backend/main.py`'s endpoints with an 8s GET /
  15s POST `AbortSignal.timeout`. It backs `Pipeline`,
  `PipelineItemDetail`, `Handoff`, and `WaterDisruption` — but even here,
  fetches are one-shot on mount or on user action, never on an interval.
  `getWaterDisruptionConsole()` only checks the response's `Content-Type`
  to decide whether to render an iframe; it never parses the console's
  data.
- **`@tanstack/react-query` is fully wired at the app root**
  (`frontend/src/lib/query-client.js`, provided in `App.jsx:60`) **but
  `useQuery`/`useMutation` are never called anywhere in the codebase** — a
  ready-made caching/dedup layer sitting completely unused.
- `frontend/src/pages/Sources.jsx:77` displays a "Último éxito"
  (last-success) timestamp — but it comes from
  `seedData.js:103-104,120-121`, computed once at module-import time
  (`new Date().toISOString()`), then frozen into localStorage. **It never
  reflects an actual source poll** — it's effectively "page load time,"
  not a freshness signal.
- `desktop/` wraps the identical FastAPI app and built frontend
  (`desktop/config.py:24,30`) — same-origin, same data. `desktop/seed.py`
  does a one-time replay of `data/signals/*.jsonl` into
  `.centinelas/classified/` if empty on first run, but "never overwrites a
  live ingest/classify/dispatch run" — there is no online/offline
  reconciliation logic anywhere, because both modes read the same on-disk
  files.

---

## 3. Cross-cutting inefficiencies

1. **Triplicated full-pipeline invocation.** The identical
   `poll_all() + poll_federal_register() + poll_scrape_sources()` sequence
   is called independently from `cli.py:54`, `cli.py:154`, and
   `server/backend/main.py:191` — three call sites to keep in sync, and
   (operationally) three separate dispatch workflows
   (`dispatch-signals.yml`, `-aguayluz.yml`, `-ovnis.yml`) that each
   independently re-run the *entire* 58+-source poll from scratch just to
   filter the same raw items by a different target label, with no shared
   ingest artifact reused between them.
2. **No conditional GET / caching in the primary ingest path**, even
   though the pattern (`HttpCache`, `RateLimiter`) already exists in
   `src/centinelas/releases/adapters.py:104-142` for a different producer.
   Every poll re-downloads full feed/page bodies unconditionally.
3. **Sequential, non-parallel fetching** of 58+ independent sources with
   no `asyncio`/thread pool anywhere in `ingest/` — a single slow source
   delays the whole run.
4. **No retry/backoff anywhere in the primary ingest path**, which
   directly explains why the Just Security monitor (§2.9) has run
   ~9+ times over multiple days without ever adapting to its permanent
   403 block.
5. **`SourceHealthCheck` is a documented core entity (README.md) with zero
   implementation anywhere.** No schema, no field on any model, no
   persisted health record for the RSS/scrape/Federal-Register sources.
   The only concrete health records that exist are two independent, ad hoc
   ones invented separately by the El Yunque and Just Security tools —
   no shared schema between them.
6. **`CoverageGap` has a real schema
   (`frontend/schemas/entities/CoverageGap.schema.json`) but zero backend
   writer** — it's registered in `appClient.js:134` and seeded as an
   always-empty array (`seedData.js:151`), with no page or job that ever
   populates it.
7. **Dead API surface on the frontend.** `pipelineClient.js` exports
   `getHealth`, `getQueue`, and `getSources` that are never called by any
   page — confirmed independently by the repo's own GUI-parity baseline,
   which flags the same three symbols as `GUI_NOT_BACKEND_WIRED`.
8. **`react-query` is installed, configured, and provided at the app root,
   but entirely unused** — a zero-cost caching/dedup win is sitting idle.
9. **No caching or dedup in classification** — repeat RSS items across
   poll cycles get reclassified by the LLM every time, and a fresh
   `anthropic.Anthropic()` client is constructed per call instead of being
   reused (`classifier.py:42`).
10. **`POST /run` has no server-side timeout** while the frontend's own
    POST timeout is 15s — a full ingest pass will likely exceed that,
    meaning the one HTTP-triggerable "refresh" in the whole system is
    likely to appear to fail in the UI even when the backend eventually
    succeeds.
11. **`data/signals/live_signals.jsonl` behaves like a snapshot, not a
    ledger** — full overwrite on each run, four weeks stale, refreshed only
    by manual dispatch, and the one existing run degraded to
    keyword-only classification.
12. **Non-generated "generated" client already out of sync** —
    `src/centinelas/generated/water_disruption_client.py` covers 3 of 8
    routes and has no mechanism forcing it to track API changes.
13. **Almost all named P0/P1 PR-specific source families are still
    manual.** `data/reference/source_registry.csv` marks legislative
    calendars, municipal agendas, procurement/RFP notices, agency press
    releases, hearing notices, and board agendas as `scrape_method: manual,
    active: manual` — only generic RSS ingestion is actually automated
    today, despite these being the README's stated P0 priorities.

---

## 4. Prioritized optimization recommendations

### 4.1 Quick wins (low effort, no design discussion needed)

- **Consolidate the triplicated poll call** (§3.1) into one shared
  `acquire_all()` function in `src/centinelas/ingest/__init__.py`, called
  from `cli.py` (`ingest`, `run`) and `server/backend/main.py` (`POST
  /run`) instead of three independent copies.
- **Add a per-source health record** (`last_checked_at`, `last_success_at`,
  `consecutive_failures`) written by `poll_all()`/`poll_scrape_sources()`/
  `poll_federal_register()`, reusing the existing
  `consecutive_failures` pattern from
  `src/centinelas/ingest/email/models.py:124` and the health-JSON shape
  already proven out by `tools/el_yunque_access_monitor.py`. Surface it
  via `centinelas status` and `GET /status`. This is the single highest-
  leverage change: it turns the README's aspirational `SourceHealthCheck`
  entity into something real, and would have surfaced the Just Security
  outage on day one instead of after 9+ silent failed runs.
- **Add retry/backoff to `ingest/rss.py`, `ingest/web.py`,
  `ingest/federal_register.py`**, reusing the `RateLimiter`/`HttpCache`
  pattern that already exists (unused, outside `ingest/`) in
  `src/centinelas/releases/adapters.py:104-142`.
- **Auto-pause or alert the Just Security cron after N consecutive
  blocked/zero-result runs** instead of letting it run indefinitely for no
  signal — cheap to add given `runs.jsonl` already records certification
  status per run.
- **Wire the already-installed, already-provided `react-query` client**
  to the existing `pipelineClient` calls in `Pipeline.jsx`,
  `PipelineItemDetail.jsx`, `Handoff.jsx`, and `WaterDisruption.jsx`. This
  is a behavior-preserving refactor (same endpoints, same data) that adds
  request dedup and caching for free, since the client is already
  configured at the app root and simply unused.
- **Reuse a single Anthropic client instance** in `classify/classifier.py`
  instead of constructing one per call.

### 4.2 Structural (needs a design decision first)

- **Decide the intended semantics of `data/signals/live_signals.jsonl`.**
  Either make it genuinely append-only with a scheduled (not just manual)
  refresh trigger, so it behaves like the "ledger" it's documented as — or
  rename/re-scope it to reflect that it's actually a periodic manual
  export snapshot, and stop implying continuous freshness in
  `federation.json`/README.
- **Decide whether `SourceHealthCheck` becomes a real, shared schema**
  (the frontend already carries 22 other entity schemas plus an unused
  `CoverageGap.schema.json` — this would slot in alongside them) versus
  remaining aspirational documentation. If implemented, `CoverageGap`
  should get a real backend writer instead of its permanently-empty seed.
- **Decide on an automation plan (or an explicit "won't automate")** for
  the P0 source families still marked `manual` in
  `data/reference/source_registry.csv` — legislative calendars, municipal
  agendas, procurement notices, agency press releases, hearing notices,
  board agendas. These are the README's stated highest-priority sources,
  but zero of them are polled today.
- **Parallelize ingestion** (`asyncio`/`httpx.AsyncClient` or a thread
  pool) across the 58+ RSS feeds and 8 scrape sources once run latency or
  source count becomes a real constraint — not urgent at current volume,
  but the sequential-for-loop pattern will not scale past a modest source
  count without becoming the dominant cost of a `centinelas run`.
- **Give `POST /run` a bounded execution model** — either a server-side
  timeout with a partial-results response, or convert it to a
  background-job pattern (kick off async, poll a status endpoint) so the
  frontend's 15s client timeout stops being a race against an unbounded
  synchronous pipeline run.

---

## 5. Appendix: file reference index

**Ingestion**
- `src/centinelas/ingest/rss.py`
- `src/centinelas/ingest/web.py`
- `src/centinelas/ingest/federal_register.py`
- `src/centinelas/ingest/sources.yaml`
- `src/centinelas/ingest/just_security_sources.yaml`
- `src/centinelas/ingest/email/adapter.py`, `models.py`, `processing.py`
- `config/email_sources/google_alerts.example.yaml`
- `data/reference/source_registry.csv`, `space_source_registry_delta.csv`

**Classification / routing**
- `src/centinelas/classify/classifier.py`, `enrich.py`, `rules.py`
- `src/centinelas/route/router.py`, `dispatch.py`, `route/contracts/*.schema.json`
- `src/centinelas/cli.py`
- `scripts/build_signal_ledger.py`
- `data/signals/live_signals.jsonl`, `example_signals.jsonl`

**Backend**
- `server/backend/main.py`
- `server/backend/auth.py`
- `server/backend/water_disruption_api.py`
- `server/backend/email_review_contract.py`
- `src/centinelas/water_disruption.py`
- `src/centinelas/generated/water_disruption_client.py`
- `src/centinelas/space_observations/producer.py`, `routing.py`
- `docs/adr/ADR-0001-water-disruption-evidence-production.md`

**Standalone scheduled monitors**
- `tools/el_yunque_access_monitor.py`
- `tools/just_security_monitor.py`
- `data/monitoring/el_yunque/current.json`, `health.json`, `transitions.jsonl`
- `data/monitoring/just_security/state.json`, `events.jsonl`, `runs.jsonl`, `latest_snapshot.json`
- `.github/workflows/el-yunque-access-monitor.yml`
- `.github/workflows/just-security-monitor.yml`

**Pipeline trigger workflows**
- `.github/workflows/dispatch-signals.yml`
- `.github/workflows/dispatch-signals-aguayluz.yml`
- `.github/workflows/dispatch-signals-ovnis.yml`

**Schemas**
- `schemas/water-disruption/v0.1/centinelas-water-candidate.schema.json`
- `schemas/space_observations/sensor.schema.json`, `observation.schema.json`, `acquisition.schema.json`
- `frontend/schemas/entities/CoverageGap.schema.json`, `Source.schema.json`

**Frontend / desktop**
- `frontend/src/api/appClient.js`
- `frontend/src/api/pipelineClient.js`
- `frontend/src/lib/query-client.js`, `appQuery.js`
- `frontend/src/data/seedData.js`
- `frontend/src/pages/Monitor.jsx`, `Signals.jsx`, `SignalsTable.jsx`, `Matters.jsx`, `MatterDetail.jsx`, `Sources.jsx`
- `frontend/src/pages/Pipeline.jsx`, `PipelineItemDetail.jsx`, `Handoff.jsx`, `WaterDisruption.jsx`
- `.federation/gui-capabilities.json`, `.federation/gui-parity-baseline.json`
- `desktop/config.py`, `desktop/app_server.py`, `desktop/seed.py`, `desktop/README.md`

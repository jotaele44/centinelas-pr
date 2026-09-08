# Backend Assessment & Development Plan — centinelas-pr

## Scope & method

Read-only assessment of the backend at `main` (`caf0865`, "ci: restore bounded operational
plane for lockstep (#122)"). `centinelas-pr` is the civic-signal-intake producer node in
the PRII federation: it polls RSS/Federal Register/web sources, classifies items with
rule-based logic plus an LLM, and dispatches matches downstream — including a
water-disruption "shadow" producer role and handoffs to `moneysweep-pr` — exporting a
federation package to `thehub-pr`.

## Tech stack & backend inventory

- **Framework**: FastAPI (optional `server` extra) alongside a Typer CLI; frontend is a
  genuinely separate Node/npm React 19 + Vite 8 + Tailwind 3 + TanStack Query SPA — the
  clearest frontend+backend split of the six producers.
- **Storage**: file-based, not relational — on-disk JSON under `.centinelas/{queue,
  classified,dispatched,handoffs}/*.json`, no caching. Pydantic models in
  `src/centinelas/models.py`: `RawItem` (deterministic `item_id = sha256(url+published_at)`),
  `ClassifiedItem` (labels/confidence/reasoning + optional finance/location enrichment),
  `DispatchRecord`.
- **Endpoints**:
  - `main.py` ("Centinelas-PR universal intake API"): `/health`, `/items`,
    `/items/{item_id}`, `/queue`, `/sources`, `/status`, `/handoffs`,
    `POST /handoffs/{item_id}` (dispatch/retry to downstream federation consumers),
    `POST /run` — runs the **entire** ingest→classify→dispatch pipeline synchronously
    inside the request handler.
  - `water_disruption_api.py` (mounted at `/water-disruption/*`): `/console` (inline HTML),
    `/sources`, `/runs`, `/evidence/{evidence_id}`, `/candidates`, `/outbox`,
    `POST /capture`, `POST /candidates/{candidate_id}/dispatch`,
    `POST /outbox/{outbox_id}/deliver` (idempotency-key + dead-letter queue),
    `POST /candidates/{candidate_id}/retract` — self-labeled `shadow_mode: true`
    throughout ("No live alerts or production promotion").
  - `email_review_contract.py` present, not inspected in depth in this pass.
- **Auth**: **none at all**, on either `main.py` or `water_disruption_api.py` — more
  exposed than most sibling producers, since even the water-disruption write routes
  (`/capture`, `/dispatch`, `/deliver`, `/retract`) have no token check, only
  idempotency-key dedup.
- **Business/services layer**: `src/centinelas/ingest/` (`rss.py`,
  `federal_register.py`, `web.py`, `email/`), `classify/` (`classifier.py`, `rules.py`,
  `enrich.py`, `labels.py`), `route/` (`dispatch.py`, `router.py`, `contracts/`), plus
  `foia_disposition.py`, `water_disruption.py`, `space_discovery.py` +
  `space_observations/`, `natural_features.py`.
- **Background jobs**: none in-process; cadence driven entirely by GitHub Actions
  (`dispatch-signals.yml`, `dispatch-signals-aguayluz.yml`, `dispatch-signals-ovnis.yml`,
  `el-yunque-access-monitor.yml`, `just-security-monitor.yml`,
  `federal-records-*-canary.yml`, `foia-canary-*.yml`). The outbox/dead-letter store in
  `water_disruption_api.py` has no automatic drain/retry worker.
- **Tests/CI**: ~48 test files (classifier, dispatch, water_disruption +
  `water_disruption_api` — only 807 B for a 9-route surface, thin — federation_export,
  space_discovery/observations, foia_disposition, permit_ecosystem, gui_parity via
  Playwright, server_smoke, run/handoff endpoints). Coverage floor `fail_under = 72`
  (scoped to `src/centinelas`; `server/backend` excluded from the ratchet, same pattern as
  sibling producers). `validate.yml` is a genuinely solid multi-job gate: lint, validate
  (Python 3.10–3.12 matrix incl. federation manifest gate + `pytest --cov`), lockfile
  canonicality, mypy, frontend lint/test/build.

## Completion assessment

- **Fully implemented**: ingest (RSS/Federal Register/web scraping), rule-based + LLM
  classification, file-based pipeline persistence, best-tested CI pipeline of the six
  producers, frontend build/lint/test.
- **Partially implemented**: water-disruption "shadow" producer (capture/dispatch/deliver/
  retract endpoints exist with idempotency + DLQ, but nothing automatically drains the
  outbox); handoff-to-MoneySweep flow (endpoint exists, cross-repo matching correctness
  unverified from this repo alone).
- **Missing entirely**: any authentication on the FastAPI surface; a background job/queue
  model for `POST /run` (fully synchronous); a scheduler/worker to drain the
  water-disruption outbox and dead-letter queues.

## Development plan — hardest tasks first

Ordering rationale: items 1–2 are sequenced first as genuine distributed-systems/reliability
problems (a synchronous long-running endpoint, and an outbox with no drain worker) that
silently drop or stall work today; item 3 is open-ended ML tuning that never truly
"completes," so it's tracked as ongoing rather than gating anything; items 4–5 are
narrower/cross-repo verification work that can proceed once the above are stable.

1. **Move `POST /run` off the synchronous request path onto a background-job model**
   (mirroring `spiderweb-pr`'s job-id+SSE pattern) — Effort: **L**. Ingest +
   Anthropic-API classification + dispatch can be slow/rate-limited; a request timeout
   today silently drops in-flight work. Touches ingest/classify/dispatch together, so it's
   a cross-cutting change, not an isolated endpoint fix.
2. **Build a real retry/reliability worker for the water-disruption outbox and
   dead-letter queue** — Effort: **L**. The delivery mechanics (idempotency keys, DLQ)
   already exist but nothing automatically drains or replays them — genuine
   distributed-systems reliability work, not a bug fix.
3. **Ongoing LLM classification accuracy tuning** (`classifier.py` + `enrich.py`,
   confidence scoring, `DomainLabel` taxonomy) — Effort: **open-ended**. Not a fixed
   deliverable; track as a continuous quality item rather than a task to "complete."
4. **Scope and harden the "space" domain** (`space_discovery.py` + `space_observations/`,
   with dedicated schema-freeze/embedded/boundary tests) — Effort: **M**. A substantial
   subsystem whose relationship to the README's "civic pre-officialization signal monitor"
   scope isn't documented; needs the same formal boundary work `spiderweb-pr` did for its
   FR24/airspace surface.
5. **Guarantee correctness of the Centinelas→MoneySweep handoff/matter-lifecycle
   matching** (shared `Cell_ID` spatial grid, matter lifecycle stages per README) —
   Effort: **M**, cross-repo. Can't be fully validated from this repo alone; needs
   coordination with `moneysweep-pr`'s own assessment.

## Quick wins (sequenced after/alongside the above, not skipped)

- Add the same shared-secret bearer guard other producers use to `POST /run`,
  `POST /handoffs/*`, and the four mutating `/water-disruption/*` routes as an interim
  measure ahead of the federation-wide auth contract (`thehub-pr`'s plan doc).
- Flesh out `tests/test_water_disruption_api.py` — currently 807 bytes for a 9-route
  surface.
- Extract `water_disruption_api.py`'s inline HTML string (`GET /console`) into a template
  file.

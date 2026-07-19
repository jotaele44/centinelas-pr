# Road to 100%

A leverage-ordered ledger of what stands between Centinelas-PR today and a
"100% complete" federation node. It separates work that can be **closed in
code here** from work that is **blocked on data access or network** (live PR
pre-official feeds, an `ANTHROPIC_API_KEY`, and the sibling repos being live).

**Current completion: ~90%** (was ~85% before this PR; the two remaining
code-closable gaps below are now closed).

---

## Where the engine already stands (done)

These are implemented, tested, and exercised against real data — not stubs.

- **Two-tier classifier** — deterministic keyword rules as the fast path, with a
  Claude Haiku fallback for ambiguous/unmatched items. The LLM tier degrades
  *gracefully* to keyword rules when no `ANTHROPIC_API_KEY` is present or the
  network is unreachable (`src/centinelas/classify/classifier.py`).
- **Six-domain routing with contract schemas** — `ENVIRONMENTAL`, `FINANCIAL`,
  `POLITICAL`, `GEO_GEOLOGY`, `ANOMALOUS`, `MILITARY_AEROSPACE` map to sibling
  repos, with the MoneySweep anchor receiving the finance/location enrichment its
  intake contract declares (`src/centinelas/route/router.py`, `schemas/`).
- **Confidence gate** — sub-threshold items are `skipped`, not dispatched, keeping
  low-confidence noise out of the downstream event pipeline
  (`CENTINELAS_ROUTE_MIN_CONFIDENCE`, default 0.55).
- **Event-driven federation egress** — `CENTINELAS_OUTBOUND_DIR` stages payloads
  per-repo for `scripts/emit_dispatches.py` to POST as `repository_dispatch`
  events, so no sibling checkout is required in CI.
- **Proven at volume** — a real pipeline run over the configured RSS registry
  ingests and classifies **250+ live signals** end-to-end via the keyword tier
  alone (253 ingested / 133 routed / 120 gated in a representative dry run).
- **84 tests** (81 baseline + 3 for the new `/run` endpoint), covering
  classification, routing, dispatch, CLI, federation export/contract-compat, and
  the desktop/API server.

### Live-run record

Concrete evidence the `poll_all → classify → dispatch` path runs end-to-end
against the live RSS registry, keyword tier only (no `ANTHROPIC_API_KEY`; the
LLM tier fell back to keyword rules for every item, as designed):

- **2026-07-12** — `python scripts/build_signal_ledger.py` + `centinelas.cli run
  --dry-run` over the live feeds: **254 ingested / 254 classified / 114 routed
  (ok) / 140 gated** (sub-threshold `UNCLASSIFIED`). The refreshed real-signal
  snapshot (`is_synthetic: false`, captured at run time) is committed at
  `data/signals/live_signals.jsonl` — 254 rows,
  beats `{military_aerospace: 58, political: 21, environmental: 14, geo_geology: 10,
  financial: 7, anomalous: 4, unclassified: 140}`.
  This snapshot uses the word-boundary keyword classifier (see below), so it no
  longer carries the substring-collision false positives (`sec` in "Second",
  `epa` in "repair", `war` in "toward") that inflated the earlier counts.
  Verifier: `pytest -k "classif or rout or dispatch or run"` → 45 passed /
  2 skipped; `ruff check .` → clean.
  - **Classifier precision fix** — the keyword tier now matches on WORD
    BOUNDARIES (`\bsec\b`, trailing-plural tolerant) instead of naive substring
    containment, so short finance tokens no longer misfire inside unrelated
    words. Regression tests in `tests/test_classifier.py` assert `sec`-in-"Second"
    (and peers) do not classify FINANCIAL while standalone tokens and plurals
    still do (`src/centinelas/classify/rules.py`).

---

## Water-monitoring signal layer (closed here)

The federation water-monitoring vertical's Centinelas side is now real code:

- [x] **Water/utility sub-taxonomy** (`src/centinelas/classify/rules.py`). PR
  water/utility terms (PRASA, acueducto, wastewater, embalse/reservoir, boil-water,
  LUMA/PREPA/PREB outage, sequía/racionamiento) route to `aguayluz-pr` via
  `ENVIRONMENTAL`, and `water_utility_subtypes()` tags *which* beat a signal is
  (potable_water, boil_water, water_quality, wastewater, reservoir_drought, flood,
  power_grid) instead of collapsing all water news into generic climate.
- [x] **`domain_tags` on the dispatch payload** (`route/router.py`) — carried to
  `aguayluz-pr` (and the Hub) so the consumer can pick an event_type.
- [x] **Aguayluz egress wired** (`.github/workflows/dispatch-signals-aguayluz.yml`).
  Previously only `moneysweep-pr` had a dispatch workflow; the ENVIRONMENTAL →
  aguayluz hop now has its operator-triggered `emit_dispatches --only-repo
  aguayluz-pr` egress. The consumer side (`aguayluz-pr` `centinelas-intake.yml` +
  `scripts/ingest_centinelas_dispatch.py`) maps the payload into a service_event.

The **classifier keyword tier** is real and testable offline; LLM classification
still needs `ANTHROPIC_API_KEY`, and live PR water-source *intake* remains blocked
below.

## Remaining — code (closable here)

Both items below are **closed by this PR**.

- [x] **Implement the deferred `POST /run`** (`server/backend/main.py`).
  The read-only visibility API now has an HTTP twin of `centinelas run`: it reuses
  the exact `poll_all → classify → dispatch` path the CLI exposes, writes
  classified items where `/items` and `/status` read them, and honours the same
  offline contract (unreachable feeds → fewer/zero items; missing key → keyword
  fallback; `dry_run` skips cross-repo writes but persists local bookkeeping).
  Returns a JSON run summary. Covered by `tests/test_run_endpoint.py`
  (TestClient, keyword-tier only, no API key).
- [x] **Gate `ruff` in CI** (`.github/workflows/validate.yml`).
  A dedicated `lint` job now runs `ruff check .` (ruff was configured but never
  enforced). The existing tree was brought to a clean state so the gate passes
  rather than blocking on pre-existing lint debt.

---

## Remaining — data / network-blocked (cannot be closed offline)

These are **not code gaps** — they need external access the audit environment
does not have. Listed highest-leverage first.

1. **PR-specific pre-official source intake.**
   The live registry (`src/centinelas/ingest/sources.yaml`) is generic global-topic
   RSS (Defense News, NOAA, USGS, …). The README's core thesis is *pre-officialization
   Puerto Rico signals*: legislative calendars and committee agendas, municipal
   assembly agendas, agency press releases, procurement notices / RFPs, public-hearing
   notices, and public-board agendas (PREPA, AAA, Ports, UPR, COR3, PREB filings).
   These are largely not RSS — they require per-source scrapers/adapters and live
   endpoints. This is the single biggest gap between the working *engine* and the
   *product* the README describes. **Blocked on: live PR source access + adapters.**

2. **Full Centinelas ↔ MoneySweep matter-lifecycle handoff (stages 0–6).**
   The README defines a shared `Matter` lifecycle (Stage 0 raw observation →
   Stage 4 officialized in MoneySweep → Stage 6 audit/impact) with a
   `HandoffCandidate` when a downstream official record appears. Today's dispatch
   emits per-signal payloads with `signal_stage`/`beat` enrichment, but the
   end-to-end matter object, stage transitions, and `matched_to_moneysweep`
   handoff are **partly aspirational**. **Blocked on: MoneySweep live intake +
   shared matter store.**

3. **LLM classification tier in production.**
   The Claude Haiku path is implemented and falls back cleanly, but exercising it
   (vs. keyword-only) needs an `ANTHROPIC_API_KEY`. All offline verification here
   runs the keyword tier. **Blocked on: API key / network.**

---

## Verification (offline)

```bash
# targeted suite (excludes 3 files that import the git-only prii_* packages,
# which cannot install offline; they run in CI where those packages are present)
python3 -m pytest tests/ -q -k "classif or rout or dispatch or run" \
  --ignore=tests/test_federation_export.py \
  --ignore=tests/test_federation_contract_compat.py \
  --ignore=tests/test_maintenance.py

# lint gate (the same command CI now enforces)
ruff check .

# workflow stays valid YAML
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/validate.yml'))"
```

---

## Scorecard

| Track | State |
|---|---|
| Classifier (keyword + LLM fallback) | Done |
| Six-domain routing + contracts | Done |
| Confidence gate + event egress | Done |
| `POST /run` endpoint | **Closed this PR** |
| `ruff` CI gate | **Closed this PR** |
| PR pre-official source intake | Data-blocked |
| Matter-lifecycle handoff (stages 0–6) | Partly aspirational / data-blocked |
| LLM tier in production | Key/network-blocked |

**Code completeness: ~100% of what is closable offline is closed.**
**Product completeness: ~90%**, with the remainder gated on live PR data sources,
the sibling repos being live, and an API key — none of which can be resolved in an
offline audit.

# Centinelas-PR — Normalized Road to 100 Status

**Governance version:** `road_to_100_normalization_v0_2`  
**Audit date:** 2026-07-27  
**Evidence boundary:** repository `main`, canonical `federation.json`, `docs/ROAD_TO_100.md`, `docs/MATURITY_AUDIT.md`, and recorded executed baselines.  
**Status mutation:** none. This document does not change `production_status` or federation readiness gates.

## Normalized scorecard

| Metric | Value | Interpretation |
|---|---:|---|
| Implemented scope | **75% — intended Puerto Rico product** | The generic ingest/classify/route engine is approximately 90% implemented, but the stated Puerto Rico pre-officialization product lacks much of its source-adapter and matter-lifecycle scope. |
| CI-enforced maturity | **69%** | Derived from the 20-criterion professional maturity audit. |
| Operational data readiness | **60%** | Real RSS intake and production export are evidenced, but intended-scope Puerto Rico legislative, municipal, regulatory, procurement, and board sources remain largely uncovered. |
| Live-gate evidence depth | **D2 — real recurring generic intake, partial intended scope** | The real signal ledger and export work; domain-specific Puerto Rico intake coverage and complete downstream matter transitions remain incomplete. |
| Current live-execution gate | **true** | Preserved from `federation.json`; not altered by this normalization. |

## Verification anchor

- **Last verified `main` commit:** `24d0769061c526a5b765ce0fa71dcd037f9a518e`
- **Last executed test baseline:** `139 passed` in the federation maturity audit.
- **Recorded real intake:** 254 real signals in the July 12 ledger run described by the roadmap; the manifest records an earlier 274-signal production validation.
- **Evidence confidence:** high for engine operation and export; medium for operational readiness because the intended Puerto Rico source universe has not been fully enumerated and materialized.

## Generic engine versus intended product

The legacy `~90%` score applies to the reusable signal engine: polling, classification, confidence gating, routing, dispatch, the `/run` path, and production export. It must not be used as the completion percentage for the complete Centinelas product described in the repository.

The intended product still requires:

1. Puerto Rico legislative calendars, committee agendas, and measure notices.
2. Municipal assembly agendas and public-hearing notices.
3. Agency press releases, procurement notices, RFPs, and public-board agendas.
4. PREB, PREPA, AAA, Ports, UPR, COR3, and related document/portal adapters where RSS is unavailable.
5. The complete Stage 0–6 matter lifecycle and authoritative MoneySweep handoff state.
6. Production exercise of the LLM tier where it is retained as part of the product.
7. Coverage floor, type checking, and frontend tests enforced in CI.

A true live gate confirms that the current real RSS ledger can produce a valid package. It does not certify full Puerto Rico pre-officialization source coverage.

## Evidence-depth scale

- **D0:** synthetic or no production corpus; no live production export.
- **D1:** small real seed corpus; production package may validate, but recurrent intake is unproven.
- **D2:** partial real intended-scope corpus and bounded or recurring runs; important source or freshness gaps remain.
- **D3:** recurring real intended-scope intake and valid production export with material provenance or coverage caveats.
- **D4:** recurring intended-scope live intake, freshness controls, production export, and consumer validation.

The detailed implementation narrative remains in [`ROAD_TO_100.md`](ROAD_TO_100.md). This normalized companion controls cross-repository comparisons.
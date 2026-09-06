# Road to 100 — normalized federation score

**Audit date:** 2026-08-19
**Scoring model:** code completeness 20%; main-branch availability 15%; CI enforcement 15%; data materialization 15%; operator verification 15%; GUI completeness 10%; federation readiness 10%.

## Current normalized score: 75.35 / 100

| Dimension | Weight | Score | Weighted |
|---|---:|---:|---:|
| Code completeness | 20 | 92 | 18.40 |
| Main-branch availability | 15 | 88 | 13.20 |
| CI enforcement | 15 | 75 | 11.25 |
| Data materialization | 15 | 55 | 8.25 |
| Operator verification | 15 | 65 | 9.75 |
| GUI completeness | 10 | 70 | 7.00 |
| Federation readiness | 10 | 75 | 7.50 |

The former ~90% figure measured offline code completeness. It is historical and is not used for cross-repository comparison.

## State reconciliation

- The classifier, confidence gate, routing contracts, dispatch path, water taxonomy and backend run surface are on `main`.
- PR #78 merged on `main`; isolated-clone runtime and immutable shared-package sources are now authoritative.
- PR #77 is superseded for runtime setup by the merged isolated-clone contract. Any remaining workspace-policy text must be reconciled independently with TheHub.
- PR #79 is rescued branch history, not certified current implementation.
- PR #80 is a governance-only skill disposition and no longer blocks runtime delivery.
- Production export is fail-closed for empty, malformed, future-dated, synthetic, or stale ledgers. Hub live execution remains blocked until acquisition refreshes the committed ledger and downstream validation succeeds.
- The Water Disruption shadow console is wired through API discovery, navigation, failure/retry UI, unit coverage, and GUI-parity E2E coverage.
- Puerto Rico pre-official source acquisition is locally complete on draft PR #124 at `d0006cfe20a6fbc1fca663d2607d8f68e0c83092`; hosted checks are blocked before execution by the GitHub Actions billing lock.
- The remaining central product gap is a durable Matter lifecycle through MoneySweep.

## 2026-09-06 Puerto Rico source checkpoint

- Scope: six official source manifestations across PREB, AAA, COR3, Senate, and House; source records are discovery candidates with `identity_effect=NONE`, `binding_state=UNRESOLVED`, and `candidate_cardinality=UNRESOLVED`.
- Frozen result: `1,131 = 56 PREB notices + 363 AAA releases + 706 COR3 releases + 0 active COR3 RFPs + 5 Senate calendar items + 1 House calendar item` across 80 byte-bound responses.
- Provenance: PREB and AAA linked archives are fully paginated; COR3 press pagination closes against a stable 706-row response header; current COR3 RFP emptiness is explicit; Senate and House scope is every item exposed on their configured current calendar pages.
- Verification: 373 tests pass with 1 skip; Ruff and mypy pass; the final receipt has zero failed gates and zero self-verification errors.
- Boundaries: this is bounded source-manifestation exhaustion, not universal Puerto Rico source exhaustion and not canonical matter identity. The implementation remains off `main` while PR #124 is draft and exact-head hosted checks cannot execute.

## Priority exit sequence

1. Refresh the live ledger through a bounded, receipt-producing Puerto Rico acquisition run and validate the production export downstream.
2. Dispose of rescued and governance-only PRs without importing stale data by assumption.
3. Land the locally complete PREB, AAA, COR3, and legislative acquisition accounting after exact-head hosted checks can execute; operator freshness/failure state is implemented by `centinelas source-status`.
4. Certify shared Matter stages 0–6 and MoneySweep reconciliation across repositories.
5. Exercise the LLM tier with secret-safe production receipts while preserving deterministic fallback.

## Machine-readable authority

See `docs/unfinished_implementation_ledger.v1.json`. Only evidence on `main` closes an item; draft PRs remain candidates.

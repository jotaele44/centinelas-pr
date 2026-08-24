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
- The central product gap remains Puerto Rico pre-official source acquisition and a durable Matter lifecycle through MoneySweep.

## Priority exit sequence

1. Refresh the live ledger through a bounded, receipt-producing Puerto Rico acquisition run and validate the production export downstream.
2. Dispose of rescued and governance-only PRs without importing stale data by assumption.
3. Complete PREB, AAA, COR3, and legislative acquisition accounting and expose freshness/failure state to operators.
4. Certify shared Matter stages 0–6 and MoneySweep reconciliation across repositories.
5. Exercise the LLM tier with secret-safe production receipts while preserving deterministic fallback.

## Machine-readable authority

See `docs/unfinished_implementation_ledger.v1.json`. Only evidence on `main` closes an item; draft PRs remain candidates.

# Road to 100 — normalized federation score

**Audit date:** 2026-08-04  
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
- PR #78 is the current isolated-clone candidate.
- PR #77 is a workspace-policy candidate whose authority should be reconciled with #78 and TheHub.
- PR #79 is rescued branch history, not certified current implementation.
- PR #80 records a proposed skill deletion and requires an explicit keep/remove decision.
- The central product gap remains Puerto Rico pre-official source acquisition and a durable Matter lifecycle through MoneySweep.

## Priority exit sequence

1. Adjudicate isolated-clone and workspace-policy changes.
2. Dispose of rescued and deletion-intent PRs without importing stale data by assumption.
3. Implement a bounded first Puerto Rico source tranche with acquisition accounting.
4. Add the shared Matter stages 0–6 and MoneySweep handoff reconciliation.
5. Exercise the LLM tier with secret-safe production receipts while preserving deterministic fallback.

## Machine-readable authority

See `docs/unfinished_implementation_ledger.v1.json`. Only evidence on `main` closes an item; draft PRs remain candidates.

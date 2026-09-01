# Water-disruption ingestion producer contract v0.1

## Source registry

Required fields: `source_id`, `name`, `source_class`, `evidence_tier`, `authority_scope`, `municipalities`, `entrypoints`, `poll_interval`, `capture_method`, `parser_version`, `enabled`, `access_notes`, `created_at`, and `updated_at`.

A run ledger records exactly one terminal outcome for every enabled source: `success`, `not_modified`, `empty`, `blocked`, `rate_limited`, `parse_failed`, or `transport_failed`. Coverage is `accounted sources / enabled sources`; release requires 100% accounting, not 100% successful retrieval.

## Producer API

| Method | Path | Purpose |
|---|---|---|
| GET | `/water-disruption/sources` | Registry and current source health |
| GET | `/water-disruption/runs` | Source-accounting runs |
| GET | `/water-disruption/evidence/{id}` | Immutable evidence object |
| GET | `/water-disruption/candidates` | Candidate review queue |
| GET | `/water-disruption/outbox` | Delivery state |
| POST | `/water-disruption/candidates/{id}/dispatch` | Idempotent dispatch/retry |
| POST | `/water-disruption/candidates/{id}/retract` | Append retraction event |

All mutation endpoints require an idempotency key and return the persisted envelope hash.

## Queue design

1. `acquisition_attempts`: one record per source/run.
2. `raw_evidence`: append-only, content-addressed.
3. `candidate_extract`: deterministic extraction jobs.
4. `candidate_review`: unresolved/ambiguous candidates.
5. `delivery_outbox`: at-least-once delivery to Agua y Luz.
6. `delivery_receipts`: consumer acknowledgement keyed by envelope hash.
7. `dead_letter`: schema, provenance, integrity, or retry-exhaustion failures.

Ordering is per candidate, not global. Redelivery may occur. Consumers must be idempotent.

## Test matrix

| Area | Required cases |
|---|---|
| Schema | valid envelope; missing evidence; forbidden `confirmed` state; invalid hashes; unknown subtype |
| Evidence | append-only enforcement; correction linkage; deleted-source preservation |
| Accounting | every enabled source terminally accounted; blocked and empty retained; disabled excluded |
| Extraction | Spanish/English break, repair, outage, pressure, advisory, restoration vocabulary |
| Exclusions | private plumbing, account shutoff, cistern failure, stale repost, ambiguous `sin agua` |
| Dedup | stable across replay; six-hour bucket boundary; distinct municipalities/assets remain separate |
| Confidence | deterministic component scores; no score promotes truth state |
| Delivery | duplicate send, lost acknowledgement, retry, dead-letter, unsupported consumer version |
| Retraction | source correction; wrong location/type; downstream notification without evidence deletion |
| API/GUI | list/detail/filter/retry/retract paths; loading, empty, stale, failure, and recovery states |

## Implementation sequence

1. Land producer and consumer schemas plus compatibility fixtures.
2. Extend water vocabulary and candidate extraction without changing existing generic dispatch.
3. Add immutable evidence store and complete source-run ledger.
4. Add deterministic candidate IDs, dedup keys, confidence decomposition, and review queue.
5. Add durable outbox and Agua y Luz acknowledgement contract.
6. Implement Agua y Luz validation gate and canonical incident lifecycle.
7. Add API surfaces.
8. Add discoverable GUI surfaces and end-to-end parity tests.
9. Shadow-run beside the generic payload, compare accounting and false-positive rates.
10. Enable v0.1 dispatch only after schema, replay, retraction, and no-unverified-promotion gates pass.

## Acceptance gates

- 100% enabled-source accounting per run.
- zero candidate envelopes with a truth state other than `candidate`.
- deterministic IDs/hashes under replay.
- no evidence mutation or destructive retraction.
- idempotent redelivery.
- complete restoration and retraction propagation.
- backend → API → client → component → discoverable GUI parity before production activation.

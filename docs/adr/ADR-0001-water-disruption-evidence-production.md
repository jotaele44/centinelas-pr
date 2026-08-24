# ADR-0001: Centinelas as water-disruption evidence producer

- Status: Proposed
- Contract: `prii.water-disruption/v0.1`
- Producer: `centinelas-pr`
- Consumer: `aguayluz-pr`

## Decision

Centinelas owns source discovery, acquisition, immutable evidence capture, candidate extraction, source accounting, and delivery. Agua y Luz owns domain validation, canonical incident identity, service-impact truth state, lifecycle transitions, restoration tracking, and retractions.

Centinelas MUST NOT emit a confirmed outage. It emits only a `candidate_event` with an explicit confidence assessment and linked immutable evidence.

## Required flow

`source registry -> acquisition attempt -> raw evidence -> candidate extraction -> deterministic candidate deduplication -> durable outbox -> Agua y Luz validation queue`

Every enabled source produces an acquisition-attempt record on every scheduled run, including `success`, `not_modified`, `empty`, `blocked`, `rate_limited`, `parse_failed`, and `transport_failed`. This is the basis for 100% source accounting.

## Source classes

- PRASA/AAA official notices and service channels
- Puerto Rico municipal and emergency-management channels
- news and radio reporting
- public social reporting
- public-works, road-work, excavation, and repair notices

Each source has a stable `source_id`, evidence tier, authority scope, polling policy, parser version, terms/access notes, and enabled state. Social and eyewitness sources remain unverified evidence unless corroborated.

## Evidence invariants

1. Raw evidence is append-only. Corrections create a new evidence object linked by `supersedes_evidence_id`.
2. Evidence identity is deterministic from canonical source URL, publisher timestamp, normalized content hash, and capture method.
3. Original text, retrieval timestamp, HTTP metadata where available, content hash, parser version, and source identity are retained.
4. Candidate objects reference evidence IDs and never embed an untraceable derived claim.
5. A deleted or changed source does not delete prior evidence.
6. Retractions are explicit events, not destructive edits.

## Candidate scope

Candidate types include broken mains or tubing, leaks, emergency and scheduled repairs, valve work, planned shutdowns, loss of service, low pressure, intermittent service, pump/well/tank/treatment failures, boil-water or water-quality advisories, and restoration notices.

Building-only plumbing, account-specific shutoffs, private cistern failures, stale reposts, and ambiguous `sin agua` reports are retained as evidence but fail the promotion gate unless the report establishes a public distribution-system impact.

## Confidence

Confidence is decomposed rather than represented by a single opaque score:

- `source_reliability`: source-tier prior
- `claim_specificity`: explicit cause, location, time, and service effect
- `location_resolution`: municipality/barrio/sector/asset resolution quality
- `corroboration`: independent evidence support
- `freshness`: relation between publication, event, and capture times
- `overall`: deterministic weighted result

Confidence never changes the truth-state vocabulary. A high-confidence candidate is still a candidate until Agua y Luz validates it.

## Deterministic deduplication

Centinelas candidate deduplication uses a stable key over:

`event_family | normalized municipality | normalized locality | normalized infrastructure mention | service_effect | 6-hour event-time bucket`

This key groups reporting candidates only. Agua y Luz performs canonical incident deduplication using its domain state and may merge or split candidate groups without altering Centinelas evidence.

## Delivery and queue semantics

The durable outbox is at-least-once. Every envelope carries `event_id`, `candidate_id`, `schema_version`, `producer`, `produced_at`, and `payload_sha256`. Agua y Luz acknowledges by idempotency key. Redelivery is expected and must not create duplicate evidence or incidents.

Dead-letter reasons are enumerated: unsupported schema, invalid signature/hash, malformed payload, missing evidence, prohibited truth-state claim, and exhausted delivery attempts.

## API and GUI parity

The implementation phase must expose source health, acquisition accounting, candidate queue, evidence detail, dispatch state, retry, and dead-letter review through the Centinelas GUI. No normal operator action may require a terminal or direct API call.

## Consequences

- Centinelas remains reusable for other domains.
- Agua y Luz receives structured candidates without surrendering validation authority.
- Unverified citizen reports cannot silently become confirmed outages.
- Source and delivery failures become measurable instead of disappearing.

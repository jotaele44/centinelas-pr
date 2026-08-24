# FOIA Disposition Engine Validation Ledger v0.4

## Scope

Target branch: `codex/foia-disposition-engine-v0-1`

Base: `24d0769061c526a5b765ce0fa71dcd037f9a518e`

Draft PR: `#50`

## CI-certified implementation

- Finding-level multi-destination routing remains deterministic-first.
- Versioned `FederationEnvelope` schema: `prii.foia.finding` `0.2.0`.
- Durable receipt states: pending, acknowledged, failed, superseded.
- Per-target failed export retry selection.
- Append-only review queue storage with idempotent case insertion.
- Reversible superseding decisions.
- Explicit entity-collision review behavior.
- Semantic scores cannot create routes without deterministic terms.
- Raw low-confidence OCR cannot bypass review.

## Python compatibility remediations

1. Replaced Python 3.11-only `enum.StrEnum` with `str, Enum`.
2. Replaced Python 3.11-only `datetime.UTC` with `timezone.utc`.

## Authoritative CI certificate

| Gate | Result |
|---|---|
| Ruff | PASS |
| Python 3.10 full validation and pytest | PASS |
| Python 3.11 full validation and pytest | PASS |
| Python 3.12 full validation and pytest | PASS |
| Federation manifest/export gates | PASS |
| Puerto Rico spatial-grid gate | PASS |
| Federation template drift | PASS |

## Isolated live persistence canary v0.4

Canary ID: `centinelas-foia-canary-v0-4-20260727`

Input was a non-private synthetic mixed-content FOIA finding. No real person, contract, aircraft, utility event, or anomalous incident was represented.

Production datasets were not modified. Every destination write was isolated on branch `canary/centinelas-foia-v0-4`.

| Destination | Repository | Record ID | Result |
|---|---|---|---|
| TheHub Evidence | `jotaele44/thehub-pr` | `thehub_evidence-canary-b5a9725373b4c7cba1f2` | ACKNOWLEDGED |
| TheHub Intelligence | `jotaele44/thehub-pr` | `thehub_intelligence-canary-76998f1f53c93a11a511` | ACKNOWLEDGED |
| OVNIS | `jotaele44/ovnis-pr` | `ovnis-canary-15f142cac8289e537f90` | ACKNOWLEDGED |
| Skywatcher | `jotaele44/skywatcher-pr` | `skywatcher-canary-de2c2d3b39f73a9fb097` | ACKNOWLEDGED |
| AguaYLuz | `jotaele44/aguayluz-pr` | `aguayluz-canary-05aa789b7579dabb3427` | ACKNOWLEDGED |
| MoneySweep | `jotaele44/moneysweep-pr` | `moneysweep-canary-61c2d8d7b357162e3999` | ACKNOWLEDGED |
| Spiderweb | `jotaele44/spiderweb-pr` | `spiderweb-canary-cceda8858b4548b260a3` | ACKNOWLEDGED AFTER RETRY |

### Failure and retry

The first Spiderweb write targeted the deliberately nonexistent branch `canary/injected-failure-v0-4` and returned HTTP 404. Only Spiderweb was retried. The retry persisted successfully on the valid canary branch.

### Idempotency probe

A second create attempt against the existing OVNIS canary receipt path was rejected with HTTP 422 because the path already existed and no replacement SHA was supplied. No duplicate record was created.

### Review controls

- Synthetic entity-collision case remained review-only; no identity auto-merge was authorized.
- Synthetic OCR confidence `0.42` remained blocked from automatic export.
- Page-level citation and document-binding controls remained unchanged.

### Captured evidence

`artifacts/foia_canary_v0_4/CANARY_MANIFEST.json` records destination repositories, branches, record IDs, commit SHAs, injected failure, retry scope, idempotency probe, and review-control dispositions.

## Certification boundary

This was a **live cross-repository isolated-branch persistence canary**, not a production `repository_dispatch` adapter canary.

The production dispatch workflows were not used because at least one existing consumer commits promoted records directly into its default-branch production corpus. Therefore the following remain unverified:

- downstream adapter transformation into each production domain schema;
- callback acknowledgment into Centinelas via `centinelas-handoff-ack`;
- live consumer-side duplicate flags;
- live partial-failure retry through `FEDERATION_DISPATCH_TOKEN`.

## Disposition

`ISOLATED_LIVE_PERSISTENCE_CERTIFIED_PRODUCTION_DISPATCH_NOT_CERTIFIED`

# FOIA Disposition Engine Validation Ledger v0.2

## Scope

Target branch: `codex/foia-disposition-engine-v0-1`

Base: `24d0769061c526a5b765ce0fa71dcd037f9a518e`

## Implemented integration

- Finding-level multi-destination routing remains deterministic-first.
- Added a versioned `FederationEnvelope` compatible with the repository's shared federation pattern.
- Added durable receipt state: pending, acknowledged, failed, superseded.
- Added per-target failed export retry selection.
- Added append-only review queue storage with idempotent case insertion.
- Added reversible superseding decisions.
- Added explicit entity-collision review behavior.
- Semantic scores are clamped to `[0, 1]` and cannot create routes without deterministic terms.
- Threshold order is validated at construction.

## Preservation controls

- Raw OCR cannot bypass extraction-confidence review.
- Findings require at least one page citation.
- Every citation must reference the finding's document.
- Entity collision does not auto-merge identities.
- Canonical evidence is routed independently from intelligence indexing.
- Routing decisions remain reversible and auditable.

## Added acceptance tests

- export failure
- acknowledged receipt
- duplicate receipt
- failed-target-only retry selection
- entity collision
- AguaYLuz routing
- Spiderweb routing
- semantic score boundaries
- invalid threshold ordering
- superseding decision
- review queue deduplication

## Validation limitations

The execution container could not resolve `github.com`, and the GitHub CLI was unavailable. Therefore this run could not execute the branch's pytest, Ruff, JSON Schema, or full-repository gates locally. The draft PR is intended to trigger repository CI. Runtime certification remains pending CI results and must not be inferred from connector-level source validation.

## Disposition

`IMPLEMENTED_PENDING_CI`

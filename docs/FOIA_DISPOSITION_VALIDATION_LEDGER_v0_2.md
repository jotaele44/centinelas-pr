# FOIA Disposition Engine Validation Ledger v0.3

## Scope

Target branch: `codex/foia-disposition-engine-v0-1`

Base: `24d0769061c526a5b765ce0fa71dcd037f9a518e`

Certified head: `015a465b4159efc8394afb28a87fad873e9ce43e`

Draft PR: `#50`

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

## Acceptance tests

- mixed-content multi-destination routing
- duplicate release suppression
- low-confidence OCR review
- sensitive-content hold
- no-route archive disposition
- AguaYLuz routing
- Spiderweb entity-collision review
- semantic score clamping
- prevention of semantic-only route creation
- invalid threshold ordering
- export failure
- acknowledged receipt
- duplicate receipt
- failed-target-only retry selection
- receipt attempt accounting
- review queue deduplication
- reversible superseding decision

## Reproducible defects remediated

1. Python 3.10 could not import `enum.StrEnum`, introduced in Python 3.11.
   - Remediation: use the compatible `str, Enum` pattern for all serialized enums.
2. Python 3.10 could not import `datetime.UTC`, introduced in Python 3.11.
   - Remediation: use `datetime.now(timezone.utc)`.

Neither remediation changes schema values, routing behavior, receipt behavior, or stored JSON representations.

## Authoritative CI certificate

Final workflow head: `015a465b4159efc8394afb28a87fad873e9ce43e`

| Gate | Result |
|---|---|
| Ruff check | PASS |
| Python 3.10 federation manifest gate | PASS |
| Python 3.10 spatial-grid validation | PASS |
| Python 3.10 canonical federation export | PASS |
| Python 3.10 full pytest suite | PASS |
| Python 3.11 full validation job | PASS |
| Python 3.12 full validation job | PASS |
| Federation template drift | PASS |

Workflow runs:

- `validate` run `148`: success
- `Federation template drift` run `168`: success

The repository workflow executes the full pytest suite in each supported Python validation job. The targeted FOIA tests are therefore included in three clean full-suite executions, including Python 3.10, 3.11, and 3.12.

## Schema certificate

- Python enum values remain stable strings.
- Pydantic v2 model validation passed in all supported Python jobs.
- Federation envelope serialization passed the canonical export gate.
- No CI evidence of enum drift, Pydantic serialization errors, schema-reference errors, or line-length/lint failures.
- The standalone JSON Schema files are parseable repository artifacts, but the current workflow does not expose a distinct named `jsonschema` command. Certification is grounded in successful tests and federation export validation rather than a separately identified schema-only job.

## Remaining risks

- Downstream consumers have not yet returned real production acknowledgments for FOIA envelopes.
- Retry and acknowledgment persistence are certified through repository tests, not a live multi-repository dispatch.
- Schema evolution beyond `0.2.0` still requires an explicit compatibility and migration policy.

## Disposition

`CI_CERTIFIED_DRAFT_NO_MERGE`

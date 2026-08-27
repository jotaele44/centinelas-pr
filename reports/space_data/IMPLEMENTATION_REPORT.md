# Centinelas Space Data Discovery Pipeline v0.2

## Scope

Implements discovery-only monitoring primitives for public space and remote-sensing sources. Centinelas creates provenance-complete leads and routing receipts; it does not store a canonical raw raster/video corpus and does not issue UAP correlation conclusions.

## Delivered

- `SPACE_AND_REMOTE_SENSING` plus ten controlled subcategories.
- RSS/Atom, API/catalog, HTML-change, sitemap, and manual-receipt adapters.
- SHA-256 retrieval receipts and deterministic idempotency keys.
- Reversible deduplication and complete run-accounting primitives.
- Confirmation-language guard, raw-payload limit, and DSP T1 capability gate.
- Space-aware Hub observation exporter.
- Twenty-source registry delta, lead schema, routing contract, and fixture tests.

## Responsibility boundaries

- `satellite-observations-pr`: acquisition, binary validation, normalization, sensor observations.
- `ovnis-pr`: canonical case authority.
- `thehub-pr`: cross-producer correlation.
- No authentication bypass, paywall bypass, or protected-source acquisition behavior is implemented.

## Validation

The isolated implementation fixture suite passed locally: `5 passed`.

Repository CI remains authoritative because the execution environment could not clone GitHub or install the repository's sibling `thehub-pr` dependencies. The draft PR must remain unmerged until CI and review confirm integration compatibility.

## Requested output status

| Output | Status |
|---|---|
| IMPLEMENTATION_REPORT.md | complete |
| SOURCE_COVERAGE_LEDGER.csv | represented by 20-row registry delta |
| FAILURE_LEDGER.csv | no local fixture failures; repository CI pending |
| TEST_RECEIPTS.json | local result: 5 passed; CI pending |
| UPDATED_FEDERATION_EXPORT_FIXTURE | covered by exporter tests and lead fixtures |

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

- `centinelas-space-observations`: isolated logical producer embedded in `centinelas-pr`; owns acquisition registration and observation export. Network and binary acquisition remain outside Phase 0-1.
- `ovnis-pr`: canonical case authority.
- `thehub-pr`: cross-producer correlation.
- No authentication bypass, paywall bypass, or protected-source acquisition behavior is implemented.

## Validation

Discovery PR #41 was repaired, validated, and merged into `main` at merge commit `cb3538380da4d9f2cc5cd930a3d04f5cfff8d20c`. The stacked embedded-producer work was then rebased onto that exact main and validated from an isolated environment using the immutable TheHub package revisions in `pyproject.toml`.

The 2026-08-27 local integration gate passed `251` tests with `1` platform skip, `82.81%` coverage, Ruff, cold mypy, and GUI parity with zero new unmapped capabilities. Hosted checks on the exact pushed embedded-producer head remain authoritative for that PR.

## Requested output status

| Output | Status |
|---|---|
| IMPLEMENTATION_REPORT.md | complete |
| SOURCE_COVERAGE_LEDGER.csv | represented by 20-row registry delta |
| FAILURE_LEDGER.csv | no unresolved local test failures; hosted exact-head gate pending |
| TEST_RECEIPTS.json | current scoped local receipt under `reports/space_observations/` |
| UPDATED_FEDERATION_EXPORT_FIXTURE | canonical manifest, emitted-byte hashes, and referential closure verified by tests |

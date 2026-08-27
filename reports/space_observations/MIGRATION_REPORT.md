# Satellite Observations Phase 0–1 Migration Report

## Result

Migrated the standalone Phase 0–1 intake implementation into Centinelas as the isolated logical producer `centinelas-space-observations`.

## Preserved controls

- qualified-lead validation;
- receiver-side canonical lead SHA-256 recomputation;
- route-boundary validation;
- persistent intake, deduplication, failure, source-health, routing-acknowledgement, and run ledgers;
- idempotent replay after restart;
- failure isolation and exact run accounting;
- production synthetic rejection;
- DSP/public-evidence and negative-inference safeguards;
- PRII source, entity, relationship, observation, and manifest export.

## Changed boundaries

- package path: `src/centinelas/space_observations`;
- logical producer: `centinelas-space-observations`;
- ledger root: `data/space_observations/`;
- external binary root: `CENTINELAS_EVIDENCE_ROOT`;
- case authority: `ovnis-pr`;
- correlation authority: `thehub-pr`.

## Phase limitation

No network acquisition is implemented in Phase 0–1. No large binary, imagery, video, raster, telemetry, archive, or ephemeris corpus is committed to Git.

## Local validation

On 2026-08-27, the rebased integration worktree passed:

- focused discovery, routing, intake, export, schema-freeze, and GUI-contract tests: `34 passed, 1 skipped`;
- full repository suite: `251 passed, 1 skipped`;
- branch coverage: `82.81%` against the repository `72%` floor;
- Ruff: pass;
- cold mypy analysis: pass across 24 source files;
- GUI parity: `290 current / 140 mapped / 150 legacy / 0 new`.

The platform skip is the repository's existing symlink-dependent test. GitHub checks on the exact pushed head remain the authoritative hosted gate.

The integration tests cover canonical-to-embedded route migration, idempotent routing, two clean replays, partial-write recovery, contradictory-ledger rejection, complete run accounting, emitted-byte package hashes, referential closure, deterministic whole-row source selection, duplicate/conflict adjudication, production synthetic rejection, case-reference restraint, DSP rejection, negative-inference rejection, route-mismatch isolation, schema freeze completeness, and stale-output removal.

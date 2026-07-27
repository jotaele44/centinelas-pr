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

## Local certification

The migrated standalone fixture suite passed locally: `8 passed`.

The repository integration test adds route migration, two clean replays, persistence after restart, complete accounting, federation export, case-reference restraint, DSP rejection, negative-inference rejection, synthetic rejection, and route-mismatch isolation.

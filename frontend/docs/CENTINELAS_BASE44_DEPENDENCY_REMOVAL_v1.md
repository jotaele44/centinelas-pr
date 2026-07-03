# CENTINELAS_BASE44_DEPENDENCY_REMOVAL_v1

## Vector

Remove Base44 runtime coupling from Centinelas while preserving the Centinelas → MoneySweep lifecycle model.

## Removed

- `@base44/sdk` dependency
- `@base44/vite-plugin` dependency
- `base44` CLI dev dependency
- Vite Base44 plugin configuration
- `base44/` runtime directory
- direct SDK auth/public-settings calls
- Base44 serverless function imports

## Replaced with

- `src/api/appClient.js`: platform-neutral frontend data/function/auth adapter
- `src/data/seedData.js`: local seed dataset for render-safe development
- `schemas/entities/`: neutral JSON schema references migrated from former entity definitions
- local handlers for:
  - `evaluateHandoffCandidate`
  - `acceptHandoffCandidate`
  - `rejectHandoffCandidate`
  - `syncMoneySweepRecord`
  - `validatePreOfficialLanguage`

## Preserved lifecycle guarantees

- Matter ID continuity
- Signal → Matter → OfficialRecord linkage
- MoneySweep handoff queue
- duplicate OfficialRecord guard by `canonical_key`
- pre-official language validation
- evidence tier model
- route compatibility for legacy legislative views

## Verification

- `npm install`: PASS
- `npm audit`: PASS, 0 vulnerabilities
- `npm run lint`: PASS
- `npm run typecheck`: PASS
- `npm run build`: PASS
- route smoke test: PASS for `/`, `/monitor`, `/signals`, `/matters`, `/sources`, `/handoff`, `/tabla`, `/autores`, `/login`, `/register`, `/forgot-password`, `/reset-password`

## Remaining backend work

The app is Base44-free at the frontend/package level, but the local adapter is not a production database. Next backend options:

1. attach a shared MoneySweep API;
2. add a Postgres-backed API for Matter/Signal/OfficialRecord;
3. add server-side auth and role enforcement;
4. move ingestion/alert jobs to a worker queue or cron service.

# CENTINELAS_LIFECYCLE_PATCH_VERIFY_AND_DEPLOY_v1

## Vector

`CENTINELAS_LIFECYCLE_PATCH_VERIFY_AND_DEPLOY_v1`

## Objective

Convert Centinelas into the upstream sibling of MoneySweep:

- Centinelas captures pre-official public signals.
- MoneySweep catalogs downstream official records.
- `matter_id` preserves continuity between both apps.

## Implemented hardening

### Unique Matter ID

Implemented in `src/lib/lifecycle.js`:

- `createMatterId()`
- `normalizeMatterId()`
- `canonical_key` schema fields for `Matter`, `Signal`, `HandoffCandidate`, and `OfficialRecord`

### OfficialRecord duplicate guard

Implemented in backend functions:

- `acceptHandoffCandidate`
- `syncMoneySweepRecord`

Duplicate matching uses:

1. `canonical_key`
2. `matter_id + record_type + official_identifier`

### Pre-official language validator

Implemented in:

- `src/lib/lifecycle.js` via `validatePreOfficialLanguage()`
- `base44/functions/validatePreOfficialLanguage/entry.ts`

Blocked pre-official claims include phrases such as:

- `contrato adjudicado`
- `ley vigente`
- `fondos desembolsados`
- `permiso emitido`
- `contract awarded`
- `funds disbursed`

These are blocked before `officialized` stage unless a canonical MoneySweep record exists.

### MoneySweep sync bridge

Implemented function:

- `base44/functions/syncMoneySweepRecord/entry.ts`

This accepts a MoneySweep-style official record payload, deduplicates it, creates or updates `OfficialRecord`, and links back to `Matter`.

### Handoff accept/reject flow

Implemented in:

- `base44/functions/acceptHandoffCandidate/entry.ts`
- `base44/functions/rejectHandoffCandidate/entry.ts`
- `src/pages/Handoff.jsx`

The `/handoff` UI now supports:

- Evaluate candidate
- Accept / create official record
- Reject candidate

## Verification results

| Check | Result |
|---|---|
| `npm install` | PASS |
| `npm audit fix` | PASS, non-breaking fixes applied |
| Remove unused vulnerable `react-quill` | PASS |
| `npm audit` | PASS, 0 vulnerabilities |
| Base44 entity JSON parse | PASS |
| `npm run lint` | PASS |
| `npm run typecheck` | PASS |
| `npm run build` | PASS |
| Route HTTP render smoke test | PASS |
| Base44 auth check | FAIL/BLOCKED: CLI not logged in and device-code fetch failed in sandbox |
| Entity schema push | NOT EXECUTED: blocked by Base44 auth check |
| Deploy | NOT EXECUTED: blocked by Base44 auth check |

## Route smoke test

All tested routes returned HTTP 200 from Vite preview:

- `/`
- `/monitor`
- `/signals`
- `/matters`
- `/sources`
- `/handoff`
- `/tabla`
- `/autores`
- `/login`
- `/register`
- `/forgot-password`
- `/reset-password`
- `/matters/test-matter`

## Deployment blocker

The Base44 CLI auth check failed:

```txt
npx base44 whoami
→ You need to login first to continue.
→ Error: Failed to generate device code
→ Error: fetch failed
```

No `base44` push/deploy command was executed after the failed auth check.

## Manual deployment sequence

Run locally in a logged-in environment:

```bash
cd centinelas_audit
npx base44 login
npx base44 whoami
npm run lint
npm run typecheck
npm run build
npx base44 entities push
npx base44 functions push
npx base44 deploy
```

Command names may vary by installed Base44 CLI version; run `npx base44 --help` after login if needed.

## Remaining P0 after deploy

1. Add real MoneySweep API/shared-database connector endpoint.
2. Add backend publication validator that calls `validatePreOfficialLanguage` before public publishing.
3. Add source ingestion jobs for P0 Puerto Rico source universe.
4. Add Playwright browser-level E2E tests.
5. Add role enforcement for reporter/editor/admin handoff actions.

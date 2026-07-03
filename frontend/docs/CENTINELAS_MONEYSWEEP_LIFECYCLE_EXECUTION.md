# CENTINELAS_MONEYSWEEP_LIFECYCLE_SYSTEM_v1 — Execution Report

## Active vector

`CENTINELAS_MONEYSWEEP_LIFECYCLE_SYSTEM_v1`

## Objective

Convert the uploaded law-centered frontend into a sibling lifecycle system:

- **Centinelas** = upstream public signal capture.
- **MoneySweep** = downstream official record catalog.
- **Matter ID** = shared cross-app continuity layer.

## Implemented

### 1. Public matter shared ID

Added `src/lib/lifecycle.js` with:

- `createMatterId()`
- `MATTER_LIFECYCLE_STAGES`
- `MATTER_TYPES`
- `SIGNAL_TYPES`
- `OFFICIAL_RECORD_TYPES`
- `HANDOFF_TRIGGERS`
- `PRE_OFFICIAL_LANGUAGE_GUARD`
- `EVIDENCE_TIERS`
- `getConfidenceBand()`
- `isReadyForMoneySweep()`
- legacy `Law` → `Signal` / `Matter` mapping

### 2. Upstream model

Added Base44 entity schemas:

- `Signal`
- `Matter`
- `Source`
- `Evidence`
- `Watchlist`
- `AlertRule`
- `AlertEvent`
- `CoverageGap`
- `Story`
- `EditorialNote`
- `Entity`
- `EntityMention`
- `Beat`
- `Municipality`

### 3. Downstream model

Added:

- `OfficialRecord`
- `HandoffCandidate`

### 4. Handoff rules

Added:

- `src/pages/Handoff.jsx`
- `base44/functions/evaluateHandoffCandidate/entry.ts`

Accepted officialization triggers:

- `law_number_assigned`
- `contract_awarded`
- `signed_contract_published`
- `payment_issued`
- `permit_number_issued`
- `court_case_number_assigned`
- `audit_report_published`
- `grant_obligation_published`
- `appointment_confirmed`
- `executive_order_published`

### 5. Frontend refactor

Added routes:

- `/monitor`
- `/signals`
- `/matters`
- `/matters/:id`
- `/sources`
- `/handoff`

Reworked:

- `src/App.jsx`
- `src/components/Header.jsx`
- `src/components/Footer.jsx`
- `src/pages/Home.jsx`
- `index.html`
- `base44/config.jsonc`
- `package.json`
- `README.md`

### 6. New UI components

Added:

- `MatterTimeline`
- `ConfidenceBadge`
- `EvidenceTierBadge`
- `HandoffStatusBadge`
- `MetricCard`
- `SignalCard`

## Verification performed

- Entity JSON schemas parse successfully.
- Added no source-media dependencies.
- Preserved legacy law routes for backwards compatibility.
- Added normalized lowercase auth routes with redirects from legacy casing.
- Lint/build were not executable in this sandbox because `node_modules` is absent and `eslint` is not installed locally.

## Alignment status

| Check | Status |
|---|---|
| No duplicate canonical records | Partially enforced by `Matter.moneysweep_record_ids` and `OfficialRecord.matter_id`; backend uniqueness still needed. |
| Pre-official language guard | Implemented as constants and UI wording; backend/editor validation still needed. |
| Evidence tiering | Implemented in `Evidence` schema and `EvidenceTierBadge`. |
| Cross-app ID continuity | Implemented through `Matter.matter_id`, `Signal.matter_id`, `OfficialRecord.matter_id`, and `HandoffCandidate.matter_id`. |
| MoneySweep linkage | Implemented structurally; requires MoneySweep API/entity connector for real sync. |

## Remaining P0 backend work

1. Enforce unique `matter_id` and `record_id` constraints where Base44 permits.
2. Create ingestion functions for P0 source families.
3. Add backend validation for pre-official language guard.
4. Add MoneySweep sync connector or shared database bridge.
5. Add atomic handoff matching to prevent duplicate `OfficialRecord` creation.
6. Add CI: lint, typecheck, Vitest, Playwright, Lighthouse, accessibility.

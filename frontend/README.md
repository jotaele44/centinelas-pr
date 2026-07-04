# Centinelas

Centinelas is the upstream sibling to MoneySweep.

- **Centinelas** captures early public signals relevant to Puerto Rico before they become official records: announcements, agendas, hearings, RFPs, public notices, board actions, draft bills, social statements, emergency notices, and media reports.
- **MoneySweep** catalogs the downstream official record after the fact: laws, contracts, payments, permits, audits, court records, amendments, and executed/public documents.

The shared connective object is `Matter`, identified by `matter_id`.

## Core routes

- `/` — public product framing
- `/monitor` — upstream monitoring command center
- `/signals` — signal inbox
- `/matters` — public matter ledger
- `/matters/:id` — lifecycle detail page
- `/sources` — source registry and coverage state
- `/handoff` — candidates ready for MoneySweep official-record matching

Legacy legislative routes are retained as compatibility views:

- `/ley/:id`
- `/tabla`
- `/autores`
- `/autor/:id`

## Core entity model

- `Matter` — shared lifecycle object across Centinelas and MoneySweep
- `Signal` — upstream Centinelas record
- `OfficialRecord` — downstream MoneySweep record linkage
- `Source` — monitored source registry
- `Evidence` — provenance and evidence tiering
- `HandoffCandidate` — officialization candidate queue
- `Watchlist`, `AlertRule`, `AlertEvent` — alerting layer
- `CoverageGap`, `SourceHealthCheck`-style fields — source gap tracking
- `Story`, `EditorialNote` — reporting workflow foundation
- `Entity`, `EntityMention`, `Beat`, `Municipality` — entity resolution and PR taxonomy

## Pre-official language guard

Until a MoneySweep official record exists, Centinelas should describe matters as:

- announced
- proposed
- scheduled
- under consideration
- pending vote
- pending award
- included in agenda
- opened for bids
- reported by source
- awaiting official record

It should not state that a contract was awarded, law enacted, payment made, permit issued, or case filed unless an official record exists.

## Platform-neutral runtime

This package is no longer coupled to Base44.

Removed runtime dependencies:

- `@base44/sdk`
- `@base44/vite-plugin`
- `base44` CLI dev dependency
- `base44/` runtime configuration and function directory

Replacement runtime:

- `src/api/appClient.js` provides a platform-neutral local adapter with the same high-level `entities`, `auth`, and `functions.invoke` surfaces used by the frontend.
- `src/data/seedData.js` seeds local demo data for route rendering and lifecycle validation.
- `schemas/entities/` preserves the former entity definitions as neutral schema references.

The local adapter is intended as a clean seam for a future backend: Postgres/Supabase, Django/FastAPI, Node API, or a shared MoneySweep service can replace the local adapter without changing the frontend page architecture.

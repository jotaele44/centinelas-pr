# Centinelas PR

Centinelas PR is the upstream early-signal monitor for Puerto Rico public-interest information.

It captures announcements, agendas, public notices, hearings, RFPs, press releases, official social statements, proposed projects, draft legislation, public meetings, emergency notices, and other signals that appear before a law, contract, permit, project, payment, audit, or official record is finalized.

Centinelas is a sibling system to MoneySweep PR:

- Centinelas detects intent before officialization.
- MoneySweep catalogs execution after officialization.
- Both systems should link through a shared public-matter lifecycle.

## Federation role

| System | Lifecycle role | Primary question |
|---|---|---|
| Centinelas PR | Pre-officialization signal monitor | What is emerging or about to happen? |
| MoneySweep PR | Post-officialization record catalog | What officially happened? |
| TheHub PR | Federation rollup and cross-repo correlation | How do signals and records connect? |

Centinelas should not duplicate MoneySweep. It should create the upstream context that MoneySweep later verifies through official records.

## Setup / Development

Requires **Python 3.10+** (CI tests 3.10–3.12).

```bash
git clone https://github.com/jotaele44/centinelas-pr.git
cd centinelas-pr
python3 -m venv .venv
source .venv/bin/activate

# Runtime + dev tooling + the export extra (matches CI). The `export` extra pulls
# the shared prii-export-utils package from the hub at a pinned commit, so this
# needs network access:
pip install -e ".[dev,export]" -r server/backend/requirements.txt
```

Run the checks CI runs (`.github/workflows/validate.yml`):

```bash
ruff check .                                         # lint
python scripts/validate_pr_grid.py --require-sha     # spatial-grid gate
python3 scripts/federation_export.py --ledger data/signals/live_signals.jsonl --mode test
pytest -q                                            # tests
```

The `centinelas` CLI (`ingest`, `classify`, `route`, `run`, `status`) drives the
live pipeline; live RSS intake needs internet and LLM classification needs an
`ANTHROPIC_API_KEY`. For the double-click desktop app, see
[`desktop/README.md`](desktop/README.md).

## Core concept: Public Matter

A public matter is any public-interest item relevant to Puerto Rico that may evolve over time.

Examples:

- Proposed law or regulation
- Public project
- Procurement or RFP
- Contract candidate
- Permit process
- Emergency notice
- Board agenda item
- Municipal ordinance
- Budget allocation
- Appointment
- Lawsuit or investigation
- Audit or compliance issue
- Infrastructure event

Centinelas captures early signals attached to a matter. MoneySweep later attaches official records to the same matter when they become final.

```text
Public Matter
├── Centinelas signals
│   ├── announcement
│   ├── agenda item
│   ├── hearing notice
│   ├── RFP notice
│   ├── agency statement
│   └── public meeting record
└── MoneySweep records
    ├── enacted law
    ├── awarded contract
    ├── issued permit
    ├── payment record
    ├── amendment
    └── audit record
```

## Primary operating model

Centinelas should track the lifecycle before officialization:

| Stage | Name | App of record | Meaning |
|---|---|---|---|
| 0 | Raw observation | Centinelas | Mention, notice, post, agenda entry, or source change |
| 1 | Public signal | Centinelas | Publicly observable announcement or official pre-final notice |
| 2 | Developing matter | Centinelas | Multiple signals or a clear active process |
| 3 | Pending officialization | Centinelas | Vote, award, signature, permit, or final document expected |
| 4 | Officialized | MoneySweep | Law, contract, award, permit, filing, or payment exists |
| 5 | Execution or amendment | MoneySweep | Implementation, amendment, payment, compliance, or closure |
| 6 | Audit, dispute, or impact | MoneySweep plus Centinelas | Post-fact record creates a new reporting signal |

## Handoff rule

Centinelas should hand off a matter to MoneySweep when a downstream official record appears.

| Handoff trigger | Example |
|---|---|
| Contract awarded | Award notice or signed contract appears |
| Law enacted | Law number or governor signature appears |
| Permit issued | Permit number or official permit document appears |
| Payment made | Disbursement, invoice, or payment record appears |
| Lawsuit filed | Case number or docket record appears |
| Audit published | Comptroller, inspector general, or agency audit appears |
| Appointment confirmed | Confirmation or appointment document appears |
| Project officially funded | Grant agreement, obligation, or budget certification appears |

Before a trigger exists, the item remains a Centinelas signal or developing matter.

## Core entities

Centinelas should prioritize these entities:

| Entity | Purpose |
|---|---|
| `Signal` | Early public trace that something may happen |
| `Matter` | Shared lifecycle object connecting signals to official records |
| `Source` | Monitored source registry entry |
| `SourceHealthCheck` | Freshness and reliability status for a source |
| `Evidence` | Captured source URL, document, excerpt, timestamp, and hash |
| `Entity` | Person, agency, contractor, organization, or institution |
| `EntityMention` | Mention of an entity inside a signal or evidence item |
| `Beat` | Topic taxonomy such as energy, courts, contracts, health, or environment |
| `Municipality` | Geographic relevance layer for Puerto Rico municipalities |
| `Watchlist` | User-defined monitored topics, entities, geographies, or document types |
| `AlertRule` | Trigger logic for user or editorial alerts |
| `AlertEvent` | Alert generated from a source change or signal |
| `Lead` | Reporter-reviewed story candidate |
| `Story` | Drafted or published reporting output |
| `EditorialNote` | Internal review, assignment, or fact-check note |
| `HandoffCandidate` | Matter ready for MoneySweep matching |
| `CoverageGap` | Missing, broken, stale, manual, or blocked source coverage |

## Signal entity baseline

A `Signal` should include:

```text
signal_id
matter_id
signal_type
title
summary
source_id
source_url
captured_at
published_at
signal_stage
beat
municipalities
agencies
entities
estimated_value
deadline_date
urgency_score
confidence_score
handoff_status
```

Recommended signal stages:

```text
raw_observation
announced
proposed
scheduled
under_review
hearing_pending
rfp_open
bid_pending
vote_pending
award_pending
officialization_pending
matched_to_moneysweep
archived
```

## Source universe

Centinelas should monitor upstream sources that reveal public intent early.

| Priority | Source family | Purpose |
|---|---|---|
| P0 | Legislative calendars and committee agendas | Earliest legislative movement |
| P0 | Municipal assembly agendas | Local projects, ordinances, and procurements before award |
| P0 | Agency press releases | Early government project announcements |
| P0 | Procurement notices and RFPs | Pre-contract signals |
| P0 | Public hearing notices | Regulatory, permit, and infrastructure signals |
| P0 | Public-board agendas | PREPA, AAA, Ports, UPR, COR3, and similar bodies |
| P1 | Official social media | Fast-moving public statements |
| P1 | Local media | Narrative detection and leak discovery |
| P1 | Environmental and public-comment notices | Permits, impact statements, and project objections |
| P1 | Budget documents | Funding signals before execution |
| P2 | Community groups and NGOs | Impact and local concern signals |
| P2 | Academic and technical reports | Context and validation |

## Recommended routes

Internal monitor routes:

```text
/monitor
/signals
/signals/:id
/matters
/matters/:id
/sources
/sources/:id
/beats
/municipios
/handoff
/alerts
/reports
/editorial
/admin/coverage
```

Public-facing routes:

```text
/
/noticias
/investigaciones
/alertas
/temas/:beat
/municipios/:municipio
/agencias/:agency
/personas/:person
/documentos
/metodologia
/correcciones
```

## UI priorities

P0 frontend changes:

| Current pattern | Replace with |
|---|---|
| MoneySweep branding | Centinelas branding |
| Legislative-only home | Live signal monitor |
| Law filter panel | Signal filter panel |
| Law detail | Matter detail with signal timeline |
| Author detail | Entity profile |
| Category subscription | Watchlist builder |
| Vote buttons | Confidence, evidence, and status badges |
| Comments | Tips, submissions, or editorial notes depending on role |
| Law calendar | Hearings, deadlines, public meetings, RFPs, votes, and board agendas |
| Vote chart | Signal velocity, beat spikes, and coverage health |

## Confidence language

Centinelas handles pre-official information. It must avoid presenting signals as final facts.

Preferred status language:

```text
announced
proposed
scheduled
under consideration
pending vote
pending award
listed in agenda
opened for bids
reported by source
awaiting official record
```

Avoid finalizing language unless an official record exists:

```text
approved
awarded
enacted
paid
completed
```

## Confidence scoring

| Score | Meaning |
|---:|---|
| 95-100 | Official public notice, document, agenda, filing, or dataset |
| 85-94 | Official agency, legislative, municipal, or board source |
| 70-84 | Reputable media report with named source or documentary support |
| 50-69 | Multiple weaker sources or indirect confirmation |
| 30-49 | Single weak source; monitor only |
| 0-29 | Do not publish as fact; internal lead only |

## Evidence tiers

| Tier | Meaning |
|---|---|
| T1 | Primary official document, filing, contract, law, dataset, archive, or meeting record |
| T2 | Operational or organizational source, official statement, or agency communication |
| T3 | Eyewitness report, interview, or tip |
| T4 | Secondary media, commentary, social repost, or aggregation |

## Shared spatial baseline

Centinelas participates in the federation-wide Puerto Rico baseline grid.

Expected grid path:

```text
registry/spatial/pr_grid_full_cell_index_saturated.csv
```

Validation:

```bash
python scripts/validate_pr_grid.py --require-sha
```

The grid provides a shared `Cell_ID` spatial key so Centinelas signals can be correlated with MoneySweep records, SkyWatcher events, AguaYLuz infrastructure layers, SpiderWeb incident layers, OVNIS records, and TheHub rollups.

## Release gate

Centinelas should not be considered production-ready until these gates pass:

| Gate | Requirement |
|---|---|
| Branding | 100 percent Centinelas naming, metadata, routes, and visual identity |
| Source coverage | P0 and P1 source families listed with automation status |
| Ingestion | Every source has active, manual, blocked, stale, or deprecated status |
| Freshness | Active sources expose `last_checked_at` and `last_success_at` |
| Traceability | Every public item links to source evidence |
| Lifecycle | Matters can move from signal to handoff candidate |
| MoneySweep bridge | Officialized matters can link to MoneySweep records |
| Alerts | Watchlists trigger alerts from source changes and signal updates |
| Editorial workflow | Lead, assignment, review, fact-check, publish, and correction stages exist |
| Accessibility | WCAG AA baseline |
| QA | Unit, integration, route smoke, and Playwright checks for core flows |
| Observability | Source failures, ingest failures, and frontend errors are visible |
| Gap detection | Broken, stale, missing, or manual sources are reported |

## Architecture sentence

Centinelas detects intent. MoneySweep verifies execution. The shared matter lifecycle is the connective tissue.

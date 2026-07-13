# Puerto Rico Open-Web Discovery — Implementation Plan

## Purpose

This document converts ADR 0002 into an implementation-ready package while preserving the current RSS pipeline, Signal/Matter/Handoff lifecycle, federation export contract, and T1–T4 evidence model.

## Proposed file tree

```text
src/centinelas/discovery/
├── __init__.py
├── models.py
├── provider.py
├── scheduler.py
├── query_lattice.py
├── policy.py
├── extraction.py
├── relevance.py
├── classification.py
├── deduplication.py
├── provenance.py
├── evidence.py
├── coverage.py
├── blind_spots.py
├── domain_profiles.py
├── registries.py
└── providers/
    ├── __init__.py
    ├── search_base.py
    ├── rss.py
    ├── sitemap.py
    ├── government.py
    ├── link_expansion.py
    └── archive.py

config/discovery/
├── providers.example.yaml
├── budgets.yaml
├── policy.yaml
├── relevance_weights.yaml
├── query_topics.yaml
└── source_families.yaml

registry/discovery/
├── municipalities.json
├── barrios.json
├── agencies.json
├── infrastructure_assets.json
├── official_domains.json
└── aliases.json

schemas/
├── open_web_discovery.schema.json
├── discovery_provider.schema.json
├── coverage_report.schema.json
├── blind_spot.schema.json
└── domain_candidate.schema.json

data/discovery/
├── candidates/.gitkeep
├── coverage/.gitkeep
├── blind_spots/.gitkeep
└── domain_profiles/.gitkeep

tests/discovery/
├── fixtures/
├── gold/
├── test_models.py
├── test_provider_contract.py
├── test_query_lattice.py
├── test_policy.py
├── test_relevance.py
├── test_classification.py
├── test_deduplication.py
├── test_provenance.py
├── test_evidence.py
├── test_coverage.py
├── test_blind_spots.py
└── test_backward_compatibility.py

scripts/
├── build_discovery_registries.py
├── validate_discovery_contract.py
├── run_discovery_fixture.py
├── build_recall_gold_set.py
├── evaluate_discovery_recall.py
└── report_discovery_coverage.py
```

This is a target tree, not authorization to create all modules in one change. Each phase should land as a bounded PR.

## Interface contracts

### DiscoveryProvider

```python
from collections.abc import AsyncIterator
from typing import Protocol

class DiscoveryProvider(Protocol):
    provider_id: str

    async def discover(self, request: DiscoveryRequest) -> AsyncIterator[DiscoveryCandidate]: ...
    async def health(self) -> ProviderHealth: ...
    def estimate_cost(self, request: DiscoveryRequest) -> CostEstimate: ...
```

Requirements:

- Must not return Signal objects.
- Must identify the query cell and provider provenance.
- Must expose deterministic fixture mode.
- Must report quota/rate failures explicitly.
- Must not fetch disallowed content outside the policy gate.

### FetchPolicy

```python
class FetchPolicy(Protocol):
    async def evaluate(self, candidate: DiscoveryCandidate) -> FetchPolicyDecision: ...
```

Requirements:

- Fail closed for content retention.
- Permit metadata-only discovery when full fetch is not authorized.
- Persist robots, terms, rate, privacy, and retention decisions.
- Be independently testable from network adapters.

### RelevanceScorer

```python
class RelevanceScorer(Protocol):
    def score(self, document: ExtractedDocument, context: RelevanceContext) -> RelevanceAssessment: ...
```

Requirements:

- Score PR relevance only; do not infer truth or event confirmation.
- Return contributing positive and negative signals.
- Include model/ruleset version.
- Support deterministic rules before optional semantic enrichment.

### ContentClassifier

```python
class ContentClassifier(Protocol):
    def classify(self, document: ExtractedDocument) -> ContentClassification: ...
```

Requirements:

- Separate original reporting, opinion, advocacy, official releases, syndicated copy, promotional content, and unknown material.
- Never infer independent corroboration from publication count.

### GlobalDeduplicator

```python
class GlobalDeduplicator(Protocol):
    def assess(self, document: ExtractedDocument, index: DedupIndex) -> DeduplicationAssessment: ...
```

Requirements:

- Distinguish exact duplicates, near duplicates, republications, syndicated copies, and distinct reporting about the same event.
- Preserve all source URLs while preventing duplicate corroboration counts.

### EvidenceTierMapper

```python
class EvidenceTierMapper(Protocol):
    def map(self, document: ExtractedDocument, provenance: ProvenanceChain) -> EvidenceAssessment: ...
```

Requirements:

- Use the repo's existing T1–T4 definitions.
- Treat search engines and archives only as discovery mechanisms.
- Set `single_source_only=true` until independent corroboration exists.
- Prevent promotion eligibility when policy or provenance is incomplete.

### CoverageReporter

```python
class CoverageReporter(Protocol):
    def record_candidate(self, record: DiscoveryRecord) -> None: ...
    def record_gap(self, gap: BlindSpot) -> None: ...
    def build_report(self, window: TimeWindow) -> CoverageReport: ...
```

Requirements:

- Report query-cell execution, municipality recency, provider overlap, unique yield, latency, gold-set recall, and blind spots.
- Never report a percentage of the entire internet.

## Data boundaries

### Persist by default

- Canonical URL and source domain.
- Title, bounded snippet, dates, language, and content type.
- Discovery query/provider metadata.
- Relevance, classification, deduplication, provenance, policy, and evidence assessments.
- Named public entities and geographic references necessary for routing.
- Hashes and version identifiers.

### Do not persist by default

- Full copyrighted article body.
- Publisher images.
- Tracking parameters.
- Unnecessary residential addresses or sensitive personal data.
- Minor identities or sensitive health details unless an approved public-interest policy explicitly requires them.

## Query lattice design

The lattice is represented as sparse cells rather than a full Cartesian product.

```yaml
cell_id: municipality:adjuntas|topic:landslide|event:notice|lang:es|window:24h
geographies:
  - Adjuntas
aliases:
  - Ciudad del Gigante Dormido
topics:
  - landslide
  - deslizamiento
event_types:
  - official_notice
  - emergency_notice
priority: P0
source_family_bias:
  - government
  - local_media
```

Scheduling score:

```text
priority weight
+ uncovered-cell weight
+ active-incident weight
+ stale-cell weight
+ source-family deficit weight
- recent-success saturation
- provider cost
- quota pressure
```

## Registry policy

Registries must be versioned and provenance-backed. Government and infrastructure registries require source citations inside their source data or build manifest. Aliases must include ambiguity notes to reduce false positives.

The municipality registry must assert exactly 78 canonical municipalities. Tests must fail on duplicate canonical names, missing identifiers, or alias collisions without an explicit ambiguity rule.

## Coverage metrics

| Metric | Formula or rule |
|---|---|
| Query-cell execution | executed eligible cells / scheduled eligible cells |
| Municipality recency | municipalities with qualifying discovery inside SLA / 78 |
| Provider overlap | number of providers yielding the same canonical candidate |
| Unique yield | deduplicated relevant candidates / executed provider requests |
| Discovery latency | discovered_at - published_at |
| Primary-source ratio | T1+T2 candidates / promoted candidates |
| Gold-set recall | recovered eligible gold items / eligible gold items |
| False-positive rate | rejected reviewed candidates / reviewed candidates |
| Blind-spot burden | severity-weighted unresolved gaps |

No single aggregate score may hide municipality or source-family failure. Reports must include distributions and missing cells.

## Recall gold-set specification

Minimum initial set: 240 items.

- At least 2 positives per municipality where feasible.
- P0/P1/P2 source families represented.
- Spanish and English material.
- HTML, RSS, PDF, and structured notice formats.
- Explicit and implicit PR relevance.
- Homonym and abbreviation hard negatives.
- Republishing/syndication clusters.
- Time-sensitive items with known publication timestamps.

Split:

- 60% development.
- 20% calibration.
- 20% locked evaluation.

The locked evaluation set must not be used to tune weights.

## Test matrix

| Area | Unit | Contract | Integration | Regression |
|---|---:|---:|---:|---:|
| Provider normalization | Required | Required | Required | Required |
| Query lattice | Required | — | Required | Required |
| Robots/terms policy | Required | Required | Required | Required |
| Generic extraction | Required | Required | Required | Required |
| PR relevance scoring | Required | — | Required | Gold-set |
| Content classification | Required | — | Required | Gold-set |
| Dedup/source lineage | Required | Required | Required | Required |
| Provenance chain | Required | Required | Required | Required |
| T1–T4 mapping | Required | Required | Required | Required |
| PII minimization | Required | Required | Required | Required |
| Coverage reporting | Required | Required | Required | Required |
| Existing RSS pipeline | — | — | Required | Required |
| Federation export | — | Required | Required | Required |

### Mandatory failure cases

- Provider timeout, quota exhaustion, malformed result, and partial pagination.
- Unknown or disallowed robots policy.
- Terms restriction and metadata-only fallback.
- Redirect loop, canonical conflict, and tracking URL normalization.
- Puerto Rico homonym false positive.
- PR-relevant item with no literal `Puerto Rico` text.
- Same press release copied by many publishers.
- Distinct reporting on the same matter.
- Missing publisher, date, or source attribution.
- Minor or residential-address PII in extracted content.
- Search result incorrectly treated as T1/T2.
- Single-source candidate incorrectly marked corroborated.
- Coverage report with a failed provider or unexecuted municipality cells.

## Phase plan

### Phase 1 — Search federation

Deliverables:

- Core models and JSON-schema validation.
- Provider protocol.
- Two fixture-backed search providers.
- Query lattice v1.
- Deterministic PR relevance scorer v1.
- Canonical URL and metadata deduplication.
- Coverage ledger v1.
- CLI fixture command.

Exit criteria:

- Existing tests remain green.
- Schema fixtures validate.
- Two providers return equivalent normalized candidates.
- Locked gold-set recall target is defined before production claims.
- No live discovery result bypasses review into confirmed status.

### Phase 2 — Autonomous source discovery

Deliverables:

- Feed and sitemap autodiscovery.
- Generic extraction.
- Domain profiles and review-based promotion.
- Source-lineage and syndication classification.
- Bounded link expansion.
- Robots/terms cache and blind-spot report.

Exit criteria:

- Newly discovered domains can be monitored generically without a custom adapter.
- Promotion requires explicit policy approval.
- Duplicate republications do not inflate corroboration.
- Per-domain budgets and circuit breakers are verified.

### Phase 3 — Open-Web Observatory

Deliverables:

- Official-domain and government-source registry.
- Archive/Common Crawl discovery.
- Semantic/geospatial relevance enrichment.
- Full recall benchmark automation.
- Freshness and municipality coverage reporting.
- Sustained cost budget and operational runbook.

Exit criteria:

- Coverage is reported by municipality, topic, source family, provider, and time window.
- Blind spots have owners and mitigation states.
- Historical and current discovery coexist without starving P0 intake.
- Federation export remains provenance-complete and backward-compatible.

## Migration plan

1. **Introduce schemas and models only.** No runtime routing changes.
2. **Wrap current RSS intake as a DiscoveryProvider.** Preserve existing CLI behavior and output.
3. **Add fixture-only search providers.** Validate normalization and scoring without network dependency.
4. **Run shadow discovery.** Store candidates and coverage telemetry separately from live signals.
5. **Enable review-queue routing.** No automatic factual promotion.
6. **Enable generic source promotion.** Human approval and policy gate required.
7. **Add archive/government expansion.** Maintain separate cost and freshness queues.
8. **Retire redundant custom adapters only after parity evidence exists.**

Rollback is achieved by disabling discovery providers and continuing the existing RSS pipeline. Existing signal and federation-export schemas remain the stable downstream contract.

## Readiness gate

| Gate | Required state | Current architecture status |
|---|---|---|
| ADR and scope boundaries | Approved | Ready for review |
| Candidate schema | Validated | Drafted |
| Provider protocol | Contract tests | Specified |
| Two-provider independence | Fixture pass | Not implemented |
| Query lattice | 78 municipalities validated | Specified |
| Relevance scorer | Gold-set thresholds pass | Specified |
| Dedup/source lineage | Regression fixtures pass | Specified |
| Robots/terms | Persisted before fetch | Specified |
| PII minimization | Automated fixtures pass | Specified |
| Coverage/blind spots | Reports missing cells | Specified |
| RSS backward compatibility | Existing CI green | Must verify during Phase 1 |
| Federation compatibility | Existing export gate green | Must verify during Phase 1 |

### Architecture package completeness

- Architecture decision record: **100%**
- Target file tree: **100%**
- Core schema: **100% draft, validation pending**
- Interface contracts: **100%**
- Test matrix: **100%**
- Migration plan: **100%**
- Readiness gate: **100%**
- Runtime implementation: **0% by design**

Overall architecture handoff readiness: **92%**.

Remaining blockers are execution-level: schema validation in repository CI, exact mapping to current internal model classes, fixture construction, provider selection, cost ceilings, and legal review policy ownership.

## Required implementation safeguards

- No literal 100%-of-internet claim.
- No unauthorized full-text or image archive.
- No one-provider completeness claim.
- No search-ranking-to-evidence inference.
- No repeated press-release copies counted as corroboration.
- No single-source truth promotion.
- No production routing until shadow-mode metrics and gold-set results are reviewed.

# ADR 0002: Puerto Rico Open-Web Discovery Architecture

- **Status:** Proposed
- **Date:** 2026-07-13
- **Decision owner:** Centinelas PR
- **Scope:** Discovery, relevance scoring, provenance, deduplication, coverage measurement, and phased migration

## Context

Centinelas currently operates as an upstream early-signal monitor with live RSS intake and a source registry. That model is useful but requires source-by-source wiring and cannot approximate broad Puerto Rico relevance coverage across the public internet.

Literal 100% internet coverage is not measurable or achievable. The open web has no stable denominator and includes inaccessible, deleted, private, paywalled, robots-excluded, unindexed, dynamic, and transient content. The correct objective is therefore:

> Maximize recall over publicly discoverable Puerto Rico-relevant material, quantify blind spots, retain provenance, minimize stored content, and prevent single-source promotion to fact.

## Decision

Centinelas will evolve from a source-adapter-first monitor into a **provider-federated discovery and evidence-routing system**. Dedicated source adapters remain supported, but become an optimization for high-value or structurally unusual sources rather than the default integration path.

The architecture has seven bounded stages:

1. **Discover** URLs and documents through multiple independent providers.
2. **Authorize fetch** using robots, terms, rate, privacy, and content-retention gates.
3. **Extract metadata** using generic HTML, feed, sitemap, JSON-LD, OpenGraph, and PDF metadata parsers.
4. **Score Puerto Rico relevance** using geographic, institutional, semantic, and link-context signals.
5. **Classify and deduplicate** content before persistence or export.
6. **Assign provenance and evidence tier** without treating discovery as verification.
7. **Measure coverage and blind spots** against a known query lattice and recall benchmark.

## Non-goals

- Claiming complete coverage of the internet.
- Archiving unrestricted full text or images.
- Treating search ranking as evidence quality.
- Promoting a single media report into a confirmed public matter.
- Replacing MoneySweep's official-record verification role.
- Depending on one commercial search provider.

## Logical architecture

```text
Discovery scheduler
  ├── Search providers
  ├── News providers
  ├── RSS/Atom autodiscovery
  ├── Sitemap discovery
  ├── Government portal discovery
  ├── Common Crawl / archive indexes
  └── Link expansion
        ↓
DiscoveryCandidate queue
        ↓
FetchPolicy gate
  ├── robots
  ├── terms policy
  ├── rate budget
  ├── content type
  └── privacy / retention
        ↓
GenericExtractor
        ↓
PRRelevanceScorer
        ↓
ContentClassifier
        ↓
GlobalDeduplicator
        ↓
ProvenanceBuilder + EvidenceTierMapper
        ↓
Review queue / Signal candidate / Coverage ledger
```

## Discovery provider abstraction

Every provider implements the same contract and returns candidates rather than final signals.

```python
class DiscoveryProvider(Protocol):
    provider_id: str

    async def discover(self, request: DiscoveryRequest) -> AsyncIterator[DiscoveryCandidate]: ...
    async def health(self) -> ProviderHealth: ...
    def estimate_cost(self, request: DiscoveryRequest) -> CostEstimate: ...
```

Provider classes:

| Provider family | Primary use | Required independence control |
|---|---|---|
| Web search | Broad indexed-web discovery | At least two providers before provider-completeness claims |
| News search | Fast current-event discovery | Ranking must not affect evidence tier |
| RSS/Atom | Efficient recurring source monitoring | Feed ownership and canonical-domain checks |
| Sitemap | Archive and incremental enumeration | Respect robots and crawl-delay policy |
| Government discovery | Primary notices and documents | Agency/domain registry validation |
| Common Crawl/archive | Historical backfill | Snapshot date and original URL required |
| Link expansion | Discover adjacent sources and documents | Depth, domain, and budget limits |

## Search federation

The scheduler executes equivalent query cells across configured providers and records provider overlap. Results are normalized by canonical URL and content fingerprint. Provider identity, rank, query, execution time, and result position are retained as discovery provenance only.

No provider is authoritative. A candidate discovered by multiple engines is more discoverable, not necessarily more true.

## RSS and sitemap autodiscovery

For a newly encountered domain, Centinelas may inspect:

- HTML `<link rel="alternate">` declarations.
- Conventional feed paths.
- `robots.txt` sitemap declarations.
- Sitemap indexes and child sitemaps.
- Schema.org and OpenGraph publisher metadata.

Autodiscovered feeds and sitemaps remain `candidate` until policy validation passes. Recurring high-yield domains may be promoted into the source registry without a custom parser.

## Link expansion

Link expansion is breadth-limited and policy-gated:

- Maximum depth: 1 by default.
- Same-domain links preferred.
- Cross-domain links enter discovery as new candidates only.
- Binary assets are metadata-only unless explicitly permitted.
- Tracking parameters are removed before canonicalization.
- Expansion cannot bypass robots or terms controls.

## Common Crawl and archive backfill

Historical indexes are used to discover prior URLs and timestamps, not to bulk-republish content. Every record must retain archive collection, snapshot timestamp, original URL, and retrieval provenance. Backfill is lower priority than current P0/P1 upstream monitoring.

## Government source discovery

Government discovery combines:

- Curated authoritative domain and agency registries.
- Search queries constrained to official domains.
- Sitemap/feed discovery.
- Document-link extraction from agendas, notices, and press releases.
- Registry drift detection for renamed, migrated, or retired portals.

Official-domain status affects evidence tier only after the domain/agency mapping is validated.

## Domain candidate promotion

A domain profile is generated after repeated discovery. Promotion requires:

- Minimum relevant-document count.
- Stable canonical domain.
- Robots/terms decision.
- Acceptable duplicate and promotional-content rates.
- Provenance completeness.
- Source-family classification.
- Human review for production activation.

Promotion states:

```text
observed → candidate → policy_review → approved_generic → dedicated_adapter | rejected | suspended
```

## Puerto Rico relevance score

Relevance is a calibrated score from 0 to 100. It is separate from evidence confidence.

### Signal families

| Family | Examples | Default maximum contribution |
|---|---|---:|
| Explicit geography | Puerto Rico, Borinquen, municipality, barrio | 30 |
| Government/institution | PR agency, municipality, public corporation, court | 20 |
| Geospatial | Coordinates or geometry intersects PR baseline | 20 |
| Infrastructure | Named roads, reservoirs, substations, ports, hospitals | 10 |
| Semantic context | Meaning clearly concerns PR without exact keyword | 15 |
| Link/source context | Known PR source or PR-specific inbound context | 5 |

Negative signals reduce the score for homonyms, unrelated Puerto Rico place names, generic tourism promotion, duplicate wire copy, and non-PR entities using `PR` as an abbreviation.

Thresholds:

```text
0–29   reject or retain only aggregate coverage telemetry
30–49  low-confidence lead; no federation export
50–69  review queue
70–84  PR-relevant candidate
85–100 high-confidence PR relevance; still not factual confirmation
```

## Query lattice

The lattice is generated from:

```text
78 municipalities × barrios/communities × topics × agencies × infrastructure assets × event types × language variants × time windows
```

The scheduler must support bounded sampling rather than brute-force Cartesian execution. Priority is assigned by source family, freshness requirement, uncovered cells, active incidents, and blind-spot severity.

Minimum registries:

- 78 municipalities and aliases.
- Barrios and recognized communities.
- Commonwealth agencies, public corporations, boards, and authorities.
- Federal entities operating in Puerto Rico.
- Critical infrastructure names and asset classes.
- Courts, legislative bodies, procurement and permit terminology.
- Spanish/English variants, abbreviations, and common misspellings.

## Content classification

Required classes:

```text
official_notice
agenda_or_calendar
procurement_or_rfp
public_hearing
press_release
news_reporting
opinion_or_commentary
advocacy_statement
social_statement
technical_report
academic_report
court_or_legal_record
emergency_notice
promotional_or_advertorial
syndicated_wire
spam_or_irrelevant
unknown
```

Classification controls routing and retention. Opinion, advocacy, social, promotional, and syndicated content cannot be silently merged with original reporting.

## Global deduplication

Deduplication occurs in layers:

1. Canonical URL normalization.
2. Exact content hash where legally retained.
3. Metadata hash from normalized title, author, date, and publisher.
4. Near-duplicate fingerprint from bounded extracted text.
5. Event-level clustering using entities, time, place, and matter identifiers.
6. Source-lineage detection for press releases and syndicated copy.

Multiple republications of one source do not count as independent corroboration.

## Provenance chain

Every promoted candidate must preserve:

- Discovery provider and query cell.
- Original and canonical URLs.
- Publisher/domain identity.
- Fetch policy decision.
- Retrieval timestamp and HTTP metadata.
- Extractor and classifier versions.
- Relevance score and contributing signals.
- Deduplication cluster and source lineage.
- Evidence tier assignment and rationale.
- Human review events, corrections, and downstream handoffs.

## Evidence-tier mapping

The existing T1–T4 model remains authoritative:

| Tier | Mapping rule |
|---|---|
| T1 | Validated primary official document, filing, dataset, archive, or meeting record |
| T2 | Official operational statement or agency communication without a stronger primary artifact |
| T3 | Eyewitness, interview, tip, or direct observation with appropriate handling |
| T4 | Media, commentary, aggregation, repost, or unverified secondary account |

Search engines, crawlers, and archives are discovery mechanisms and never evidence tiers by themselves.

## Coverage metrics

Centinelas will report measurable coverage rather than an unknowable internet percentage:

- Query-lattice execution coverage.
- Municipality recency coverage.
- Topic/source-family coverage.
- Independent-domain diversity.
- Provider overlap and unique yield.
- Publication-to-discovery latency.
- Historical-year coverage.
- Primary-source ratio.
- Duplicate-adjusted unique yield.
- Gold-set recall.
- Known blind spots by cause and severity.

## Recall gold set

The benchmark contains known PR-relevant items sampled across municipalities, source families, languages, formats, and relevance difficulty. It must include hard negatives and hidden-context positives. Gold items record discovery deadline, expected source family, and minimum acceptable relevance band.

The benchmark is versioned and cannot be built solely from the same providers being evaluated.

## Freshness service levels

| Priority | Target discovery latency |
|---|---:|
| P0 emergency, agenda, hearing, procurement, official notice | 15 minutes to 2 hours depending on provider capability |
| P1 local media, official social, environmental/public comment | 6 hours |
| P2 NGO, academic, technical context | 24 hours |
| Historical backfill | Best effort within budget |

Missed SLAs are recorded as coverage gaps, not hidden.

## Blind-spot ledger

Each gap includes category, affected geography/topic/source family, first seen, last checked, cause, mitigation, owner, severity, and status. Causes include blocked, paywalled, authentication-required, unindexed, parser failure, provider quota, robots exclusion, terms restriction, deleted, unknown, and insufficient classifier recall.

## Cost and rate-limit budget

Every provider exposes estimated and actual cost units. The scheduler enforces daily and monthly ceilings, per-domain request limits, concurrency limits, cache reuse, exponential backoff, and circuit breakers. High-cost semantic processing runs only after cheaper metadata and keyword gates.

## Robots and terms gate

Fetch authorization is explicit and auditable. The gate records robots status, user-agent scope, crawl delay, terms review status, content category, retention policy, and decision. Unknown policy defaults to metadata-only discovery or manual review for non-government sources.

## PII minimization

- Store only fields necessary for public-interest monitoring.
- Avoid replicating residential addresses, minors' identities, sensitive health data, and unnecessary personal identifiers.
- Preserve allegation and procedural-status language.
- Separate public officials acting in official capacity from private persons.
- Support correction, removal, and retention-review workflows.

## Phased implementation

### Phase 1: Search federation

- Provider protocol and normalized candidate schema.
- Two independent search-provider adapters plus deterministic fixtures.
- PR relevance scorer v1.
- Query-lattice generator.
- Deduplication and coverage ledger.
- No production signal promotion without existing review rules.

### Phase 2: Autonomous source discovery

- Feed and sitemap autodiscovery.
- Domain candidate profiles and promotion workflow.
- Generic extraction and source-lineage classification.
- Link expansion with strict budgets.
- Blind-spot and freshness reporting.

### Phase 3: PR Open-Web Observatory

- Government discovery registry.
- Archive/Common Crawl backfill.
- Expanded semantic and geospatial relevance scoring.
- Recall benchmark automation.
- Cross-provider coverage dashboards and sustained operating budgets.

## Consequences

### Positive

- Source integration scales without one custom adapter per publisher.
- Coverage gaps become measurable.
- Search-provider dependence is bounded.
- Existing Signal/Matter/Handoff and T1–T4 contracts remain intact.
- Custom adapters can focus on exceptional high-value systems.

### Negative

- Infrastructure, provider cost, and governance complexity increase.
- High recall creates more false positives and review load.
- Coverage remains an approximation and must be communicated carefully.
- Historical backfill and dynamic sites require specialized handling.

## Acceptance gates

The architecture may proceed to implementation only when:

- Schemas validate and remain backward-compatible with current signal export.
- At least two provider implementations can run against fixtures.
- The relevance scorer passes gold-set thresholds by municipality and source family.
- Deduplication identifies republication lineage.
- Robots/terms decisions are persisted before fetch.
- PII and retention policies are testable.
- Coverage reports expose missed cells and provider failures.
- No code path promotes a single discovery result to confirmed fact.

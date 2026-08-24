# Centinelas FOIA Disposition Engine v0.1

## Decision

Centinelas owns FOIA release monitoring, finding segmentation, triage, and dissemination decisions. TheHub Evidence stores the canonical source package. Downstream producers receive finding-level envelopes and return idempotent acknowledgments.

## Architecture

```text
FOIA monitor -> release manifest -> document/page accounting -> extraction
-> finding segmentation -> deterministic rules -> optional semantic scoring
-> review gates -> durable outbox -> downstream acknowledgment
```

The engine routes findings, not whole documents. One document may generate separate exports to OVNIS, Skywatcher, AguaYLuz, MoneySweep, Spiderweb, Centinelas, and TheHub Intelligence while retaining one canonical evidence object in TheHub Evidence.

## Contracts

| Contract | Purpose |
|---|---|
| `FOIARelease` | Agency release identity, case number, acquisition, hash, page count |
| `FOIADocument` | File identity, MIME, hashes, OCR confidence, page count |
| `FOIAFinding` | Citation-bound claim or useful information segment |
| `RoutingDecision` | Reversible destination-specific disposition and reasons |
| `ExportReceipt` | Idempotency key, downstream acknowledgment, error state |
| `ReviewCase` | Human adjudication package for uncertain or sensitive routes |

## Routing matrix

| Destination | Deterministic triggers | Default action |
|---|---|---|
| TheHub Evidence | Every valid non-duplicate finding | Export canonical evidence |
| TheHub Intelligence | At least one downstream candidate | Export or review cross-repo index |
| Centinelas | investigation, policy, hearing, notice, release, Puerto Rico | Public-interest signal |
| OVNIS | UAP/UFO/USO/unidentified/anomalous object terminology | Case or lead candidate |
| Skywatcher | aircraft, tail number, flight, airspace, radar, surveillance | Aviation/sensor lead |
| AguaYLuz | PREPA/AEE/LUMA/PRASA/AAA/water/grid/utility | Utility/infrastructure lead |
| MoneySweep | contract, award, invoice, grant, payment, procurement | Officialized financial record candidate |
| Spiderweb | officer, director, agent, affiliate, subsidiary, relationship | Entity-link candidate |
| Archive only | duplicate, irrelevant, no route, sensitive hold | Preserve without propagation |

## Decision order

1. Validate source provenance, SHA-256, release identity, and page accounting.
2. Reject duplicate propagation using release, file, normalized-text, and page similarity keys.
3. Require at least one page-level citation for every finding.
4. Apply deterministic route rules.
5. Optionally blend semantic scores at 25%; semantic output cannot create a route without a deterministic candidate in v0.1.
6. Force review when extraction confidence is below `0.70`.
7. Export automatically only when route score is at least `0.80`.
8. Queue scores from `0.55` through `0.7999` for human review.
9. Write approved exports to an append-only outbox using deterministic idempotency keys.
10. Mark completion only after a downstream acknowledgment receipt exists.

## Reversibility and correction

Routing decisions are immutable observations. Corrections create superseding decisions; they do not delete prior decisions. Downstream systems must retain the source finding ID, document ID, citation pages, and export idempotency key.

## Acceptance coverage

| Fixture | Expected result |
|---|---|
| Mixed-content document | Multiple destinations plus TheHub Evidence/Intelligence |
| Duplicate release | `reject_duplicate`, archive only |
| Low-confidence OCR | Candidate routes become `review` |
| Entity collision | Review before Spiderweb export |
| Multi-route finding | One canonical finding, several reversible decisions |
| Export retry | Same idempotency key, no duplicate outbox row |
| Receipt duplicate | Existing acknowledgment remains authoritative |
| No useful content | Canonical evidence plus archive-only disposition |

## Implementation plan

### Phase 0 — contracts and evaluation

- Freeze JSON Schema IDs and destination enums.
- Register deterministic rules and thresholds.
- Expand fixtures to include every destination and disposition.
- Add contradiction tests for mixed official and secondary evidence.

### Phase 1 — intake integration

- Add FOIA release acquisition manifest generation.
- Perform 100% document and page accounting.
- Store original binaries outside downstream producer repositories.
- Produce citation-bound findings from text/OCR extraction.

### Phase 2 — federation export

- Map `ExportReceipt` to `prii-export-utils` envelopes.
- Implement one adapter per destination.
- Require destination acknowledgment and retry only failed targets.
- Expose outbox and review-queue status in Centinelas diagnostics.

### Phase 3 — calibrated semantic scoring

- Build a frozen, manually adjudicated corpus.
- Measure per-destination precision, recall, false-positive rate, and abstention.
- Permit semantic-only candidate generation only after destination-specific gates pass.

## Non-goals for v0.1

- Automatic public publication.
- Automatic allegation or entity-identity resolution.
- Copying complete FOIA releases into every producer repository.
- Treating associations, shared addresses, or proximity as proof of wrongdoing.
- Marking exports complete without receipts.

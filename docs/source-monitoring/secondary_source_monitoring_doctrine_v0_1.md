# Secondary-source monitoring doctrine v0.1

Status: **BINDING for the Just Security integration; candidate federation-wide pattern.**

## Scope

This doctrine governs secondary media, expert journals, commentary, newsletters,
aggregators, and similar discovery sources monitored by Centinelas.

## Identity boundary

Source taxonomy is not canonical identity. Preserve separately:

1. publisher/article identity;
2. search-result manifestation;
3. tag/category manifestation;
4. RSS/Atom manifestation;
5. living-page version identity;
6. linked-document identity.

Never prove document identity from title, normalized title, count equality, proximity,
or source absence. Canonical URL is a discovery/binding key for publisher pages; a linked
PDF, filing, dataset, or government record is an independent document candidate.

## Evidence tier

A Just Security article, podcast, recap, or Early Edition item is **T4** by default.
A linked court filing or official document does **not** inherit T4 and does **not**
automatically become T1. It receives independent evidence adjudication.

## Search and tag coverage

A literal search page and a tag archive are discovery mechanisms.

- `SEARCH_RESULT_SET != TAG_RESULT_SET` unless exact set equality is measured.
- A tag omission is not evidence of irrelevance.
- A search omission is `SEARCH_FALSE_NEGATIVE` until independently adjudicated.
- `A_ONLY` after a search refresh means "no longer returned by this search manifestation";
  it never means the underlying article was deleted.
- Every refresh computes `INTERSECTION`, `A_ONLY`, `B_ONLY`, `UNION`, and
  `SYMMETRIC_DIFFERENCE`.

A denominator may be certified only for the named manifestation, query, retrieval time,
and pagination scope. It must not be promoted to a publisher-wide topic denominator
without a separately exhausted source universe.

## Historical backfill

Whole-result acquisition precedes relevance exclusion. For every candidate preserve:

- query and manifestation;
- result position when available;
- canonical URL;
- raw title/date/author strings;
- retrieval timestamp;
- HTTP status and content hash;
- relevance disposition;
- exclusion reason;
- linked-document candidates.

Arithmetic must close:

`SOURCE_RESULTS = RETAINED + INCIDENTAL + FALSE_POSITIVE + UNRESOLVED`.

## Prospective monitoring

Use the publisher feed for broad new-item discovery and apply a high-precision Puerto Rico
relevance gate. Use tag feeds/archives as an independent high-precision manifestation.
Use literal search pages only for periodic recall audits.

Selected trackers, timelines, and other living resources are content-fingerprinted.
A page hash change is a **version-change observation**, not proof that any material claim
changed and not a verified public fact.

## Promotion controls

Secondary-source observations remain `raw_observation` until corroborated.

Prohibited automatic transitions:

- T4 article -> T1 evidence;
- search hit -> verified fact;
- page change -> substantive-event confirmation;
- tag membership -> canonical topic identity;
- disappearance from search -> deletion;
- multiple secondary articles -> primary confirmation.

## Regression gates

Positive gates must prove direct PR terms, tagged PR items, idempotent deduplication,
version-change detection, and independent linked-document adjudication.

Negative gates must prove rejection of broad Caribbean-only/territory-only matches,
fail-closed handling of blocked search pages, non-deletion semantics for `A_ONLY`, and
no evidence-tier inheritance.

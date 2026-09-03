# Just Security Puerto Rico snapshot — 2026-09-01

This directory freezes the **bounded observations available during the acquisition session**.

- `tag_archive.json` closes the canonical Puerto Rico tag manifestation at 4/4.
- `manifest.json` preserves the literal-search HTTP 403 as `BLOCKED`; its denominator remains `UNKNOWN`.
- `discovery_candidates.jsonl` preserves independently discovered Puerto Rico-relevant candidates outside the four tagged records. It is `AUDIT_ONLY`, not an exhaustive denominator.
- No file here claims source-byte identity because this session's web retrieval did not expose raw response bytes. The live monitor acquires and hashes response bytes when its runtime network can reach the publisher.

Search/tag/source taxonomy is never used as canonical article identity. A missing search result is not a deletion, and a linked court or government document receives an independent evidence-tier adjudication.

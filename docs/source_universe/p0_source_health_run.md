# P0 non-municipal source-health run

Vector: `CENTINELAS_PR_P0_SOURCE_HEALTH_RUN_v1`

This document locks the first P0 non-municipal source-health baseline for Centinelas PR. It is a ledger-only artifact: it does not add live scraping, source adapters, scheduled jobs, or repo delivery.

## Scope

The baseline covers 64 P0 non-municipal sources drawn from the broader 94-source non-municipal universe.

| Health status | Count | Handling policy |
|---|---:|---|
| `ACTIVE` | 52 | Eligible for normal HTML/RSS/API ingestion planning. |
| `DEGRADED` | 11 | Keep in repair queue until a source-specific endpoint or adapter is defined. |
| `MANUAL_ONLY` | 1 | Do not scrape the interactive page; replace with a bounded API query. |
| `BLOCKED` | 0 | Excluded from normal ingestion if present in a future run. |
| `DEMOTE` | 0 | Remove from P0 if present in a future run. |

## Source families

The P0 set spans:

- central Puerto Rico agencies
- Legislature / SUTRA
- procurement and recovery portals
- utilities and infrastructure
- emergency and environmental sources
- courts and legal sources
- aerospace and defense sources
- local media and publication sources

Every source must route to `thehub-pr`. Domain-specific routing is additive and remains governed by `data/routing/routing_policy.yaml`.

## Boundary

This run did not claim container-level HTTP status codes, robots.txt responses, redirect chains, or live content hashes. Those fields remain pending where live HTTP/DNS execution was not available. This PR intentionally records the baseline and guards it with tests before runtime ingestion is added.

## Next PRs

1. Add source registry loader and ingestor priority queue.
2. Add source-specific adapters for ASG, SUTRA, NWS/DRNA, PR.gov, Poder Judicial, local-media headline extraction, and USGS API replacement.
3. Add multi-label routing tests and TheHub run-log export.
4. Add scheduled dry-run workflow once adapters are fixture-tested.

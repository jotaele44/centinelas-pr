# Centinelas local runtime recovery — 2026-09-18

## Decision

The deleted Floot Centinelas project is no longer an identity or certification prerequisite. Centinelas continues as a governed local/GitHub development manifestation.

## Recovered manifestation

- Original export: `Centinelas PR.zip`
- ZIP SHA-256: `e88541667f8e5369d6925e72bc1282c546b15d67721062e768ad2494200ea629`
- Extracted files: 221
- Frozen source binding: `caf086598a4f99e2eb0ca4aac6d51e2d9bd46321`
- GitHub head observed during recovery: `660ff350c02c73a654b863bf4cf7dbde689ddc7b`
- GitHub compare from frozen commit: 2 commits ahead, adding only:
  - `docs/BACKEND_ASSESSMENT_AND_DEVELOPMENT_PLAN.md`
  - `governance/change_log.json`

No operational source file changed in that compare interval.

## Recovery states

- Source recovery: PASS
- Application recovery: PASS
- Prior evidence recovery: PASS
- Database recovery: OPEN
- Dependency/build verification: OPEN
- Local runtime verification: OPEN

The Floot export contains no PostgreSQL dump, SQL DDL/migrations, SQLite/database file, or usable database URL. Historical rows that existed only in Floot Postgres must not be synthesized.

## Authority model

- Source authority: this repository
- Local application manifestation: recovered TypeScript/Hono application
- Runtime database: separately restored/reconstructed PostgreSQL
- Floot project identity: superseded / not required
- Production certification: separate gate

Invariant: recovery of source/application bytes is not recovery of historical database state or production readiness.

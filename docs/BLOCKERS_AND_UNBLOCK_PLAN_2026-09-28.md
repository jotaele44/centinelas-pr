# Blockers and unblock plan — centinelas-pr (2026-09-28)

**Audit date:** 2026-09-28 · **`main` at audit:** `e055ae2` (not branch-protected) · **Production status:** `PRODUCTION`. The live signal ledger has been refreshed daily since #160.

**Post-audit update (2026-09-28 20:35Z):** the record_cell_binding v0.2 series was pushed straight to `main` after the audit. The Cell_Set PR #161 now conflicts with `main` and is superseded (X-05). The same series left `ruff check .` red on `main` (X-10); this PR carries the one-line fix.

This document lists every blocker that the repository, its CI, and its GitHub issues and pull requests recorded as of the audit date, then gives an ordered plan to clear them. It changes no code, gate, ledger, or status file.

Cross-repository blockers (IDs `X-nn`) are described in full in
`jotaele44/thehub-pr` → `docs/BLOCKERS_AND_UNBLOCK_PLAN_2026-09-28.md`.

## How this inventory was built

Sources checked:

- open issues (none) and all 9 open pull requests;
- CI on `main`, for push and scheduled runs (El Yunque monitor, Just Security monitor, signal-ledger refresh, maintenance, pip-audit, CodeQL, secret scan);
- `data/monitoring/just_security/runs.jsonl`;
- per-PR check results from the thehub federation completion-gate artifact (run `36326861596`);
- `docs/unfinished_implementation_ledger.v1.json`, reconciled against PR history;
- `docs/ROAD_TO_100.md`, `docs/REALTIME_DATA_ACQUISITION_AUDIT.md`, `AUDIT.md`;
- thehub `docs/FEDERATION_MAX_AUDIT_2026-09-24.md` and `docs/FEDERATION_UI_OPERATIONS_FAILURE_LEDGER.csv`;
- the branch list and branch protection.

## Summary

Each blocker is counted once, under its primary type.

| Type | Count |
|---|---:|
| CI/DATA (automation green but yielding nothing) | 1 |
| GATE | 2 |
| DATA | 1 |
| CRED | 1 |
| IMPL | 2 |
| PR | 1 group (9 PRs) |
| STALE | 1 |
| **Total** | **9** |

## Blocker inventory

| ID | Blocker | Type | Evidence | Owner | Unblock step | Exit criterion |
|---|---|---|---|---|---|---|
| CE-01 | The Just Security monitor has never produced data | CI/DATA | `docs/REALTIME_DATA_ACQUISITION_AUDIT.md` §2.9: HTTP 403 since inception. Every run in `data/monitoring/just_security/runs.jsonl` (29, the latest on 2026-09-27) records `feed_certification: BLOCKED` and `search_certification: BLOCKED` with 0 events. The workflow is still green, and it commits `data: refresh Just Security PR monitor [skip ci]` to `main` about every 5 hours. | Agent/maintainer | Auto-pause or alert after N consecutive blocked runs (audit §4.1); find a permitted access route (feed, API or permission) or retire the monitor; stop committing zero-signal state to `main` | The monitor either certifies events or is disabled with a recorded reason |
| CE-02 | Bot commits keep every centinelas PR behind `main` | GATE | 10 of the 14 commits to `main` since 09-26 are data-only bot commits (Just Security plus the daily ledger). The thehub completion gate therefore marks every centinelas PR `REBASE_REQUIRED` (X-01). | Maintainer (thehub gate owner) | Fix the gate rule (X-01), or move data commits off `main` | PRs stop drifting only because of bot commits |
| CE-03 | The Puerto Rico pre-official source tranche is not acquired | DATA/IMPL | Ledger CEN-005 (PREB, AAA, COR3, legislative). Audit §4.2: P0 families in `data/reference/source_registry.csv` are still `manual` (legislative calendars, municipal agendas, procurement notices, agency press releases, hearing notices, board agendas), and none of them is polled | Agent + operator | Build the bounded adapters with acquisition accounting, or record an explicit "won't automate" per family | Every P0 family is polled with accounting, or explicitly excluded |
| CE-04 | Matter stages 0–6 and the MoneySweep handoff are not certified across repos | GATE | Ledger CEN-006: the local lifecycle is complete; the shared store and MoneySweep reconciliation need cross-repository certification | Maintainer (centinelas + moneysweep) | Run a joint certification of the handoff receipts and reconciliation | Cross-repo certification receipt |
| CE-05 | The LLM tier has no production receipts | CRED | `docs/ROAD_TO_100.md` exit step 5; thehub UI-ops ledger F014 (LLM classification needs an external secret and network) | Operator | Provision the key in a permissioned environment; exercise the tier with secret-safe receipts; keep the deterministic fallback | Production receipt recorded |
| CE-06 | Ingestion only runs when someone triggers it by hand | IMPL | Audit §1.1: 58+ RSS feeds, the Federal Register and 7 scrapers run only via `workflow_dispatch` with `confirm=YES`, with no cron. There is no per-source health record and no retry or backoff; the USACE scrape returns 403; email/Google Alerts ingestion is hard-disabled; `POST /run` is synchronous and unbounded. | Agent | Apply the audit §4.1 quick wins (shared `acquire_all`, per-source health, retry and backoff); decide the §4.2 structural items (schedule, `SourceHealthCheck`, bounded `/run`) | Scheduled ingestion with per-source health surfaced in `centinelas status` |
| CE-07 | Frontend pages without backends | IMPL | Audit §1.1: 6 of 10 routed pages render `localStorage` mock data. `AUDIT.md`: no backend modules for Entities, Matters, Signals or Sources. MAX audit L3: the export has 0 relationships. | Agent | Add backend endpoints or explicitly mark the pages as mock; wire them through `pipelineClient` and react-query | No routed page shows mock data unlabelled |
| CE-08 | Open PRs | PR | See the next table | Agent + maintainer | Per-PR actions below | No red or conflicting PRs |
| CE-09 | Stale ledger entries | STALE | See the reconciliation below: CEN-002, 003 and 004 are dispositioned (#77, #79 and #80 closed), and CEN-007 was mostly fixed by #160 | Agent/maintainer | Record in a new ledger version (X-07) | Ledger matches `main` |

### Open pull requests (CE-08)

| PR | State | Action |
|---|---|---|
| #161 Cell_Set uncertainty contract | Conflicts with `main` since the post-audit v0.2 series, which already carries the contract in `federation/spatial/registry_version.json` | Confirm v0.2 covers it, then close as superseded (X-05) |
| #148 package-root installer gate (draft) | RED: validate 3.10/3.11/3.12 and lint; no merge commit (conflict); overlaps 2 paths | Rebase and fix, or close |
| #155 actions minor/patch group | RED: Federation template drift | Land the bump via thehub `federation-templates`, re-render, close this PR |
| #154 vitest 5, #152 lucide-react 1.47, #151 @types/node 26, #150 eslint-plugin-react-hooks 7 | Green heads, but all majors. Earlier dependabot majors were closed unmerged on 2026-09-19 and re-opened. | Migrate and merge, or add a dependabot `ignore` in the thehub baseline template (X-02) |
| #153 python group, #149 npm group | Green | Update the branch and merge |

## Unblock plan

### P1 — executable now
1. **CE-01:** add the auto-pause and stop committing blocked zero-signal runs.
2. **CE-08:** merge the green groups; route #155 through the templates; rebase or close #148.
3. **CE-06:** audit §4.1 quick wins.

### P2 — operator inputs
1. **CE-05:** LLM key and receipts.
2. **CE-03:** decide source access for the P0 families.

### P3 — maintainer decisions
1. **CE-02:** X-01 gate rule or bot-commit strategy.
2. Decide on the dependabot majors.
3. Branch protection on `main` (X-03).
4. **CE-04:** joint certification with moneysweep.

### P4 — longer horizon
1. **CE-03:** adapters.
2. **CE-06:** audit §4.2 structural items.
3. **CE-07:** backends for Entities, Matters, Signals and Sources.

## Ledger reconciliation (`docs/unfinished_implementation_ledger.v1.json`, dated 2026-08-19)

| Ledger ID | Ledger state | State on 2026-09-28 |
|---|---|---|
| CEN-001 | complete | Complete |
| CEN-002 | superseded_runtime_scope (PR-77) | #77 closed unmerged 2026-08-27. Any remaining policy text belongs in TheHub |
| CEN-003 | rescue_pr (PR-79) | Resolved: #79 closed unmerged 2026-09-03 |
| CEN-004 | governance_only_nonblocking (PR-80) | Resolved: #80 closed unmerged 2026-08-11; the skill stays |
| CEN-005 | main_gap | Still open → CE-03 |
| CEN-006 | cross-repo certification open | Still open → CE-04 |
| CEN-007 | blocked | Mostly resolved by #160 (daily `signal-ledger-refresh.yml`, production export passes). Still open: the durable hub receipt re-pin (X-04) |

## Notes
- `AUDIT.md` calls `server/backend/auth.py` a "stub". It is a small but functional write boundary: bearer token when `CENTINELAS_WRITE_TOKEN` is set, otherwise local-network only. Correct the wording.

## Federation-wide blockers that affect this repo
- X-01: completion gate, made worse by CE-02.
- X-02: dependabot backlog and template drift.
- X-03: `main` is unprotected.
- X-04: the hub receipt re-pin after #160.
- X-05: the Cell_Set PR set, now superseded by v0.2 on `main`.
- X-07: stale ledgers.
- X-10: `main` lint is red since the v0.2 series; this PR carries the fix.

See the thehub document for details.

## Not verifiable with the access used for this audit
- Code-scanning and Dependabot security-alert inventories.
- Actions secrets.
- Whether Just Security grants any permitted access route.

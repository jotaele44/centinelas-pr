---
name: centinelas-pr-unified-live-skillpack
description: "Compiled non-activating dispatch contract for shared and centinelas-pr capabilities."
version: 1.0.0
compatibility: claude
repository: centinelas-pr
---

# centinelas-pr Unified Live Skillpack

Pinned base: `f766efb6ede23398114a85cebf52d6530fa13891`.

## Execution contract

- Exact capability identifiers only; unknown identifiers fail closed.
- Runtime activation, automatic dispatch, live polling, notifications, external writes, promotion, control actions, merge, and release are disabled.
- Source module semantics remain cryptographically bound in `MANIFEST.json`; this file is the compiled live dispatcher.
- Repository-specific authority overrides shared defaults.

## Capability dispatch

| Capability | Module | Status | Preserved responsibility |
|---|---|---|---|
| `repo-state-reader` | `repository-governance` | `` |  |
| `repo-identity-guard` | `repository-governance` | `` |  |
| `branch-guard` | `repository-governance` | `` |  |
| `task-scope-guard` | `repository-governance` | `` |  |
| `git-action-guard` | `repository-governance` | `` |  |
| `skill-authoring-template` | `skill-lifecycle` | `` |  |
| `skill-package-builder` | `skill-lifecycle` | `` |  |
| `validation-gate-runner` | `validation-and-recovery` | `` |  |
| `failure-packet-builder` | `validation-and-recovery` | `` |  |
| `delta-reporter` | `reporting-and-receipts` | `` |  |
| `status-writer` | `reporting-and-receipts` | `` |  |
| `foia-correspondence-manager` | `foia-operations` | `` |  |
| `foia-request-sender` | `foia-operations` | `` |  |
| `centinelas-operator` | `orchestration-and-intelligence` | `` |  |
| `puerto-rico-weekly-intelligence` | `orchestration-and-intelligence` | `` |  |
| `centinelas-source-registry` | `source-governance` | `` |  |
| `centinelas-source-health-audit` | `source-governance` | `` |  |
| `centinelas-coverage-reconciliation` | `source-governance` | `` |  |
| `centinelas-signal-ingest` | `signal-pipeline` | `` |  |
| `centinelas-signal-classifier` | `signal-pipeline` | `` |  |
| `centinelas-matter-lifecycle` | `matter-lifecycle` | `` |  |
| `centinelas-moneysweep-handoff` | `moneysweep-handoff` | `` |  |

## Required output fields

Every execution receipt must include `capability_id`, `repository`, `pinned_base_commit`, `inputs`, `outputs`, `validation`, `limitations`, `authority`, and `next_action`.

## Non-activation boundary

This binding does not invoke repository code. A later runtime adapter requires separate design, tests, review, and explicit authorization.

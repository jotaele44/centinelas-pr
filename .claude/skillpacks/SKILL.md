---
name: centinelas-pr-unified-live-skillpack
description: "Compiled non-activating dispatch contract for shared and centinelas-pr capabilities."
version: 1.0.1
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

### `repo-state-reader` {#capability-repo-state-reader}

- **Module:** `repository-governance`
- **Status:** `preserved-active-contract`
- **Preserved responsibility:** Preserve the `repo-state-reader` responsibility defined by the `repository-governance` module under fail-closed repository authority.

### `repo-identity-guard` {#capability-repo-identity-guard}

- **Module:** `repository-governance`
- **Status:** `preserved-active-contract`
- **Preserved responsibility:** Preserve the `repo-identity-guard` responsibility defined by the `repository-governance` module under fail-closed repository authority.

### `branch-guard` {#capability-branch-guard}

- **Module:** `repository-governance`
- **Status:** `preserved-active-contract`
- **Preserved responsibility:** Preserve the `branch-guard` responsibility defined by the `repository-governance` module under fail-closed repository authority.

### `task-scope-guard` {#capability-task-scope-guard}

- **Module:** `repository-governance`
- **Status:** `preserved-active-contract`
- **Preserved responsibility:** Preserve the `task-scope-guard` responsibility defined by the `repository-governance` module under fail-closed repository authority.

### `git-action-guard` {#capability-git-action-guard}

- **Module:** `repository-governance`
- **Status:** `preserved-active-contract`
- **Preserved responsibility:** Preserve the `git-action-guard` responsibility defined by the `repository-governance` module under fail-closed repository authority.

### `skill-authoring-template` {#capability-skill-authoring-template}

- **Module:** `skill-lifecycle`
- **Status:** `preserved-active-contract`
- **Preserved responsibility:** Preserve the `skill-authoring-template` responsibility defined by the `skill-lifecycle` module under fail-closed repository authority.

### `skill-package-builder` {#capability-skill-package-builder}

- **Module:** `skill-lifecycle`
- **Status:** `preserved-active-contract`
- **Preserved responsibility:** Preserve the `skill-package-builder` responsibility defined by the `skill-lifecycle` module under fail-closed repository authority.

### `validation-gate-runner` {#capability-validation-gate-runner}

- **Module:** `validation-and-recovery`
- **Status:** `preserved-active-contract`
- **Preserved responsibility:** Preserve the `validation-gate-runner` responsibility defined by the `validation-and-recovery` module under fail-closed repository authority.

### `failure-packet-builder` {#capability-failure-packet-builder}

- **Module:** `validation-and-recovery`
- **Status:** `preserved-active-contract`
- **Preserved responsibility:** Preserve the `failure-packet-builder` responsibility defined by the `validation-and-recovery` module under fail-closed repository authority.

### `delta-reporter` {#capability-delta-reporter}

- **Module:** `reporting-and-receipts`
- **Status:** `preserved-active-contract`
- **Preserved responsibility:** Preserve the `delta-reporter` responsibility defined by the `reporting-and-receipts` module under fail-closed repository authority.

### `status-writer` {#capability-status-writer}

- **Module:** `reporting-and-receipts`
- **Status:** `preserved-active-contract`
- **Preserved responsibility:** Preserve the `status-writer` responsibility defined by the `reporting-and-receipts` module under fail-closed repository authority.

### `foia-correspondence-manager` {#capability-foia-correspondence-manager}

- **Module:** `foia-operations`
- **Status:** `preserved-active-contract`
- **Preserved responsibility:** Preserve the `foia-correspondence-manager` responsibility defined by the `foia-operations` module under fail-closed repository authority.

### `foia-request-sender` {#capability-foia-request-sender}

- **Module:** `foia-operations`
- **Status:** `preserved-active-contract`
- **Preserved responsibility:** Preserve the `foia-request-sender` responsibility defined by the `foia-operations` module under fail-closed repository authority.

### `centinelas-operator` {#capability-centinelas-operator}

- **Module:** `orchestration-and-intelligence`
- **Status:** `preserved-active-contract`
- **Preserved responsibility:** Preserve the `centinelas-operator` responsibility defined by the `orchestration-and-intelligence` module under fail-closed repository authority.

### `puerto-rico-weekly-intelligence` {#capability-puerto-rico-weekly-intelligence}

- **Module:** `orchestration-and-intelligence`
- **Status:** `preserved-active-contract`
- **Preserved responsibility:** Preserve the `puerto-rico-weekly-intelligence` responsibility defined by the `orchestration-and-intelligence` module under fail-closed repository authority.

### `centinelas-source-registry` {#capability-centinelas-source-registry}

- **Module:** `source-governance`
- **Status:** `preserved-active-contract`
- **Preserved responsibility:** Preserve the `centinelas-source-registry` responsibility defined by the `source-governance` module under fail-closed repository authority.

### `centinelas-source-health-audit` {#capability-centinelas-source-health-audit}

- **Module:** `source-governance`
- **Status:** `preserved-active-contract`
- **Preserved responsibility:** Preserve the `centinelas-source-health-audit` responsibility defined by the `source-governance` module under fail-closed repository authority.

### `centinelas-coverage-reconciliation` {#capability-centinelas-coverage-reconciliation}

- **Module:** `source-governance`
- **Status:** `preserved-active-contract`
- **Preserved responsibility:** Preserve the `centinelas-coverage-reconciliation` responsibility defined by the `source-governance` module under fail-closed repository authority.

### `centinelas-signal-ingest` {#capability-centinelas-signal-ingest}

- **Module:** `signal-pipeline`
- **Status:** `preserved-active-contract`
- **Preserved responsibility:** Preserve the `centinelas-signal-ingest` responsibility defined by the `signal-pipeline` module under fail-closed repository authority.

### `centinelas-signal-classifier` {#capability-centinelas-signal-classifier}

- **Module:** `signal-pipeline`
- **Status:** `preserved-active-contract`
- **Preserved responsibility:** Preserve the `centinelas-signal-classifier` responsibility defined by the `signal-pipeline` module under fail-closed repository authority.

### `centinelas-matter-lifecycle` {#capability-centinelas-matter-lifecycle}

- **Module:** `matter-lifecycle`
- **Status:** `preserved-active-contract`
- **Preserved responsibility:** Preserve the `centinelas-matter-lifecycle` responsibility defined by the `matter-lifecycle` module under fail-closed repository authority.

### `centinelas-moneysweep-handoff` {#capability-centinelas-moneysweep-handoff}

- **Module:** `moneysweep-handoff`
- **Status:** `preserved-active-contract`
- **Preserved responsibility:** Preserve the `centinelas-moneysweep-handoff` responsibility defined by the `moneysweep-handoff` module under fail-closed repository authority.

## Required output fields

Every execution receipt must include `capability_id`, `repository`, `pinned_base_commit`, `inputs`, `outputs`, `validation`, `limitations`, `authority`, and `next_action`.

## Non-activation boundary

This binding does not invoke repository code. A later runtime adapter requires separate design, tests, review, and explicit authorization.

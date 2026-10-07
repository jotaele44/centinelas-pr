# Federation code review — 2026-10-07

Review base: `1fcf246b9c3b7df0fcab066983347f8e3d5e630a`.

Scope: repository API and data boundaries, federation metadata, existing regression tests, GUI capability gates, and shared infrastructure where applicable. This is a targeted review with automated validation, not a claim that every possible defect has been eliminated.

## Changes

- **P1:** Ledger lookups accepted unsafe IDs/symlink targets and directory reads accepted nonobject JSON. Confine lookup/write paths to the ledger directory and skip nonobject or escaping directory entries.
- **P2:** Pipeline auth tests conflated the endpoint guard with the earlier token guard. Explicitly establish the intended principal and accept either documented denying boundary.
- **P2:** The dashboard route/component lacked capability bindings and the timeline browser test still expected the old home layout. Bind the existing dashboard and navigate through the visible home link.

## Validation

Validation results are recorded in the pull request description. Regression cases include invalid inputs and preservation of normal behavior. GUI parity baselines were not regenerated.

The review uses isolated local checkouts and synthetic regression fixtures. Existing frozen-source receipts retain their original scope and date; they do not establish live source freshness. Shared-package consumer pins remain immutable until a separate release/pin update.

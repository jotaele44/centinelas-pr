# FOIA Canary Dispatch Post-Merge Runbook v0.6

## Purpose

Activate and certify the receipt-only `foia-canary` path without promoting any synthetic finding into a production corpus.

## Preconditions

1. All seven PRs pass their repository CI and remain unchanged from the certified heads.
2. `FEDERATION_DISPATCH_TOKEN` exists in Centinelas and all six consumer repositories with only the scopes required for repository dispatch.
3. Branch protection and required checks are recorded before merge.
4. No repository contains a canary workflow that writes outside `artifacts/foia_canary_receipts`, `artifacts/foia_canary_dispatch`, or `artifacts/foia_canary_acks`.
5. Create or allow the orchestrator to create `canary/centinelas-foia-v0-5` in Centinelas. Create the same branch in each consumer from its post-merge default-branch head.

## Safe merge order

1. TheHub consumer PR.
2. OVNIS consumer PR.
3. Skywatcher consumer PR.
4. AguaYLuz consumer PR.
5. MoneySweep consumer PR.
6. Spiderweb consumer PR.
7. Centinelas orchestrator PR last.

This order prevents Centinelas from dispatching until every consumer workflow is available on its repository default branch.

## Rollback order

1. Disable the Centinelas `FOIA canary dispatch`, acknowledgment, and retry workflows.
2. Revert the Centinelas orchestrator merge.
3. Revert consumers in reverse merge order.
4. Preserve canary receipt and acknowledgment branches as evidence until the rollback ledger is complete; then delete them only with explicit approval.

## Canary execution

1. Run `FOIA canary dispatch` with branch `canary/centinelas-foia-v0-5` and no injected failure.
2. Require seven logical acknowledgments: TheHub Evidence, TheHub Intelligence, OVNIS, Skywatcher, AguaYLuz, MoneySweep, and Spiderweb.
3. Rerun the same dispatch. Require seven duplicate acknowledgments and no additional receipt files.
4. Run again with `inject_failure_target=spiderweb-pr`.
5. Confirm six acknowledgments and one `injected_failure_pending_retry` row.
6. Run `FOIA canary failed-target retry` against the canary branch.
7. Confirm only Spiderweb's attempt counter increments and its acknowledgment appears.

## Certification checks

- Every receipt path is under `artifacts/foia_canary_receipts`.
- Every Centinelas acknowledgment is under `artifacts/foia_canary_acks`.
- Dispatch and retry ledgers are under `artifacts/foia_canary_dispatch`.
- No default branch receives a synthetic data record outside the workflow files themselves.
- No native corpus path changes.
- Low-confidence findings cannot have disposition `export`.
- Spiderweb entity-collision findings require disposition `review`.
- Record IDs remain stable across duplicate delivery.
- Retry selects failed or unacknowledged targets only.

## Stop conditions

Stop and revert the latest activation step when any workflow writes to a native corpus, a callback lacks the canary branch, a record ID changes across duplicate delivery, an acknowledged target is retried, or a secret is missing.

## Current status

Implementation staged in seven draft PRs. Live `repository_dispatch` certification must occur only after the consumer workflows are merged to their default branches and Centinelas is merged last.

# Centinelas local-authority migration v1

## State

```text
CERTIFICATION_STATE = PROVISIONAL
READY_FOR_HUB_LIVE_EXECUTION = false
POLICY_AUTHORITY = Jotaele44/thehub-pr#246
IMPLEMENTATION_CHILD = Jotaele44/thehub-pr#260
IMPLEMENTATION_SHA = 2a8b662262130fc9013a7bc5016a6c74117e8c4a
```

This document defines the bounded Centinelas-first producer migration. It does
not certify Centinelas, TheHub, or a downstream consumer.

PR `Jotaele44/thehub-pr#247` is a separate completion-gate change on
`audit/completion-gate-v3-20260904`. It is not the implementation child of the
Federation freedom policy. The evidence-correct stack for this vector is:

```text
main
└── TheHub #246  audit/federation-freedom-v1
    └── TheHub #260  remediate/local-authority-v1
        └── Centinelas producer migration
```

Repository number alone is never sufficient identity evidence. The binding uses
repository, pull-request number, head branch, and exact commit SHA.

## Preserved scope

The migration preserves:

- raw source acquisitions and source registries;
- existing signal ledgers and canonical exports;
- all mature local parsing, validation, scientific, and geospatial libraries;
- deterministic keyword classification rules;
- target-specific JSON Schema contracts;
- confidence thresholds and local dispatch bookkeeping;
- optional hosted classification as an explicit adapter;
- optional GitHub transport as a downstream mirror.

The migration does not reinterpret, deduplicate, normalize, or promote any
source record. No `data/`, `research/`, or raw-source artifact is intentionally
modified.

## Classification authority

The core classifier is now:

```text
CENTINELAS_CLASSIFIER_BACKEND=local
```

Properties:

- no hosted SDK import at module load;
- no account or credential requirement;
- no network call;
- deterministic result for identical title/body input;
- explicit `UNCLASSIFIED` result when no keyword rule matches;
- explicit error for an unknown backend value.

The Anthropic adapter is available only through the `hosted-classifier` extra
and explicit backend selection. If the adapter fails, Centinelas returns the
local result with visible fallback provenance. Hosted output is augmentation,
not authority.

## Local transport authority

The authoritative operation is:

```text
route payload
→ canonical prii.artifact-message.v1 envelope
→ .centinelas/exchange/outbox/<target>/<message_id>.json
```

Message identity binds:

```text
source
+ target
+ kind
+ stable idempotency key
+ canonical payload SHA-256
```

The payload's `routed_at` observation binds to the stable item capture time,
not the wall clock at replay. Therefore an exact replay produces an exact
message identity rather than a timestamp-created false duplicate.

A local dispatch is successful only when each selected envelope is either newly
`EMITTED` or independently verified as an exact `DUPLICATE`. Partial local
failure is preserved as `failed`; successful targets remain listed and are not
silently rolled back or synthesized into an all-success result.

Manual operator handoffs use these distinct states:

```text
staged_local
 dry_run
 partial
 failed
```

`dry_run` never claims that an envelope exists.

## Optional hosted mirror

`scripts/emit_dispatches.py` reads only canonical local outbox files. It does
not reconstruct application payloads, truncate bodies, or mint message IDs.

Each optional GitHub request carries `prii.artifact-mirror.v1`, which includes:

- source, target, kind, and message-ID bindings;
- exact local envelope byte size;
- SHA-256 of the complete local envelope bytes;
- base64 of those exact bytes.

The bridge fails closed on malformed or noncanonical bytes, duplicate JSON
keys, filename/target mismatch, unexpected outbox residue, symbolic links,
wrapper hash mismatch, or a hosted payload-size excess. A bridge failure leaves
the local envelope unchanged.

The event name is intentionally different from the former raw-signal event:

```text
centinelas-artifact-mirror
```

This prevents an older downstream workflow from accidentally treating the new
wrapper as the previous `client_payload.signal` contract. Downstream consumer
migration is a separate vector.

## Dependency manifestations

The core `pyproject.toml` and desktop `requirements-desktop.txt` both bind
`prii-export-utils` to the exact TheHub #260 implementation SHA.

That source pin proves selected source revision only. It does not prove:

- retained source-archive bytes;
- retained wheel bytes;
- license completeness;
- a disconnected installation;
- a disconnected source rebuild.

`uv.lock` and `constraints-desktop.txt` remain generated-manifest residue until
regenerated and reconciled against the exact migration tree. They must not be
hand-edited into an apparently clean state.

## Workflow behavior

The three manual producer workflows default to local classification and local
outbox authority. They attempt a hosted mirror only when the operator enters
`confirm=YES`. Otherwise they perform a mirror dry run over the exact local
bytes.

Workflow artifacts are copies of local exchange state. Their existence, hashes,
or successful upload do not make GitHub authoritative or service-independent.

The main validation workflow is read-only. Its lock job may regenerate a local
candidate and compare it, but it cannot commit or push generated bytes.

## Invariants

The migration must preserve all of these:

1. application dispatch imports no hosted network client;
2. local classification runs without `ANTHROPIC_API_KEY`;
3. hosted classification cannot activate implicitly;
4. every routed payload binds its own `item_id` and `routed_to` target;
5. exact replay creates no additional envelope file;
6. hosted payload construction never mutates local bytes;
7. desktop and core transport pins select the same implementation SHA;
8. validation workflows have no repository write permission;
9. no raw-source or canonical-ledger file enters the changed-file set;
10. all eight Federation freedom gates remain `OPEN` until observed.

## Dynamic gates

```text
CLEAN_CACHE_INSTALL = OPEN
NETWORK_DENY_STARTUP = OPEN
ALLOWLIST_ONLY_CONNECTOR_RUN = OPEN
NO_SECRET_STARTUP = OPEN
PACKAGED_RELEASE_EGRESS_CAPTURE = OPEN
POSTINSTALL_BINARY_CAPTURE = OPEN
OFFLINE_CORE_BROWSE_ANALYZE_EXPORT = OPEN
OFFLINE_REBUILD_FROM_LOCAL_DEPENDENCY_BYTES = OPEN
```

Script success, workflow success, a stable Git pin, a retained wheel, or an
uploaded workflow artifact cannot independently close any of these gates.

## Promotion conditions

This producer PR may advance only after:

- the exact lock and desktop constraints are regenerated and reconciled;
- local tests, lint, type checking, and frontend checks execute at the exact
  head rather than failing before step execution;
- TheHub #260 is independently reviewed and its exact source/wheel bytes are
  frozen;
- at least one downstream consumer verifies and imports the exact mirror bytes
  or local envelope without semantic drift;
- all remaining contradictions are either adjudicated or preserved as explicit
  residue.

Repository certification remains out of scope until all eight dynamic gates
close with frozen inputs and zero unresolved residue inside the claim.

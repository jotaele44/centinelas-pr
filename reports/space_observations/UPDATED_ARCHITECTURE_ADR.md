# ADR — Embedded Centinelas Space Observations Producer

`centinelas-space-observations` is a distinct logical producer embedded under `src/centinelas/space_observations`.

## Boundary

- Centinelas discovery qualifies leads.
- The embedded producer registers acquisitions, validates intake, maintains isolated ledgers, and exports PRII streams.
- Raw and derived bytes live outside Git under `CENTINELAS_EVIDENCE_ROOT`, content-addressed by SHA-256 in later acquisition phases.
- Metadata and ledgers use `data/space_observations/`.
- `ovnis-pr` remains canonical case authority.
- `thehub-pr` remains correlation authority.
- No UAP confirmation, classified-capability inference, negative inference, case duplication, or correlation implementation is permitted.

## Migration route

The route bridge upgrades qualified leads from the former `satellite-observations-pr` target to:

- logical producer: `centinelas-space-observations`;
- repository: `centinelas-pr`;
- correlation target: `thehub-pr`;
- case authority: `ovnis-pr`.

The module remains intentionally extractable if storage volume or operational isolation later requires a standalone repository.

## Persistence and export invariants

- The canonical discovery lead is validated before route ownership changes, and the embedded representation is revalidated through an equivalent canonical view at intake.
- Acquisition rows persist `schema_version`, `idempotency_key`, and `synthetic`; production intake and export reject synthetic records.
- A durable acquisition without its dedup acceptance row is recoverable on replay. A dedup binding without acquisition metadata, duplicate acquisition rows, or conflicting identity bindings fails closed.
- Export manifests hash emitted JSONL bytes, declare stream and schema identity, remove stale unlisted streams, and preserve source/entity/observation referential closure.

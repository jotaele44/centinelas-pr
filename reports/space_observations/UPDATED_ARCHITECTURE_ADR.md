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

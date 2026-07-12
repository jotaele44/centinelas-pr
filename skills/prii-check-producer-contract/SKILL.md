---
name: prii-check-producer-contract
description: >-
  Check Centinelas's local producer contract against the shared PRII contract
  and, when available, the Hub-owned schemas. Use when the user asks whether the
  signal manifest/export is compatible with the Hub. Read-only: reports the
  manifest, callable commands, canonical outputs, readiness, and schema/boundary
  checks, and flags any divergence (naming the manifest key or schema version)
  without asserting Hub-side compatibility it cannot verify.
default_mode: read_only
allowed_modes: [read_only]
command_ids: []
owner_repo: jotaele44/centinelas-pr
---

# prii-check-producer-contract

Reads the local contract surface and compares it to the shared PRII contract; it
does not own or reimplement the Hub schemas. Authorities are `federation.json`
and `schemas/prii_skill_contract.schema.json` (plus the Hub-owned schemas from
`thehub-pr` when present). This skill compares and flags divergences — it never
mutates the manifest, the export, or any schema.

## When this fires
Shared PRII manifest/export compatibility checks against the Hub.

## When this does NOT fire (boundary)
- Ingesting, classifying, or routing signals → the Centinelas engine
  (`src/centinelas`) and its future domain skills.
- Building or emitting the canonical export → `scripts/federation_export.py`.
- Owning or editing Hub-side schemas → `thehub-pr` owns them; this skill only
  compares the local contract against them.
- Cross-producer aggregation or correlation → `thehub-pr`.

## Procedure
1. Read the local contract surface: `federation.json` (hub_callable_commands,
   canonical_outputs, federation_readiness_gate) and
   `schemas/prii_skill_contract.schema.json`.
2. When the Hub-owned schemas from `thehub-pr` are in hand, diff the local
   manifest / commands / outputs against them, key by key and schema version by
   version. Without them, report local-only findings and mark Hub compatibility
   UNVERIFIED — do not assert it.
3. Note Centinelas's production posture (`federation.json`:
   `ready_for_hub_live_execution: true`) as context for any divergence, but do
   not change it — readiness state is owner-governed.

## Required outputs
- the manifest, callable commands, declared canonical outputs, and readiness
  state;
- schema-conformance and boundary-ownership checks; every divergence with the
  manifest key or schema version that diverged.

## Stop conditions
- Local contract diverges from the Hub contract → STOP; cite the manifest key or
  schema version that diverged and route the fix to its owner.

## Evidence & result envelope
Emit `{status, commands_considered, commands_run, artifacts, blockers,
contradictions, next_safe_action}`. Do NOT assert Hub-side compatibility without
the Hub schema in hand; report it UNVERIFIED. Secrets by name only.

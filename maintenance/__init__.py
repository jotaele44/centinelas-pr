"""Repo-specific maintenance adapter for centinelas-pr.

The generic maintenance core (models/state/detect/corrections/quarantine/report/
runner) lives in the shared `prii_maintenance` package
(thehub-pr/packages/prii_maintenance, pinned via pyproject.toml's base
dependencies). Only `adapters/local.py` — the centinelas-specific checks —
is vendored here; it is passed into
`prii_maintenance.run_maintenance(..., local_checks=local.run_checks)`.
Run via ``python3 scripts/run_maintenance.py --repo centinelas-pr --mode audit``.
"""

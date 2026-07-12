"""The committed PRII skill packet passes the shared validator.

Master gate: run scripts/validate_skills.py over the real repo and assert zero
errors across all ten checks. Uses the subprocess form (not an import) so it is
robust to how the repo puts things on sys.path — the validator is a standalone
CLI, and the main pytest job collects this test without scripts/ being
importable."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]

TEN_CHECKS = {
    "skill-structure",
    "skill-registry",
    "command-resolution",
    "path-resolution",
    "boundary-policy",
    "mode-safety",
    "coverage-accounting",
    "export-contract",
    "activation",
    "drift",
}


def _run_validator() -> dict:
    proc = subprocess.run(
        [sys.executable, "scripts/validate_skills.py", "--json"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, f"validator exited {proc.returncode}:\n{proc.stdout}\n{proc.stderr}"
    return json.loads(proc.stdout)


def test_committed_packet_passes_every_check():
    result = _run_validator()
    assert result["ok"] is True, f"skill packet validation failed: {result['errors']}"


def test_all_ten_checks_ran():
    result = _run_validator()
    assert set(result["errors"]) == TEN_CHECKS


def test_registry_validates_against_declared_schema():
    # The registry declares a schema; it must actually conform to it, including
    # the top-level packet_config block (the pure-Python validator does not
    # enforce the schema's additionalProperties, so a jsonschema consumer would).
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads((ROOT / "schemas" / "prii_skill_contract.schema.json").read_text())
    registry = yaml.safe_load((ROOT / "skill-registry.yaml").read_text())
    jsonschema.validate(registry, schema)

"""Federation canonical-export contract-compat test (hub-facing).

Pins the manifest envelope produced by ``scripts/federation_export.py``
``write_package`` against the hub's contract: the exact top-level key set,
the federation handshake block, the per-file entries, and validity against
the vendored copy of thehub-pr's ``federation_export_manifest`` schema
(``schemas/federation_export_manifest.schema.json``). A producer-side change
that alters any of these breaks this test before it can silently break the
hub's consumer.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import federation_export as fx  # noqa: E402

LEDGER = REPO_ROOT / "data/signals/example_signals.jsonl"
SOURCES = REPO_ROOT / "data/reference/source_registry.csv"
SCHEMA_PATH = REPO_ROOT / "schemas/federation_export_manifest.schema.json"

FIXED_NOW = "2026-01-01T00:00:00Z"
MODE = "test"

EXPECTED_MANIFEST_KEYS = {
    "package_id", "producer", "export_contract_version", "mode",
    "created_at", "extracted_at", "federation", "files",
}


def _manifest(tmp_path):
    signals = [json.loads(x) for x in LEDGER.read_text().splitlines() if x.strip()]
    registry = fx._load_source_registry(SOURCES)
    streams = fx.build_streams(signals, registry, FIXED_NOW)
    manifest_path = fx.write_package(streams, tmp_path, MODE, FIXED_NOW)
    return json.loads(manifest_path.read_text())


def test_manifest_top_level_keys_exact(tmp_path):
    manifest = _manifest(tmp_path)
    assert set(manifest) == EXPECTED_MANIFEST_KEYS


def test_federation_handshake_block(tmp_path):
    manifest = _manifest(tmp_path)
    assert manifest["federation"]["hub_parent"] == "thehub-pr"
    assert manifest["federation"]["producer_repo"] == "centinelas-pr"


def test_file_entries_carry_required_fields(tmp_path):
    manifest = _manifest(tmp_path)
    assert manifest["files"]
    for f in manifest["files"]:
        assert set(f) >= {"filename", "stream", "record_count", "sha256", "schema_id"}


def test_manifest_validates_against_vendored_hub_schema(tmp_path):
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads(SCHEMA_PATH.read_text())
    jsonschema.validate(_manifest(tmp_path), schema)


def test_package_id_is_deterministic(tmp_path):
    a = _manifest(tmp_path / "a")
    b = _manifest(tmp_path / "b")
    assert a["package_id"] == b["package_id"]
    assert a == b

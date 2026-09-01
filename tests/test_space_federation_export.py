from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import federation_export_space as exporter  # noqa: E402
from centinelas.space_discovery import ManualReceiptAdapter, build_lead  # noqa: E402

FIXED_NOW = "2026-08-27T12:00:00Z"


def _lead(
    *,
    source_id: str = "CENT-SRC-SPACE-TEST",
    synthetic: bool = True,
    dataset_version: str | None = None,
    evidence_tier: str = "T1",
):
    source_url = f"https://example.test/{source_id.casefold()}"
    body = f"payload:{source_id}".encode()
    receipt = ManualReceiptAdapter().receipt(source_url=source_url, body=body)
    return build_lead(
        source_id=source_id,
        source_url=source_url,
        title=f"Dataset {source_id}",
        subcategory="SATELLITE_DATASET_RELEASE",
        body=body,
        receipt=receipt,
        synthetic=synthetic,
        dataset_version=dataset_version,
        evidence_tier=evidence_tier,
    )


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def test_space_package_uses_canonical_manifest_and_hashes_emitted_bytes(tmp_path):
    manifest_path = exporter.write_space_package(
        [_lead(source_id="SOURCE-A"), _lead(source_id="SOURCE-B")],
        out=tmp_path,
        ledger_ref="data/space/leads.jsonl",
        mode="test",
        created_at=FIXED_NOW,
    )
    manifest = json.loads(manifest_path.read_text())

    assert manifest_path.name == "manifest.json"
    assert set(manifest) == {
        "package_id",
        "producer",
        "export_contract_version",
        "mode",
        "created_at",
        "extracted_at",
        "federation",
        "files",
    }
    assert {entry["stream"] for entry in manifest["files"]} == {
        "sources",
        "entities",
        "observations",
    }
    schema_ids = {
        "sources": "federation_source.schema.json",
        "entities": "federation_entity.schema.json",
        "observations": "federation_observation.schema.json",
    }
    for entry in manifest["files"]:
        emitted = tmp_path / entry["filename"]
        assert entry["sha256"] == hashlib.sha256(emitted.read_bytes()).hexdigest()
        assert entry["record_count"] == len(_read_jsonl(emitted))
        assert entry["schema_id"] == schema_ids[entry["stream"]]

    source_ids = {row["source_id"] for row in _read_jsonl(tmp_path / "sources.jsonl")}
    entities = _read_jsonl(tmp_path / "entities.jsonl")
    entity_ids = {row["entity_id"] for row in entities}
    observations = _read_jsonl(tmp_path / "observations.jsonl")
    assert all(row["source_id"] in source_ids for row in entities)
    assert all(row["source_id"] in source_ids for row in observations)
    assert all(row["entity_id"] in entity_ids for row in observations)

    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads((REPO_ROOT / "schemas/federation_export_manifest.schema.json").read_text())
    jsonschema.validate(manifest, schema)


def test_production_export_rejects_synthetic_leads(tmp_path):
    with pytest.raises(ValueError, match="rejects synthetic"):
        exporter.write_space_package(
            [_lead(synthetic=True)],
            out=tmp_path,
            ledger_ref="fixture.jsonl",
            mode="production",
            created_at=FIXED_NOW,
        )

    manifest_path = exporter.write_space_package(
        [_lead(synthetic=False)],
        out=tmp_path,
        ledger_ref="live.jsonl",
        mode="production",
        created_at=FIXED_NOW,
    )
    assert json.loads(manifest_path.read_text())["mode"] == "production"


def test_export_rejects_empty_or_duplicate_identity_ledgers(tmp_path):
    with pytest.raises(ValueError, match="empty lead ledger"):
        exporter.write_space_package(
            [],
            out=tmp_path,
            ledger_ref="empty.jsonl",
            mode="test",
            created_at=FIXED_NOW,
        )

    lead = _lead()
    with pytest.raises(ValueError, match="duplicate lead identity"):
        exporter.write_space_package(
            [lead, lead],
            out=tmp_path,
            ledger_ref="duplicate.jsonl",
            mode="test",
            created_at=FIXED_NOW,
        )


def test_source_manifestation_selection_is_deterministic_and_whole_row():
    older = _lead(source_id="SOURCE-A", dataset_version="1", evidence_tier="T1")
    newer = _lead(source_id="SOURCE-A", dataset_version="2", evidence_tier="T2")
    older["discovered_at"] = older["last_verified_at"] = "2026-08-27T10:00:00Z"
    newer["discovered_at"] = newer["last_verified_at"] = "2026-08-27T11:00:00Z"

    forward = exporter.build_streams([older, newer], ledger_ref="leads.jsonl", mode="test")
    reverse = exporter.build_streams([newer, older], ledger_ref="leads.jsonl", mode="test")

    assert forward["sources"] == reverse["sources"]
    assert forward["sources"][0]["confidence"] == 0.8
    assert forward["sources"][0]["created_at"] == "2026-08-27T11:00:00Z"

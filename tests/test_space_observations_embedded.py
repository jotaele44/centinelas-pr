import copy
import hashlib
import json
from pathlib import Path

import pytest

from centinelas.space_observations import IntakeEngine, export_federation
from centinelas.space_observations.routing import route_to_embedded_producer
from tests.space_observations_helpers import qualified_lead

FIXED_NOW = "2026-08-27T12:00:00Z"
REPO_ROOT = Path(__file__).resolve().parents[1]


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _write_acquisitions(root: Path, rows: list[dict]) -> None:
    path = root / "data/space_observations/metadata/acquisitions.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows))


def test_route_bridge_and_two_clean_replays(tmp_path):
    routed = route_to_embedded_producer(qualified_lead())
    first = IntakeEngine(tmp_path, production=True).process(routed, run_id="run-1")
    second = IntakeEngine(tmp_path, production=True).process(routed, run_id="run-2")
    assert first.disposition == "accepted"
    assert second.disposition == "duplicate"
    assert first.acknowledgement["receiver"] == "centinelas-space-observations"
    assert first.acquisition["schema_version"] == "1.0.0"
    assert first.acquisition["synthetic"] is False
    assert first.acquisition["network_acquisition_performed"] is False
    assert first.acquisition["analytic_boundaries"]["correlation_owner"] == "thehub-pr"


def test_restart_reconciles_only_the_recoverable_partial_write(tmp_path):
    routed = route_to_embedded_producer(qualified_lead())
    recoverable = tmp_path / "recoverable"
    first = IntakeEngine(recoverable, production=True).process(routed, run_id="first")
    assert first.disposition == "accepted"

    dedup_path = recoverable / "data/space_observations/ledgers/dedup.jsonl"
    acquisition_path = recoverable / "data/space_observations/metadata/acquisitions.jsonl"
    dedup_path.unlink()
    replay = IntakeEngine(recoverable, production=True).process(routed, run_id="replay")
    assert replay.disposition == "duplicate"
    assert len(_read_jsonl(acquisition_path)) == 1
    assert [row["disposition"] for row in _read_jsonl(dedup_path)] == [
        "accepted",
        "duplicate",
    ]

    inconsistent = tmp_path / "inconsistent"
    assert (
        IntakeEngine(inconsistent, production=True).process(routed, run_id="first").disposition
        == "accepted"
    )
    (inconsistent / "data/space_observations/metadata/acquisitions.jsonl").unlink()
    failed = IntakeEngine(inconsistent, production=True).process(routed, run_id="replay")
    assert failed.disposition == "failed"
    assert failed.acknowledgement["reason_code"] == "INTAKE_INTERNAL_ERROR"


def test_persistence_accounting_and_export(tmp_path):
    routed = route_to_embedded_producer(qualified_lead())
    bad = copy.deepcopy(routed)
    bad["review_status"] = "new"
    results = IntakeEngine(tmp_path, production=True).process_many([routed, bad], run_id="run")
    assert [result.disposition for result in results] == ["accepted", "rejected"]
    run = json.loads((tmp_path / "data/space_observations/ledgers/runs.jsonl").read_text())
    assert (
        run["input_count"] == run["accepted"] + run["duplicate"] + run["rejected"] + run["failed"]
    )
    export_dir = tmp_path / "export"
    manifest = export_federation(
        tmp_path,
        export_dir,
        mode="production",
        created_at=FIXED_NOW,
    )
    assert manifest["producer"] == "centinelas-space-observations"
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
        emitted = export_dir / entry["filename"]
        assert entry["sha256"] == hashlib.sha256(emitted.read_bytes()).hexdigest()
        assert entry["record_count"] == len(emitted.read_text().splitlines())
        assert entry["schema_id"] == schema_ids[entry["stream"]]

    jsonschema = pytest.importorskip("jsonschema")
    manifest_schema = json.loads(
        (REPO_ROOT / "schemas/federation_export_manifest.schema.json").read_text()
    )
    acquisition_schema = json.loads(
        (REPO_ROOT / "schemas/space_observations/acquisition.schema.json").read_text()
    )
    observation_schema = json.loads(
        (REPO_ROOT / "schemas/space_observations/observation.schema.json").read_text()
    )
    jsonschema.validate(manifest, manifest_schema)
    jsonschema.validate(results[0].acquisition, acquisition_schema)

    source_ids = {row["source_id"] for row in _read_jsonl(export_dir / "sources.jsonl")}
    entities = _read_jsonl(export_dir / "entities.jsonl")
    entity_ids = {row["entity_id"] for row in entities}
    observations = _read_jsonl(export_dir / "observations.jsonl")
    for observation in observations:
        jsonschema.validate(observation, observation_schema)
    assert all(row["source_id"] in source_ids for row in entities)
    assert all(row["source_id"] in source_ids for row in observations)
    assert all(row["entity_id"] in entity_ids for row in observations)


def test_case_authority_dsp_negative_and_synthetic_guards(tmp_path):
    case_link = {
        "producer": "ovnis-pr",
        "case_id": "OVNIS-TEST",
        "link_basis": ["time_overlap"],
        "link_strength": "candidate",
        "not_a_confirmation": True,
    }
    linked = route_to_embedded_producer(qualified_lead(identity="linked", case_links=[case_link]))
    assert IntakeEngine(tmp_path).process(linked, run_id="case").disposition == "accepted"

    dsp = route_to_embedded_producer(qualified_lead(identity="dsp"))
    dsp["sensor"].update(
        {
            "sensor_type": "infrared_warning",
            "capability_known": True,
            "capability_source_ref": None,
        }
    )
    assert IntakeEngine(tmp_path).process(dsp, run_id="dsp").disposition == "rejected"

    negative = route_to_embedded_producer(qualified_lead(identity="negative"))
    negative["negative_inference"] = "absence proves no event"
    assert IntakeEngine(tmp_path).process(negative, run_id="negative").disposition == "rejected"

    synthetic = route_to_embedded_producer(qualified_lead(identity="synthetic", synthetic=True))
    assert (
        IntakeEngine(tmp_path, production=True).process(synthetic, run_id="synthetic").disposition
        == "rejected"
    )


def test_test_export_preserves_synthetic_and_production_export_rejects_it(tmp_path):
    synthetic = route_to_embedded_producer(qualified_lead(synthetic=True))
    result = IntakeEngine(tmp_path).process(synthetic, run_id="synthetic-test")
    assert result.disposition == "accepted"
    assert result.acquisition["synthetic"] is True

    test_out = tmp_path / "test-export"
    export_federation(tmp_path, test_out, mode="test", created_at=FIXED_NOW)
    for stream in ("sources", "entities", "observations"):
        row = json.loads((test_out / f"{stream}.jsonl").read_text())
        assert row["synthetic"] is True

    with pytest.raises(ValueError, match="rejects synthetic"):
        export_federation(
            tmp_path,
            tmp_path / "production-export",
            mode="production",
            created_at=FIXED_NOW,
        )


def test_route_mismatch_isolated_failure(tmp_path):
    mismatch = qualified_lead()
    result = IntakeEngine(tmp_path).process(mismatch, run_id="mismatch")
    assert result.disposition == "rejected"
    assert result.acknowledgement["reason_code"] == "ROUTE_MISMATCH"


def test_intake_rejects_incomplete_canonical_lead_after_routing(tmp_path):
    malformed = route_to_embedded_producer(qualified_lead())
    malformed.pop("signal_type")
    result = IntakeEngine(tmp_path).process(malformed, run_id="malformed")
    assert result.disposition == "rejected"
    assert result.acknowledgement["reason_code"] == "INVALID_SCHEMA"


def test_checked_in_federation_fixture_is_self_certifying():
    fixture = REPO_ROOT / "reports/space_observations/FEDERATION_EXPORT_FIXTURE"
    manifest = json.loads((fixture / "manifest.json").read_text())
    listed = {entry["filename"] for entry in manifest["files"]}
    actual = {path.name for path in fixture.glob("*.jsonl")}
    assert actual == listed

    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads((REPO_ROOT / "schemas/federation_export_manifest.schema.json").read_text())
    observation_schema = json.loads(
        (REPO_ROOT / "schemas/space_observations/observation.schema.json").read_text()
    )
    jsonschema.validate(manifest, schema)
    for entry in manifest["files"]:
        emitted = fixture / entry["filename"]
        assert entry["sha256"] == hashlib.sha256(emitted.read_bytes()).hexdigest()
        assert entry["record_count"] == len(_read_jsonl(emitted))

    sources = _read_jsonl(fixture / "sources.jsonl")
    entities = _read_jsonl(fixture / "entities.jsonl")
    observations = _read_jsonl(fixture / "observations.jsonl")
    for observation in observations:
        jsonschema.validate(observation, observation_schema)
    source_ids = {row["source_id"] for row in sources}
    entity_ids = {row["entity_id"] for row in entities}
    assert all(row["source_id"] in source_ids for row in entities)
    assert all(row["source_id"] in source_ids for row in observations)
    assert all(row["entity_id"] in entity_ids for row in observations)
    assert all(row["synthetic"] is False for row in sources + entities + observations)


def test_export_adjudicates_order_duplicates_conflicts_and_residue(tmp_path):
    seed = IntakeEngine(tmp_path / "seed", production=True).process(
        route_to_embedded_producer(qualified_lead()),
        run_id="seed",
    )
    first = copy.deepcopy(seed.acquisition)
    first["created_at"] = "2026-08-27T12:00:00Z"
    second = copy.deepcopy(first)
    second.update(
        {
            "acquisition_id": "acq_dddddddddddddddddddddddddddddddd",
            "lead_id": "CENT-SPACE-2026-EEEEEEEEEEEEEEEE",
            "lead_sha256": "f" * 64,
            "idempotency_key": "e" * 64,
            "created_at": "2026-08-27T13:00:00Z",
        }
    )

    forward_root = tmp_path / "forward"
    reverse_root = tmp_path / "reverse"
    _write_acquisitions(forward_root, [first, second])
    _write_acquisitions(reverse_root, [second, first])
    forward_out = tmp_path / "forward-out"
    reverse_out = tmp_path / "reverse-out"
    forward_out.mkdir()
    (forward_out / "relationships.jsonl").write_text('{"stale": true}\n')
    export_federation(forward_root, forward_out, created_at=FIXED_NOW)
    export_federation(reverse_root, reverse_out, created_at=FIXED_NOW)
    assert not (forward_out / "relationships.jsonl").exists()
    assert (forward_out / "sources.jsonl").read_bytes() == (
        reverse_out / "sources.jsonl"
    ).read_bytes()
    assert _read_jsonl(forward_out / "sources.jsonl")[0]["created_at"] == second["created_at"]
    assert len(_read_jsonl(forward_out / "entities.jsonl")) == 2

    duplicate_root = tmp_path / "duplicate"
    _write_acquisitions(duplicate_root, [first, first])
    with pytest.raises(ValueError, match="duplicate acquisition identity"):
        export_federation(duplicate_root, tmp_path / "duplicate-out")

    conflicting = copy.deepcopy(second)
    conflicting["source_url"] = "https://conflict.example.test/item"
    conflict_root = tmp_path / "conflict"
    _write_acquisitions(conflict_root, [first, conflicting])
    with pytest.raises(ValueError, match="conflicting source manifestations"):
        export_federation(conflict_root, tmp_path / "conflict-out")

    with pytest.raises(ValueError, match="empty acquisition ledger"):
        export_federation(tmp_path / "empty", tmp_path / "empty-out")

    malformed_root = tmp_path / "malformed"
    malformed_path = malformed_root / "data/space_observations/metadata/acquisitions.jsonl"
    malformed_path.parent.mkdir(parents=True)
    malformed_path.write_text("{not-json}\n")
    with pytest.raises(ValueError, match="invalid JSONL"):
        export_federation(malformed_root, tmp_path / "malformed-out")


def test_engine_rejects_duplicate_or_conflicting_persistent_indexes(tmp_path):
    seed = IntakeEngine(tmp_path / "seed", production=True).process(
        route_to_embedded_producer(qualified_lead()),
        run_id="seed",
    )
    acquisition = seed.acquisition

    duplicate_root = tmp_path / "duplicate-acquisition"
    _write_acquisitions(duplicate_root, [acquisition, acquisition])
    with pytest.raises(ValueError, match="duplicate acquisitions"):
        IntakeEngine(duplicate_root)

    conflict_root = tmp_path / "conflicting-dedup"
    dedup_path = conflict_root / "data/space_observations/ledgers/dedup.jsonl"
    dedup_path.parent.mkdir(parents=True)
    key = acquisition["idempotency_key"]
    accepted = {
        "idempotency_key": key,
        "acquisition_id": acquisition["acquisition_id"],
        "lead_id": acquisition["lead_id"],
        "disposition": "accepted",
    }
    conflicting = {**accepted, "acquisition_id": "acq_ffffffffffffffffffffffffffffffff"}
    dedup_path.write_text(
        json.dumps(accepted, sort_keys=True) + "\n" + json.dumps(conflicting, sort_keys=True) + "\n"
    )
    with pytest.raises(ValueError, match="conflicting dedup bindings"):
        IntakeEngine(conflict_root)

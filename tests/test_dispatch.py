"""Tests for local-authority dispatch and Centinelas bookkeeping."""

import json
from datetime import datetime, timezone

import pytest

from prii_export_utils import verify_envelope

from centinelas.classify.labels import DomainLabel
from centinelas.models import ClassifiedItem, DispatchRecord
from centinelas.route import dispatch as dispatch_module


@pytest.fixture
def isolated_data_dir(tmp_path, monkeypatch):
    data_dir = tmp_path / ".centinelas"
    exchange = data_dir / "exchange"
    monkeypatch.setattr(dispatch_module, "_DATA_DIR", data_dir)
    monkeypatch.setenv("CENTINELAS_EXCHANGE_ROOT", str(exchange))
    return data_dir


def _make_item(
    item_id: str,
    *,
    label: DomainLabel = DomainLabel.ENVIRONMENTAL,
    confidence: float = 0.9,
) -> ClassifiedItem:
    observed = datetime(2026, 1, 2, 12, 0, tzinfo=timezone.utc)
    return ClassifiedItem(
        item_id=item_id,
        source_url="https://example.com/test",
        source_name="Test Source",
        title="Test Title",
        body_text="Test body",
        published_at=observed,
        captured_at=observed,
        labels=[label],
        confidence=confidence,
        classifier_reasoning="test",
    )


def _outbox_files(data_dir, target: str):
    return sorted((data_dir / "exchange" / "outbox" / target).glob("*.json"))


def _load_envelope(path):
    value = json.loads(path.read_text(encoding="utf-8"))
    verify_envelope(value)
    return value


def test_dispatch_commits_local_envelopes_and_persists_record(isolated_data_dir):
    item = _make_item("persist001")
    record = dispatch_module.dispatch(item, dry_run=False)

    path = isolated_data_dir / "dispatched" / "persist001.json"
    loaded = DispatchRecord.model_validate_json(path.read_text())
    assert loaded == record
    assert record.status == "ok"
    assert set(record.dispatched_to) == {"aguayluz-pr", "thehub-pr"}

    for target in record.dispatched_to:
        files = _outbox_files(isolated_data_dir, target)
        assert len(files) == 1
        envelope = _load_envelope(files[0])
        assert envelope["source"] == "centinelas-pr"
        assert envelope["target"] == target
        assert envelope["kind"] == "centinelas-signal"
        assert envelope["payload"]["item_id"] == "persist001"
        assert envelope["payload"]["routed_to"] == target


def test_dispatch_persists_record_even_under_dry_run(isolated_data_dir):
    item = _make_item("dryrun001")
    record = dispatch_module.dispatch(item, dry_run=True)

    assert record.status == "ok"
    assert set(record.dispatched_to) == {"aguayluz-pr", "thehub-pr"}
    assert (isolated_data_dir / "dispatched" / "dryrun001.json").is_file()
    assert not (isolated_data_dir / "exchange").exists()


def test_dispatched_record_round_trips_exactly(isolated_data_dir):
    item = _make_item("roundtrip001")
    record = dispatch_module.dispatch(item, dry_run=False)
    reloaded = DispatchRecord.model_validate_json(
        (isolated_data_dir / "dispatched" / "roundtrip001.json").read_text()
    )
    assert reloaded == record


def test_low_confidence_item_is_skipped(isolated_data_dir, monkeypatch):
    monkeypatch.setenv("CENTINELAS_ROUTE_MIN_CONFIDENCE", "0.55")
    item = _make_item(
        "lowconf001", label=DomainLabel.FINANCIAL, confidence=0.40
    )
    record = dispatch_module.dispatch(item, dry_run=False)

    assert record.status == "skipped"
    assert record.dispatched_to == []
    assert not (isolated_data_dir / "exchange").exists()
    assert (isolated_data_dir / "dispatched" / "lowconf001.json").exists()


def test_at_threshold_item_is_staged_locally(isolated_data_dir, monkeypatch):
    monkeypatch.setenv("CENTINELAS_ROUTE_MIN_CONFIDENCE", "0.55")
    item = _make_item(
        "okconf001", label=DomainLabel.FINANCIAL, confidence=0.55
    )
    record = dispatch_module.dispatch(item, dry_run=False)

    assert record.status == "ok"
    assert "moneysweep-pr" in record.dispatched_to
    assert len(_outbox_files(isolated_data_dir, "moneysweep-pr")) == 1


def test_exact_replay_is_idempotent(isolated_data_dir):
    item = _make_item("replay001", label=DomainLabel.FINANCIAL)
    first = dispatch_module.dispatch(item, dry_run=False)
    first_paths = {
        target: [path.name for path in _outbox_files(isolated_data_dir, target)]
        for target in first.dispatched_to
    }

    second = dispatch_module.dispatch(item, dry_run=False)
    second_paths = {
        target: [path.name for path in _outbox_files(isolated_data_dir, target)]
        for target in second.dispatched_to
    }

    assert first.status == second.status == "ok"
    assert first_paths == second_paths
    assert all(len(names) == 1 for names in second_paths.values())


def test_partial_local_failure_is_not_reported_as_success(
    isolated_data_dir, monkeypatch
):
    item = _make_item("partial001", label=DomainLabel.FINANCIAL)
    original = dispatch_module._stage_payload

    def fail_thehub(item_id, target, payload):
        if target == "thehub-pr":
            raise OSError("fixture failure")
        return original(item_id, target, payload)

    monkeypatch.setattr(dispatch_module, "_stage_payload", fail_thehub)
    record = dispatch_module.dispatch(item, dry_run=False)

    assert record.status == "failed"
    assert record.dispatched_to == ["moneysweep-pr"]
    assert record.error == "thehub-pr: fixture failure"
    assert len(_outbox_files(isolated_data_dir, "moneysweep-pr")) == 1
    assert _outbox_files(isolated_data_dir, "thehub-pr") == []

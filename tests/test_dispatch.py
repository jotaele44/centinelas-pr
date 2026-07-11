"""Tests for dispatch record persistence."""

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from centinelas.classify.labels import DomainLabel
from centinelas.models import ClassifiedItem, DispatchRecord
from centinelas.route import dispatch as dispatch_module


@pytest.fixture
def isolated_data_dir(tmp_path, monkeypatch):
    """Point CENTINELAS_DATA_DIR and CENTINELAS_REPOS_DIR at a scratch tmp_path
    so this test never touches real sibling repos or a real .centinelas/ dir."""
    data_dir = tmp_path / ".centinelas"
    repos_dir = tmp_path / "repos"
    monkeypatch.setattr(dispatch_module, "_DATA_DIR", data_dir)
    monkeypatch.setattr(dispatch_module, "_REPOS_BASE", repos_dir)
    return data_dir


def _make_item(item_id: str) -> ClassifiedItem:
    return ClassifiedItem(
        item_id=item_id,
        source_url="https://example.com/test",
        source_name="Test Source",
        title="Test Title",
        body_text="Test body",
        published_at=datetime.now(timezone.utc),
        captured_at=datetime.now(timezone.utc),
        labels=[DomainLabel.ENVIRONMENTAL],
        confidence=0.9,
        classifier_reasoning="test",
    )


def test_dispatch_persists_record_when_not_dry_run(isolated_data_dir):
    item = _make_item("persist001")
    record = dispatch_module.dispatch(item, dry_run=False)

    path = isolated_data_dir / "dispatched" / "persist001.json"
    assert path.exists()

    loaded = DispatchRecord.model_validate_json(path.read_text())
    assert loaded.item_id == record.item_id
    assert loaded.dispatched_to == record.dispatched_to
    assert loaded.status == record.status


def test_dispatch_persists_record_even_under_dry_run(isolated_data_dir):
    """dry_run must skip cross-repo intake/ writes but still persist local bookkeeping."""
    item = _make_item("dryrun001")
    record = dispatch_module.dispatch(item, dry_run=True)

    path = isolated_data_dir / "dispatched" / "dryrun001.json"
    assert path.exists(), "dispatch record must persist locally even under dry_run"

    loaded = DispatchRecord.model_validate_json(path.read_text())
    assert loaded.item_id == "dryrun001"

    # No cross-repo intake/ files should have been written under dry_run.
    repos_dir = isolated_data_dir.parent / "repos"
    assert not any(repos_dir.glob("*/intake/*.json"))


def test_dispatched_record_round_trips_exactly(isolated_data_dir):
    item = _make_item("roundtrip001")
    record = dispatch_module.dispatch(item, dry_run=False)

    path = isolated_data_dir / "dispatched" / "roundtrip001.json"
    raw = json.loads(path.read_text())
    reloaded = DispatchRecord.model_validate(raw)

    assert reloaded == record


def _make_item_conf(item_id: str, confidence: float) -> ClassifiedItem:
    return ClassifiedItem(
        item_id=item_id,
        source_url="https://example.com/test",
        source_name="Test Source",
        title="Test Title",
        body_text="Test body",
        published_at=datetime.now(timezone.utc),
        captured_at=datetime.now(timezone.utc),
        labels=[DomainLabel.FINANCIAL],
        confidence=confidence,
        classifier_reasoning="test",
    )


def test_low_confidence_item_is_skipped(isolated_data_dir, monkeypatch):
    """Below the route minimum, an item is skipped and writes no intake payloads."""
    monkeypatch.setenv("CENTINELAS_ROUTE_MIN_CONFIDENCE", "0.55")
    item = _make_item_conf("lowconf001", 0.40)
    record = dispatch_module.dispatch(item, dry_run=False)

    assert record.status == "skipped"
    assert record.dispatched_to == []
    # No cross-repo intake payloads written for a skipped item.
    repos_dir = isolated_data_dir.parent / "repos"
    assert not any(repos_dir.glob("*/intake/*.json"))
    # But the skip is still recorded for bookkeeping/idempotency.
    assert (isolated_data_dir / "dispatched" / "lowconf001.json").exists()


def test_at_threshold_item_is_dispatched(isolated_data_dir, monkeypatch):
    monkeypatch.setenv("CENTINELAS_ROUTE_MIN_CONFIDENCE", "0.55")
    item = _make_item_conf("okconf001", 0.55)
    record = dispatch_module.dispatch(item, dry_run=False)

    assert record.status == "ok"
    assert "moneysweep-pr" in record.dispatched_to


def test_outbound_dir_stages_payloads_for_ci(tmp_path, isolated_data_dir, monkeypatch):
    """CENTINELAS_OUTBOUND_DIR stages payloads locally instead of a sibling checkout."""
    outbound = tmp_path / "outbound"
    monkeypatch.setenv("CENTINELAS_OUTBOUND_DIR", str(outbound))
    item = _make_item_conf("outbound001", 0.9)
    record = dispatch_module.dispatch(item, dry_run=False)

    assert record.status == "ok"
    staged = outbound / "moneysweep-pr" / "outbound001.json"
    assert staged.exists(), "payload should be staged under <outbound>/<repo>/"
    payload = json.loads(staged.read_text())
    assert payload["item_id"] == "outbound001"
    assert payload["routed_to"] == "moneysweep-pr"

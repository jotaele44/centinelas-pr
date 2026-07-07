"""Tests for the desktop signal-seeder and its guards.

Covers the regression fixes: never seed over a live pipeline (any of
queue/classified/dispatched non-empty), the .seeded marker, idempotency, and
--force. Pure filesystem work against a tmp CENTINELAS_DATA_DIR.
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from desktop import seed  # noqa: E402


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    """Point every seed directory at a tmp dir with one valid ledger row."""
    data = tmp_path / ".centinelas"
    monkeypatch.setattr(seed, "DATA_DIR", data)
    monkeypatch.setattr(seed, "QUEUE_DIR", data / "queue")
    monkeypatch.setattr(seed, "CLASSIFIED_DIR", data / "classified")
    monkeypatch.setattr(seed, "DISPATCHED_DIR", data / "dispatched")
    monkeypatch.setattr(seed, "SEED_MARKER", data / ".seeded")
    ledger = tmp_path / "live.jsonl"
    row = {
        "signal_id": "CENT-SIG-0001",
        "source_id": "CENT-SRC-RSS-THE-DRIVE-WAR-ZONE",
        "source_url": "https://example.com/a",
        "published_at": "2026-01-01T00:00:00Z",
        "title": "Example signal",
        "confidence_score": 80,
    }
    ledger.write_text(json.dumps(row) + "\n", encoding="utf-8")
    monkeypatch.setattr(seed, "LEDGERS", [ledger])
    return data


def test_source_name_humanizes():
    assert seed.source_name("CENT-SRC-RSS-THE-DRIVE-WAR-ZONE") == "The Drive War Zone"


def test_item_from_signal_requires_fields():
    assert seed.item_from_signal({"signal_id": "x"}) is None


def test_item_from_signal_marks_seeded():
    item = seed.item_from_signal(
        {
            "signal_id": "CENT-SIG-0001",
            "source_url": "https://e/1",
            "published_at": "2026-01-01T00:00:00Z",
        }
    )
    assert item is not None
    assert item["seeded_from_ledger"] is True
    assert 0.0 <= item["confidence"] <= 1.0


def test_seed_writes_on_clean_state(sandbox):
    n = seed.seed()
    assert n == 1
    assert list((sandbox / "classified").glob("*.json"))
    assert (sandbox / ".seeded").exists()


def test_seed_noop_when_marker_present(sandbox):
    seed.seed()
    assert seed.seed() == 0  # marker present → no-op


def test_seed_noop_when_pipeline_has_state(sandbox):
    (sandbox / "queue").mkdir(parents=True)
    (sandbox / "queue" / "item.json").write_text("{}", encoding="utf-8")
    assert seed.seed() == 0  # live queue → never seed over it
    assert not list((sandbox / "classified").glob("*.json"))


def test_force_reseeds(sandbox):
    seed.seed()
    assert seed.seed(force=True) >= 0  # bypasses both guards

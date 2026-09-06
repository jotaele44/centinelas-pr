from datetime import datetime, timezone

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from starlette.testclient import TestClient

from centinelas.classify.labels import DomainLabel
from centinelas.models import ClassifiedItem
from server.backend import main


@pytest.fixture
def client(tmp_path, monkeypatch):
    data = tmp_path / ".centinelas"
    classified = data / "classified"
    classified.mkdir(parents=True)
    observed = datetime(2026, 1, 2, 12, 0, tzinfo=timezone.utc)
    item = ClassifiedItem(
        item_id="handoff-001",
        source_url="https://example.com/signal",
        source_name="Test",
        title="Multi-domain signal",
        body_text="A signal selected by an operator.",
        published_at=observed,
        captured_at=observed,
        labels=[DomainLabel.ENVIRONMENTAL],
        confidence=0.9,
    )
    (classified / "handoff-001.json").write_text(item.model_dump_json())
    monkeypatch.setattr(main, "DATA_DIR", data)
    monkeypatch.setattr(main, "CLASSIFIED_DIR", classified)
    monkeypatch.setattr(main, "HANDOFF_DIR", data / "handoffs")
    monkeypatch.setenv("CENTINELAS_EXCHANGE_ROOT", str(data / "exchange"))
    with TestClient(main.app) as test_client:
        yield test_client, data


def test_handoff_stages_selected_targets_and_persists_receipt(client):
    test_client, data = client
    response = test_client.post(
        "/handoffs/handoff-001",
        json={"targets": ["spiderweb-pr", "skywatcher-pr"]},
    )
    assert response.status_code == 200
    receipt = response.json()
    assert receipt["status"] == "staged_local"
    assert {attempt["target"] for attempt in receipt["attempts"]} == {
        "spiderweb-pr",
        "skywatcher-pr",
    }
    assert all(attempt["status"] == "staged_local" for attempt in receipt["attempts"])
    assert all(attempt["transport_status"] == "EMITTED" for attempt in receipt["attempts"])
    assert all(len(attempt["message_id"]) == 64 for attempt in receipt["attempts"])
    assert len({attempt["idempotency_key"] for attempt in receipt["attempts"]}) == 2
    assert len(list(main.HANDOFF_DIR.glob("*.json"))) == 1
    for target in ("spiderweb-pr", "skywatcher-pr"):
        assert len(list((data / "exchange" / "outbox" / target).glob("*.json"))) == 1


def test_handoff_exact_replay_reports_duplicate_local(client):
    test_client, data = client
    request = {"targets": ["moneysweep-pr"]}
    first = test_client.post("/handoffs/handoff-001", json=request).json()
    second = test_client.post("/handoffs/handoff-001", json=request).json()

    assert first["status"] == second["status"] == "staged_local"
    assert first["attempts"][0]["message_id"] == second["attempts"][0]["message_id"]
    assert first["attempts"][0]["transport_status"] == "EMITTED"
    assert second["attempts"][0]["transport_status"] == "DUPLICATE"
    assert len(list((data / "exchange" / "outbox" / "moneysweep-pr").glob("*.json"))) == 1


def test_handoff_dry_run_creates_no_outbox(client):
    test_client, data = client
    response = test_client.post(
        "/handoffs/handoff-001",
        json={"targets": ["aguayluz-pr"], "dry_run": True},
    )
    assert response.status_code == 200
    receipt = response.json()
    assert receipt["status"] == "staged_local"
    assert receipt["attempts"][0]["status"] == "dry_run"
    assert not (data / "exchange").exists()


def test_handoff_rejects_unknown_target(client):
    test_client, _ = client
    response = test_client.post(
        "/handoffs/handoff-001",
        json={"targets": ["unknown-pr"]},
    )
    assert response.status_code == 422


def test_handoff_list_includes_local_history(client):
    test_client, _ = client
    test_client.post(
        "/handoffs/handoff-001",
        json={"targets": ["aguayluz-pr", "moneysweep-pr"]},
    )
    rows = test_client.get("/handoffs").json()
    assert rows[0]["item_id"] == "handoff-001"
    assert rows[0]["handoffs"][0]["status"] == "staged_local"

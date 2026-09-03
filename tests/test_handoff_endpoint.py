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
    item = ClassifiedItem(
        item_id="handoff-001",
        source_url="https://example.com/signal",
        source_name="Test",
        title="Multi-domain signal",
        body_text="A signal selected by an operator.",
        published_at=datetime.now(timezone.utc),
        captured_at=datetime.now(timezone.utc),
        labels=[DomainLabel.ENVIRONMENTAL],
        confidence=0.9,
    )
    (classified / "handoff-001.json").write_text(item.model_dump_json())
    monkeypatch.setattr(main, "DATA_DIR", data)
    monkeypatch.setattr(main, "CLASSIFIED_DIR", classified)
    monkeypatch.setattr(main, "HANDOFF_DIR", data / "handoffs")
    monkeypatch.setenv("CENTINELAS_OUTBOUND_DIR", str(tmp_path / "outbound"))
    monkeypatch.setenv("CENTINELAS_GITHUB_TOKEN", "test-token")
    monkeypatch.setattr(
        "centinelas.route.dispatch._repository_dispatch",
        lambda target, body, token: 204,
    )
    with TestClient(main.app) as test_client:
        yield test_client, tmp_path


def test_handoff_delivers_selected_targets_and_persists_receipt(client):
    test_client, tmp_path = client
    response = test_client.post(
        "/handoffs/handoff-001",
        json={"targets": ["spiderweb-pr", "skywatcher-pr"]},
    )
    assert response.status_code == 200
    receipt = response.json()
    assert receipt["status"] == "pending_ack"
    assert {a["target"] for a in receipt["attempts"]} == {
        "spiderweb-pr",
        "skywatcher-pr",
    }
    assert all(a["status"] == "pending_ack" for a in receipt["attempts"])
    assert all(a["dispatch_http_status"] == 204 for a in receipt["attempts"])
    assert len({a["idempotency_key"] for a in receipt["attempts"]}) == 2
    assert len(list(main.HANDOFF_DIR.glob("*.json"))) == 1


def test_handoff_rejects_unknown_target(client):
    test_client, _ = client
    response = test_client.post(
        "/handoffs/handoff-001",
        json={"targets": ["unknown-pr"]},
    )
    assert response.status_code == 422


def test_handoff_list_includes_history(client):
    test_client, _ = client
    test_client.post(
        "/handoffs/handoff-001",
        json={"targets": ["aguayluz-pr", "moneysweep-pr"]},
    )
    rows = test_client.get("/handoffs").json()
    assert rows[0]["item_id"] == "handoff-001"
    assert rows[0]["handoffs"][0]["status"] == "pending_ack"

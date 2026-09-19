"""Tests for the POST /run pipeline-trigger endpoint (server.backend.main).

Exercises the endpoint end-to-end through the FastAPI TestClient using only the
keyword classifier tier — no ANTHROPIC_API_KEY and no network.
"""

from datetime import datetime, timezone

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from starlette.testclient import TestClient  # noqa: E402

import server.backend.auth as auth  # noqa: E402
import server.backend.main as main  # noqa: E402
from centinelas.models import RawItem  # noqa: E402


def _raw_item(item_id: str) -> RawItem:
    now = datetime.now(timezone.utc)
    return RawItem(
        item_id=item_id,
        source_url=f"https://example.com/{item_id}",
        source_name="Test Source",
        title="Earthquake near military base",
        body_text="A magnitude 6 earthquake struck near a military installation.",
        published_at=now,
        captured_at=now,
    )


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Explicitly establish the local-write principal used by these pipeline tests."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(auth, "WRITE_TOKEN", "")
    # Starlette/httpx TestClient host labels are implementation details and have
    # changed across releases. Bind this fixture to the intended local principal
    # rather than silently inheriting a pseudo-host such as "testclient".
    monkeypatch.setattr(auth, "_is_local_network", lambda host: host == "testclient")

    data_dir = tmp_path / ".centinelas"
    monkeypatch.setattr(main, "DATA_DIR", data_dir)
    monkeypatch.setattr(main, "QUEUE_DIR", data_dir / "queue")
    monkeypatch.setattr(main, "CLASSIFIED_DIR", data_dir / "classified")
    monkeypatch.setattr(main, "DISPATCHED_DIR", data_dir / "dispatched")

    monkeypatch.setattr("centinelas.ingest.rss.poll_all", lambda: [_raw_item("run-ep-001")])
    monkeypatch.setattr("centinelas.ingest.federal_register.poll_federal_register", list)
    monkeypatch.setattr("centinelas.ingest.web.poll_scrape_sources", list)

    with TestClient(main.app) as c:
        yield c


def test_run_dry_run_returns_summary(client):
    r = client.post("/run", json={"dry_run": True})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "ok"
    assert body["dry_run"] is True
    assert body["ingested"] == 1
    assert body["classified"] == 1
    assert body["dispatched"] == 1
    assert body["dispatch_breakdown"].get("ok") == 1


def test_run_persists_classified_and_items_endpoint_reflects_it(client):
    client.post("/run", json={"dry_run": True})
    written = list(main.CLASSIFIED_DIR.glob("*.json"))
    assert [p.name for p in written] == ["run-ep-001.json"]
    items = client.get("/items").json()
    assert any(it["item_id"] == "run-ep-001" for it in items)


def test_run_dispatch_records_land_in_server_data_dir(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(auth, "WRITE_TOKEN", "")
    monkeypatch.setattr(auth, "_is_local_network", lambda host: host == "testclient")
    cwd = tmp_path / "elsewhere"
    cwd.mkdir()
    monkeypatch.chdir(cwd)

    data_dir = tmp_path / "server_data"
    monkeypatch.setattr(main, "DATA_DIR", data_dir)
    monkeypatch.setattr(main, "CLASSIFIED_DIR", data_dir / "classified")
    monkeypatch.setattr(main, "DISPATCHED_DIR", data_dir / "dispatched")
    monkeypatch.setattr("centinelas.ingest.rss.poll_all", lambda: [_raw_item("run-ep-002")])
    monkeypatch.setattr("centinelas.ingest.federal_register.poll_federal_register", list)
    monkeypatch.setattr("centinelas.ingest.web.poll_scrape_sources", list)

    with TestClient(main.app) as c:
        r = c.post("/run", json={"dry_run": True})
        assert r.status_code == 200, r.text
        assert (data_dir / "dispatched" / "run-ep-002.json").exists()
        assert not (cwd / ".centinelas").exists()
        item = next(it for it in c.get("/items").json() if it["item_id"] == "run-ep-002")
        assert item["dispatch"] is not None


def test_run_empty_body_defaults_to_full_run(client):
    r = client.post("/run", json={"dry_run": True, "limit": 5})
    assert r.status_code == 200, r.text
    assert r.json()["ingested"] == 1


def test_run_rejects_nonlocal_client_without_token(tmp_path, monkeypatch):
    monkeypatch.setattr(auth, "WRITE_TOKEN", "")
    monkeypatch.setattr(auth, "_is_local_network", lambda host: False)
    with TestClient(main.app) as c:
        r = c.post("/run", json={"dry_run": True})
    assert r.status_code == 403


def test_run_rejects_bad_bearer_when_token_mode_enabled(monkeypatch):
    monkeypatch.setattr(auth, "WRITE_TOKEN", "expected-token")
    with TestClient(main.app) as c:
        r = c.post(
            "/run",
            json={"dry_run": True},
            headers={"Authorization": "Bearer wrong-token"},
        )
    assert r.status_code == 401

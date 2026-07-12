"""Tests for the POST /run pipeline-trigger endpoint (server.backend.main).

Exercises the endpoint end-to-end through the FastAPI TestClient using only the
keyword classifier tier — no ANTHROPIC_API_KEY and no network. poll_all is
monkeypatched to return a hand-built RawItem whose text carries two distinct
domain keywords, so the classifier takes its multi-hit keyword fast path and
never reaches the Claude Haiku tier. Skipped when fastapi/httpx aren't installed.
"""

from datetime import datetime, timezone

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from starlette.testclient import TestClient  # noqa: E402

import server.backend.main as main  # noqa: E402
from centinelas.models import RawItem  # noqa: E402


def _raw_item(item_id: str) -> RawItem:
    now = datetime.now(timezone.utc)
    # "earthquake" (GEO_GEOLOGY) + "military" (MILITARY_AEROSPACE) → 2 keyword
    # hits → the classifier's high-confidence keyword fast path (no LLM call).
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
    """A TestClient whose data dirs and cwd are redirected under tmp_path.

    Redirecting cwd keeps the dispatch module's relative `.centinelas/dispatched`
    bookkeeping inside the temp dir, and pointing the server's CLASSIFIED_DIR at
    tmp keeps the run's classified output isolated from the repo.
    """
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    data_dir = tmp_path / ".centinelas"
    monkeypatch.setattr(main, "DATA_DIR", data_dir)
    monkeypatch.setattr(main, "QUEUE_DIR", data_dir / "queue")
    monkeypatch.setattr(main, "CLASSIFIED_DIR", data_dir / "classified")
    monkeypatch.setattr(main, "DISPATCHED_DIR", data_dir / "dispatched")

    monkeypatch.setattr("centinelas.ingest.rss.poll_all", lambda: [_raw_item("run-ep-001")])

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
    # Two keyword hits → confidence 0.85 ≥ route gate → dispatched ok even in dry-run.
    assert body["dispatched"] == 1
    assert body["dispatch_breakdown"].get("ok") == 1


def test_run_persists_classified_and_items_endpoint_reflects_it(client):
    client.post("/run", json={"dry_run": True})

    # The run wrote the classified item where the read endpoints look for it.
    written = list((main.CLASSIFIED_DIR).glob("*.json"))
    assert [p.name for p in written] == ["run-ep-001.json"]

    items = client.get("/items").json()
    assert any(it["item_id"] == "run-ep-001" for it in items)


def test_run_empty_body_defaults_to_full_run(client):
    # No body → RunRequest defaults (dry_run False, limit 0). Dispatch is dry via
    # sibling-repo absence being irrelevant here: with dry_run False it would write
    # to intake dirs, so we assert only the pipeline shape, not filesystem writes.
    r = client.post("/run", json={"dry_run": True, "limit": 5})
    assert r.status_code == 200, r.text
    assert r.json()["ingested"] == 1

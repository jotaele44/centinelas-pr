"""Tests for the repository_dispatch emitter (offline — no network)."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "emit_dispatches.py"
_spec = importlib.util.spec_from_file_location("emit_dispatches", _SCRIPT)
emit = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(emit)


def _stage(outbound: Path, repo: str, item_id: str, payload: dict) -> None:
    d = outbound / repo
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{item_id}.json").write_text(json.dumps(payload), encoding="utf-8")


def test_build_body_wraps_within_client_payload_key_limit():
    # A realistic intake record has >10 fields; wrapping must keep client_payload <= 10 keys.
    payload = {f"field_{i}": i for i in range(15)}
    body = emit.build_dispatch_body("abc123", "moneysweep-pr", payload, "centinelas-signal")
    assert body["event_type"] == "centinelas-signal"
    assert set(body["client_payload"]) == {"item_id", "repo", "signal"}
    assert len(body["client_payload"]) <= 10
    assert body["client_payload"]["signal"] == payload
    assert body["client_payload"]["item_id"] == "abc123"


def test_long_body_text_is_bounded_under_github_limit():
    # A full-article feed can yield an enormous body_text; the wrapped client_payload
    # must stay under GitHub's 65,535-char cap so the dispatch is not rejected (HTTP 422).
    payload = {
        "item_id": "big001",
        "source_url": "https://example.com/article",
        "labels": ["FINANCIAL"],
        "municipalities": ["San Juan"],
        "body_text": "x" * 200_000,
    }
    body = emit.build_dispatch_body("big001", "moneysweep-pr", payload, "centinelas-signal")
    serialized = json.dumps(body["client_payload"])
    assert len(serialized) < 65_535
    # Structured fields survive; only body_text is trimmed.
    signal = body["client_payload"]["signal"]
    assert signal["item_id"] == "big001"
    assert signal["source_url"] == "https://example.com/article"
    assert signal["municipalities"] == ["San Juan"]
    assert len(signal["body_text"]) < len(payload["body_text"])
    # The caller's payload is not mutated.
    assert len(payload["body_text"]) == 200_000


def test_short_body_text_is_left_intact():
    payload = {"item_id": "s1", "body_text": "short body"}
    body = emit.build_dispatch_body("s1", "moneysweep-pr", payload, "centinelas-signal")
    assert body["client_payload"]["signal"]["body_text"] == "short body"


def test_iter_payloads_discovers_staged_files(tmp_path):
    _stage(tmp_path, "moneysweep-pr", "id1", {"item_id": "id1"})
    _stage(tmp_path, "thehub-pr", "id2", {"item_id": "id2"})
    found = {(repo, item_id) for repo, item_id, _ in emit.iter_payloads(tmp_path)}
    assert found == {("moneysweep-pr", "id1"), ("thehub-pr", "id2")}


def test_dry_run_emits_nothing_over_network(tmp_path, capsys):
    _stage(tmp_path, "moneysweep-pr", "id1", {"item_id": "id1"})
    rc = emit.run(tmp_path, owner="jotaele44", event_type="centinelas-signal", token=None, dry_run=True)
    assert rc == 0
    out = capsys.readouterr().out
    assert "[dry-run] centinelas-signal → jotaele44/moneysweep-pr (item id1)" in out


def test_missing_outbound_dir_is_noop(tmp_path):
    rc = emit.run(tmp_path / "nope", owner="jotaele44", event_type="x", token=None, dry_run=False)
    assert rc == 0


def test_only_repo_filters_dispatch_targets(tmp_path, capsys):
    """--only-repo scopes the chain: Centinelas fires MoneySweep, not the Hub copy."""
    _stage(tmp_path, "moneysweep-pr", "id1", {"item_id": "id1"})
    _stage(tmp_path, "thehub-pr", "id1", {"item_id": "id1"})
    rc = emit.run(
        tmp_path,
        owner="jotaele44",
        event_type="centinelas-signal",
        token=None,
        dry_run=True,
        only_repo="moneysweep-pr",
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "jotaele44/moneysweep-pr" in out
    assert "thehub-pr" not in out

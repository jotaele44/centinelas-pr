"""Offline tests for the optional exact-byte GitHub mirror."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from prii_export_utils import emit_message, sha256, verify_mirror_payload

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "emit_dispatches.py"
_spec = importlib.util.spec_from_file_location("emit_dispatches", _SCRIPT)
assert _spec and _spec.loader
emit = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(emit)


def _stage(exchange: Path, target: str, item_id: str, *, body_text: str = "body"):
    payload = {
        "schema_version": "1.0",
        "item_id": item_id,
        "source_url": f"https://example.com/{item_id}",
        "title": "Test",
        "body_text": body_text,
        "routed_to": target,
        "routed_at": "2026-01-02T12:00:00+00:00",
    }
    return emit_message(
        exchange,
        source="centinelas-pr",
        target=target,
        kind="centinelas-signal",
        idempotency_key=f"fixture-{item_id}-{target}",
        payload=payload,
    )


def test_build_body_wraps_exact_local_envelope_bytes(tmp_path):
    exchange = tmp_path / "exchange"
    staged = _stage(exchange, "moneysweep-pr", "abc123")

    body = emit.build_dispatch_body(staged.path, "centinelas-artifact-mirror")
    envelope, data = verify_mirror_payload(body["client_payload"])

    assert body["event_type"] == "centinelas-artifact-mirror"
    assert data == staged.path.read_bytes()
    assert envelope["message_id"] == staged.message_id
    assert envelope["payload"]["item_id"] == "abc123"


def test_large_envelope_fails_closed_without_truncating_local_bytes(tmp_path):
    exchange = tmp_path / "exchange"
    staged = _stage(
        exchange,
        "moneysweep-pr",
        "big001",
        body_text="x" * 100_000,
    )
    before = sha256(staged.path)

    try:
        emit.build_dispatch_body(staged.path, "centinelas-artifact-mirror")
    except emit.MirrorDispatchError as exc:
        assert "local envelope remains authoritative" in str(exc)
    else:
        raise AssertionError("oversized hosted mirror must fail closed")

    assert sha256(staged.path) == before
    assert len(staged.path.read_bytes()) > 100_000


def test_iter_envelopes_discovers_validated_outbox(tmp_path):
    exchange = tmp_path / "exchange"
    one = _stage(exchange, "moneysweep-pr", "id1")
    two = _stage(exchange, "thehub-pr", "id2")

    found = {
        (target, path.name, envelope["message_id"])
        for target, path, envelope in emit.iter_envelopes(exchange)
    }
    assert found == {
        ("moneysweep-pr", one.path.name, one.message_id),
        ("thehub-pr", two.path.name, two.message_id),
    }


def test_dry_run_performs_no_network_call(tmp_path, capsys, monkeypatch):
    exchange = tmp_path / "exchange"
    staged = _stage(exchange, "moneysweep-pr", "id1")

    def forbidden(*_args, **_kwargs):
        raise AssertionError("dry run must not call the hosted bridge")

    monkeypatch.setattr(emit, "post_dispatch", forbidden)
    code = emit.run(
        exchange,
        owner="jotaele44",
        event_type="centinelas-artifact-mirror",
        token=None,
        dry_run=True,
    )

    assert code == 0
    output = capsys.readouterr().out
    assert staged.message_id in output
    assert "jotaele44/moneysweep-pr" in output


def test_missing_outbox_is_noop(tmp_path):
    code = emit.run(
        tmp_path / "exchange",
        owner="jotaele44",
        event_type="x",
        token=None,
        dry_run=False,
    )
    assert code == 0


def test_only_repo_filters_mirror_targets(tmp_path, capsys):
    exchange = tmp_path / "exchange"
    moneysweep = _stage(exchange, "moneysweep-pr", "id1")
    _stage(exchange, "thehub-pr", "id1")

    code = emit.run(
        exchange,
        owner="jotaele44",
        event_type="centinelas-artifact-mirror",
        token=None,
        dry_run=True,
        only_repo="moneysweep-pr",
    )

    assert code == 0
    output = capsys.readouterr().out
    assert moneysweep.message_id in output
    assert "jotaele44/moneysweep-pr" in output
    assert "thehub-pr" not in output


def test_non_dry_mirror_requires_token_but_preserves_local_message(tmp_path):
    exchange = tmp_path / "exchange"
    staged = _stage(exchange, "moneysweep-pr", "id1")

    code = emit.run(
        exchange,
        owner="jotaele44",
        event_type="centinelas-artifact-mirror",
        token=None,
        dry_run=False,
    )

    assert code == 2
    assert staged.path.is_file()


def test_outbox_target_directory_mismatch_fails_closed(tmp_path, capsys):
    exchange = tmp_path / "exchange"
    staged = _stage(exchange, "moneysweep-pr", "id1")
    wrong_dir = exchange / "outbox" / "thehub-pr"
    wrong_dir.mkdir(parents=True)
    staged.path.replace(wrong_dir / staged.path.name)
    (exchange / "outbox" / "moneysweep-pr").rmdir()

    code = emit.run(
        exchange,
        owner="jotaele44",
        event_type="centinelas-artifact-mirror",
        token=None,
        dry_run=True,
    )

    assert code == 1
    assert "target directory mismatch" in capsys.readouterr().err


def test_unexpected_outbox_member_fails_closed(tmp_path, capsys):
    exchange = tmp_path / "exchange"
    target = exchange / "outbox" / "moneysweep-pr"
    target.mkdir(parents=True)
    (target / "residue.tmp").write_text("residue", encoding="utf-8")

    code = emit.run(
        exchange,
        owner="jotaele44",
        event_type="centinelas-artifact-mirror",
        token=None,
        dry_run=True,
    )

    assert code == 1
    assert "unexpected outbox member" in capsys.readouterr().err

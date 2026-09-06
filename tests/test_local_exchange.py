from __future__ import annotations

import json
from pathlib import Path

import pytest

from centinelas.route.local_exchange import (
    InvalidEnvelopeError,
    LocalCollisionError,
    build_envelope,
    canonical_json_bytes,
    stage_envelope,
    verify_envelope_file,
)


def test_stage_and_retry_are_logically_idempotent_across_timestamps(tmp_path: Path) -> None:
    first = stage_envelope(
        target_repository="moneysweep-pr",
        event_type="centinelas-signal-v1",
        idempotency_key="centinelas:item-1:moneysweep-pr:stable",
        payload={"item_id": "item-1", "labels": ["FINANCIAL"]},
        exchange_root=tmp_path,
        created_at_utc="2026-09-06T01:00:00Z",
    )
    retry = stage_envelope(
        target_repository="moneysweep-pr",
        event_type="centinelas-signal-v1",
        idempotency_key="centinelas:item-1:moneysweep-pr:stable",
        payload={"labels": ["FINANCIAL"], "item_id": "item-1"},
        exchange_root=tmp_path,
        created_at_utc="2026-09-06T02:00:00Z",
    )

    assert first.state == "STAGED"
    assert retry.state == "DUPLICATE"
    assert retry.envelope == first.envelope
    assert retry.path == first.path
    assert retry.sha256 == first.sha256
    assert verify_envelope_file(first.path) == first.envelope


def test_changed_payload_under_same_idempotency_key_fails_closed(tmp_path: Path) -> None:
    kwargs = {
        "target_repository": "moneysweep-pr",
        "event_type": "centinelas-signal-v1",
        "idempotency_key": "centinelas:item-2:moneysweep-pr:stable",
        "exchange_root": tmp_path,
    }
    first = stage_envelope(payload={"amount": 10}, **kwargs)

    with pytest.raises(LocalCollisionError, match="idempotency key"):
        stage_envelope(payload={"amount": 11}, **kwargs)

    outbox = tmp_path / "outbox" / "Jotaele44__moneysweep-pr"
    assert list(outbox.rglob("*.json")) == [first.path]


def test_payload_tampering_is_detected(tmp_path: Path) -> None:
    staged = stage_envelope(
        target_repository="thehub-pr",
        event_type="centinelas-signal-v1",
        idempotency_key="centinelas:item-3:thehub-pr:stable",
        payload={"value": 1},
        exchange_root=tmp_path,
    )
    envelope = json.loads(staged.path.read_text(encoding="utf-8"))
    envelope["payload"]["value"] = 2
    staged.path.write_text(json.dumps(envelope), encoding="utf-8")

    with pytest.raises(InvalidEnvelopeError):
        verify_envelope_file(staged.path)


def test_duplicate_json_keys_are_rejected(tmp_path: Path) -> None:
    staged = stage_envelope(
        target_repository="thehub-pr",
        event_type="centinelas-signal-v1",
        idempotency_key="centinelas:item-4:thehub-pr:stable",
        payload={"value": 1},
        exchange_root=tmp_path,
    )
    raw = staged.path.read_text(encoding="utf-8")
    staged.path.write_text(
        raw.replace('{"created_at_utc"', '{"message_id":"bad","created_at_utc"'),
        encoding="utf-8",
    )

    with pytest.raises(InvalidEnvelopeError, match="duplicate JSON key"):
        verify_envelope_file(staged.path)


def test_unknown_repository_and_path_components_fail_closed() -> None:
    with pytest.raises(InvalidEnvelopeError, match="allowlist"):
        build_envelope(
            target_repository="outside-pr",
            event_type="signal",
            idempotency_key="key-1",
            payload={},
        )
    with pytest.raises(InvalidEnvelopeError, match="event_type"):
        build_envelope(
            target_repository="thehub-pr",
            event_type="../signal",
            idempotency_key="key-1",
            payload={},
        )


def test_envelope_file_uses_exact_canonical_bytes(tmp_path: Path) -> None:
    staged = stage_envelope(
        target_repository="thehub-pr",
        event_type="centinelas-signal-v1",
        idempotency_key="centinelas:item-5:thehub-pr:stable",
        payload={"z": 1, "a": 2},
        exchange_root=tmp_path,
    )
    assert staged.path.read_bytes() == canonical_json_bytes(staged.envelope)


def test_symlinked_exchange_directory_is_rejected(tmp_path: Path) -> None:
    if not hasattr(Path, "symlink_to"):
        pytest.skip("symbolic links unavailable")
    real = tmp_path / "real"
    real.mkdir()
    exchange = tmp_path / "exchange"
    try:
        exchange.symlink_to(real, target_is_directory=True)
    except OSError:
        pytest.skip("symbolic links unavailable in this environment")

    with pytest.raises(LocalCollisionError, match="regular directory"):
        stage_envelope(
            target_repository="thehub-pr",
            event_type="centinelas-signal-v1",
            idempotency_key="centinelas:item-6:thehub-pr:stable",
            payload={},
            exchange_root=exchange,
        )

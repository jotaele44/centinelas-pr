from __future__ import annotations

import base64
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from centinelas.classify.labels import DomainLabel
from centinelas.models import ClassifiedItem
from centinelas.route import dispatch as dispatch_mod
from centinelas.route.local_exchange import LocalExchangeError, canonical_json_bytes


def _item() -> ClassifiedItem:
    now = datetime(2026, 9, 6, tzinfo=timezone.utc)
    return ClassifiedItem(
        item_id="local-first-fixture",
        source_url="https://example.test/award",
        source_name="fixture",
        title="Agency awards infrastructure contract",
        body_text="The public contract was awarded after procurement review.",
        published_at=now,
        captured_at=now,
        labels=[DomainLabel.FINANCIAL],
        confidence=0.90,
        classifier_reasoning="fixture",
    )


def _configure(tmp_path: Path, monkeypatch) -> Path:
    exchange = tmp_path / "exchange"
    dispatch_mod._DATA_DIR = tmp_path / "state"
    dispatch_mod._REPOS_BASE = tmp_path / "repos"
    monkeypatch.setenv("CENTINELAS_EXCHANGE_ROOT", str(exchange))
    monkeypatch.setenv("CENTINELAS_ENABLE_LEGACY_INTAKE_MIRROR", "0")
    monkeypatch.delenv("CENTINELAS_ENABLE_GITHUB_MIRROR", raising=False)
    monkeypatch.delenv("FEDERATION_DISPATCH_TOKEN", raising=False)
    monkeypatch.delenv("CENTINELAS_GITHUB_TOKEN", raising=False)
    return exchange


def test_default_dispatch_never_calls_github_even_when_token_exists(
    tmp_path: Path, monkeypatch
) -> None:
    exchange = _configure(tmp_path, monkeypatch)
    monkeypatch.setenv("FEDERATION_DISPATCH_TOKEN", "configured-but-not-authority")
    monkeypatch.setattr(
        dispatch_mod,
        "_repository_dispatch",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("GitHub mirror was not explicitly enabled")
        ),
    )

    record = dispatch_mod.dispatch(_item())

    assert record.status == "ok"
    assert record.authority == "local_exchange"
    assert record.local_envelopes
    assert list((exchange / "outbox").rglob("*.json"))
    assert all("github:" not in state for state in record.mirror_states.values())


def test_enabled_github_mirror_contains_exact_canonical_envelope_bytes(
    tmp_path: Path, monkeypatch
) -> None:
    _configure(tmp_path, monkeypatch)
    monkeypatch.setenv("CENTINELAS_ENABLE_GITHUB_MIRROR", "1")
    monkeypatch.setenv("FEDERATION_DISPATCH_TOKEN", "test-token")
    observed: list[tuple[str, dict, str]] = []

    def capture(target: str, body: dict, token: str) -> int:
        observed.append((target, body, token))
        return 204

    monkeypatch.setattr(dispatch_mod, "_repository_dispatch", capture)
    record = dispatch_mod.dispatch(_item())

    assert record.status == "ok"
    assert observed
    for target, body, token in observed:
        assert token == "test-token"
        assert body["event_type"] == "centinelas-envelope-mirror"
        payload = body["client_payload"]
        exact_bytes = base64.b64decode(payload["envelope_b64"], validate=True)
        assert hashlib.sha256(exact_bytes).hexdigest() == payload["envelope_sha256"]
        envelope = json.loads(exact_bytes)
        assert exact_bytes == canonical_json_bytes(envelope)
        assert envelope["message_id"] == payload["message_id"]
        assert envelope["message_id"] == record.local_envelopes[target]
        assert envelope["target_repository"].endswith(f"/{target}")


def test_hosted_mirror_failure_does_not_displace_local_success(
    tmp_path: Path, monkeypatch
) -> None:
    exchange = _configure(tmp_path, monkeypatch)
    monkeypatch.setenv("CENTINELAS_ENABLE_GITHUB_MIRROR", "1")
    monkeypatch.setenv("FEDERATION_DISPATCH_TOKEN", "test-token")
    monkeypatch.setattr(
        dispatch_mod,
        "_repository_dispatch",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("network denied")),
    )

    record = dispatch_mod.dispatch(_item())

    assert record.status == "ok"
    assert record.local_envelopes
    assert list((exchange / "outbox").rglob("*.json"))
    assert all("github:failed:OSError" in state for state in record.mirror_states.values())


def test_local_stage_failure_prevents_all_mirrors(tmp_path: Path, monkeypatch) -> None:
    _configure(tmp_path, monkeypatch)
    monkeypatch.setenv("CENTINELAS_ENABLE_GITHUB_MIRROR", "1")
    monkeypatch.setenv("FEDERATION_DISPATCH_TOKEN", "test-token")
    monkeypatch.setenv("CENTINELAS_ENABLE_LEGACY_INTAKE_MIRROR", "1")
    monkeypatch.setattr(
        dispatch_mod,
        "stage_envelope",
        lambda **_kwargs: (_ for _ in ()).throw(LocalExchangeError("fail closed")),
    )
    monkeypatch.setattr(
        dispatch_mod,
        "_repository_dispatch",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("hosted mirror ran before local authority")
        ),
    )
    monkeypatch.setattr(
        dispatch_mod,
        "_write_legacy_mirror",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("legacy mirror ran before local authority")
        ),
    )

    record = dispatch_mod.dispatch(_item())

    assert record.status == "failed"
    assert record.dispatched_to == []
    assert record.local_envelopes == {}
    assert record.mirror_states == {}


def test_manual_handoff_api_contract_can_be_local_only_with_token_present(
    tmp_path: Path, monkeypatch
) -> None:
    _configure(tmp_path, monkeypatch)
    monkeypatch.setenv("FEDERATION_DISPATCH_TOKEN", "configured-token")
    monkeypatch.setattr(
        dispatch_mod,
        "_repository_dispatch",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("explicit hosted_mirror=False was ignored")
        ),
    )

    receipt = dispatch_mod.dispatch_to_targets(
        _item(),
        ["moneysweep-pr"],
        hosted_mirror=False,
        legacy_mirror=False,
    )

    assert receipt["status"] == "local_staged"
    assert receipt["authority"] == "local_exchange"
    assert receipt["hosted_mirror_failures"] == 0
    assert receipt["attempts"][0]["hosted_mirror"] == "not_requested"


def test_dry_run_builds_identity_without_writing(tmp_path: Path, monkeypatch) -> None:
    exchange = _configure(tmp_path, monkeypatch)
    record = dispatch_mod.dispatch(_item(), dry_run=True)

    assert record.status == "ok"
    assert record.local_envelopes
    assert not exchange.exists()

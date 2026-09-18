from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "record_handoff_ack.py"
SPEC = importlib.util.spec_from_file_location("record_handoff_ack", SCRIPT)
assert SPEC and SPEC.loader
observer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(observer)


def _ack(**overrides):
    value = {
        "item_id": "signal-17",
        "target": "moneysweep-pr",
        "idempotency_key": "centinelas-signal-17-moneysweep-pr",
        "status": "acknowledged",
        "duplicate": False,
    }
    value.update(overrides)
    return value


def test_valid_ack_is_audit_only_not_certified() -> None:
    observation = observer.build_observation(
        _ack(), github_run_id="12345", github_run_attempt="2"
    )
    assert observation["observation_class"] == "NONCANONICAL_HOSTED_ACK_OBSERVATION"
    assert observation["certified"] is False
    assert observation["certification_state"] == "AUDIT_ONLY"
    assert len(observation["acknowledgment_sha256"]) == 64
    assert len(observation["delivery_manifestation_id"]) == 64


def test_ack_field_set_is_exact() -> None:
    with pytest.raises(observer.AckObservationError, match="fields mismatch"):
        observer.validate_ack(_ack(extra="unexpected"))
    value = _ack()
    del value["duplicate"]
    with pytest.raises(observer.AckObservationError, match="fields mismatch"):
        observer.validate_ack(value)


def test_ack_target_is_bounded() -> None:
    with pytest.raises(observer.AckObservationError, match="unsupported"):
        observer.validate_ack(_ack(target="thehub-pr"))


def test_ack_status_and_duplicate_types_fail_closed() -> None:
    with pytest.raises(observer.AckObservationError, match="status"):
        observer.validate_ack(_ack(status="processed"))
    with pytest.raises(observer.AckObservationError, match="boolean"):
        observer.validate_ack(_ack(duplicate=1))


def test_observation_write_is_idempotent(tmp_path: Path) -> None:
    observation = observer.build_observation(
        _ack(), github_run_id="12345", github_run_attempt="2"
    )
    first = observer.write_observation(tmp_path, observation)
    second = observer.write_observation(tmp_path, observation)
    assert first == second
    assert json.loads(first.read_text(encoding="utf-8")) == observation


def test_conflicting_existing_observation_fails_closed(tmp_path: Path) -> None:
    observation = observer.build_observation(
        _ack(), github_run_id="12345", github_run_attempt="2"
    )
    path = tmp_path / f"{observation['delivery_manifestation_id']}.json"
    path.write_text("{}\n", encoding="utf-8")
    with pytest.raises(observer.AckObservationError, match="collision"):
        observer.write_observation(tmp_path, observation)

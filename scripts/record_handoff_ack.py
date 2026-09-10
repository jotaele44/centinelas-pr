#!/usr/bin/env python3
"""Validate a legacy hosted handoff acknowledgment as a noncanonical observation.

This script does not create a Federation processing receipt. Canonical receipts
must be written by a local consumer after it commits the referenced envelope.
The hosted callback is retained only as a bounded transport observation.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Mapping

ACK_FIELDS = frozenset(
    {"item_id", "target", "idempotency_key", "status", "duplicate"}
)
ALLOWED_TARGETS = frozenset(
    {"aguayluz-pr", "moneysweep-pr", "skywatcher-pr", "spiderweb-pr"}
)
_COMPONENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$")
SCHEMA_VERSION = "centinelas.hosted-handoff-ack-observation.v1"


class AckObservationError(ValueError):
    """Raised when a hosted acknowledgment cannot be retained safely."""


def canonical_json_bytes(value: object) -> bytes:
    try:
        return (
            json.dumps(
                value,
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise AckObservationError(f"value is not canonical JSON: {exc}") from exc


def _component(value: object, field: str) -> str:
    if not isinstance(value, str) or not _COMPONENT.fullmatch(value):
        raise AckObservationError(f"{field} is not a valid component")
    return value


def validate_ack(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise AckObservationError("acknowledgment must be a JSON object")
    fields = frozenset(value)
    if fields != ACK_FIELDS:
        raise AckObservationError(
            "acknowledgment fields mismatch: "
            f"missing={sorted(ACK_FIELDS - fields)} extra={sorted(fields - ACK_FIELDS)}"
        )
    item_id = _component(value["item_id"], "item_id")
    target = _component(value["target"], "target")
    if target not in ALLOWED_TARGETS:
        raise AckObservationError(f"unsupported acknowledgment target: {target}")
    key = _component(value["idempotency_key"], "idempotency_key")
    status = _component(value["status"], "status")
    if status != "acknowledged":
        raise AckObservationError("status must equal 'acknowledged'")
    duplicate = value["duplicate"]
    if not isinstance(duplicate, bool):
        raise AckObservationError("duplicate must be a boolean")
    return {
        "item_id": item_id,
        "target": target,
        "idempotency_key": key,
        "status": status,
        "duplicate": duplicate,
    }


def build_observation(
    acknowledgment: object,
    *,
    github_run_id: str,
    github_run_attempt: str,
) -> dict[str, Any]:
    ack = validate_ack(acknowledgment)
    run_id = _component(github_run_id, "github_run_id")
    run_attempt = _component(github_run_attempt, "github_run_attempt")
    ack_bytes = canonical_json_bytes(ack)
    ack_sha256 = hashlib.sha256(ack_bytes).hexdigest()
    manifestation_id = hashlib.sha256(
        ack_sha256.encode("ascii")
        + b"\0"
        + run_id.encode("ascii")
        + b"\0"
        + run_attempt.encode("ascii")
    ).hexdigest()
    return {
        "schema_version": SCHEMA_VERSION,
        "observation_class": "NONCANONICAL_HOSTED_ACK_OBSERVATION",
        "acknowledgment_sha256": ack_sha256,
        "delivery_manifestation_id": manifestation_id,
        "github_run_id": run_id,
        "github_run_attempt": run_attempt,
        "acknowledgment": ack,
        "certified": False,
        "certification_state": "AUDIT_ONLY",
    }


def write_observation(output_directory: Path, observation: Mapping[str, Any]) -> Path:
    output_directory.mkdir(parents=True, exist_ok=True)
    manifestation_id = observation.get("delivery_manifestation_id")
    if not isinstance(manifestation_id, str) or not re.fullmatch(
        r"[0-9a-f]{64}", manifestation_id
    ):
        raise AckObservationError("delivery_manifestation_id is invalid")
    path = output_directory / f"{manifestation_id}.json"
    data = canonical_json_bytes(observation)
    if path.exists():
        if path.is_symlink() or not path.is_file() or path.read_bytes() != data:
            raise AckObservationError(f"hosted observation collision at {path}")
        return path

    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", dir=output_directory
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return path


def main() -> int:
    raw = os.environ.get("CENTINELAS_ACK")
    if raw is None:
        raise SystemExit("CENTINELAS_ACK is required")
    try:
        acknowledgment = json.loads(raw)
        observation = build_observation(
            acknowledgment,
            github_run_id=os.environ.get("GITHUB_RUN_ID", "unknown-run"),
            github_run_attempt=os.environ.get("GITHUB_RUN_ATTEMPT", "1"),
        )
        path = write_observation(
            Path(
                os.environ.get(
                    "CENTINELAS_ACK_OUTPUT_DIR",
                    "reports/hosted-handoff-ack-observations",
                )
            ),
            observation,
        )
    except (AckObservationError, json.JSONDecodeError, OSError) as exc:
        raise SystemExit(str(exc)) from exc
    print(path.as_posix())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

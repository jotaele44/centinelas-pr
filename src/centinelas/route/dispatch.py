"""Local-first Centinelas routing and operator handoff.

The canonical operation is an immutable local artifact emission. Hosted delivery
is implemented separately as an optional exact-byte mirror of that committed
file; this module performs no network access and requires no hosted credential.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from jsonschema import ValidationError as SchemaValidationError
from jsonschema import validate
from prii_export_utils import ArtifactTransportError, canonical_json_bytes, emit_message

from centinelas.models import ClassifiedItem, DispatchRecord
from centinelas.route.router import route

log = logging.getLogger(__name__)

_DATA_DIR = Path(os.environ.get("CENTINELAS_DATA_DIR", ".centinelas"))
_DEFAULT_ROUTE_MIN_CONFIDENCE = 0.55
HANDOFF_TARGETS = frozenset(
    {"spiderweb-pr", "aguayluz-pr", "moneysweep-pr", "skywatcher-pr"}
)
_CONTRACT_DIR = Path(__file__).parent / "contracts"
_SOURCE = "centinelas-pr"
_KIND = "centinelas-signal"


def _route_min_confidence() -> float:
    """Read the route gate at call time so tests and operators can override it."""

    try:
        return float(
            os.environ.get(
                "CENTINELAS_ROUTE_MIN_CONFIDENCE", _DEFAULT_ROUTE_MIN_CONFIDENCE
            )
        )
    except ValueError:
        return _DEFAULT_ROUTE_MIN_CONFIDENCE


def _exchange_root() -> Path:
    configured = os.environ.get("CENTINELAS_EXCHANGE_ROOT")
    return Path(configured) if configured else _DATA_DIR / "exchange"


def _idempotency_key(item_id: str, target: str, payload: dict) -> str:
    """Derive one bounded key from the full deterministic logical payload."""

    digest = hashlib.sha256(
        item_id.encode("utf-8")
        + b"\0"
        + target.encode("utf-8")
        + b"\0"
        + canonical_json_bytes(payload)
    ).hexdigest()
    return f"centinelas-{digest}"


def _stage_payload(item_id: str, target: str, payload: dict):
    """Validate target bindings and atomically emit one canonical envelope."""

    if payload.get("item_id") != item_id:
        raise ValueError("payload item_id does not match dispatch identity")
    if payload.get("routed_to") != target:
        raise ValueError("payload routed_to does not match dispatch target")
    key = _idempotency_key(item_id, target, payload)
    result = emit_message(
        _exchange_root(),
        source=_SOURCE,
        target=target,
        kind=_KIND,
        idempotency_key=key,
        payload=payload,
    )
    return result, key


def _dispatched_record_path(item_id: str) -> Path:
    return _DATA_DIR / "dispatched" / f"{item_id}.json"


def _persist_dispatch_record(record: DispatchRecord) -> None:
    """Persist Centinelas-local bookkeeping, including dry runs and failures."""

    path = _dispatched_record_path(record.item_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(record.model_dump_json(indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def dispatch(item: ClassifiedItem, dry_run: bool = False) -> DispatchRecord:
    """Route an item and commit each target envelope to the local outbox.

    `dry_run` reports the complete target plan without creating cross-repository
    artifacts. A successful non-dry result means local authority exists; it says
    nothing about optional hosted mirror delivery or downstream consumption.
    """

    threshold = _route_min_confidence()
    if item.confidence < threshold:
        log.info(
            "Skipping %s: confidence %.2f < route minimum %.2f",
            item.item_id,
            item.confidence,
            threshold,
        )
        record = DispatchRecord(
            item_id=item.item_id,
            dispatched_to=[],
            dispatched_at=datetime.now(timezone.utc),
            status="skipped",
            error=f"confidence {item.confidence:.2f} < route minimum {threshold:.2f}",
        )
        _persist_dispatch_record(record)
        return record

    payloads = route(item)
    dispatched_to: list[str] = []
    errors: list[str] = []

    for target, payload in payloads.items():
        if dry_run:
            log.info("[dry-run] would stage %s -> %s", item.item_id, target)
            dispatched_to.append(target)
            continue
        try:
            result, _key = _stage_payload(item.item_id, target, payload)
            dispatched_to.append(target)
            log.info(
                "Local artifact %s for %s -> %s (%s)",
                result.message_id,
                item.item_id,
                target,
                result.status,
            )
        except (ArtifactTransportError, OSError, ValueError) as exc:
            log.error("Local artifact failed for %s -> %s: %s", item.item_id, target, exc)
            errors.append(f"{target}: {exc}")

    record = DispatchRecord(
        item_id=item.item_id,
        dispatched_to=dispatched_to,
        dispatched_at=datetime.now(timezone.utc),
        status="failed" if errors else "ok",
        error="; ".join(errors) if errors else None,
    )
    _persist_dispatch_record(record)
    return record


def dispatch_many(
    items: list[ClassifiedItem], dry_run: bool = False
) -> list[DispatchRecord]:
    return [dispatch(item, dry_run=dry_run) for item in items]


def dispatch_to_targets(
    item: ClassifiedItem,
    targets: list[str],
    *,
    dry_run: bool = False,
) -> dict:
    """Stage an operator-selected handoff into the canonical local outbox.

    Each target payload is contract-validated before emission. Hosted delivery is
    deliberately absent; `scripts/emit_dispatches.py` can optionally mirror the
    exact committed envelope later.
    """

    from centinelas.route.router import build_payload

    requested = list(dict.fromkeys(targets))
    invalid = [target for target in requested if target not in HANDOFF_TARGETS]
    if invalid:
        raise ValueError(f"unsupported handoff target(s): {', '.join(invalid)}")
    if not requested:
        raise ValueError("at least one handoff target is required")

    attempts: list[dict] = []
    for target in requested:
        attempted_at = datetime.now(timezone.utc).isoformat()
        payload = build_payload(item, target)
        contract_path = _CONTRACT_DIR / f"{target.removesuffix('-pr')}.schema.json"
        try:
            contract = json.loads(contract_path.read_text(encoding="utf-8"))
            validate(instance=payload, schema=contract)
        except (OSError, json.JSONDecodeError, SchemaValidationError) as exc:
            attempts.append(
                {
                    "target": target,
                    "status": "failed",
                    "attempted_at": attempted_at,
                    "error": f"contract validation failed: {exc}",
                }
            )
            continue

        key = _idempotency_key(item.item_id, target, payload)
        if dry_run:
            attempts.append(
                {
                    "target": target,
                    "status": "dry_run",
                    "attempted_at": attempted_at,
                    "idempotency_key": key,
                }
            )
            continue

        try:
            result, observed_key = _stage_payload(item.item_id, target, payload)
            attempts.append(
                {
                    "target": target,
                    "status": "staged_local",
                    "attempted_at": attempted_at,
                    "transport_status": result.status,
                    "message_id": result.message_id,
                    "output_path": str(result.path),
                    "idempotency_key": observed_key,
                }
            )
        except (ArtifactTransportError, OSError, ValueError) as exc:
            log.exception("Local handoff failed for %s -> %s", item.item_id, target)
            attempts.append(
                {
                    "target": target,
                    "status": "failed",
                    "attempted_at": attempted_at,
                    "error": str(exc),
                    "idempotency_key": key,
                }
            )

    succeeded = sum(
        attempt["status"] in {"staged_local", "dry_run"} for attempt in attempts
    )
    return {
        "item_id": item.item_id,
        "status": (
            "staged_local"
            if succeeded == len(attempts)
            else ("partial" if succeeded else "failed")
        ),
        "dry_run": dry_run,
        "attempts": attempts,
    }

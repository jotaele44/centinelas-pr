"""Local-first dispatch with optional legacy and GitHub mirrors."""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jsonschema import ValidationError, validate

from centinelas.models import ClassifiedItem, DispatchRecord
from centinelas.route.local_exchange import (
    LocalExchangeError,
    build_envelope,
    canonical_json_bytes,
    exchange_root_from_env,
    sha256_bytes,
    stage_envelope,
)
from centinelas.route.router import route

log = logging.getLogger(__name__)

_REPOS_BASE = Path(os.environ.get("CENTINELAS_REPOS_DIR", str(Path.home() / "Developer")))
_DATA_DIR = Path(os.environ.get("CENTINELAS_DATA_DIR", ".centinelas"))

# Minimum classifier confidence for an item to be routed/exported. Below this the
# item is skipped (not dispatched to any repo) — the gate that keeps low-confidence
# noise out of downstream event pipelines.
_DEFAULT_ROUTE_MIN_CONFIDENCE = 0.55
HANDOFF_TARGETS = frozenset(
    {
        "spiderweb-pr",
        "aguayluz-pr",
        "moneysweep-pr",
        "ovnis-pr",
        "skywatcher-pr",
    }
)
_CONTRACT_DIR = Path(__file__).parent / "contracts"
_GITHUB_API = "https://api.github.com"
_LOCAL_EVENT_TYPE = "centinelas-signal-v1"
_HOSTED_EVENT_TYPE = "centinelas-envelope-mirror"


def _env_flag(name: str, *, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off", ""}:
        return False
    raise ValueError(f"{name} must be a boolean flag, got {raw!r}")


def _idempotency_key(item_id: str, target: str, payload: dict[str, Any]) -> str:
    digest = hashlib.sha256(
        canonical_json_bytes(
            {
                "item_id": item_id,
                "target": target,
                "payload": payload,
            }
        )
    ).hexdigest()
    return f"centinelas:{item_id}:{target}:{digest[:20]}"


def _hosted_mirror_body(envelope: dict[str, Any]) -> dict[str, Any]:
    """Wrap exact canonical bytes; hosted JSON serialization cannot mint identity."""

    envelope_bytes = canonical_json_bytes(envelope)
    return {
        "event_type": _HOSTED_EVENT_TYPE,
        "client_payload": {
            "message_id": envelope["message_id"],
            "source_repository": envelope["source_repository"],
            "target_repository": envelope["target_repository"],
            "envelope_sha256": sha256_bytes(envelope_bytes),
            "envelope_b64": base64.b64encode(envelope_bytes).decode("ascii"),
        },
    }


def _repository_dispatch(target: str, body: dict[str, Any], token: str) -> int:
    owner = os.environ.get("CENTINELAS_GITHUB_OWNER", "jotaele44")
    request = urllib.request.Request(
        f"{_GITHUB_API}/repos/{owner}/{target}/dispatches",
        data=canonical_json_bytes(body),
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        return response.status


def _route_min_confidence() -> float:
    """Read the route confidence gate at call time so tests/CI can override it."""

    try:
        return float(
            os.environ.get("CENTINELAS_ROUTE_MIN_CONFIDENCE", _DEFAULT_ROUTE_MIN_CONFIDENCE)
        )
    except ValueError:
        return _DEFAULT_ROUTE_MIN_CONFIDENCE


def _repo_intake_dir(repo_name: str) -> Path:
    """Return the explicitly non-authoritative compatibility mirror directory."""

    outbound = os.environ.get("CENTINELAS_OUTBOUND_DIR")
    if outbound:
        return Path(outbound) / repo_name
    return _REPOS_BASE / repo_name / "intake"


def _legacy_mirror_enabled() -> bool:
    # Transitional default remains enabled until downstream consumers migrate.
    # Local staging always happens first and is the only identity authority.
    return _env_flag("CENTINELAS_ENABLE_LEGACY_INTAKE_MIRROR", default=True)


def _github_mirror_enabled() -> bool:
    return _env_flag("CENTINELAS_ENABLE_GITHUB_MIRROR", default=False)


def _write_legacy_mirror(path: Path, payload: dict[str, Any]) -> str:
    """Write canonical payload bytes after local staging, never before it."""

    data = canonical_json_bytes(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.is_symlink() or not path.is_file():
            raise RuntimeError(f"legacy mirror path is not a regular file: {path}")
        if path.read_bytes() != data:
            raise RuntimeError(f"legacy mirror collision at {path}")
        return "duplicate"
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("xb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        if path.exists():
            if path.read_bytes() != data:
                raise RuntimeError(f"legacy mirror collision at {path}")
            return "duplicate"
        os.replace(temporary, path)
        return "written"
    finally:
        temporary.unlink(missing_ok=True)


def _mirror_to_github(target: str, envelope: dict[str, Any]) -> str:
    token = os.environ.get("FEDERATION_DISPATCH_TOKEN") or os.environ.get(
        "CENTINELAS_GITHUB_TOKEN"
    )
    if not token:
        raise RuntimeError(
            "FEDERATION_DISPATCH_TOKEN or CENTINELAS_GITHUB_TOKEN is required "
            "only when CENTINELAS_ENABLE_GITHUB_MIRROR is enabled"
        )
    status = _repository_dispatch(target, _hosted_mirror_body(envelope), token)
    return f"pending_ack:{status}"


def _dispatched_record_path(item_id: str) -> Path:
    return _DATA_DIR / "dispatched" / f"{item_id}.json"


def _persist_dispatch_record(record: DispatchRecord) -> None:
    """Persist Centinelas local bookkeeping, including mirror diagnostics."""

    path = _dispatched_record_path(record.item_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(record.model_dump_json(indent=2), encoding="utf-8")


def _validate_target_payload(target: str, payload: dict[str, Any]) -> None:
    contract_path = _CONTRACT_DIR / f"{target.removesuffix('-pr')}.schema.json"
    try:
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
        validate(instance=payload, schema=contract)
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        raise ValueError(f"contract validation failed for {target}: {exc}") from exc


def dispatch(item: ClassifiedItem, dry_run: bool = False) -> DispatchRecord:
    """Stage routed payloads locally, then create explicitly secondary mirrors.

    The legacy intake mirror remains enabled during the Centinelas-first migration
    so downstream repositories continue to receive their existing files.  The
    local envelope is always created first; a mirror can neither mint nor replace
    its message identity.
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
    local_envelopes: dict[str, str] = {}
    mirror_states: dict[str, str] = {}
    errors: list[str] = []

    for target, payload in payloads.items():
        key = _idempotency_key(item.item_id, target, payload)
        if dry_run:
            envelope = build_envelope(
                target_repository=target,
                event_type=_LOCAL_EVENT_TYPE,
                idempotency_key=key,
                payload=payload,
            )
            local_envelopes[target] = envelope["message_id"]
            mirror_states[target] = "dry_run"
            dispatched_to.append(target)
            continue

        try:
            staged = stage_envelope(
                target_repository=target,
                event_type=_LOCAL_EVENT_TYPE,
                idempotency_key=key,
                payload=payload,
                exchange_root=exchange_root_from_env(),
            )
        except (LocalExchangeError, OSError, ValueError) as exc:
            log.error("Local authority failed for %s → %s: %s", item.item_id, target, exc)
            errors.append(f"{target}: {type(exc).__name__}: {exc}")
            continue

        local_envelopes[target] = staged.envelope["message_id"]
        dispatched_to.append(target)
        states = [f"local:{staged.state.lower()}"]

        if _legacy_mirror_enabled():
            try:
                mirror_path = _repo_intake_dir(target) / f"{item.item_id}.json"
                states.append(f"legacy:{_write_legacy_mirror(mirror_path, payload)}")
            except Exception as exc:
                log.warning(
                    "Non-authoritative legacy mirror failed for %s → %s: %s",
                    item.item_id,
                    target,
                    type(exc).__name__,
                )
                states.append(f"legacy:failed:{type(exc).__name__}")

        if _github_mirror_enabled():
            try:
                states.append(f"github:{_mirror_to_github(target, staged.envelope)}")
            except Exception as exc:
                log.warning(
                    "Non-authoritative GitHub mirror failed for %s → %s: %s",
                    item.item_id,
                    target,
                    type(exc).__name__,
                )
                states.append(f"github:failed:{type(exc).__name__}")

        mirror_states[target] = ";".join(states)

    record = DispatchRecord(
        item_id=item.item_id,
        dispatched_to=dispatched_to,
        dispatched_at=datetime.now(timezone.utc),
        status="failed" if errors else "ok",
        error="; ".join(errors) if errors else None,
        local_envelopes=local_envelopes,
        mirror_states=mirror_states,
    )
    _persist_dispatch_record(record)
    return record


def dispatch_many(items: list[ClassifiedItem], dry_run: bool = False) -> list[DispatchRecord]:
    return [dispatch(item, dry_run=dry_run) for item in items]


def dispatch_to_targets(
    item: ClassifiedItem,
    targets: list[str],
    *,
    dry_run: bool = False,
    hosted_mirror: bool | None = None,
    legacy_mirror: bool | None = None,
) -> dict[str, Any]:
    """Stage one item for explicit targets and optionally mirror it.

    ``hosted_mirror`` defaults to the explicit environment flag.  For temporary
    direct-call compatibility only, a configured dispatch token also opts in when
    the parameter is omitted.  The API passes an explicit boolean and therefore
    defaults to local-only behavior.
    """

    from centinelas.route.router import build_payload

    requested = list(dict.fromkeys(targets))
    invalid = [target for target in requested if target not in HANDOFF_TARGETS]
    if invalid:
        raise ValueError(f"unsupported handoff target(s): {', '.join(invalid)}")
    if not requested:
        raise ValueError("at least one handoff target is required")

    if hosted_mirror is None:
        hosted_mirror = _github_mirror_enabled() or bool(
            os.environ.get("FEDERATION_DISPATCH_TOKEN")
            or os.environ.get("CENTINELAS_GITHUB_TOKEN")
        )
    if legacy_mirror is None:
        legacy_mirror = _legacy_mirror_enabled()

    attempts: list[dict[str, Any]] = []
    for target in requested:
        attempted_at = datetime.now(timezone.utc).isoformat()
        payload = build_payload(item, target)
        try:
            _validate_target_payload(target, payload)
        except ValueError as exc:
            attempts.append(
                {
                    "target": target,
                    "status": "failed",
                    "attempted_at": attempted_at,
                    "error": str(exc),
                }
            )
            continue

        key = _idempotency_key(item.item_id, target, payload)
        if dry_run:
            envelope = build_envelope(
                target_repository=target,
                event_type=_LOCAL_EVENT_TYPE,
                idempotency_key=key,
                payload=payload,
            )
            attempts.append(
                {
                    "target": target,
                    "status": "dry_run",
                    "attempted_at": attempted_at,
                    "authority": "local_exchange",
                    "message_id": envelope["message_id"],
                    "idempotency_key": key,
                    "hosted_mirror": "dry_run" if hosted_mirror else "not_requested",
                    "legacy_mirror": "dry_run" if legacy_mirror else "not_requested",
                }
            )
            continue

        try:
            staged = stage_envelope(
                target_repository=target,
                event_type=_LOCAL_EVENT_TYPE,
                idempotency_key=key,
                payload=payload,
                exchange_root=exchange_root_from_env(),
            )
        except (LocalExchangeError, OSError, ValueError) as exc:
            attempts.append(
                {
                    "target": target,
                    "status": "failed",
                    "attempted_at": attempted_at,
                    "authority": "local_exchange",
                    "error": f"local stage failed: {type(exc).__name__}: {exc}",
                }
            )
            continue

        attempt: dict[str, Any] = {
            "target": target,
            "status": "local_duplicate" if staged.state == "DUPLICATE" else "local_staged",
            "attempted_at": attempted_at,
            "authority": "local_exchange",
            "message_id": staged.envelope["message_id"],
            "envelope_sha256": staged.sha256,
            "envelope_path": str(staged.path),
            "idempotency_key": key,
            "hosted_mirror": "not_requested",
            "legacy_mirror": "not_requested",
        }

        if legacy_mirror:
            try:
                out_path = _repo_intake_dir(target) / f"{item.item_id}.json"
                attempt["legacy_mirror"] = _write_legacy_mirror(out_path, payload)
                attempt["legacy_output_path"] = str(out_path)
            except Exception as exc:
                attempt["legacy_mirror"] = f"failed:{type(exc).__name__}"

        if hosted_mirror:
            try:
                attempt["hosted_mirror"] = _mirror_to_github(target, staged.envelope)
            except Exception as exc:
                log.exception("Hosted mirror failed for %s → %s", item.item_id, target)
                attempt["hosted_mirror"] = f"failed:{type(exc).__name__}"

        attempts.append(attempt)

    local_success = sum(
        attempt["status"] in {"local_staged", "local_duplicate", "dry_run"}
        for attempt in attempts
    )
    hosted_failures = sum(
        str(attempt.get("hosted_mirror", "")).startswith("failed:")
        for attempt in attempts
    )
    return {
        "item_id": item.item_id,
        "status": (
            "local_staged"
            if local_success == len(attempts)
            else ("partial" if local_success else "failed")
        ),
        "authority": "local_exchange",
        "dry_run": dry_run,
        "local_successes": local_success,
        "hosted_mirror_failures": hosted_failures,
        "attempts": attempts,
    }

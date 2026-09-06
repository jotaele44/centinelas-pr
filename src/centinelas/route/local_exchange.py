"""Immutable, standard-library local artifact authority for Centinelas.

This producer adapter implements the envelope boundary required by the stacked
Federation freedom work while that shared package remains under independent
review.  GitHub delivery is deliberately absent from this module: a hosted
bridge may mirror the exact stored bytes only after :func:`stage_envelope`
succeeds.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

ENVELOPE_SCHEMA_VERSION = "prii.local-artifact-envelope.v1"
SOURCE_REPOSITORY = "Jotaele44/centinelas-pr"
FEDERATION_REPOSITORIES = frozenset(
    {
        "Jotaele44/aguayluz-pr",
        "Jotaele44/centinelas-pr",
        "Jotaele44/moneysweep-pr",
        "Jotaele44/ovnis-pr",
        "Jotaele44/skywatcher-pr",
        "Jotaele44/spiderweb-pr",
        "Jotaele44/thehub-pr",
    }
)
_SHORT_TO_FULL = {
    repository.split("/", 1)[1]: repository for repository in FEDERATION_REPOSITORIES
}
_COMPONENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_IDEMPOTENCY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_ENVELOPE_FIELDS = frozenset(
    {
        "schema_version",
        "message_id",
        "source_repository",
        "target_repository",
        "event_type",
        "idempotency_key",
        "created_at_utc",
        "payload_sha256",
        "payload",
    }
)


class LocalExchangeError(RuntimeError):
    """Base exception for local authority failures."""


class InvalidEnvelopeError(LocalExchangeError):
    """Raised when an envelope or its path/hash bindings are invalid."""


class LocalCollisionError(LocalExchangeError):
    """Raised when an immutable identity is already bound to different bytes."""


@dataclass(frozen=True)
class StageResult:
    envelope: dict[str, Any]
    path: Path
    state: str
    byte_size: int
    sha256: str


def canonical_json_bytes(value: Any) -> bytes:
    """Return the one canonical JSON serialization used for byte identity."""

    try:
        text = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as exc:
        raise InvalidEnvelopeError(f"value is not canonical JSON: {exc}") from exc
    return text.encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _require_utc(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise InvalidEnvelopeError(f"{field} must be an RFC3339 UTC string ending in Z")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise InvalidEnvelopeError(f"{field} must be a valid RFC3339 timestamp") from exc
    if parsed.utcoffset() != timedelta(0):
        raise InvalidEnvelopeError(f"{field} must use UTC")
    return value


def _require_component(value: Any, field: str) -> str:
    if not isinstance(value, str) or not _COMPONENT.fullmatch(value):
        raise InvalidEnvelopeError(f"{field} is not a safe canonical component")
    return value


def _require_idempotency_key(value: Any) -> str:
    if not isinstance(value, str) or not _IDEMPOTENCY.fullmatch(value):
        raise InvalidEnvelopeError("idempotency_key is not a safe canonical key")
    return value


def canonical_repository(value: Any, field: str = "repository") -> str:
    if not isinstance(value, str):
        raise InvalidEnvelopeError(f"{field} must be a string")
    repository = _SHORT_TO_FULL.get(value, value)
    if repository not in FEDERATION_REPOSITORIES:
        raise InvalidEnvelopeError(f"{field} is outside the Federation allowlist")
    return repository


def _identity_document(
    *,
    source_repository: str,
    target_repository: str,
    event_type: str,
    idempotency_key: str,
    payload_sha256: str,
) -> dict[str, str]:
    return {
        "schema_version": ENVELOPE_SCHEMA_VERSION,
        "source_repository": source_repository,
        "target_repository": target_repository,
        "event_type": event_type,
        "idempotency_key": idempotency_key,
        "payload_sha256": payload_sha256,
    }


def build_envelope(
    *,
    target_repository: str,
    event_type: str,
    idempotency_key: str,
    payload: Any,
    created_at_utc: str | None = None,
) -> dict[str, Any]:
    """Build a validated envelope without writing it."""

    target = canonical_repository(target_repository, "target_repository")
    event = _require_component(event_type, "event_type")
    key = _require_idempotency_key(idempotency_key)
    payload_sha256 = sha256_bytes(canonical_json_bytes(payload))
    identity = _identity_document(
        source_repository=SOURCE_REPOSITORY,
        target_repository=target,
        event_type=event,
        idempotency_key=key,
        payload_sha256=payload_sha256,
    )
    envelope: dict[str, Any] = {
        **identity,
        "message_id": sha256_bytes(canonical_json_bytes(identity)),
        "created_at_utc": created_at_utc or utc_now(),
        "payload": payload,
    }
    validate_envelope(envelope)
    return envelope


def _exact_fields(value: Mapping[str, Any]) -> None:
    observed = frozenset(value)
    if observed != _ENVELOPE_FIELDS:
        raise InvalidEnvelopeError(
            "envelope fields mismatch: "
            f"missing={sorted(_ENVELOPE_FIELDS - observed)} "
            f"extra={sorted(observed - _ENVELOPE_FIELDS)}"
        )


def validate_envelope(value: Mapping[str, Any]) -> None:
    """Recompute every identity and fail closed on any disagreement."""

    if not isinstance(value, Mapping):
        raise InvalidEnvelopeError("envelope must be a JSON object")
    _exact_fields(value)
    if value["schema_version"] != ENVELOPE_SCHEMA_VERSION:
        raise InvalidEnvelopeError("unsupported envelope schema_version")
    message_id = value["message_id"]
    if not isinstance(message_id, str) or not _SHA256.fullmatch(message_id):
        raise InvalidEnvelopeError("message_id must be a lowercase SHA-256 digest")
    source = canonical_repository(value["source_repository"], "source_repository")
    if source != SOURCE_REPOSITORY:
        raise InvalidEnvelopeError("source_repository is not Centinelas")
    target = canonical_repository(value["target_repository"], "target_repository")
    event = _require_component(value["event_type"], "event_type")
    key = _require_idempotency_key(value["idempotency_key"])
    _require_utc(value["created_at_utc"], "created_at_utc")
    declared_payload_sha256 = value["payload_sha256"]
    if not isinstance(declared_payload_sha256, str) or not _SHA256.fullmatch(
        declared_payload_sha256
    ):
        raise InvalidEnvelopeError("payload_sha256 must be a lowercase SHA-256 digest")
    observed_payload_sha256 = sha256_bytes(canonical_json_bytes(value["payload"]))
    if observed_payload_sha256 != declared_payload_sha256:
        raise InvalidEnvelopeError("payload_sha256 does not match canonical payload")
    expected_id = sha256_bytes(
        canonical_json_bytes(
            _identity_document(
                source_repository=source,
                target_repository=target,
                event_type=event,
                idempotency_key=key,
                payload_sha256=observed_payload_sha256,
            )
        )
    )
    if expected_id != message_id:
        raise InvalidEnvelopeError("message_id does not match canonical identity")


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise InvalidEnvelopeError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def verify_envelope_file(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise InvalidEnvelopeError(f"cannot read envelope {path}: {exc}") from exc
    try:
        value = json.loads(raw, object_pairs_hook=_reject_duplicate_keys)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise InvalidEnvelopeError(f"envelope is not canonical UTF-8 JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise InvalidEnvelopeError("envelope must be a JSON object")
    validate_envelope(value)
    if raw != canonical_json_bytes(value):
        raise InvalidEnvelopeError("envelope bytes are not canonical JSON")
    return value


def exchange_root_from_env() -> Path:
    return Path(os.environ.get("CENTINELAS_EXCHANGE_ROOT", ".federation/exchange"))


def _repository_key(repository: str) -> str:
    return repository.replace("/", "__")


def _ensure_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    current = path
    while True:
        if current.is_symlink() or not current.is_dir():
            raise LocalCollisionError(f"exchange directory is not a regular directory: {current}")
        if current == current.parent:
            break
        current = current.parent
        if current.exists() and current == path.anchor:
            break


def _fsync_directory(path: Path) -> None:
    try:
        descriptor = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)


def _immutable_write(path: Path, data: bytes) -> str:
    _ensure_directory(path.parent)
    if path.exists() or path.is_symlink():
        if path.is_symlink() or not path.is_file():
            raise LocalCollisionError(f"immutable path is not a regular file: {path}")
        if path.read_bytes() != data:
            raise LocalCollisionError(f"immutable byte collision at {path}")
        return "DUPLICATE"

    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            if path.is_symlink() or not path.is_file() or path.read_bytes() != data:
                raise LocalCollisionError(f"concurrent immutable collision at {path}")
            return "DUPLICATE"
        except OSError:
            # Cross-platform fallback: create the destination exclusively, never replace.
            try:
                destination_fd = os.open(
                    path,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                    0o600,
                )
            except FileExistsError:
                if path.is_symlink() or not path.is_file() or path.read_bytes() != data:
                    raise LocalCollisionError(f"concurrent immutable collision at {path}")
                return "DUPLICATE"
            with os.fdopen(destination_fd, "wb") as destination:
                destination.write(data)
                destination.flush()
                os.fsync(destination.fileno())
        _fsync_directory(path.parent)
        return "STAGED"
    finally:
        temporary.unlink(missing_ok=True)


def stage_envelope(
    *,
    target_repository: str,
    event_type: str,
    idempotency_key: str,
    payload: Any,
    exchange_root: Path | None = None,
    created_at_utc: str | None = None,
) -> StageResult:
    """Atomically stage one authoritative local outbox envelope."""

    envelope = build_envelope(
        target_repository=target_repository,
        event_type=event_type,
        idempotency_key=idempotency_key,
        payload=payload,
        created_at_utc=created_at_utc,
    )
    root = exchange_root or exchange_root_from_env()
    target_key = _repository_key(envelope["target_repository"])
    path = (
        root
        / "outbox"
        / target_key
        / envelope["event_type"]
        / f"{envelope['message_id']}.json"
    )
    data = canonical_json_bytes(envelope)
    state = _immutable_write(path, data)
    verify_envelope_file(path)
    return StageResult(
        envelope=envelope,
        path=path,
        state=state,
        byte_size=len(data),
        sha256=sha256_bytes(data),
    )

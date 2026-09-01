"""Embedded Centinelas satellite-observations producer (Phase 0-1)."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .routing import _validate_embedded_lead

LOGICAL_PRODUCER = "centinelas-space-observations"
PRODUCER_REPO = "centinelas-pr"
CONTRACT_VERSION = "1.0.0"
PRODUCER_MODULE = "src/centinelas/space_observations/producer.py"
ACQUISITION_FIELDS = frozenset(
    {
        "schema_version",
        "acquisition_id",
        "lead_id",
        "lead_sha256",
        "idempotency_key",
        "source_id",
        "source_url",
        "phase",
        "network_acquisition_performed",
        "status",
        "external_storage_root",
        "created_at",
        "analytic_boundaries",
        "synthetic",
    }
)
STREAM_SCHEMA = {
    "sources": "federation_source.schema.json",
    "entities": "federation_entity.schema.json",
    "relationships": "federation_relationship.schema.json",
    "observations": "federation_observation.schema.json",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _record_sha256(value: Any) -> str:
    return _sha256_bytes(_canonical_json_bytes(value))


def _stable_id(prefix: str, *parts: Any) -> str:
    material = "|".join(str(part) for part in parts)
    return f"{prefix}_{_sha256_bytes(material.encode())[:32]}"


def _append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSONL at {path}:{line_number}: {exc}") from exc
        if not isinstance(row, dict):
            raise ValueError(f"JSONL row at {path}:{line_number} must be an object")
        rows.append(row)
    return rows


class _DedupLedger:
    def __init__(self, path: Path):
        self.path = path
        self.index: dict[str, str] = {}
        for row in _read_jsonl(path):
            if row.get("disposition") == "accepted":
                key = row["idempotency_key"]
                acquisition_id = row["acquisition_id"]
                existing = self.index.get(key)
                if existing and existing != acquisition_id:
                    raise ValueError(f"conflicting dedup bindings for idempotency key {key}")
                self.index[key] = acquisition_id

    def lookup(self, key: str) -> str | None:
        return self.index.get(key)

    def accept(self, key: str, acquisition_id: str, lead_id: str) -> None:
        self.index[key] = acquisition_id
        _append_jsonl(
            self.path,
            {
                "idempotency_key": key,
                "acquisition_id": acquisition_id,
                "lead_id": lead_id,
                "disposition": "accepted",
                "recorded_at": _utc_now(),
            },
        )

    def duplicate(self, key: str, acquisition_id: str, lead_id: str) -> None:
        _append_jsonl(
            self.path,
            {
                "idempotency_key": key,
                "acquisition_id": acquisition_id,
                "lead_id": lead_id,
                "disposition": "duplicate",
                "recorded_at": _utc_now(),
            },
        )


class _AcquisitionStore:
    def __init__(self, path: Path):
        self.path = path
        self.index: dict[str, dict[str, Any]] = {}
        for row in _read_jsonl(path):
            _validate_acquisition(row)
            key = row["idempotency_key"]
            existing = self.index.get(key)
            if existing:
                qualifier = (
                    "duplicate"
                    if existing["acquisition_id"] == row["acquisition_id"]
                    else "conflicting"
                )
                raise ValueError(f"{qualifier} acquisitions for idempotency key {key}")
            self.index[key] = row

    def lookup(self, key: str) -> dict[str, Any] | None:
        return self.index.get(key)

    def append(self, row: dict[str, Any]) -> None:
        _validate_acquisition(row)
        key = row["idempotency_key"]
        if key in self.index:
            raise ValueError(f"acquisition already exists for idempotency key {key}")
        _append_jsonl(self.path, row)
        self.index[key] = row


class _JsonlLedger:
    def __init__(self, path: Path):
        self.path = path

    def record(self, row: dict[str, Any]) -> None:
        _append_jsonl(self.path, {**row, "recorded_at": row.get("recorded_at") or _utc_now()})


@dataclass
class _RunAccounting:
    input_count: int = 0
    accepted: int = 0
    duplicate: int = 0
    rejected: int = 0
    failed: int = 0

    def assert_complete(self) -> None:
        if self.input_count != self.accepted + self.duplicate + self.rejected + self.failed:
            raise AssertionError("run accounting does not reconcile")

    def persist(self, ledger: _JsonlLedger, run_id: str) -> None:
        self.assert_complete()
        ledger.record({"run_id": run_id, **asdict(self)})


class _LeadValidationError(ValueError):
    def __init__(self, reason_code: str, message: str):
        super().__init__(message)
        self.reason_code = reason_code


def _validate_intake_lead(lead: dict[str, Any], *, production: bool) -> None:
    route = lead.get("downstream_route")
    if not isinstance(route, dict) or (
        route.get("primary") != LOGICAL_PRODUCER
        or route.get("repository") != PRODUCER_REPO
        or route.get("case_authority") != "ovnis-pr"
        or route.get("correlation_target") != "thehub-pr"
    ):
        raise _LeadValidationError("ROUTE_MISMATCH", "invalid embedded producer route")
    if lead.get("review_status") not in {"qualified", "routed"}:
        raise _LeadValidationError("UNQUALIFIED_LEAD", "lead is not qualified")
    try:
        _validate_embedded_lead(lead)
    except ValueError as exc:
        raise _LeadValidationError("INVALID_SCHEMA", str(exc)) from exc
    if production and lead["synthetic"]:
        raise _LeadValidationError("INVALID_SCHEMA", "synthetic lead rejected in production")


@dataclass(frozen=True)
class IntakeResult:
    disposition: str
    acknowledgement: dict[str, Any]
    acquisition: dict[str, Any] | None


class IntakeEngine:
    """Network-disabled, restart-safe Phase 0-1 intake engine."""

    def __init__(self, root: str | Path, *, production: bool = False):
        self.root = Path(root)
        self.production = production
        self.evidence_root = Path(
            os.environ.get("CENTINELAS_EVIDENCE_ROOT", self.root / "external_evidence")
        )
        ledgers = self.root / "data" / "space_observations" / "ledgers"
        acquisition_path = (
            self.root / "data" / "space_observations" / "metadata" / "acquisitions.jsonl"
        )
        self.intake = _JsonlLedger(ledgers / "intake.jsonl")
        self.dedup = _DedupLedger(ledgers / "dedup.jsonl")
        self.acquisitions = _AcquisitionStore(acquisition_path)
        self.failures = _JsonlLedger(ledgers / "failures.jsonl")
        self.health = _JsonlLedger(ledgers / "source_health.jsonl")
        self.acks = _JsonlLedger(ledgers / "routing_acks.jsonl")
        self.runs = _JsonlLedger(ledgers / "runs.jsonl")

    def _ack(
        self,
        lead: dict[str, Any],
        lead_sha: str,
        disposition: str,
        reason: str,
        acquisition_id: str | None,
    ) -> dict[str, Any]:
        core = {
            "lead_id": lead.get("lead_id", "unknown"),
            "lead_sha256": lead_sha,
            "receiver": LOGICAL_PRODUCER,
            "received_at": _utc_now(),
            "disposition": disposition,
            "reason_code": reason,
            "acquisition_id": acquisition_id,
            "idempotency_key": lead.get("dedup_key"),
        }
        return {
            "ack_id": _stable_id("ack", lead_sha, disposition, reason),
            **core,
            "receipt_sha256": _record_sha256(core),
        }

    def process(self, lead: dict[str, Any], *, run_id: str) -> IntakeResult:
        lead_sha = _record_sha256(lead)
        self.intake.record({"run_id": run_id, "lead_sha256": lead_sha, "lead": lead})
        try:
            _validate_intake_lead(lead, production=self.production)
            key = lead["dedup_key"]
            dedup_acquisition_id = self.dedup.lookup(key)
            persisted_acquisition = self.acquisitions.lookup(key)
            if dedup_acquisition_id and persisted_acquisition is None:
                raise RuntimeError(
                    "dedup ledger references an acquisition missing from persistent metadata"
                )
            if persisted_acquisition and dedup_acquisition_id not in {
                None,
                persisted_acquisition["acquisition_id"],
            }:
                raise RuntimeError("dedup and acquisition ledgers disagree on acquisition identity")
            if persisted_acquisition:
                existing = persisted_acquisition["acquisition_id"]
                if dedup_acquisition_id is None:
                    self.dedup.accept(key, existing, lead["lead_id"])
                self.dedup.duplicate(key, existing, lead["lead_id"])
                ack = self._ack(lead, lead_sha, "duplicate", "ALREADY_REGISTERED", existing)
                self.acks.record(ack)
                return IntakeResult("duplicate", ack, None)

            acquisition_id = _stable_id("acq", lead_sha, key)
            acquisition = {
                "schema_version": "1.0.0",
                "acquisition_id": acquisition_id,
                "lead_id": lead["lead_id"],
                "lead_sha256": lead_sha,
                "idempotency_key": key,
                "source_id": lead["source_id"],
                "source_url": lead["canonical_url"],
                "phase": "intake_only",
                "network_acquisition_performed": False,
                "status": "registered",
                "external_storage_root": str(self.evidence_root),
                "created_at": _utc_now(),
                "analytic_boundaries": {
                    "uap_confirmation_prohibited": True,
                    "classified_capability_inference_prohibited": True,
                    "negative_inference_prohibited": True,
                    "correlation_owner": "thehub-pr",
                },
                "synthetic": lead["synthetic"],
            }
            self.acquisitions.append(acquisition)
            self.dedup.accept(key, acquisition_id, lead["lead_id"])
            ack = self._ack(lead, lead_sha, "accepted", "ACCEPTED_FOR_ACQUISITION", acquisition_id)
            self.acks.record(ack)
            self.health.record(
                {"source_id": lead["source_id"], "status": "accepted", "success": True}
            )
            return IntakeResult("accepted", ack, acquisition)
        except _LeadValidationError as exc:
            ack = self._ack(lead, lead_sha, "rejected", exc.reason_code, None)
            self.acks.record(ack)
            self.failures.record(
                {
                    "run_id": run_id,
                    "lead_id": lead.get("lead_id"),
                    "failure_class": exc.reason_code,
                    "detail": str(exc),
                    "retryable": False,
                }
            )
            return IntakeResult("rejected", ack, None)
        except Exception as exc:
            ack = self._ack(lead, lead_sha, "failed", "INTAKE_INTERNAL_ERROR", None)
            self.acks.record(ack)
            self.failures.record(
                {
                    "run_id": run_id,
                    "lead_id": lead.get("lead_id"),
                    "failure_class": "INTAKE_INTERNAL_ERROR",
                    "detail": str(exc),
                    "retryable": True,
                }
            )
            return IntakeResult("failed", ack, None)

    def process_many(self, leads: list[dict[str, Any]], *, run_id: str) -> list[IntakeResult]:
        accounting = _RunAccounting(input_count=len(leads))
        results: list[IntakeResult] = []
        for lead in leads:
            result = self.process(lead, run_id=run_id)
            results.append(result)
            setattr(accounting, result.disposition, getattr(accounting, result.disposition) + 1)
        accounting.persist(self.runs, run_id)
        return results


def _validate_acquisition(acquisition: dict[str, Any]) -> None:
    missing = sorted(ACQUISITION_FIELDS - acquisition.keys())
    unexpected = sorted(acquisition.keys() - ACQUISITION_FIELDS)
    if missing or unexpected:
        raise ValueError(
            "acquisition fields do not match the frozen schema: "
            f"missing={missing} unexpected={unexpected}"
        )
    if acquisition["schema_version"] != "1.0.0":
        raise ValueError("unsupported acquisition schema version")
    acquisition_id = acquisition["acquisition_id"]
    if not (
        isinstance(acquisition_id, str)
        and acquisition_id.startswith("acq_")
        and len(acquisition_id) == 36
        and all(character in "0123456789abcdef" for character in acquisition_id[4:])
    ):
        raise ValueError("invalid acquisition ID")
    for field in ("lead_sha256", "idempotency_key"):
        value = acquisition[field]
        if not (
            isinstance(value, str)
            and len(value) == 64
            and all(character in "0123456789abcdef" for character in value)
        ):
            raise ValueError(f"invalid acquisition {field}")
    if acquisition["phase"] != "intake_only" or acquisition["status"] != "registered":
        raise ValueError("unsupported acquisition state")
    if acquisition["network_acquisition_performed"] is not False:
        raise ValueError("Phase 0-1 acquisitions cannot claim network acquisition")
    if not isinstance(acquisition["synthetic"], bool):
        raise ValueError("acquisition synthetic flag must be a boolean")


def _lineage() -> dict[str, Any]:
    return {
        "producer_script": PRODUCER_MODULE,
        "producer_phase": "INTAKE",
        "source_inputs": ["data/space_observations/metadata/acquisitions.jsonl"],
        "extraction_method": "validated_acquisition_projection",
    }


def _build_streams(
    acquisitions: list[dict[str, Any]], *, mode: str, extracted_at: str
) -> dict[str, list[dict[str, Any]]]:
    if not acquisitions:
        raise ValueError("space-observation export rejects an empty acquisition ledger")
    if mode not in {"test", "production"}:
        raise ValueError(f"unsupported export mode: {mode}")

    sources: dict[str, dict[str, Any]] = {}
    source_selection: dict[str, tuple[str, str]] = {}
    entities: dict[str, dict[str, Any]] = {}
    observations: dict[str, dict[str, Any]] = {}
    lineage = _lineage()

    for acquisition in sorted(acquisitions, key=lambda row: str(row.get("acquisition_id", ""))):
        _validate_acquisition(acquisition)
        synthetic = acquisition["synthetic"]
        if mode == "production" and synthetic:
            raise ValueError("production export rejects synthetic acquisitions")

        source_id = _stable_id("src", acquisition["source_id"])
        entity_id = _stable_id("ent", "acquisition", acquisition["acquisition_id"])
        observation_id = _stable_id("obs", "intake", acquisition["acquisition_id"])
        source_row = {
            "source_id": source_id,
            "source_type": "space_data_lead_source",
            "source_name": acquisition["source_id"],
            "source_ref": acquisition["source_url"],
            "confidence": 1.0,
            "lineage": lineage,
            "synthetic": synthetic,
            "created_at": acquisition["created_at"],
            "extracted_at": extracted_at,
        }
        existing_source = sources.get(source_id)
        stable_fields = ("source_type", "source_name", "source_ref", "synthetic")
        if existing_source is not None and any(
            existing_source[field] != source_row[field] for field in stable_fields
        ):
            raise ValueError(f"conflicting source manifestations for {acquisition['source_id']}")
        selection_key = (acquisition["created_at"], acquisition["acquisition_id"])
        if existing_source is None or selection_key > source_selection[source_id]:
            sources[source_id] = source_row
            source_selection[source_id] = selection_key

        if entity_id in entities or observation_id in observations:
            raise ValueError(
                f"duplicate acquisition identity in export: {acquisition['acquisition_id']}"
            )
        entities[entity_id] = {
            "entity_id": entity_id,
            "source_id": source_id,
            "name": acquisition["acquisition_id"],
            "normalized_name": acquisition["acquisition_id"],
            "entity_type": "satellite_acquisition",
            "jurisdiction": "UNRESOLVED",
            "confidence": 1.0,
            "lineage": lineage,
            "synthetic": synthetic,
            "created_at": acquisition["created_at"],
            "extracted_at": extracted_at,
        }
        observations[observation_id] = {
            "observation_id": observation_id,
            "entity_id": entity_id,
            "source_id": source_id,
            "observation_type": "satellite_acquisition_registered",
            "observed_at": acquisition["created_at"],
            "attributes": {
                "lead_id": acquisition["lead_id"],
                "lead_sha256": acquisition["lead_sha256"],
                "idempotency_key": acquisition["idempotency_key"],
                "network_acquisition_performed": False,
                "analytic_boundaries": acquisition["analytic_boundaries"],
            },
            "confidence": 1.0,
            "lineage": lineage,
            "synthetic": synthetic,
            "created_at": acquisition["created_at"],
            "extracted_at": extracted_at,
        }

    return {
        "sources": list(sources.values()),
        "entities": list(entities.values()),
        "relationships": [],
        "observations": list(observations.values()),
    }


def _write_package(
    streams: dict[str, list[dict[str, Any]]],
    out: Path,
    *,
    mode: str,
    created_at: str,
) -> dict[str, Any]:
    out.mkdir(parents=True, exist_ok=True)
    files: list[dict[str, Any]] = []
    for stream in ("sources", "entities", "relationships", "observations"):
        path = out / f"{stream}.jsonl"
        rows = streams[stream]
        if not rows:
            path.unlink(missing_ok=True)
            continue
        emitted = "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows).encode()
        path.write_bytes(emitted)
        files.append(
            {
                "filename": path.name,
                "stream": stream,
                "record_count": len(rows),
                "sha256": _sha256_bytes(emitted),
                "schema_id": STREAM_SCHEMA[stream],
            }
        )

    digest_material = (
        "|".join(f"{entry['filename']}:{entry['sha256']}" for entry in files) + f"|{mode}"
    )
    manifest = {
        "package_id": f"pkg_{_sha256_bytes(digest_material.encode())[:32]}",
        "producer": LOGICAL_PRODUCER,
        "export_contract_version": CONTRACT_VERSION,
        "mode": mode,
        "created_at": created_at,
        "extracted_at": created_at,
        "federation": {"producer_repo": PRODUCER_REPO, "hub_parent": "thehub-pr"},
        "files": files,
    }
    (out / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
    )
    return manifest


def export_federation(
    root: str | Path,
    out: str | Path,
    *,
    mode: str = "test",
    created_at: str | None = None,
) -> dict[str, Any]:
    """Export persisted acquisitions as a Hub-conformant federation package."""

    root_path = Path(root)
    timestamp = created_at or _utc_now()
    acquisitions = _read_jsonl(
        root_path / "data" / "space_observations" / "metadata" / "acquisitions.jsonl"
    )
    streams = _build_streams(acquisitions, mode=mode, extracted_at=timestamp)
    return _write_package(streams, Path(out), mode=mode, created_at=timestamp)

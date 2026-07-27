"""Embedded Centinelas satellite-observations producer (Phase 0-1)."""
from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

LOGICAL_PRODUCER = "centinelas-space-observations"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def record_sha256(value: Any) -> str:
    return sha256_bytes(canonical_json_bytes(value))


def stable_id(prefix: str, *parts: Any) -> str:
    material = "|".join(str(part) for part in parts)
    return f"{prefix}_{sha256_bytes(material.encode())[:32]}"


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


class DedupLedger:
    def __init__(self, path: Path):
        self.path = path
        self.index: dict[str, str] = {}
        for row in read_jsonl(path):
            if row.get("disposition") == "accepted":
                self.index[row["idempotency_key"]] = row["acquisition_id"]

    def lookup(self, key: str) -> str | None:
        return self.index.get(key)

    def accept(self, key: str, acquisition_id: str, lead_id: str) -> None:
        self.index[key] = acquisition_id
        append_jsonl(self.path, {"idempotency_key": key, "acquisition_id": acquisition_id,
                                "lead_id": lead_id, "disposition": "accepted", "recorded_at": utc_now()})

    def duplicate(self, key: str, acquisition_id: str, lead_id: str) -> None:
        append_jsonl(self.path, {"idempotency_key": key, "acquisition_id": acquisition_id,
                                "lead_id": lead_id, "disposition": "duplicate", "recorded_at": utc_now()})


class JsonlLedger:
    def __init__(self, path: Path):
        self.path = path

    def record(self, row: dict[str, Any]) -> None:
        append_jsonl(self.path, {**row, "recorded_at": row.get("recorded_at") or utc_now()})


@dataclass
class RunAccounting:
    input_count: int = 0
    accepted: int = 0
    duplicate: int = 0
    rejected: int = 0
    failed: int = 0

    def assert_complete(self) -> None:
        if self.input_count != self.accepted + self.duplicate + self.rejected + self.failed:
            raise AssertionError("run accounting does not reconcile")

    def persist(self, ledger: JsonlLedger, run_id: str) -> None:
        self.assert_complete()
        ledger.record({"run_id": run_id, **asdict(self)})


LEAD_ID = re.compile(r"^CENT-SPACE-[0-9]{4}-[A-F0-9]{16}$")
HASH = re.compile(r"^[a-f0-9]{64}$")
FORBIDDEN_ASSERTION = re.compile(
    r"\b(confirm(?:s|ed|ation)?|proves?|verified uap|alien craft|definitive uap|"
    r"sensor detected the (?:uap|object)|no detection proves)\b", re.I,
)


class LeadValidationError(ValueError):
    def __init__(self, reason_code: str, message: str):
        super().__init__(message)
        self.reason_code = reason_code


def validate_lead(lead: dict[str, Any], *, production: bool) -> None:
    required = {"schema_version", "lead_id", "category", "subcategory", "source_id", "source_url",
                "canonical_url", "discovered_at", "title", "discovery_provenance", "access_status",
                "temporal_coverage", "geographic_coverage", "sensor", "potential_case_links",
                "downstream_route", "evidence_tier", "confidence_score", "review_status",
                "content_fingerprint", "dedup_key", "raw_binary_storage_prohibited",
                "confirmation_claim_prohibited", "analyst_assertion", "negative_inference"}
    missing = sorted(required - lead.keys())
    if missing:
        raise LeadValidationError("INVALID_SCHEMA", f"missing required fields: {missing}")
    if lead["schema_version"] != "1.0.0" or not LEAD_ID.fullmatch(str(lead["lead_id"])):
        raise LeadValidationError("INVALID_SCHEMA", "invalid schema version or lead id")
    if lead["category"] != "SPACE_AND_REMOTE_SENSING":
        raise LeadValidationError("OUT_OF_SCOPE", "lead is outside the space-data category")
    if lead["review_status"] not in {"qualified", "routed"}:
        raise LeadValidationError("UNQUALIFIED_LEAD", "lead is not qualified")
    route = lead.get("downstream_route") or {}
    if route.get("primary") != LOGICAL_PRODUCER or route.get("correlation_target") != "thehub-pr":
        raise LeadValidationError("ROUTE_MISMATCH", "invalid downstream route")
    if lead.get("raw_binary_storage_prohibited") is not True:
        raise LeadValidationError("INVALID_SCHEMA", "raw-binary boundary missing")
    if lead.get("confirmation_claim_prohibited") is not True:
        raise LeadValidationError("INVALID_SCHEMA", "confirmation boundary missing")
    if lead.get("negative_inference") is not False:
        raise LeadValidationError("INVALID_SCHEMA", "negative inference prohibited")
    assertion = lead.get("analyst_assertion")
    if assertion and FORBIDDEN_ASSERTION.search(str(assertion)):
        raise LeadValidationError("INVALID_SCHEMA", "producer-level confirmation language prohibited")
    for field in ("content_fingerprint", "dedup_key"):
        if not HASH.fullmatch(str(lead.get(field, ""))):
            raise LeadValidationError("INVALID_SCHEMA", f"invalid {field}")
    for link in lead.get("potential_case_links") or []:
        if link.get("producer") != "ovnis-pr" or link.get("not_a_confirmation") is not True:
            raise LeadValidationError("INVALID_SCHEMA", "case references must remain ovnis-pr foreign references")
    sensor = lead.get("sensor") or {}
    infrared_claim = sensor.get("sensor_type") == "infrared_warning" and any(
        sensor.get(key) not in (None, False, "", [], {})
        for key in ("capability_known", "coverage_claim", "detection_claim", "sensitivity_claim")
    )
    if infrared_claim and (lead.get("evidence_tier") != "T1" or not sensor.get("capability_source_ref")):
        raise LeadValidationError("INVALID_SCHEMA", "unsupported DSP/infrared claim")
    if production and lead.get("synthetic") is True:
        raise LeadValidationError("INVALID_SCHEMA", "synthetic lead rejected in production")


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
        self.evidence_root = Path(os.environ.get("CENTINELAS_EVIDENCE_ROOT", self.root / "external_evidence"))
        ledgers = self.root / "data" / "space_observations" / "ledgers"
        self.intake = JsonlLedger(ledgers / "intake.jsonl")
        self.dedup = DedupLedger(ledgers / "dedup.jsonl")
        self.failures = JsonlLedger(ledgers / "failures.jsonl")
        self.health = JsonlLedger(ledgers / "source_health.jsonl")
        self.acks = JsonlLedger(ledgers / "routing_acks.jsonl")
        self.runs = JsonlLedger(ledgers / "runs.jsonl")

    def _ack(self, lead: dict[str, Any], lead_sha: str, disposition: str, reason: str,
             acquisition_id: str | None) -> dict[str, Any]:
        core = {"lead_id": lead.get("lead_id", "unknown"), "lead_sha256": lead_sha,
                "receiver": LOGICAL_PRODUCER, "received_at": utc_now(),
                "disposition": disposition, "reason_code": reason,
                "acquisition_id": acquisition_id, "idempotency_key": lead.get("dedup_key")}
        return {"ack_id": stable_id("ack", lead_sha, disposition, reason), **core,
                "receipt_sha256": record_sha256(core)}

    def process(self, lead: dict[str, Any], *, run_id: str) -> IntakeResult:
        lead_sha = record_sha256(lead)
        self.intake.record({"run_id": run_id, "lead_sha256": lead_sha, "lead": lead})
        try:
            validate_lead(lead, production=self.production)
            key = lead["dedup_key"]
            existing = self.dedup.lookup(key)
            if existing:
                self.dedup.duplicate(key, existing, lead["lead_id"])
                ack = self._ack(lead, lead_sha, "duplicate", "ALREADY_REGISTERED", existing)
                self.acks.record(ack)
                return IntakeResult("duplicate", ack, None)
            acquisition_id = stable_id("acq", lead_sha, key)
            acquisition = {"acquisition_id": acquisition_id, "lead_id": lead["lead_id"],
                           "lead_sha256": lead_sha, "source_id": lead["source_id"],
                           "source_url": lead["canonical_url"], "phase": "intake_only",
                           "network_acquisition_performed": False, "status": "registered",
                           "external_storage_root": str(self.evidence_root), "created_at": utc_now(),
                           "analytic_boundaries": {"uap_confirmation_prohibited": True,
                               "classified_capability_inference_prohibited": True,
                               "negative_inference_prohibited": True, "correlation_owner": "thehub-pr"}}
            JsonlLedger(self.root / "data" / "space_observations" / "metadata" / "acquisitions.jsonl").record(acquisition)
            self.dedup.accept(key, acquisition_id, lead["lead_id"])
            ack = self._ack(lead, lead_sha, "accepted", "ACCEPTED_FOR_ACQUISITION", acquisition_id)
            self.acks.record(ack)
            self.health.record({"source_id": lead["source_id"], "status": "accepted", "success": True})
            return IntakeResult("accepted", ack, acquisition)
        except LeadValidationError as exc:
            ack = self._ack(lead, lead_sha, "rejected", exc.reason_code, None)
            self.acks.record(ack)
            self.failures.record({"run_id": run_id, "lead_id": lead.get("lead_id"),
                                  "failure_class": exc.reason_code, "detail": str(exc), "retryable": False})
            return IntakeResult("rejected", ack, None)
        except Exception as exc:
            ack = self._ack(lead, lead_sha, "failed", "INTAKE_INTERNAL_ERROR", None)
            self.acks.record(ack)
            self.failures.record({"run_id": run_id, "lead_id": lead.get("lead_id"),
                                  "failure_class": "INTAKE_INTERNAL_ERROR", "detail": str(exc), "retryable": True})
            return IntakeResult("failed", ack, None)

    def process_many(self, leads: list[dict[str, Any]], *, run_id: str) -> list[IntakeResult]:
        accounting = RunAccounting(input_count=len(leads))
        results: list[IntakeResult] = []
        for lead in leads:
            result = self.process(lead, run_id=run_id)
            results.append(result)
            setattr(accounting, result.disposition, getattr(accounting, result.disposition) + 1)
        accounting.persist(self.runs, run_id)
        return results


def export_federation(root: str | Path, out: str | Path) -> dict[str, Any]:
    root, out = Path(root), Path(out)
    out.mkdir(parents=True, exist_ok=True)
    acquisitions = read_jsonl(root / "data" / "space_observations" / "metadata" / "acquisitions.jsonl")
    sources: dict[str, Any] = {}
    entities: dict[str, Any] = {}
    relationships: dict[str, Any] = {}
    observations: dict[str, Any] = {}
    for acq in acquisitions:
        source_id = stable_id("src", acq["source_id"])
        entity_id = stable_id("ent", "acquisition", acq["acquisition_id"])
        observation_id = stable_id("obs", "intake", acq["acquisition_id"])
        sources[source_id] = {"source_id": source_id, "source_type": "space_data_lead_source",
            "source_name": acq["source_id"], "source_ref": acq["source_url"], "confidence": 1.0,
            "lineage": {"producer_phase": "INTAKE"}, "synthetic": False,
            "created_at": acq["created_at"], "extracted_at": acq["created_at"]}
        entities[entity_id] = {"entity_id": entity_id, "source_id": source_id,
            "name": acq["acquisition_id"], "normalized_name": acq["acquisition_id"],
            "entity_type": "satellite_acquisition", "jurisdiction": "GLOBAL", "confidence": 1.0,
            "lineage": {"producer_phase": "INTAKE"}, "synthetic": False,
            "created_at": acq["created_at"], "extracted_at": acq["created_at"]}
        observations[observation_id] = {"observation_id": observation_id, "entity_id": entity_id,
            "source_id": source_id, "observation_type": "satellite_acquisition_registered",
            "observed_at": acq["created_at"], "attributes": {"lead_id": acq["lead_id"],
                "lead_sha256": acq["lead_sha256"], "network_acquisition_performed": False,
                "analytic_boundaries": acq["analytic_boundaries"]}, "confidence": 1.0,
            "lineage": {"producer_phase": "INTAKE"}, "synthetic": False,
            "created_at": acq["created_at"], "extracted_at": acq["created_at"]}
    streams = {"sources": list(sources.values()), "entities": list(entities.values()),
               "relationships": list(relationships.values()), "observations": list(observations.values())}
    files = []
    for name, rows in streams.items():
        path = out / f"{name}.jsonl"
        path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")
        files.append({"filename": path.name, "record_count": len(rows), "sha256": record_sha256(rows)})
    manifest = {"producer": LOGICAL_PRODUCER, "contract_version": "1.0.0", "mode": "production",
                "created_at": utc_now(), "files": files, "network_acquisition_performed": False}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return manifest

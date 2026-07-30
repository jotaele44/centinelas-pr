"""Deterministic, append-only water-disruption producer for shadow mode."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

TerminalOutcome = Literal[
    "success", "not_modified", "empty", "blocked", "rate_limited",
    "parse_failed", "transport_failed",
]

_EVENT_PATTERNS: list[tuple[str, tuple[str, ...]]] = [
    ("service_outage", ("sin agua", "interrupcion", "interrupción", "water outage", "no water service")),
    ("low_pressure", ("baja presion", "baja presión", "low pressure")),
    ("main_break", ("tuberia rota", "tubería rota", "averia", "avería", "main break", "water main")),
    ("boil_advisory", ("hervir el agua", "boil water", "boil-water")),
    ("restoration", ("restablecido", "restaurado", "servicio normal", "service restored", "restoration")),
    ("repair", ("reparacion", "reparación", "trabajos de reparacion", "repair work")),
]
_EXCLUSIONS = (
    "cisterna", "plomeria", "plomería", "private plumbing", "account shutoff",
    "corte por falta de pago", "building plumbing",
)


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256(value: Any) -> str:
    material = value if isinstance(value, str) else canonical_json(value)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def stable_id(prefix: str, value: Any, length: int = 24) -> str:
    return f"{prefix}-{sha256(value)[:length]}"


def six_hour_bucket(value: datetime) -> str:
    utc = value.astimezone(timezone.utc)
    return utc.replace(hour=(utc.hour // 6) * 6, minute=0, second=0, microsecond=0).isoformat()


@dataclass(frozen=True)
class SourceRecord:
    source_id: str
    name: str
    source_class: str
    evidence_tier: str
    authority_scope: str
    municipalities: tuple[str, ...]
    entrypoints: tuple[str, ...]
    enabled: bool = True


class AppendOnlyJsonl:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def append(self, stream: str, record: dict[str, Any]) -> str:
        persisted = dict(record)
        persisted.setdefault("recorded_at", datetime.now(timezone.utc).isoformat())
        persisted.setdefault("record_hash", sha256(persisted))
        path = self.root / f"{stream}.jsonl"
        with path.open("a", encoding="utf-8") as handle:
            handle.write(canonical_json(persisted) + "\n")
        return str(persisted["record_hash"])

    def read(self, stream: str) -> list[dict[str, Any]]:
        path = self.root / f"{stream}.jsonl"
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def by_key(self, stream: str, key: str, value: str) -> dict[str, Any] | None:
        return next((row for row in reversed(self.read(stream)) if str(row.get(key)) == value), None)


class WaterDisruptionProducer:
    def __init__(self, root: Path, sources: list[SourceRecord]) -> None:
        self.store = AppendOnlyJsonl(root)
        self.sources = {source.source_id: source for source in sources}
        self.shadow_mode = True

    def record_run(self, run_id: str, outcomes: dict[str, TerminalOutcome]) -> dict[str, Any]:
        enabled = {sid for sid, source in self.sources.items() if source.enabled}
        if set(outcomes) != enabled:
            missing = sorted(enabled - set(outcomes))
            extra = sorted(set(outcomes) - enabled)
            raise ValueError(f"incomplete_source_accounting:missing={missing}:extra={extra}")
        records = []
        for source_id in sorted(enabled):
            record = {"run_id": run_id, "source_id": source_id, "outcome": outcomes[source_id]}
            self.store.append("acquisition_attempts", record)
            records.append(record)
        return {"run_id": run_id, "enabled": len(enabled), "accounted": len(records), "coverage": 1.0}

    def capture_evidence(
        self,
        source_id: str,
        source_url: str,
        title: str,
        body_text: str,
        published_at: datetime,
        captured_at: datetime | None = None,
    ) -> dict[str, Any]:
        if source_id not in self.sources:
            raise ValueError("unknown_source")
        captured_at = captured_at or datetime.now(timezone.utc)
        content_hash = sha256({"title": title, "body_text": body_text})
        evidence_id = stable_id("EVD", {"source_id": source_id, "source_url": source_url, "published_at": published_at.isoformat(), "content_hash": content_hash})
        existing = self.store.by_key("raw_evidence", "evidence_id", evidence_id)
        if existing:
            return existing
        evidence = {
            "schema_version": "centinelas.water-evidence/v0.1",
            "evidence_id": evidence_id,
            "source_id": source_id,
            "source_url": source_url,
            "title": title,
            "body_text": body_text,
            "published_at": published_at.isoformat(),
            "captured_at": captured_at.isoformat(),
            "content_hash": content_hash,
            "append_only": True,
        }
        self.store.append("raw_evidence", evidence)
        return evidence

    @staticmethod
    def classify_text(title: str, body_text: str) -> tuple[str | None, list[str], bool]:
        folded = re.sub(r"\s+", " ", f"{title} {body_text}".lower())
        excluded = any(term in folded for term in _EXCLUSIONS)
        matches = [kind for kind, terms in _EVENT_PATTERNS if any(term in folded for term in terms)]
        if excluded or not matches:
            return None, matches, excluded
        priority = ["boil_advisory", "main_break", "service_outage", "low_pressure", "restoration", "repair"]
        return next(kind for kind in priority if kind in matches), matches, False

    def extract_candidate(
        self,
        evidence: dict[str, Any],
        municipalities: list[str] | None = None,
        asset_hint: str | None = None,
    ) -> dict[str, Any] | None:
        event_type, matches, excluded = self.classify_text(evidence["title"], evidence["body_text"])
        if excluded or event_type is None:
            return None
        source = self.sources[evidence["source_id"]]
        published = datetime.fromisoformat(evidence["published_at"])
        municipalities = sorted(set(municipalities or []))
        dedup_material = {
            "event_type": event_type,
            "municipalities": municipalities,
            "asset_hint": (asset_hint or "").strip().lower(),
            "bucket": six_hour_bucket(published),
        }
        dedup_key = stable_id("WDK", dedup_material)
        candidate_id = stable_id("WDC", {"dedup_key": dedup_key, "evidence_id": evidence["evidence_id"]})
        authority = 1.0 if source.evidence_tier == "T1" else 0.7 if source.evidence_tier == "T2" else 0.4
        location = 1.0 if municipalities else 0.25
        specificity = min(1.0, 0.35 + 0.15 * len(matches) + (0.2 if asset_hint else 0.0))
        freshness = 1.0
        overall = round(0.35 * authority + 0.25 * location + 0.25 * specificity + 0.15 * freshness, 4)
        candidate = {
            "schema_version": "centinelas.water-candidate/v0.1",
            "candidate_id": candidate_id,
            "truth_state": "candidate",
            "event_type": event_type,
            "municipalities": municipalities,
            "asset_hint": asset_hint,
            "dedup_key": dedup_key,
            "evidence_ids": [evidence["evidence_id"]],
            "source_ids": [evidence["source_id"]],
            "confidence": {
                "authority": authority,
                "location": location,
                "specificity": round(specificity, 4),
                "freshness": freshness,
                "overall": overall,
            },
            "review_state": "pending",
            "shadow_mode": True,
        }
        existing = self.store.by_key("candidate_review", "candidate_id", candidate_id)
        if existing:
            return existing
        self.store.append("candidate_review", candidate)
        return candidate

    def dispatch(self, candidate_id: str, idempotency_key: str) -> dict[str, Any]:
        candidate = self.store.by_key("candidate_review", "candidate_id", candidate_id)
        if not candidate:
            raise KeyError(candidate_id)
        if candidate.get("truth_state") != "candidate":
            raise ValueError("producer_truth_state_violation")
        prior = self.store.by_key("delivery_outbox", "idempotency_key", idempotency_key)
        if prior:
            return prior
        envelope = {
            "outbox_id": stable_id("OUT", {"candidate_id": candidate_id, "idempotency_key": idempotency_key}),
            "candidate_id": candidate_id,
            "idempotency_key": idempotency_key,
            "envelope_hash": sha256(candidate),
            "status": "shadow_queued",
            "notifications_enabled": False,
            "production_promotion_enabled": False,
            "payload": candidate,
        }
        self.store.append("delivery_outbox", envelope)
        return envelope

    def retract(self, candidate_id: str, reason: str, idempotency_key: str) -> dict[str, Any]:
        if not self.store.by_key("candidate_review", "candidate_id", candidate_id):
            raise KeyError(candidate_id)
        prior = self.store.by_key("retractions", "idempotency_key", idempotency_key)
        if prior:
            return prior
        event = {
            "retraction_id": stable_id("RET", {"candidate_id": candidate_id, "idempotency_key": idempotency_key}),
            "candidate_id": candidate_id,
            "idempotency_key": idempotency_key,
            "reason": reason,
            "destructive": False,
        }
        self.store.append("retractions", event)
        return event

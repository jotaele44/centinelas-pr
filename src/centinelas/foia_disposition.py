"""Auditable finding-level FOIA disposition and export routing."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, model_validator


class EvidenceTier(StrEnum):
    T1 = "T1"
    T2 = "T2"
    T3 = "T3"
    T4 = "T4"


class Destination(StrEnum):
    CENTINELAS = "centinelas"
    THEHUB_EVIDENCE = "thehub_evidence"
    THEHUB_INTELLIGENCE = "thehub_intelligence"
    OVNIS = "ovnis"
    SKYWATCHER = "skywatcher"
    AGUAYLUZ = "aguayluz"
    MONEYSWEEP = "moneysweep"
    SPIDERWEB = "spiderweb"
    ARCHIVE_ONLY = "archive_only"


class Disposition(StrEnum):
    EXPORT = "export"
    REVIEW = "review"
    REFERENCE_ONLY = "reference_only"
    HOLD_SENSITIVE = "hold_sensitive"
    ARCHIVE_ONLY = "archive_only"
    REJECT_DUPLICATE = "reject_duplicate"
    REJECT_IRRELEVANT = "reject_irrelevant"
    EXPORT_FAILED = "export_failed"
    SUPERSEDED = "superseded"


class ReceiptStatus(StrEnum):
    PENDING = "pending"
    ACKNOWLEDGED = "acknowledged"
    FAILED = "failed"
    SUPERSEDED = "superseded"


class PageCitation(BaseModel):
    document_id: str
    page: int = Field(ge=1)
    excerpt: str = Field(min_length=1)
    bbox: tuple[float, float, float, float] | None = None


class FOIARelease(BaseModel):
    release_id: str
    agency: str = Field(min_length=1)
    foia_case_number: str | None = None
    released_at: datetime | None = None
    acquired_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    source_url: str | None = None
    release_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    page_count: int = Field(ge=1)


class FOIADocument(BaseModel):
    document_id: str
    release_id: str
    filename: str
    mime_type: str
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    page_count: int = Field(ge=1)
    text_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    ocr_confidence: float | None = Field(default=None, ge=0, le=1)


class FOIAFinding(BaseModel):
    finding_id: str
    release_id: str
    document_id: str
    finding_type: str
    title: str
    summary: str
    citations: list[PageCitation] = Field(min_length=1)
    entities: list[str] = Field(default_factory=list)
    places: list[str] = Field(default_factory=list)
    event_dates: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    evidence_tier: EvidenceTier
    extraction_confidence: float = Field(ge=0, le=1)
    sensitive: bool = False
    entity_collision: bool = False

    @model_validator(mode="after")
    def citation_document_matches(self) -> "FOIAFinding":
        if any(c.document_id != self.document_id for c in self.citations):
            raise ValueError("all citations must reference finding.document_id")
        return self


class RoutingDecision(BaseModel):
    decision_id: str
    finding_id: str
    destination: Destination
    disposition: Disposition
    score: float = Field(ge=0, le=1)
    reason_codes: list[str] = Field(min_length=1)
    decided_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    reversible: bool = True
    supersedes_decision_id: str | None = None


class FederationEnvelope(BaseModel):
    schema_name: str = "prii.foia.finding"
    schema_version: str = "0.2.0"
    producer: str = "centinelas-pr"
    event_id: str
    idempotency_key: str
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    destination: Destination
    finding: FOIAFinding
    decision: RoutingDecision


class ExportReceipt(BaseModel):
    export_id: str
    finding_id: str
    destination: Destination
    idempotency_key: str
    status: ReceiptStatus
    attempts: int = Field(default=0, ge=0)
    downstream_record_id: str | None = None
    acknowledged_at: datetime | None = None
    last_attempt_at: datetime | None = None
    error: str | None = None


class ReviewCase(BaseModel):
    review_case_id: str
    finding_id: str
    reason_codes: list[str]
    proposed_decisions: list[RoutingDecision]
    status: str = "pending"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


ROUTE_TERMS: dict[Destination, set[str]] = {
    Destination.OVNIS: {"uap", "ufo", "uso", "unidentified", "anomalous", "flying object"},
    Destination.SKYWATCHER: {"aircraft", "tail number", "flight", "airspace", "radar", "surveillance"},
    Destination.AGUAYLUZ: {"prepa", "aee", "luma", "prasa", "aaa", "reservoir", "water", "grid", "utility"},
    Destination.MONEYSWEEP: {"contract", "award", "invoice", "grant", "payment", "procurement", "obligation"},
    Destination.SPIDERWEB: {"officer", "director", "registered agent", "affiliate", "subsidiary", "relationship"},
    Destination.CENTINELAS: {"investigation", "policy", "hearing", "notice", "release", "puerto rico"},
}


class FOIADispositionEngine:
    def __init__(self, semantic_scorer: Callable[[FOIAFinding, Destination], float] | None = None,
                 export_threshold: float = 0.80, review_threshold: float = 0.55,
                 minimum_extraction_confidence: float = 0.70) -> None:
        if not 0 <= review_threshold <= export_threshold <= 1:
            raise ValueError("thresholds must satisfy 0 <= review <= export <= 1")
        self.semantic_scorer = semantic_scorer
        self.export_threshold = export_threshold
        self.review_threshold = review_threshold
        self.minimum_extraction_confidence = minimum_extraction_confidence

    def route(self, finding: FOIAFinding, *, duplicate: bool = False,
              relevant_to_puerto_rico: bool = True) -> list[RoutingDecision]:
        if duplicate:
            return [self._decision(finding, Destination.ARCHIVE_ONLY, Disposition.REJECT_DUPLICATE, 1.0, ["DUPLICATE"])]
        if not relevant_to_puerto_rico:
            return [self._decision(finding, Destination.ARCHIVE_ONLY, Disposition.REJECT_IRRELEVANT, 1.0, ["OUT_OF_SCOPE"])]
        if finding.sensitive:
            return [self._decision(finding, Destination.ARCHIVE_ONLY, Disposition.HOLD_SENSITIVE, 1.0, ["SENSITIVE_CONTENT"])]

        decisions = [self._decision(finding, Destination.THEHUB_EVIDENCE, Disposition.EXPORT, 1.0, ["CANONICAL_EVIDENCE"])]
        haystack = " ".join([finding.finding_type, finding.title, finding.summary, *finding.keywords]).lower()
        for destination, terms in ROUTE_TERMS.items():
            matched = sorted(term for term in terms if term in haystack)
            if not matched:
                continue
            deterministic = min(0.95, 0.58 + 0.10 * len(matched))
            semantic = self.semantic_scorer(finding, destination) if self.semantic_scorer else deterministic
            semantic = min(1.0, max(0.0, semantic))
            score = round(0.75 * deterministic + 0.25 * semantic, 4)
            disposition = self._classify(score, finding.extraction_confidence)
            reasons = [f"TERM:{term.upper().replace(' ', '_')}" for term in matched]
            if finding.entity_collision and destination == Destination.SPIDERWEB:
                disposition = Disposition.REVIEW
                reasons.append("ENTITY_COLLISION")
            decisions.append(self._decision(finding, destination, disposition, score, reasons))

        downstream = [d for d in decisions if d.destination not in {Destination.THEHUB_EVIDENCE, Destination.ARCHIVE_ONLY}]
        if downstream:
            disposition = Disposition.EXPORT if all(d.disposition == Disposition.EXPORT for d in downstream) else Disposition.REVIEW
            decisions.append(self._decision(finding, Destination.THEHUB_INTELLIGENCE, disposition,
                                            max(d.score for d in downstream), ["CROSS_REPO_INDEX"]))
        else:
            decisions.append(self._decision(finding, Destination.ARCHIVE_ONLY, Disposition.ARCHIVE_ONLY, 1.0, ["NO_ROUTE_MATCH"]))
        return decisions

    def build_review_case(self, finding: FOIAFinding,
                          decisions: Iterable[RoutingDecision]) -> ReviewCase | None:
        proposed = [d for d in decisions if d.disposition in {Disposition.REVIEW, Disposition.HOLD_SENSITIVE}]
        if not proposed:
            return None
        digest = hashlib.sha256(f"{finding.finding_id}:review".encode()).hexdigest()[:20]
        return ReviewCase(review_case_id=f"review-{digest}", finding_id=finding.finding_id,
                          reason_codes=sorted({c for d in proposed for c in d.reason_codes}),
                          proposed_decisions=proposed)

    def supersede(self, prior: RoutingDecision, *, disposition: Disposition,
                  reason_codes: list[str]) -> RoutingDecision:
        replacement = self._decision_stub(prior.finding_id, prior.destination, disposition,
                                          prior.score, reason_codes)
        replacement.supersedes_decision_id = prior.decision_id
        return replacement

    def _classify(self, score: float, extraction_confidence: float) -> Disposition:
        if extraction_confidence < self.minimum_extraction_confidence:
            return Disposition.REVIEW
        if score >= self.export_threshold:
            return Disposition.EXPORT
        if score >= self.review_threshold:
            return Disposition.REVIEW
        return Disposition.ARCHIVE_ONLY

    @classmethod
    def _decision(cls, cls_finding: FOIAFinding, destination: Destination,
                  disposition: Disposition, score: float, reasons: list[str]) -> RoutingDecision:
        return cls._decision_stub(cls_finding.finding_id, destination, disposition, score, reasons)

    @staticmethod
    def _decision_stub(finding_id: str, destination: Destination, disposition: Disposition,
                       score: float, reasons: list[str]) -> RoutingDecision:
        raw = f"{finding_id}:{destination}:{disposition}:{'|'.join(reasons)}"
        return RoutingDecision(decision_id=f"decision-{hashlib.sha256(raw.encode()).hexdigest()[:20]}",
                               finding_id=finding_id, destination=destination,
                               disposition=disposition, score=score, reason_codes=reasons)


def build_federation_envelope(finding: FOIAFinding,
                              decision: RoutingDecision) -> FederationEnvelope:
    key = hashlib.sha256(f"{finding.finding_id}:{decision.destination}:{finding.document_id}".encode()).hexdigest()
    return FederationEnvelope(event_id=f"foia-export-{key[:20]}", idempotency_key=key,
                              destination=decision.destination, finding=finding, decision=decision)


class _JsonlStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def read_all(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def _rewrite(self, rows: list[dict[str, Any]]) -> None:
        body = "".join(json.dumps(row, sort_keys=True, default=str) + "\n" for row in rows)
        self.path.write_text(body, encoding="utf-8")


class DurableOutbox(_JsonlStore):
    def enqueue(self, finding: FOIAFinding, decision: RoutingDecision) -> ExportReceipt:
        envelope = build_federation_envelope(finding, decision)
        rows = self.read_all()
        existing = next((r for r in rows if r["receipt"]["idempotency_key"] == envelope.idempotency_key), None)
        if existing:
            return ExportReceipt.model_validate(existing["receipt"])
        receipt = ExportReceipt(export_id=envelope.event_id, finding_id=finding.finding_id,
                                destination=decision.destination, idempotency_key=envelope.idempotency_key,
                                status=ReceiptStatus.PENDING)
        rows.append({"envelope": envelope.model_dump(mode="json"), "receipt": receipt.model_dump(mode="json")})
        self._rewrite(rows)
        return receipt

    def record_attempt(self, idempotency_key: str, *, downstream_record_id: str | None = None,
                       error: str | None = None) -> ExportReceipt:
        rows = self.read_all()
        for row in rows:
            if row["receipt"]["idempotency_key"] != idempotency_key:
                continue
            receipt = ExportReceipt.model_validate(row["receipt"])
            receipt.attempts += 1
            receipt.last_attempt_at = datetime.now(UTC)
            receipt.error = error
            if error:
                receipt.status = ReceiptStatus.FAILED
            else:
                receipt.status = ReceiptStatus.ACKNOWLEDGED
                receipt.downstream_record_id = downstream_record_id
                receipt.acknowledged_at = receipt.last_attempt_at
            row["receipt"] = receipt.model_dump(mode="json")
            self._rewrite(rows)
            return receipt
        raise KeyError(idempotency_key)

    def retryable(self) -> list[ExportReceipt]:
        return [ExportReceipt.model_validate(r["receipt"]) for r in self.read_all()
                if r["receipt"]["status"] == ReceiptStatus.FAILED]


class ReviewQueue(_JsonlStore):
    def enqueue(self, review_case: ReviewCase) -> ReviewCase:
        rows = self.read_all()
        if not any(r["review_case_id"] == review_case.review_case_id for r in rows):
            rows.append(review_case.model_dump(mode="json"))
            self._rewrite(rows)
        return review_case

"""FastAPI surface for the Centinelas shadow water-disruption producer."""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from centinelas.water_disruption import SourceRecord, WaterDisruptionProducer

router = APIRouter(prefix="/water-disruption", tags=["water-disruption"])
_ROOT = Path(os.environ.get("CENTINELAS_DATA_DIR", ".centinelas")) / "water-disruption"
_SOURCES = [
    SourceRecord("prasa", "PRASA", "utility", "T1", "Puerto Rico public water service", (), ()),
    SourceRecord("municipalities", "Puerto Rico municipalities", "government", "T2", "municipal public notices", (), ()),
    SourceRecord("emergency-management", "Emergency management", "government", "T1", "emergency notices", (), ()),
    SourceRecord("news", "News", "news", "T4", "reported observations", (), ()),
    SourceRecord("radio", "Radio", "radio", "T4", "reported observations", (), ()),
    SourceRecord("social", "Public social reports", "social", "T3", "eyewitness reports", (), ()),
    SourceRecord("public-works", "Public works", "government", "T2", "public works notices", (), ()),
]
service = WaterDisruptionProducer(_ROOT, _SOURCES)


class CaptureRequest(BaseModel):
    source_id: str
    source_url: str
    title: str
    body_text: str
    published_at: datetime
    municipalities: list[str] = []
    asset_hint: str | None = None


class RetractRequest(BaseModel):
    reason: str


@router.get("/sources")
def sources() -> dict[str, Any]:
    attempts = service.store.read("acquisition_attempts")
    return {"shadow_mode": True, "total": len(service.sources), "items": [vars(value) for value in service.sources.values()], "attempts": attempts[-100:]}


@router.get("/runs")
def runs() -> dict[str, Any]:
    items = service.store.read("acquisition_attempts")
    return {"shadow_mode": True, "total": len(items), "items": items}


@router.get("/evidence/{evidence_id}")
def evidence(evidence_id: str) -> dict[str, Any]:
    item = service.store.by_key("raw_evidence", "evidence_id", evidence_id)
    if not item:
        raise HTTPException(status_code=404, detail="evidence_not_found")
    return item


@router.get("/candidates")
def candidates() -> dict[str, Any]:
    items = service.store.read("candidate_review")
    return {"shadow_mode": True, "total": len(items), "items": items}


@router.get("/outbox")
def outbox() -> dict[str, Any]:
    items = service.store.read("delivery_outbox")
    return {"shadow_mode": True, "notifications_enabled": False, "total": len(items), "items": items}


@router.post("/capture")
def capture(request: CaptureRequest) -> dict[str, Any]:
    evidence_item = service.capture_evidence(request.source_id, request.source_url, request.title, request.body_text, request.published_at)
    candidate = service.extract_candidate(evidence_item, request.municipalities, request.asset_hint)
    return {"evidence": evidence_item, "candidate": candidate, "shadow_mode": True}


@router.post("/candidates/{candidate_id}/dispatch")
def dispatch(candidate_id: str, idempotency_key: str = Header(alias="Idempotency-Key")) -> dict[str, Any]:
    try:
        return service.dispatch(candidate_id, idempotency_key)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="candidate_not_found") from exc


@router.post("/candidates/{candidate_id}/retract")
def retract(candidate_id: str, request: RetractRequest, idempotency_key: str = Header(alias="Idempotency-Key")) -> dict[str, Any]:
    try:
        return service.retract(candidate_id, request.reason, idempotency_key)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="candidate_not_found") from exc

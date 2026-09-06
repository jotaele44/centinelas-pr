"""FastAPI surface for the Centinelas shadow water-disruption producer."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from centinelas.water_disruption import SourceRecord, WaterDisruptionProducer, stable_id
from server.backend.auth import WRITE_GUARD

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


class DeliverRequest(BaseModel):
    consumer_url: str


@router.get("/console", response_class=HTMLResponse)
def console() -> str:
    return """<!doctype html><html><head><meta charset='utf-8'><title>Water Disruption Shadow Queue</title><style>body{font-family:system-ui;margin:2rem;max-width:1100px}nav a{margin-right:1rem}.badge{padding:.2rem .5rem;border:1px solid #999;border-radius:99px}pre{white-space:pre-wrap;background:#f4f4f4;padding:1rem}</style></head><body><h1>Water Disruption Shadow Queue</h1><p><span class='badge'>Shadow mode</span> No live alerts or production promotion.</p><nav><a href='/water-disruption/sources'>Sources</a><a href='/water-disruption/runs'>Run ledger</a><a href='/water-disruption/candidates'>Candidates</a><a href='/water-disruption/outbox'>Outbox</a></nav><h2>Map and evidence view</h2><p>Candidate records expose municipality, asset hint, evidence IDs, source IDs, confidence components, and deterministic deduplication keys. Unresolved geometry remains explicit and is never fabricated.</p></body></html>"""


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
    return {"shadow_mode": True, "notifications_enabled": False, "total": len(items), "items": items, "receipts": service.store.read("delivery_receipts"), "dead_letter": service.store.read("dead_letter")}


@router.post("/capture", dependencies=WRITE_GUARD)
def capture(request: CaptureRequest) -> dict[str, Any]:
    evidence_item = service.capture_evidence(request.source_id, request.source_url, request.title, request.body_text, request.published_at)
    candidate = service.extract_candidate(evidence_item, request.municipalities, request.asset_hint)
    return {"evidence": evidence_item, "candidate": candidate, "shadow_mode": True}


@router.post("/candidates/{candidate_id}/dispatch", dependencies=WRITE_GUARD)
def dispatch(candidate_id: str, idempotency_key: str = Header(alias="Idempotency-Key")) -> dict[str, Any]:
    try:
        return service.dispatch(candidate_id, idempotency_key)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="candidate_not_found") from exc


@router.post("/outbox/{outbox_id}/deliver", dependencies=WRITE_GUARD)
def deliver(outbox_id: str, request: DeliverRequest, idempotency_key: str = Header(alias="Idempotency-Key")) -> dict[str, Any]:
    envelope = service.store.by_key("delivery_outbox", "outbox_id", outbox_id)
    if not envelope:
        raise HTTPException(status_code=404, detail="outbox_not_found")
    prior = service.store.by_key("delivery_receipts", "idempotency_key", idempotency_key)
    if prior:
        return prior
    target = request.consumer_url.rstrip("/") + "/water-disruption/intake"
    payload = json.dumps(envelope["payload"]).encode("utf-8")
    req = urllib.request.Request(target, data=payload, method="POST", headers={"Content-Type": "application/json", "Idempotency-Key": idempotency_key, "X-Shadow-Mode": "true"})
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            body = json.loads(response.read().decode("utf-8"))
            receipt = {"receipt_id": stable_id("DRC", {"outbox_id": outbox_id, "idempotency_key": idempotency_key}), "outbox_id": outbox_id, "idempotency_key": idempotency_key, "status": "acknowledged", "consumer_status": response.status, "consumer_receipt": body, "shadow_mode": True}
            service.store.append("delivery_receipts", receipt)
            return receipt
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        failure = {"dead_letter_id": stable_id("DLQ", {"outbox_id": outbox_id, "idempotency_key": idempotency_key}), "outbox_id": outbox_id, "idempotency_key": idempotency_key, "status": "transport_failed", "error": str(exc), "retryable": True, "shadow_mode": True}
        service.store.append("dead_letter", failure)
        raise HTTPException(status_code=502, detail=failure) from exc


@router.post("/candidates/{candidate_id}/retract", dependencies=WRITE_GUARD)
def retract(candidate_id: str, request: RetractRequest, idempotency_key: str = Header(alias="Idempotency-Key")) -> dict[str, Any]:
    try:
        return service.retract(candidate_id, request.reason, idempotency_key)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="candidate_not_found") from exc

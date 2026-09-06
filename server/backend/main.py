"""Centinelas-PR universal intake API — FastAPI server.

Read-only view over .centinelas/{queue,classified,dispatched}/*.json for the
pipeline-visibility frontend. Reads from disk per-request (no startup caching)
since these are low-volume, locally-written JSON files that change as the CLI
pipeline runs.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from centinelas.ingest.rss import _load_sources
from server.backend.auth import WRITE_GUARD
from server.backend.water_disruption_api import router as water_disruption_router

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = Path(os.environ.get("CENTINELAS_DATA_DIR", str(REPO_ROOT / ".centinelas")))
QUEUE_DIR = DATA_DIR / "queue"
CLASSIFIED_DIR = DATA_DIR / "classified"
DISPATCHED_DIR = DATA_DIR / "dispatched"
HANDOFF_DIR = DATA_DIR / "handoffs"

app = FastAPI(title="Centinelas-PR Intake API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)
app.include_router(water_disruption_router)


def _load_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _load_dir(directory: Path) -> list[dict[str, Any]]:
    if not directory.exists():
        return []
    items: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*.json")):
        try:
            items.append(json.loads(path.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            continue
    return items


def _dispatch_index() -> dict[str, dict[str, Any]]:
    return {rec["item_id"]: rec for rec in _load_dir(DISPATCHED_DIR) if "item_id" in rec}


def _join_dispatch(item: dict[str, Any], index: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return {**item, "dispatch": index.get(item.get("item_id"))}


def _dispatch_state(joined: dict[str, Any]) -> str:
    dispatch = joined.get("dispatch")
    return dispatch["status"] if dispatch else "pending"


@app.get("/health")
def health() -> JSONResponse:
    return JSONResponse({"status": "ok", "shadow_water_pipeline": True, "counts": {
        "queue": len(list(QUEUE_DIR.glob("*.json"))) if QUEUE_DIR.exists() else 0,
        "classified": len(list(CLASSIFIED_DIR.glob("*.json"))) if CLASSIFIED_DIR.exists() else 0,
        "dispatched": len(list(DISPATCHED_DIR.glob("*.json"))) if DISPATCHED_DIR.exists() else 0,
    }})


@app.get("/items")
def items(domain: str | None = Query(default=None), dispatch_status: str | None = Query(default=None), limit: int = Query(default=500, ge=1, le=5000)) -> JSONResponse:
    index = _dispatch_index()
    result = [_join_dispatch(item, index) for item in _load_dir(CLASSIFIED_DIR)]
    if domain:
        result = [it for it in result if domain in (it.get("labels") or [])]
    if dispatch_status:
        result = [it for it in result if _dispatch_state(it) == dispatch_status]
    result.sort(key=lambda it: it.get("captured_at") or "", reverse=True)
    return JSONResponse(result[:limit])


@app.get("/items/{item_id}")
def item_detail(item_id: str) -> JSONResponse:
    item = _load_json(CLASSIFIED_DIR / f"{item_id}.json")
    if item is None:
        raise HTTPException(status_code=404, detail=f"Item not found: {item_id}")
    return JSONResponse({**item, "dispatch": _load_json(DISPATCHED_DIR / f"{item_id}.json")})


@app.get("/queue")
def queue() -> JSONResponse:
    result = _load_dir(QUEUE_DIR)
    result.sort(key=lambda it: it.get("captured_at") or "", reverse=True)
    return JSONResponse(result)


@app.get("/sources")
def sources() -> JSONResponse:
    try:
        return JSONResponse(_load_sources())
    except (OSError, ValueError):
        return JSONResponse([])


@app.get("/status")
def status() -> JSONResponse:
    index = _dispatch_index()
    classified = [_join_dispatch(it, index) for it in _load_dir(CLASSIFIED_DIR)]
    breakdown: dict[str, int] = {}
    for it in classified:
        state = _dispatch_state(it)
        breakdown[state] = breakdown.get(state, 0) + 1
    return JSONResponse({"queue": len(list(QUEUE_DIR.glob("*.json"))) if QUEUE_DIR.exists() else 0, "classified": len(classified), "dispatched": len(index), "dispatch_breakdown": breakdown})


class RunRequest(BaseModel):
    dry_run: bool = False
    limit: int = 0


class HandoffRequest(BaseModel):
    targets: list[str]
    dry_run: bool = False
    retry_receipt_id: str | None = None


@app.get("/handoffs")
def handoffs(limit: int = Query(default=500, ge=1, le=5000)) -> JSONResponse:
    history: dict[str, list[dict[str, Any]]] = {}
    for receipt in _load_dir(HANDOFF_DIR):
        history.setdefault(receipt.get("item_id", ""), []).append(receipt)
    rows = [{**item, "handoffs": history.get(item.get("item_id", ""), [])} for item in _load_dir(CLASSIFIED_DIR)]
    rows.sort(key=lambda row: row.get("captured_at") or "", reverse=True)
    return JSONResponse(rows[:limit])


@app.post("/handoffs/{item_id}", dependencies=WRITE_GUARD)
def create_handoff(item_id: str, req: HandoffRequest) -> JSONResponse:
    from datetime import datetime, timezone

    from centinelas.models import ClassifiedItem
    from centinelas.route import dispatch as dispatch_mod
    from centinelas.route.dispatch import dispatch_to_targets
    raw = _load_json(CLASSIFIED_DIR / f"{item_id}.json")
    if raw is None:
        raise HTTPException(status_code=404, detail=f"Item not found: {item_id}")
    targets = req.targets
    if req.retry_receipt_id:
        previous = _load_json(HANDOFF_DIR / f"{req.retry_receipt_id}.json")
        if previous is None or previous.get("item_id") != item_id:
            raise HTTPException(status_code=404, detail="Retry receipt not found")
        failed = {attempt["target"] for attempt in previous.get("attempts", []) if attempt.get("status") == "failed"}
        targets = [target for target in req.targets if target in failed]
        if not targets:
            raise HTTPException(status_code=409, detail="Receipt has no failed targets to retry")
    dispatch_mod._DATA_DIR = DATA_DIR
    try:
        receipt = dispatch_to_targets(ClassifiedItem.model_validate(raw), targets, dry_run=req.dry_run)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    receipt["receipt_id"] = f"{item_id}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}"
    receipt["created_at"] = datetime.now(timezone.utc).isoformat()
    HANDOFF_DIR.mkdir(parents=True, exist_ok=True)
    (HANDOFF_DIR / f"{receipt['receipt_id']}.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    return JSONResponse(receipt)


@app.post("/run", dependencies=WRITE_GUARD)
def run_pipeline(req: RunRequest | None = None) -> JSONResponse:
    from centinelas.classify.classifier import classify as do_classify
    from centinelas.ingest.federal_register import poll_federal_register
    from centinelas.ingest.rss import poll_all
    from centinelas.ingest.web import poll_scrape_sources
    from centinelas.models import ClassifiedItem
    from centinelas.route import dispatch as dispatch_mod
    from centinelas.route.dispatch import dispatch
    dispatch_mod._DATA_DIR = DATA_DIR
    req = req or RunRequest()
    try:
        raw_items = poll_all() + poll_federal_register() + poll_scrape_sources()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"ingest failed: {exc}") from exc
    if req.limit:
        raw_items = raw_items[:req.limit]
    CLASSIFIED_DIR.mkdir(parents=True, exist_ok=True)
    classified: list[ClassifiedItem] = []
    for raw in raw_items:
        labels, confidence, reasoning = do_classify(raw)
        item = ClassifiedItem(**raw.model_dump(), labels=labels, confidence=confidence, classifier_reasoning=reasoning)
        classified.append(item)
        (CLASSIFIED_DIR / f"{item.item_id}.json").write_text(item.model_dump_json(indent=2))
    breakdown: dict[str, int] = {}
    for item in classified:
        record = dispatch(item, dry_run=req.dry_run)
        breakdown[record.status] = breakdown.get(record.status, 0) + 1
    return JSONResponse({"status": "ok", "dry_run": req.dry_run, "ingested": len(raw_items), "classified": len(classified), "dispatched": breakdown.get("ok", 0), "dispatch_breakdown": breakdown})

"""Centinelas-PR universal intake API — FastAPI server.

Read-only view over .centinelas/{queue,classified,dispatched}/*.json for the
pipeline-visibility frontend. Reads from disk per-request (no startup caching)
since these are low-volume, locally-written JSON files that change as the CLI
pipeline runs.

Run from repo root (after `pip install -e ".[server]"`):
    uvicorn server.backend.main:app --reload --port 8000
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
    # GET for the read-only visibility endpoints; POST so the SPA can trigger /run.
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


def _load_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _load_dir(directory: Path) -> list[dict[str, Any]]:
    """Read every *.json file in a directory into a list of dicts. Missing dir → []."""
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
    """Map item_id → its DispatchRecord dict (for joining onto classified items)."""
    return {rec["item_id"]: rec for rec in _load_dir(DISPATCHED_DIR) if "item_id" in rec}


def _join_dispatch(item: dict[str, Any], index: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Attach the item's dispatch record (or None) under a `dispatch` key."""
    return {**item, "dispatch": index.get(item.get("item_id"))}


def _dispatch_state(joined: dict[str, Any]) -> str:
    """Derive a filterable status: the dispatch record's status, or 'pending' if none."""
    dispatch = joined.get("dispatch")
    return dispatch["status"] if dispatch else "pending"


@app.get("/health")
def health() -> JSONResponse:
    return JSONResponse({
        "status": "ok",
        "counts": {
            "queue": len(list(QUEUE_DIR.glob("*.json"))) if QUEUE_DIR.exists() else 0,
            "classified": len(list(CLASSIFIED_DIR.glob("*.json"))) if CLASSIFIED_DIR.exists() else 0,
            "dispatched": len(list(DISPATCHED_DIR.glob("*.json"))) if DISPATCHED_DIR.exists() else 0,
        },
    })


@app.get("/items")
def items(
    domain: str | None = Query(default=None, description="Filter to items whose labels contain this domain"),
    dispatch_status: str | None = Query(default=None, description="ok | failed | skipped | pending"),
    limit: int = Query(default=500, ge=1, le=5000),
) -> JSONResponse:
    """List classified items, each joined with its dispatch record by item_id."""
    index = _dispatch_index()
    result = [_join_dispatch(item, index) for item in _load_dir(CLASSIFIED_DIR)]

    if domain:
        result = [it for it in result if domain in (it.get("labels") or [])]
    if dispatch_status:
        result = [it for it in result if _dispatch_state(it) == dispatch_status]

    # Newest first by captured_at when present.
    result.sort(key=lambda it: it.get("captured_at") or "", reverse=True)
    return JSONResponse(result[:limit])


@app.get("/items/{item_id}")
def item_detail(item_id: str) -> JSONResponse:
    """Single classified item + its joined dispatch record. 404 if not classified."""
    item = _load_json(CLASSIFIED_DIR / f"{item_id}.json")
    if item is None:
        raise HTTPException(status_code=404, detail=f"Item not found: {item_id}")
    dispatch = _load_json(DISPATCHED_DIR / f"{item_id}.json")
    return JSONResponse({**item, "dispatch": dispatch})


@app.get("/queue")
def queue() -> JSONResponse:
    """Raw (pre-classification) items still sitting in the queue."""
    result = _load_dir(QUEUE_DIR)
    result.sort(key=lambda it: it.get("captured_at") or "", reverse=True)
    return JSONResponse(result)


@app.get("/sources")
def sources() -> JSONResponse:
    """Read-only view of the configured RSS/Atom feed registry (sources.yaml)."""
    try:
        return JSONResponse(_load_sources())
    except (OSError, ValueError):
        return JSONResponse([])


@app.get("/status")
def status() -> JSONResponse:
    """Queue depth / classified / dispatched counts + dispatch-status breakdown."""
    index = _dispatch_index()
    classified = [_join_dispatch(it, index) for it in _load_dir(CLASSIFIED_DIR)]
    breakdown: dict[str, int] = {}
    for it in classified:
        state = _dispatch_state(it)
        breakdown[state] = breakdown.get(state, 0) + 1
    return JSONResponse({
        "queue": len(list(QUEUE_DIR.glob("*.json"))) if QUEUE_DIR.exists() else 0,
        "classified": len(classified),
        "dispatched": len(index),
        "dispatch_breakdown": breakdown,
    })


class RunRequest(BaseModel):
    """Body for POST /run. All fields optional — an empty POST runs the full pipeline."""

    dry_run: bool = False
    limit: int = 0


class HandoffRequest(BaseModel):
    targets: list[str]
    dry_run: bool = False
    retry_receipt_id: str | None = None


@app.get("/handoffs")
def handoffs(limit: int = Query(default=500, ge=1, le=5000)) -> JSONResponse:
    """List classified items and their durable manual-handoff history."""
    history: dict[str, list[dict[str, Any]]] = {}
    for receipt in _load_dir(HANDOFF_DIR):
        history.setdefault(receipt.get("item_id", ""), []).append(receipt)
    rows = []
    for item in _load_dir(CLASSIFIED_DIR):
        rows.append({**item, "handoffs": history.get(item.get("item_id", ""), [])})
    rows.sort(key=lambda row: row.get("captured_at") or "", reverse=True)
    return JSONResponse(rows[:limit])


@app.post("/handoffs/{item_id}")
def create_handoff(item_id: str, req: HandoffRequest) -> JSONResponse:
    """Dispatch one classified item to selected federation consumers."""
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
        failed = {
            attempt["target"]
            for attempt in previous.get("attempts", [])
            if attempt.get("status") == "failed"
        }
        targets = [target for target in req.targets if target in failed]
        if not targets:
            raise HTTPException(status_code=409, detail="Receipt has no failed targets to retry")

    dispatch_mod._DATA_DIR = DATA_DIR
    try:
        receipt = dispatch_to_targets(
            ClassifiedItem.model_validate(raw),
            targets,
            dry_run=req.dry_run,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    receipt["receipt_id"] = f"{item_id}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}"
    receipt["created_at"] = datetime.now(timezone.utc).isoformat()
    HANDOFF_DIR.mkdir(parents=True, exist_ok=True)
    (HANDOFF_DIR / f"{receipt['receipt_id']}.json").write_text(
        json.dumps(receipt, indent=2),
        encoding="utf-8",
    )
    return JSONResponse(receipt)


@app.post("/run")
def run_pipeline(req: RunRequest | None = None) -> JSONResponse:
    """Trigger a full ingest → classify → route pipeline run.

    This is the HTTP twin of the ``centinelas run`` CLI command and reuses the exact
    same pipeline path (poll_all → classify → dispatch). Classified items are written
    into CLASSIFIED_DIR so the read endpoints (/items, /status) reflect the run.

    Degrades gracefully with no network and no ANTHROPIC_API_KEY — the same offline
    contract the CLI honours:
      * RSS polling swallows unreachable-feed errors, so ingest yields fewer/zero
        items rather than raising;
      * classification falls back to keyword rules when the Claude Haiku tier is
        unavailable (missing key / no network);
      * ``dry_run`` skips the cross-repo intake/ writes while still persisting
        Centinelas's own classified + dispatch bookkeeping.

    Returns a JSON summary of the run (counts + dispatch-status breakdown).
    """
    from centinelas.classify.classifier import classify as do_classify
    from centinelas.ingest.federal_register import poll_federal_register
    from centinelas.ingest.rss import poll_all
    from centinelas.models import ClassifiedItem
    from centinelas.route import dispatch as dispatch_mod
    from centinelas.route.dispatch import dispatch

    # Align the dispatch module's data dir with this server's DATA_DIR before it writes
    # dispatch records. dispatch defaults to a RELATIVE ".centinelas", so when the
    # backend runs from a non-repo cwd (e.g. the desktop wrapper) its records would land
    # under the process cwd instead of DISPATCHED_DIR, and /items and /status would keep
    # showing freshly-run items as pending. DATA_DIR is the absolute source of truth.
    dispatch_mod._DATA_DIR = DATA_DIR

    req = req or RunRequest()

    # poll_all already isolates per-feed failures; guard the call itself so a hard
    # failure surfaces as a clean 502 rather than an unhandled 500. The Federal
    # Register poller (config-gated, self-swallowing) adds federal coastal/permit
    # coverage so the HTTP pipeline matches the CLI's intake sources.
    try:
        items = poll_all() + poll_federal_register()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"ingest failed: {exc}") from exc
    if req.limit:
        items = items[: req.limit]

    CLASSIFIED_DIR.mkdir(parents=True, exist_ok=True)
    classified: list[ClassifiedItem] = []
    for raw in items:
        labels, confidence, reasoning = do_classify(raw)
        item = ClassifiedItem(
            **raw.model_dump(),
            labels=labels,
            confidence=confidence,
            classifier_reasoning=reasoning,
        )
        classified.append(item)
        (CLASSIFIED_DIR / f"{item.item_id}.json").write_text(item.model_dump_json(indent=2))

    breakdown: dict[str, int] = {}
    for item in classified:
        record = dispatch(item, dry_run=req.dry_run)
        breakdown[record.status] = breakdown.get(record.status, 0) + 1

    return JSONResponse({
        "status": "ok",
        "dry_run": req.dry_run,
        "ingested": len(items),
        "classified": len(classified),
        "dispatched": breakdown.get("ok", 0),
        "dispatch_breakdown": breakdown,
    })

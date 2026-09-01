from __future__ import annotations

import hashlib
import json
import mimetypes
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable

from .models import BASELINE_CUTOFF, ReleaseState, classify_release

PDF_SIGNATURE = b"%PDF-"


@dataclass(frozen=True)
class SourceHealth:
    adapter_id: str
    status: str
    attempts: int
    enumerated: int
    acquired: int
    failed: int
    last_error: str | None = None


@dataclass(frozen=True)
class AcquisitionResult:
    source_key: str
    source_url: str
    status: str
    content_sha256: str | None
    byte_size: int
    mime_type: str | None
    file_signature: str | None
    page_count: int | None
    text_layer_present: bool | None
    attachment_count: int
    error: str | None = None


@dataclass
class DeltaRun:
    run_id: str
    adapter_id: str
    baseline_cutoff: str = BASELINE_CUTOFF
    completed_keys: set[str] = field(default_factory=set)
    results: list[AcquisitionResult] = field(default_factory=list)

    def checkpoint(self, path: Path) -> None:
        payload = {
            "run_id": self.run_id,
            "adapter_id": self.adapter_id,
            "baseline_cutoff": self.baseline_cutoff,
            "completed_keys": sorted(self.completed_keys),
            "results": [asdict(item) for item in self.results],
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(path.suffix + ".tmp")
        temp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        temp.replace(path)

    @classmethod
    def resume(cls, path: Path) -> "DeltaRun":
        payload = json.loads(path.read_text())
        if payload["baseline_cutoff"] != BASELINE_CUTOFF:
            raise ValueError("checkpoint baseline does not match immutable cutoff")
        return cls(
            run_id=payload["run_id"],
            adapter_id=payload["adapter_id"],
            completed_keys=set(payload.get("completed_keys", [])),
            results=[AcquisitionResult(**row) for row in payload.get("results", [])],
        )


def _pdf_page_count(data: bytes) -> int | None:
    if not data.startswith(PDF_SIGNATURE):
        return None
    return data.count(b"/Type /Page") - data.count(b"/Type /Pages")


def inspect_binary(data: bytes, filename: str = "") -> dict[str, Any]:
    signature = data[:8].hex()
    is_pdf = data.startswith(PDF_SIGNATURE)
    mime = "application/pdf" if is_pdf else mimetypes.guess_type(filename)[0] or "application/octet-stream"
    page_count = _pdf_page_count(data)
    text_layer = None if not is_pdf else any(token in data for token in (b"BT", b"Tj", b"TJ"))
    attachment_count = data.count(b"/EmbeddedFile") if is_pdf else 0
    return {
        "content_sha256": hashlib.sha256(data).hexdigest(),
        "byte_size": len(data),
        "mime_type": mime,
        "file_signature": signature,
        "page_count": page_count,
        "text_layer_present": text_layer,
        "attachment_count": attachment_count,
    }


def compare_versions(old: dict[str, Any] | None, new: dict[str, Any]) -> ReleaseState:
    if old is None:
        return ReleaseState.NEW_DOCUMENT
    return classify_release(
        known_document=True,
        old_sha256=old.get("content_sha256"),
        new_sha256=new.get("content_sha256"),
        old_url=old.get("source_url"),
        new_url=new.get("source_url"),
        old_redaction_count=old.get("redaction_count"),
        new_redaction_count=new.get("redaction_count"),
        old_attachment_count=old.get("attachment_count", 0),
        new_attachment_count=new.get("attachment_count", 0),
        metadata_changed=old.get("metadata") != new.get("metadata"),
        withdrawn=bool(new.get("withdrawn")),
        in_baseline=bool(old.get("in_baseline")),
    )


def run_adapter(
    *,
    adapter_id: str,
    records: Iterable[dict[str, Any]],
    fetch: Callable[[str], bytes],
    checkpoint_path: Path,
    max_attempts: int = 3,
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[DeltaRun, SourceHealth]:
    run = DeltaRun.resume(checkpoint_path) if checkpoint_path.exists() else DeltaRun(
        run_id=f"{adapter_id}-{int(time.time())}", adapter_id=adapter_id
    )
    enumerated = acquired = failed = attempts = 0
    last_error: str | None = None
    for record in records:
        enumerated += 1
        key = str(record["source_key"])
        if key in run.completed_keys:
            continue
        url = str(record["source_url"])
        error: Exception | None = None
        data: bytes | None = None
        for attempt in range(1, max_attempts + 1):
            attempts += 1
            try:
                data = fetch(url)
                error = None
                break
            except Exception as exc:  # adapter boundary intentionally records failures
                error = exc
                last_error = str(exc)
                if attempt < max_attempts:
                    sleep(0)
        if data is None:
            failed += 1
            result = AcquisitionResult(
                source_key=key, source_url=url, status="FAILED", content_sha256=None,
                byte_size=0, mime_type=None, file_signature=None, page_count=None,
                text_layer_present=None, attachment_count=0, error=str(error),
            )
        else:
            acquired += 1
            inspected = inspect_binary(data, record.get("filename", ""))
            result = AcquisitionResult(source_key=key, source_url=url, status="ACQUIRED", **inspected)
        run.results.append(result)
        run.completed_keys.add(key)
        run.checkpoint(checkpoint_path)
    status = "healthy" if failed == 0 else ("degraded" if acquired else "failed")
    return run, SourceHealth(adapter_id, status, attempts, enumerated, acquired, failed, last_error)

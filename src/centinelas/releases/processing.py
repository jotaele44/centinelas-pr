from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable

PDF_MAGIC = b"%PDF-"
ZIP_MAGIC = b"PK\x03\x04"
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
JPEG_MAGIC = b"\xff\xd8\xff"


@dataclass(frozen=True)
class PageAnalysis:
    page_number: int
    native_text: str
    native_text_confidence: float
    ocr_required: bool
    ocr_confidence: float | None
    flags: tuple[str, ...]
    perceptual_hash: str
    redaction_regions: int


@dataclass(frozen=True)
class ProcessingResult:
    content_sha256: str
    mime_type: str
    valid_signature: bool
    repaired: bool
    page_count: int
    text_layer_present: bool
    embedded_attachment_count: int
    pages: tuple[PageAnalysis, ...]
    extracted_attachments: tuple[str, ...]
    review_reasons: tuple[str, ...]
    normalized_digest: str


@dataclass(frozen=True)
class OcrTask:
    content_sha256: str
    page_number: int
    reason: str
    priority: int


@dataclass
class ManualReviewQueue:
    rows: list[dict[str, Any]] = field(default_factory=list)

    def add(self, content_sha256: str, page: PageAnalysis, reasons: Iterable[str]) -> None:
        reason_list = sorted(set(reasons))
        if not reason_list:
            return
        self.rows.append(
            {
                "content_sha256": content_sha256,
                "page_number": page.page_number,
                "reasons": reason_list,
                "native_text_confidence": page.native_text_confidence,
                "ocr_confidence": page.ocr_confidence,
                "flags": list(page.flags),
            }
        )

    def write_jsonl(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in self.rows))


def detect_mime(data: bytes) -> tuple[str, bool]:
    if data.startswith(PDF_MAGIC):
        return "application/pdf", True
    if data.startswith(ZIP_MAGIC):
        return "application/zip", True
    if data.startswith(PNG_MAGIC):
        return "image/png", True
    if data.startswith(JPEG_MAGIC):
        return "image/jpeg", True
    return "application/octet-stream", False


def repair_pdf_in_sandbox(data: bytes, repairer: Callable[[bytes], bytes] | None = None) -> tuple[bytes, bool]:
    if not data.startswith(PDF_MAGIC):
        raise ValueError("PDF repair requires a PDF magic signature")
    if b"%%EOF" in data[-2048:]:
        return data, False
    if repairer is None:
        raise ValueError("corrupt PDF: missing EOF marker and no sandbox repairer supplied")
    repaired = repairer(data)
    if not repaired.startswith(PDF_MAGIC) or b"%%EOF" not in repaired[-2048:]:
        raise ValueError("sandbox repair output failed PDF signature validation")
    return repaired, True


def _split_pdf_pages(data: bytes) -> list[bytes]:
    starts = [match.start() for match in re.finditer(rb"/Type\s*/Page\b", data)]
    count = max(1, len(starts))
    if count == 1:
        return [data]
    chunk = max(1, len(data) // count)
    return [data[index * chunk : len(data) if index == count - 1 else (index + 1) * chunk] for index in range(count)]


def _native_text(page_bytes: bytes) -> str:
    candidates = re.findall(rb"\(([\x20-\x7e]{4,})\)\s*Tj", page_bytes)
    if not candidates:
        candidates = re.findall(rb"[A-Za-z][A-Za-z0-9 ,.;:'\-]{12,}", page_bytes)
    return " ".join(value.decode("latin-1", errors="ignore") for value in candidates)[:20000]


def _flags(page_bytes: bytes, text: str) -> tuple[str, ...]:
    lowered = text.lower()
    flags: set[str] = set()
    if b"/Subtype /Image" in page_bytes or b"/Image" in page_bytes:
        flags.add("IMAGE_CONTENT")
    if any(token in lowered for token in ("latitude", "longitude", "map", "chart", "legend")):
        flags.add("MAP_OR_CHART")
    if any(token in lowered for token in ("table", "column", "subtotal", "total")):
        flags.add("TABLE")
    if b"/Font" not in page_bytes and b"/Image" in page_bytes:
        flags.add("HANDWRITING_POSSIBLE")
    return tuple(sorted(flags))


def _perceptual_hash(page_bytes: bytes) -> str:
    if not page_bytes:
        return "0" * 16
    stride = max(1, len(page_bytes) // 64)
    sample = page_bytes[::stride][:64]
    mean = sum(sample) / len(sample)
    bits = "".join("1" if value >= mean else "0" for value in sample).ljust(64, "0")
    return f"{int(bits, 2):016x}"


def hamming_distance(left: str, right: str) -> int:
    return (int(left, 16) ^ int(right, 16)).bit_count()


def redaction_region_count(page_bytes: bytes) -> int:
    black_fills = len(re.findall(rb"(?:0\s+0\s+0\s+rg|0\s+g).*?re\s+f", page_bytes, flags=re.S))
    redact_annots = page_bytes.count(b"/Subtype /Redact")
    return black_fills + redact_annots


def compare_page_versions(old: PageAnalysis, new: PageAnalysis) -> dict[str, Any]:
    redaction_delta = new.redaction_regions - old.redaction_regions
    if redaction_delta < 0:
        classification = "LESS_REDACTED"
    elif redaction_delta > 0:
        classification = "MORE_REDACTED"
    else:
        classification = "UNCHANGED_REDACTION_COUNT"
    return {
        "classification": classification,
        "redaction_delta": redaction_delta,
        "perceptual_distance": hamming_distance(old.perceptual_hash, new.perceptual_hash),
    }


def extract_embedded_attachments(data: bytes, out_dir: Path | None = None) -> tuple[str, ...]:
    matches = list(re.finditer(rb"/Type\s*/EmbeddedFile", data))
    names = tuple(f"attachment-{index + 1:04d}.bin" for index in range(len(matches)))
    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
        for name in names:
            (out_dir / name).write_bytes(b"")
    return names


def process_document(
    data: bytes,
    *,
    ocr: Callable[[bytes, int], tuple[str, float]] | None = None,
    repairer: Callable[[bytes], bytes] | None = None,
    attachment_dir: Path | None = None,
    low_confidence_threshold: float = 0.70,
) -> tuple[ProcessingResult, tuple[OcrTask, ...], ManualReviewQueue]:
    content_sha256 = hashlib.sha256(data).hexdigest()
    mime_type, valid_signature = detect_mime(data)
    if not valid_signature:
        raise ValueError("unsupported or invalid document signature")
    repaired = False
    if mime_type == "application/pdf":
        data, repaired = repair_pdf_in_sandbox(data, repairer)
        page_blobs = _split_pdf_pages(data)
    else:
        page_blobs = [data]

    queue = ManualReviewQueue()
    tasks: list[OcrTask] = []
    pages: list[PageAnalysis] = []
    for page_number, page_bytes in enumerate(page_blobs, start=1):
        native = _native_text(page_bytes)
        native_confidence = min(1.0, len(native.strip()) / 200.0)
        flags = _flags(page_bytes, native)
        needs_ocr = native_confidence < low_confidence_threshold
        ocr_confidence: float | None = None
        if needs_ocr:
            tasks.append(OcrTask(content_sha256, page_number, "LOW_NATIVE_TEXT_CONFIDENCE", 100))
            if ocr is not None:
                _ocr_text, ocr_confidence = ocr(page_bytes, page_number)
        page = PageAnalysis(
            page_number=page_number,
            native_text=native,
            native_text_confidence=native_confidence,
            ocr_required=needs_ocr,
            ocr_confidence=ocr_confidence,
            flags=flags,
            perceptual_hash=_perceptual_hash(page_bytes),
            redaction_regions=redaction_region_count(page_bytes),
        )
        pages.append(page)
        reasons: list[str] = []
        if needs_ocr and (ocr_confidence is None or ocr_confidence < low_confidence_threshold):
            reasons.append("OCR_LOW_CONFIDENCE")
        if "MAP_OR_CHART" in flags:
            reasons.append("MAP_OR_CHART_REVIEW")
        if "TABLE" in flags:
            reasons.append("TABLE_REVIEW")
        if "HANDWRITING_POSSIBLE" in flags:
            reasons.append("HANDWRITING_REVIEW")
        queue.add(content_sha256, page, reasons)

    attachments = extract_embedded_attachments(data, attachment_dir)
    normalized = {
        "content_sha256": content_sha256,
        "mime_type": mime_type,
        "repaired": repaired,
        "pages": [asdict(page) for page in pages],
        "attachments": attachments,
    }
    normalized_digest = hashlib.sha256(
        json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    review_reasons = tuple(sorted({reason for row in queue.rows for reason in row["reasons"]}))
    result = ProcessingResult(
        content_sha256=content_sha256,
        mime_type=mime_type,
        valid_signature=valid_signature,
        repaired=repaired,
        page_count=len(pages),
        text_layer_present=any(page.native_text_confidence > 0 for page in pages),
        embedded_attachment_count=len(attachments),
        pages=tuple(pages),
        extracted_attachments=attachments,
        review_reasons=review_reasons,
        normalized_digest=normalized_digest,
    )
    return result, tuple(tasks), queue

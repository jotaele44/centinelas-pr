import hashlib
import json

import pytest

from centinelas.releases.adapters import (
    AdapterPolicyError,
    RateLimiter,
    SOURCE_REGISTRY,
    build_adapter,
)
from centinelas.releases.processing import (
    compare_page_versions,
    process_document,
)


def _pdf(text=b"Puerto Rico map table", *, images=False, attachments=False, redactions=0):
    page = b"/Type /Page /Font (" + text + b") Tj "
    if images:
        page += b"/Subtype /Image "
    if attachments:
        page += b"/Type /EmbeddedFile "
    page += b"0 0 0 rg 10 10 20 20 re f " * redactions
    return b"%PDF-1.4\n" + page + b"\n%%EOF"


def test_registry_sources_disabled_by_default():
    assert len(SOURCE_REGISTRY) == 8
    assert all(not row.enabled_by_default for row in SOURCE_REGISTRY.values())


def test_explicit_policy_gates_and_pagination_resume(tmp_path):
    calls = []

    def transport(url, headers):
        calls.append(url)
        page = 2 if "page=2" in url else 1
        body = json.dumps(
            {"rows": [{"id": f"row-{page}"}], "has_next": page == 1}
        ).encode()
        return 200, {"content-type": "application/json"}, body

    def parse(body):
        payload = json.loads(body)
        return payload["rows"], payload["has_next"]

    adapter = build_adapter("nara_catalog", transport, tmp_path)
    with pytest.raises(AdapterPolicyError):
        list(adapter.enumerate_pages(parse))

    adapter = build_adapter(
        "nara_catalog",
        transport,
        tmp_path,
        explicitly_enabled=True,
        robots_approved=True,
        terms_approved=True,
        limiter=RateLimiter(0),
    )
    assert [row["id"] for row in adapter.enumerate_pages(parse)] == [
        "row-1",
        "row-2",
    ]
    assert json.loads(adapter.checkpoint_path.read_text())["next_page"] == 3
    assert len(adapter.receipts) == 2

    clean_calls = []

    def no_network(url, headers):
        clean_calls.append(url)
        raise AssertionError("cached rerun must not hit transport")

    rerun = build_adapter(
        "nara_catalog",
        no_network,
        tmp_path,
        explicitly_enabled=True,
        robots_approved=True,
        terms_approved=True,
        limiter=RateLimiter(0),
    )
    assert list(rerun.enumerate_pages(parse)) == []
    assert clean_calls == []


def test_rate_limiter_uses_injected_sleep():
    sleeps = []
    clock_values = iter([0.0, 0.0, 0.25, 1.0])
    limiter = RateLimiter(1.0, sleeper=sleeps.append)
    limiter.wait(clock=lambda: next(clock_values))
    limiter.wait(clock=lambda: next(clock_values))
    assert sleeps == [0.75]


def test_processing_is_reproducible_and_flags_review():
    data = _pdf(images=True, attachments=True, redactions=2)

    def ocr(_page, _number):
        return "Puerto Rico", 0.45

    first, tasks, queue = process_document(data, ocr=ocr)
    second, second_tasks, second_queue = process_document(data, ocr=ocr)
    assert first.normalized_digest == second.normalized_digest
    assert first.content_sha256 == hashlib.sha256(data).hexdigest()
    assert first.page_count == 1
    assert first.embedded_attachment_count == 1
    assert "MAP_OR_CHART_REVIEW" in first.review_reasons
    assert tasks == second_tasks
    assert queue.rows == second_queue.rows


def test_image_only_pdf_enters_low_confidence_queue():
    data = _pdf(text=b"", images=True)
    result, tasks, queue = process_document(data)
    assert result.text_layer_present is False
    assert tasks[0].reason == "LOW_NATIVE_TEXT_CONFIDENCE"
    assert "OCR_LOW_CONFIDENCE" in queue.rows[0]["reasons"]


def test_corrupt_pdf_requires_sandbox_repair():
    corrupt = b"%PDF-1.4\n/Type /Page"
    with pytest.raises(ValueError, match="corrupt PDF"):
        process_document(corrupt)

    repaired, _, _ = process_document(
        corrupt,
        repairer=lambda value: value + b"\n%%EOF",
    )
    assert repaired.repaired is True


def test_redaction_and_perceptual_comparison():
    old, _, _ = process_document(_pdf(redactions=3))
    new, _, _ = process_document(_pdf(redactions=1))
    delta = compare_page_versions(old.pages[0], new.pages[0])
    assert delta["classification"] == "LESS_REDACTED"
    assert delta["redaction_delta"] == -2


def test_raw_receipts_are_stable(tmp_path):
    def transport(url, headers):
        return 200, {}, json.dumps({"rows": [], "has_next": False}).encode()

    adapter = build_adapter(
        "cia_reading_room",
        transport,
        tmp_path,
        explicitly_enabled=True,
        robots_approved=True,
        terms_approved=True,
        limiter=RateLimiter(0),
    )
    list(
        adapter.enumerate_pages(
            lambda body: (json.loads(body)["rows"], False)
        )
    )
    path = tmp_path / "receipts.jsonl"
    adapter.write_receipts(path)
    row = json.loads(path.read_text())
    assert row["adapter_id"] == "cia_reading_room"
    assert len(row["response_sha256"]) == 64

import hashlib
import json
from pathlib import Path

import pytest

from centinelas.releases.adapters import AdapterPolicyError, RateLimiter, build_adapter
from centinelas.releases.parsers import PARSER_REGISTRY, ParserDriftError
from centinelas.releases.processing import process_document
from centinelas.releases.sandbox import (
    EXECUTOR_REGISTRY,
    DocumentSandbox,
    ProcessResult,
    SandboxLimits,
    SandboxOutOfMemory,
    SandboxPolicyError,
    SandboxTimeout,
    ocr_page,
    render_pdf_pages,
    repair_pdf,
)

FIXTURE_PATH = (
    Path(__file__).parent / "fixtures" / "federal_records" / "source_parser_fixtures.json"
)


def _fixtures():
    return {
        key: value.encode()
        for key, value in json.loads(FIXTURE_PATH.read_text()).items()
    }


def _pdf(text=b"", *, image=False):
    page = b"/Type /Page "
    if text:
        page += b"/Font (" + text + b") Tj "
    if image:
        page += b"/Subtype /Image "
    return b"%PDF-1.4\n" + page + b"\n%%EOF"


def _versions(binary):
    by_binary = {spec.binary: spec.pinned_version for spec in EXECUTOR_REGISTRY.values()}
    return by_binary[binary]


def _canonical_digest(rows):
    return hashlib.sha256(
        json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def test_all_source_specific_parsers_use_retained_recorded_shapes():
    fixtures = _fixtures()
    assert set(fixtures) == set(PARSER_REGISTRY)
    for adapter_id, body in fixtures.items():
        rows, has_next = PARSER_REGISTRY[adapter_id](body)
        assert has_next is False
        assert len(rows) == 1
        assert rows[0]["source_key"].startswith(adapter_id + ":")
        assert rows[0]["title"]
        assert rows[0]["detail_url"].startswith("https://")


def test_two_clean_parser_runs_have_identical_normalized_digest():
    body = _fixtures()["nara_catalog"]
    first, _ = PARSER_REGISTRY["nara_catalog"](body)
    second, _ = PARSER_REGISTRY["nara_catalog"](body)
    assert _canonical_digest(first) == _canonical_digest(second)


def test_parser_drift_fails_closed():
    with pytest.raises(ParserDriftError):
        PARSER_REGISTRY["cia_reading_room"](b"<html><body>changed layout</body></html>")
    with pytest.raises(ParserDriftError, match="record array missing"):
        PARSER_REGISTRY["nara_catalog"](b'{"unexpected": []}')


def test_robots_and_terms_denials_remain_mandatory(tmp_path):
    body = _fixtures()["nara_catalog"]
    adapter = build_adapter(
        "nara_catalog",
        lambda _url, _headers: (200, {}, body),
        tmp_path,
        explicitly_enabled=True,
        limiter=RateLimiter(0),
    )
    with pytest.raises(AdapterPolicyError, match="robots"):
        list(adapter.enumerate_pages(PARSER_REGISTRY["nara_catalog"]))

    adapter = build_adapter(
        "nara_catalog",
        lambda _url, _headers: (200, {}, body),
        tmp_path / "terms",
        explicitly_enabled=True,
        robots_approved=True,
        limiter=RateLimiter(0),
    )
    with pytest.raises(AdapterPolicyError, match="terms"):
        list(adapter.enumerate_pages(PARSER_REGISTRY["nara_catalog"]))


def test_executor_registry_is_pinned_and_network_disabled():
    assert set(EXECUTOR_REGISTRY) == {"poppler", "ghostscript", "tesseract"}
    assert all(spec.pinned_version for spec in EXECUTOR_REGISTRY.values())
    assert all(spec.network_disabled for spec in EXECUTOR_REGISTRY.values())


def test_executor_success_receipts_and_reproducible_roundtrip(tmp_path):
    def runner(command, *, input_bytes, limits):
        if command[0] == "tesseract":
            output = b"Puerto Rico map page"
        elif command[0] == "gs":
            output = input_bytes + b"\n%%EOF"
        else:
            output = b"PNG-PAGE"
        return ProcessResult(0, output, b"", 0.2, 1024, False)

    sandbox = DocumentSandbox(runner, version_probe=_versions)
    rendered, render_receipt = render_pdf_pages(sandbox, _pdf(b"Puerto Rico"))
    repaired, repair_receipt = repair_pdf(sandbox, b"%PDF-1.4\n/Type /Page")
    text, confidence, ocr_receipt = ocr_page(sandbox, b"PNG")
    assert rendered == b"PNG-PAGE"
    assert repaired.endswith(b"%%EOF")
    assert text == "Puerto Rico map page"
    assert confidence > 0
    assert all(
        receipt.status == "success" and receipt.version_verified
        for receipt in (render_receipt, repair_receipt, ocr_receipt)
    )
    path = tmp_path / "executor-receipts.jsonl"
    sandbox.write_receipts(path)
    first = path.read_bytes()
    sandbox.write_receipts(path)
    assert path.read_bytes() == first


def test_version_mismatch_and_unapproved_arguments_fail_before_execution():
    called = []

    def runner(command, *, input_bytes, limits):
        called.append(command)
        return ProcessResult(0, b"", b"", 0.0, 0)

    mismatch = DocumentSandbox(runner, version_probe=lambda _binary: "0.0.0")
    with pytest.raises(SandboxPolicyError):
        render_pdf_pages(mismatch, b"pdf")

    sandbox = DocumentSandbox(runner, version_probe=_versions)
    with pytest.raises(SandboxPolicyError):
        sandbox.execute("poppler", b"pdf", ("https://example.invalid/file.pdf",))
    with pytest.raises(SandboxPolicyError):
        sandbox.execute("poppler", b"pdf", ("-png", "INPUT", "OUTPUT"))
    assert called == []


def test_timeout_oom_and_network_attempt_are_rejected():
    timeout = DocumentSandbox(
        lambda command, *, input_bytes, limits: ProcessResult(0, b"", b"", 2.0, 1),
        SandboxLimits(timeout_seconds=1.0),
        version_probe=_versions,
    )
    with pytest.raises(SandboxTimeout):
        render_pdf_pages(timeout, b"pdf")

    oom = DocumentSandbox(
        lambda command, *, input_bytes, limits: ProcessResult(0, b"", b"", 0.1, 4096),
        SandboxLimits(memory_bytes=1024),
        version_probe=_versions,
    )
    with pytest.raises(SandboxOutOfMemory):
        render_pdf_pages(oom, b"pdf")

    network = DocumentSandbox(
        lambda command, *, input_bytes, limits: ProcessResult(0, b"", b"", 0.1, 1, True),
        version_probe=_versions,
    )
    with pytest.raises(SandboxPolicyError):
        render_pdf_pages(network, b"pdf")


def test_corrupt_object_stream_and_page_review_flags():
    corrupt = b"%PDF-1.4\n/ObjStm /Type /Page"
    with pytest.raises(ValueError, match="corrupt PDF"):
        process_document(corrupt)

    image_result, image_tasks, image_queue = process_document(_pdf(image=True))
    assert image_tasks
    assert "OCR_LOW_CONFIDENCE" in image_queue.rows[0]["reasons"]
    assert image_result.text_layer_present is False

    map_result, _, map_queue = process_document(_pdf(b"latitude longitude map legend"))
    assert "MAP_OR_CHART" in map_result.pages[0].flags
    assert "MAP_OR_CHART_REVIEW" in map_queue.rows[0]["reasons"]

    table_result, _, table_queue = process_document(_pdf(b"table column subtotal total"))
    assert "TABLE" in table_result.pages[0].flags
    assert "TABLE_REVIEW" in table_queue.rows[0]["reasons"]

    handwriting_result, _, handwriting_queue = process_document(_pdf(image=True))
    assert "HANDWRITING_POSSIBLE" in handwriting_result.pages[0].flags
    assert "HANDWRITING_REVIEW" in handwriting_queue.rows[0]["reasons"]

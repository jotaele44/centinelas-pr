import hashlib
import json

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


HTML_FIXTURES = {
    "nara_ndc": b'<a class="release" data-id="rg341" href="/declassification/ndc/releases/rg341.pdf">RG 341 release</a>',
    "cia_reading_room": b'<a href="/readingroom/document/cia-rdp-001">Puerto Rico memorandum</a>',
    "nsa_releases": b'<a class="release" href="/Portals/75/documents/news-features/declassified-documents/pr.pdf">NSA release</a>',
    "dia_reading_room": b'<a class="download" href="/FOIA/Documents/pr-report.pdf">DIA report</a>',
    "nhhc": b'<a href="/research/archives/collections/roosevelt-roads.html">Roosevelt Roads collection</a>',
    "doe_aec": b'<a href="/sites/default/files/puerto-rico-nuclear-center.pdf">AEC report</a>',
    "air_force_blue_book": b'<a href="/files/research/blue-book/puerto-rico.pdf">Project Blue Book Puerto Rico</a>',
}


def _nara_catalog_fixture():
    return json.dumps(
        {
            "records": [
                {
                    "naId": "595618",
                    "title": "Puerto Rico command history",
                    "date": "1952",
                    "recordGroupNumber": "341",
                }
            ],
            "next": None,
        }
    ).encode()


def _pdf(text=b"", *, image=False):
    page = b"/Type /Page "
    if text:
        page += b"/Font (" + text + b") Tj "
    if image:
        page += b"/Subtype /Image "
    return b"%PDF-1.4\n" + page + b"\n%%EOF"


def test_all_source_specific_parsers_use_recorded_shapes():
    fixtures = dict(HTML_FIXTURES)
    fixtures["nara_catalog"] = _nara_catalog_fixture()
    assert set(fixtures) == set(PARSER_REGISTRY)
    for adapter_id, body in fixtures.items():
        rows, has_next = PARSER_REGISTRY[adapter_id](body)
        assert has_next is False
        assert len(rows) == 1
        assert rows[0]["source_key"].startswith(adapter_id + ":")
        assert rows[0]["title"]
        assert rows[0]["detail_url"].startswith("https://")


def test_two_clean_parser_runs_have_identical_normalized_digest():
    parser = PARSER_REGISTRY["nara_catalog"]
    first, _ = parser(_nara_catalog_fixture())
    second, _ = parser(_nara_catalog_fixture())
    first_digest = hashlib.sha256(
        json.dumps(first, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    second_digest = hashlib.sha256(
        json.dumps(second, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    assert first_digest == second_digest


def test_parser_drift_fails_closed():
    with pytest.raises(ParserDriftError):
        PARSER_REGISTRY["cia_reading_room"](b"<html><body>changed layout</body></html>")
    with pytest.raises(ParserDriftError, match="record array missing"):
        PARSER_REGISTRY["nara_catalog"](b'{"unexpected": []}')


def test_robots_and_terms_denials_remain_mandatory(tmp_path):
    adapter = build_adapter(
        "nara_catalog",
        lambda _url, _headers: (200, {}, _nara_catalog_fixture()),
        tmp_path,
        explicitly_enabled=True,
        limiter=RateLimiter(0),
    )
    with pytest.raises(AdapterPolicyError, match="robots"):
        list(adapter.enumerate_pages(PARSER_REGISTRY["nara_catalog"]))

    adapter = build_adapter(
        "nara_catalog",
        lambda _url, _headers: (200, {}, _nara_catalog_fixture()),
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


def test_executor_success_receipts_and_roundtrip(tmp_path):
    def runner(command, *, input_bytes, limits):
        if command[0] == "tesseract":
            output = b"Puerto Rico map page"
        elif command[0] == "gs":
            output = input_bytes + b"\n%%EOF"
        else:
            output = b"PNG-PAGE"
        return ProcessResult(0, output, b"", 0.2, 1024, False)

    sandbox = DocumentSandbox(runner)
    rendered, render_receipt = render_pdf_pages(sandbox, _pdf(b"Puerto Rico"))
    repaired, repair_receipt = repair_pdf(sandbox, b"%PDF-1.4\n/Type /Page")
    text, confidence, ocr_receipt = ocr_page(sandbox, b"PNG")
    assert rendered == b"PNG-PAGE"
    assert repaired.endswith(b"%%EOF")
    assert text == "Puerto Rico map page"
    assert confidence > 0
    assert {render_receipt.status, repair_receipt.status, ocr_receipt.status} == {"success"}
    path = tmp_path / "executor-receipts.jsonl"
    sandbox.write_receipts(path)
    assert len(path.read_text().splitlines()) == 3


def test_timeout_oom_and_network_attempt_are_rejected():
    timeout = DocumentSandbox(
        lambda command, *, input_bytes, limits: ProcessResult(0, b"", b"", 2.0, 1),
        SandboxLimits(timeout_seconds=1.0),
    )
    with pytest.raises(SandboxTimeout):
        render_pdf_pages(timeout, b"pdf")

    oom = DocumentSandbox(
        lambda command, *, input_bytes, limits: ProcessResult(0, b"", b"", 0.1, 4096),
        SandboxLimits(memory_bytes=1024),
    )
    with pytest.raises(SandboxOutOfMemory):
        render_pdf_pages(oom, b"pdf")

    network = DocumentSandbox(
        lambda command, *, input_bytes, limits: ProcessResult(0, b"", b"", 0.1, 1, True)
    )
    with pytest.raises(SandboxPolicyError):
        render_pdf_pages(network, b"pdf")


def test_network_bearing_arguments_are_rejected_before_execution():
    called = []

    def runner(command, *, input_bytes, limits):
        called.append(command)
        return ProcessResult(0, b"", b"", 0.0, 0)

    sandbox = DocumentSandbox(runner)
    with pytest.raises(SandboxPolicyError):
        sandbox.execute("poppler", b"pdf", ("https://example.invalid/file.pdf",))
    assert called == []


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

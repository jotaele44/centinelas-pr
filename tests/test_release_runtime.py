from pathlib import Path

from centinelas.releases.models import ReleaseState
from centinelas.releases.runtime import DeltaRun, compare_versions, inspect_binary, run_adapter


def test_binary_inspection_and_version_states():
    pdf = b"%PDF-1.4\n1 0 obj<</Type /Page>>endobj\nBT (Puerto Rico) Tj ET\n/EmbeddedFile"
    info = inspect_binary(pdf, "record.pdf")
    assert info["mime_type"] == "application/pdf"
    assert info["page_count"] == 1
    assert info["text_layer_present"] is True
    assert info["attachment_count"] == 1
    assert compare_versions(None, {"content_sha256": info["content_sha256"]}) == ReleaseState.NEW_DOCUMENT
    old = {"content_sha256": info["content_sha256"], "source_url": "https://old.test/a"}
    new = {"content_sha256": info["content_sha256"], "source_url": "https://new.test/a"}
    assert compare_versions(old, new) == ReleaseState.CORPUS_RELOCATION


def test_adapter_failure_receipt_and_resume(tmp_path: Path):
    checkpoint = tmp_path / "delta.json"
    records = [
        {"source_key": "ok", "source_url": "https://example.test/ok", "filename": "ok.pdf"},
        {"source_key": "bad", "source_url": "https://example.test/bad", "filename": "bad.pdf"},
    ]

    def fetch(url: str) -> bytes:
        if url.endswith("bad"):
            raise OSError("source unavailable")
        return b"%PDF-1.4\n1 0 obj<</Type /Page>>endobj"

    run, health = run_adapter(
        adapter_id="TEST", records=records, fetch=fetch,
        checkpoint_path=checkpoint, max_attempts=2,
    )
    assert health.status == "degraded"
    assert health.acquired == 1 and health.failed == 1
    assert {row.status for row in run.results} == {"ACQUIRED", "FAILED"}
    resumed = DeltaRun.resume(checkpoint)
    assert resumed.completed_keys == {"ok", "bad"}
    rerun, health2 = run_adapter(
        adapter_id="TEST", records=records, fetch=fetch,
        checkpoint_path=checkpoint, max_attempts=2,
    )
    assert len(rerun.results) == 2
    assert health2.attempts == 0

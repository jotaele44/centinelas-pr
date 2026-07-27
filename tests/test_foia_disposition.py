from pathlib import Path

from centinelas.foia_disposition import (
    Destination,
    Disposition,
    DurableOutbox,
    EvidenceTier,
    FOIADispositionEngine,
    FOIAFinding,
    PageCitation,
)


def finding(**overrides):
    data = {
        "finding_id": "finding-1",
        "release_id": "release-1",
        "document_id": "document-1",
        "finding_type": "mixed_content",
        "title": "Aircraft contract and anomalous radar report",
        "summary": "FAA aircraft surveillance contract records an unidentified object near Puerto Rico.",
        "citations": [PageCitation(document_id="document-1", page=4, excerpt="Relevant text")],
        "keywords": ["aircraft", "contract", "unidentified", "Puerto Rico"],
        "evidence_tier": EvidenceTier.T1,
        "extraction_confidence": 0.95,
    }
    data.update(overrides)
    return FOIAFinding(**data)


def test_mixed_content_routes_to_multiple_destinations():
    decisions = FOIADispositionEngine().route(finding())
    destinations = {decision.destination for decision in decisions}
    assert Destination.THEHUB_EVIDENCE in destinations
    assert Destination.THEHUB_INTELLIGENCE in destinations
    assert Destination.OVNIS in destinations
    assert Destination.SKYWATCHER in destinations
    assert Destination.MONEYSWEEP in destinations
    assert Destination.CENTINELAS in destinations


def test_duplicate_release_is_not_propagated():
    decisions = FOIADispositionEngine().route(finding(), duplicate=True)
    assert decisions[0].disposition == Disposition.REJECT_DUPLICATE
    assert decisions[0].destination == Destination.ARCHIVE_ONLY


def test_low_confidence_ocr_requires_review():
    decisions = FOIADispositionEngine().route(finding(extraction_confidence=0.42))
    routed = [d for d in decisions if d.destination == Destination.OVNIS]
    assert routed and routed[0].disposition == Disposition.REVIEW


def test_sensitive_finding_is_held():
    decisions = FOIADispositionEngine().route(finding(sensitive=True))
    assert decisions[0].disposition == Disposition.HOLD_SENSITIVE


def test_no_route_match_is_archive_only():
    item = finding(
        finding_type="administrative",
        title="Transmittal sheet",
        summary="Blank administrative cover page.",
        keywords=[],
    )
    decisions = FOIADispositionEngine().route(item)
    assert any(d.disposition == Disposition.ARCHIVE_ONLY for d in decisions)


def test_outbox_deduplicates_idempotency_key(tmp_path: Path):
    item = finding()
    decision = next(
        d for d in FOIADispositionEngine().route(item) if d.destination == Destination.THEHUB_EVIDENCE
    )
    outbox = DurableOutbox(tmp_path / "foia-outbox.jsonl")
    first = outbox.enqueue(item, decision)
    second = outbox.enqueue(item, decision)
    assert first.idempotency_key == second.idempotency_key
    assert len(outbox.read_all()) == 1

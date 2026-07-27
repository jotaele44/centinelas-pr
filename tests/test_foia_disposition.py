from pathlib import Path

from centinelas.foia_disposition import (
    Destination,
    Disposition,
    DurableOutbox,
    EvidenceTier,
    FOIADispositionEngine,
    FOIAFinding,
    PageCitation,
    ReceiptStatus,
    ReviewQueue,
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


def by_destination(decisions, destination):
    return next(d for d in decisions if d.destination == destination)


def test_mixed_content_routes_to_multiple_destinations():
    destinations = {d.destination for d in FOIADispositionEngine().route(finding())}
    assert {Destination.THEHUB_EVIDENCE, Destination.THEHUB_INTELLIGENCE,
            Destination.OVNIS, Destination.SKYWATCHER,
            Destination.MONEYSWEEP, Destination.CENTINELAS} <= destinations


def test_duplicate_release_is_not_propagated():
    decision = FOIADispositionEngine().route(finding(), duplicate=True)[0]
    assert decision.disposition == Disposition.REJECT_DUPLICATE
    assert decision.destination == Destination.ARCHIVE_ONLY


def test_low_confidence_ocr_requires_review():
    decision = by_destination(FOIADispositionEngine().route(
        finding(extraction_confidence=0.42)), Destination.OVNIS)
    assert decision.disposition == Disposition.REVIEW


def test_sensitive_finding_is_held():
    assert FOIADispositionEngine().route(finding(sensitive=True))[0].disposition == Disposition.HOLD_SENSITIVE


def test_no_route_match_is_archive_only():
    item = finding(finding_type="administrative", title="Transmittal sheet",
                   summary="Blank administrative cover page.", keywords=[])
    assert any(d.disposition == Disposition.ARCHIVE_ONLY
               for d in FOIADispositionEngine().route(item))


def test_aguayluz_route():
    item = finding(title="LUMA grid release", summary="PREPA reservoir and utility records",
                   keywords=["LUMA", "PREPA", "reservoir"])
    assert by_destination(FOIADispositionEngine().route(item), Destination.AGUAYLUZ)


def test_spiderweb_entity_collision_requires_review():
    item = finding(title="Registered agent relationship", summary="Corporate officer relationship",
                   keywords=["registered agent", "officer"], entity_collision=True)
    decision = by_destination(FOIADispositionEngine().route(item), Destination.SPIDERWEB)
    assert decision.disposition == Disposition.REVIEW
    assert "ENTITY_COLLISION" in decision.reason_codes


def test_semantic_score_is_clamped_and_cannot_create_route():
    engine = FOIADispositionEngine(semantic_scorer=lambda _finding, _destination: 9.0)
    decisions = engine.route(finding(title="Administrative sheet", summary="No topic", keywords=[]))
    assert all(0 <= d.score <= 1 for d in decisions)
    assert not any(d.destination == Destination.SPIDERWEB for d in decisions)


def test_invalid_threshold_order_rejected():
    try:
        FOIADispositionEngine(export_threshold=0.4, review_threshold=0.8)
    except ValueError:
        pass
    else:
        raise AssertionError("invalid threshold order accepted")


def test_outbox_ack_failure_retry_and_dedup(tmp_path: Path):
    item = finding()
    decision = by_destination(FOIADispositionEngine().route(item), Destination.THEHUB_EVIDENCE)
    outbox = DurableOutbox(tmp_path / "foia-outbox.jsonl")
    first = outbox.enqueue(item, decision)
    second = outbox.enqueue(item, decision)
    assert first.idempotency_key == second.idempotency_key
    assert len(outbox.read_all()) == 1

    failed = outbox.record_attempt(first.idempotency_key, error="timeout")
    assert failed.status == ReceiptStatus.FAILED
    assert len(outbox.retryable()) == 1

    acknowledged = outbox.record_attempt(first.idempotency_key, downstream_record_id="record-7")
    assert acknowledged.status == ReceiptStatus.ACKNOWLEDGED
    assert acknowledged.attempts == 2
    assert acknowledged.downstream_record_id == "record-7"
    assert outbox.retryable() == []


def test_review_queue_deduplicates(tmp_path: Path):
    item = finding(extraction_confidence=0.4)
    engine = FOIADispositionEngine()
    review = engine.build_review_case(item, engine.route(item))
    assert review is not None
    queue = ReviewQueue(tmp_path / "review.jsonl")
    queue.enqueue(review)
    queue.enqueue(review)
    assert len(queue.read_all()) == 1


def test_superseding_decision_is_reversible():
    engine = FOIADispositionEngine()
    prior = by_destination(engine.route(finding()), Destination.OVNIS)
    replacement = engine.supersede(prior, disposition=Disposition.ARCHIVE_ONLY,
                                   reason_codes=["HUMAN_ADJUDICATION"])
    assert replacement.supersedes_decision_id == prior.decision_id
    assert replacement.reversible is True

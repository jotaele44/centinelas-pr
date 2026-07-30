from datetime import datetime, timezone

import pytest

from centinelas.water_disruption import SourceRecord, WaterDisruptionProducer


def service(tmp_path):
    return WaterDisruptionProducer(tmp_path, [
        SourceRecord("prasa", "PRASA", "utility", "T1", "public water", (), ()),
        SourceRecord("social", "Social", "social", "T3", "eyewitness", (), ()),
    ])


def test_requires_complete_source_accounting(tmp_path):
    producer = service(tmp_path)
    with pytest.raises(ValueError, match="incomplete_source_accounting"):
        producer.record_run("RUN-1", {"prasa": "success"})
    result = producer.record_run("RUN-1", {"prasa": "success", "social": "blocked"})
    assert result["coverage"] == 1.0


def test_append_only_evidence_and_replay_stability(tmp_path):
    producer = service(tmp_path)
    when = datetime(2026, 7, 30, 12, tzinfo=timezone.utc)
    first = producer.capture_evidence("prasa", "https://example.test/a", "Avería", "Tubería rota en Caguas", when)
    second = producer.capture_evidence("prasa", "https://example.test/a", "Avería", "Tubería rota en Caguas", when)
    assert first["evidence_id"] == second["evidence_id"]
    assert len(producer.store.read("raw_evidence")) == 1


def test_candidate_is_always_candidate_and_dedup_is_deterministic(tmp_path):
    producer = service(tmp_path)
    when = datetime(2026, 7, 30, 12, tzinfo=timezone.utc)
    evidence = producer.capture_evidence("prasa", "https://example.test/a", "Interrupción", "Sin agua por avería", when)
    one = producer.extract_candidate(evidence, ["Caguas"], "main-1")
    two = producer.extract_candidate(evidence, ["Caguas"], "main-1")
    assert one == two
    assert one["truth_state"] == "candidate"
    assert one["confidence"]["overall"] <= 1


def test_private_plumbing_is_excluded(tmp_path):
    producer = service(tmp_path)
    when = datetime(2026, 7, 30, 12, tzinfo=timezone.utc)
    evidence = producer.capture_evidence("social", "https://example.test/b", "Sin agua", "Problema de plomería del edificio", when)
    assert producer.extract_candidate(evidence, ["San Juan"]) is None


def test_outbox_idempotency_and_non_destructive_retraction(tmp_path):
    producer = service(tmp_path)
    when = datetime(2026, 7, 30, 12, tzinfo=timezone.utc)
    evidence = producer.capture_evidence("prasa", "https://example.test/a", "Interrupción", "Sin agua", when)
    candidate = producer.extract_candidate(evidence, ["Caguas"])
    first = producer.dispatch(candidate["candidate_id"], "KEY-1")
    second = producer.dispatch(candidate["candidate_id"], "KEY-1")
    assert first == second
    assert first["status"] == "shadow_queued"
    assert first["notifications_enabled"] is False
    retraction = producer.retract(candidate["candidate_id"], "wrong municipality", "RET-1")
    assert retraction["destructive"] is False
    assert len(producer.store.read("raw_evidence")) == 1

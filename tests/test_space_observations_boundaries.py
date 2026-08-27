import copy

import pytest

from centinelas.space_observations import IntakeEngine
from centinelas.space_observations.retry import retry_failed
from centinelas.space_observations.routing import route_to_embedded_producer
from tests.space_observations_helpers import qualified_lead


def test_route_bridge_is_immutable_and_rejects_unrelated_routes():
    source = qualified_lead()
    before = copy.deepcopy(source)
    routed = route_to_embedded_producer(source)
    assert source == before
    assert routed is not source
    assert routed["downstream_route"]["primary"] == "centinelas-space-observations"

    unrelated = qualified_lead()
    unrelated["downstream_route"]["primary"] = "moneysweep-pr"
    with pytest.raises(ValueError, match="unrelated primary route"):
        route_to_embedded_producer(unrelated)


def test_route_bridge_is_idempotent_and_revalidates_embedded_routes():
    routed = route_to_embedded_producer(qualified_lead())
    replay = route_to_embedded_producer(routed)
    assert replay == routed
    assert replay is not routed
    assert replay["downstream_route"] is not routed["downstream_route"]

    unqualified = qualified_lead(identity="unqualified")
    unqualified["review_status"] = "new"
    with pytest.raises(ValueError, match="only accepts qualified"):
        route_to_embedded_producer(unqualified)

    tampered = route_to_embedded_producer(qualified_lead(identity="tampered"))
    tampered["downstream_route"]["unreviewed_extension"] = True
    with pytest.raises(ValueError, match="embedded route fields"):
        route_to_embedded_producer(tampered)


def test_failed_target_only_retry_selects_retryable_rows(tmp_path):
    retryable = route_to_embedded_producer(qualified_lead(identity="retryable"))
    unrelated = route_to_embedded_producer(qualified_lead(identity="unrelated"))
    engine = IntakeEngine(tmp_path, production=True)
    engine.failures.record(
        {
            "run_id": "failed-run",
            "lead_id": retryable["lead_id"],
            "failure_class": "INTAKE_INTERNAL_ERROR",
            "detail": "transient fixture",
            "retryable": True,
        }
    )
    engine.failures.record(
        {
            "run_id": "failed-run",
            "lead_id": unrelated["lead_id"],
            "failure_class": "INVALID_SCHEMA",
            "detail": "permanent fixture",
            "retryable": False,
        }
    )

    results = retry_failed(
        engine,
        [retryable, unrelated],
        failed_run_id="failed-run",
        retry_run_id="retry-run",
    )
    assert len(results) == 1
    assert results[0].acknowledgement["lead_id"] == retryable["lead_id"]
    assert results[0].disposition == "accepted"

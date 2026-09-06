from __future__ import annotations

from datetime import datetime, timezone

import pytest

from centinelas.classify import classifier
from centinelas.classify.labels import DomainLabel
from centinelas.models import RawItem


def _item(title: str, body: str = "") -> RawItem:
    now = datetime(2026, 9, 6, tzinfo=timezone.utc)
    return RawItem(
        item_id="classifier-mode-fixture",
        source_url="https://example.test/item",
        source_name="fixture",
        title=title,
        body_text=body,
        published_at=now,
        captured_at=now,
    )


def test_default_local_mode_never_imports_hosted_client(monkeypatch) -> None:
    monkeypatch.delenv("CENTINELAS_CLASSIFIER_MODE", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    def forbidden_import(name: str):
        raise AssertionError(f"hosted import attempted: {name}")

    monkeypatch.setattr(classifier.importlib, "import_module", forbidden_import)
    labels, confidence, reasoning = classifier.classify(
        _item("Company awarded a construction contract")
    )

    assert labels == [DomainLabel.FINANCIAL]
    assert confidence == 0.70
    assert reasoning.startswith("LOCAL_RULES:")


def test_no_local_match_is_explicitly_unclassified(monkeypatch) -> None:
    monkeypatch.delenv("CENTINELAS_CLASSIFIER_MODE", raising=False)
    labels, confidence, reasoning = classifier.classify(
        _item("Neighborhood restaurant updates its lunch menu")
    )
    assert labels == [DomainLabel.UNCLASSIFIED]
    assert confidence == 0.30
    assert reasoning == "LOCAL_RULES: no domain rule matched."


def test_unknown_classifier_mode_fails_closed(monkeypatch) -> None:
    monkeypatch.setenv("CENTINELAS_CLASSIFIER_MODE", "automatic")
    with pytest.raises(ValueError, match="CENTINELAS_CLASSIFIER_MODE"):
        classifier.classify(_item("SEC files charges"))


def test_explicit_hosted_mode_merges_local_labels_deterministically(monkeypatch) -> None:
    monkeypatch.setenv("CENTINELAS_CLASSIFIER_MODE", "anthropic")
    monkeypatch.setattr(
        classifier,
        "_llm_classify",
        lambda _title, _body: (
            [DomainLabel.POLITICAL],
            0.91,
            "Government policy context.",
        ),
    )

    labels, confidence, reasoning = classifier.classify(
        _item("Government awards major infrastructure contract")
    )

    assert labels[0] == DomainLabel.POLITICAL
    assert DomainLabel.FINANCIAL in labels
    assert confidence == 0.91
    assert reasoning.startswith("HOSTED_OPTIONAL:anthropic:")


def test_hosted_failure_retains_local_authority_without_exception_text(monkeypatch) -> None:
    monkeypatch.setenv("CENTINELAS_CLASSIFIER_MODE", "anthropic")
    monkeypatch.delenv("CENTINELAS_HOSTED_CLASSIFIER_FAILURE_POLICY", raising=False)

    def fail(_title: str, _body: str):
        raise RuntimeError("sensitive provider diagnostic")

    monkeypatch.setattr(classifier, "_llm_classify", fail)
    labels, confidence, reasoning = classifier.classify(
        _item("The SEC announced an enforcement action")
    )

    assert labels == [DomainLabel.FINANCIAL]
    assert confidence == 0.70
    assert "HOSTED_OPTIONAL_UNAVAILABLE:RuntimeError" in reasoning
    assert "sensitive provider diagnostic" not in reasoning


def test_explicit_fail_closed_policy_propagates_typed_failure(monkeypatch) -> None:
    monkeypatch.setenv("CENTINELAS_CLASSIFIER_MODE", "anthropic")
    monkeypatch.setenv("CENTINELAS_HOSTED_CLASSIFIER_FAILURE_POLICY", "fail_closed")
    monkeypatch.setattr(
        classifier,
        "_llm_classify",
        lambda _title, _body: (_ for _ in ()).throw(RuntimeError("provider down")),
    )

    with pytest.raises(classifier.HostedClassifierUnavailable, match="RuntimeError"):
        classifier.classify(_item("The SEC announced an enforcement action"))


def test_hosted_result_schema_rejects_invalid_confidence() -> None:
    with pytest.raises(classifier.HostedClassifierUnavailable, match="confidence"):
        classifier._validate_hosted_result(
            {
                "labels": ["FINANCIAL"],
                "confidence": 1.5,
                "reasoning": "invalid fixture",
            }
        )

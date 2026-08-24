"""Tests for life-safety urgency tagging (is_critical) on dispatched signals."""

from datetime import datetime, timezone

from centinelas.classify.labels import DomainLabel
from centinelas.classify.rules import is_critical_signal
from centinelas.models import ClassifiedItem
from centinelas.route.router import build_payload, route


def _classified(title, body="", labels=None):
    return ClassifiedItem(
        item_id="u1", source_url="https://example.pr/x", source_name="Test",
        title=title, body_text=body,
        published_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
        captured_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
        labels=labels or [DomainLabel.ENVIRONMENTAL], confidence=0.8,
    )


def test_urgency_keywords_detected_english_and_spanish():
    assert is_critical_signal("Mandatory evacuation ordered for coastal zone")
    assert is_critical_signal("Emergencia: hervir el agua en Ponce")
    assert is_critical_signal("Aviso de huracán categoría 4")
    assert is_critical_signal("Tsunami warning issued")


def test_non_urgent_signal_is_not_critical():
    assert not is_critical_signal("Public hearing scheduled on water tariff")
    assert not is_critical_signal("PRASA announces routine maintenance next month")


def test_payload_carries_is_critical_true():
    item = _classified("Boil water emergency in Bayamón", body="hervir el agua ahora")
    payload = build_payload(item, "aguayluz-pr")
    assert payload["is_critical"] is True


def test_payload_is_critical_false_for_routine():
    item = _classified("Water tariff public comment period opens")
    payload = build_payload(item, "aguayluz-pr")
    assert payload["is_critical"] is False


def test_route_stamps_is_critical_on_all_targets():
    item = _classified("Evacuation ordered: dam failure risk at Carraízo")
    payloads = route(item)
    assert payloads  # at least the hub + a domain repo
    assert all(p["is_critical"] is True for p in payloads.values())

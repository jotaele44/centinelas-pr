"""Fail-closed production input guards for the Centinelas federation export."""
from __future__ import annotations

from datetime import datetime, timezone

from scripts.federation_export import production_input_errors

NOW = datetime(2026, 8, 9, 15, 0, tzinfo=timezone.utc)


def test_production_rejects_empty_live_ledger() -> None:
    errors = production_input_errors([], now=NOW, max_age_hours=168.0)
    assert errors == ["production export rejects an empty live signal ledger"]


def test_production_rejects_stale_live_ledger() -> None:
    signals = [{"captured_at": "2026-07-12T23:04:32+00:00", "is_synthetic": False}]
    errors = production_input_errors(signals, now=NOW, max_age_hours=168.0)
    assert len(errors) == 1
    assert "ledger is stale" in errors[0]


def test_production_accepts_fresh_live_ledger() -> None:
    signals = [{"captured_at": "2026-08-09T14:30:00Z", "is_synthetic": False}]
    assert production_input_errors(signals, now=NOW, max_age_hours=168.0) == []


def test_production_rejects_missing_or_invalid_capture_time() -> None:
    for value in (None, "", "not-a-date"):
        errors = production_input_errors(
            [{"captured_at": value, "is_synthetic": False}],
            now=NOW,
            max_age_hours=168.0,
        )
        assert len(errors) == 1
        assert "missing or invalid captured_at" in errors[0]


def test_production_rejects_future_capture_time() -> None:
    signals = [{"captured_at": "2026-08-09T18:00:00Z", "is_synthetic": False}]
    errors = production_input_errors(signals, now=NOW, max_age_hours=168.0)
    assert len(errors) == 1
    assert "in the future" in errors[0]


def test_production_rejects_nonpositive_max_age() -> None:
    signals = [{"captured_at": "2026-08-09T14:30:00Z", "is_synthetic": False}]
    errors = production_input_errors(signals, now=NOW, max_age_hours=0)
    assert errors == ["--max-age-hours must be greater than zero in production mode"]

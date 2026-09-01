from __future__ import annotations

from datetime import datetime, timezone

from scripts.federation_export import _production_input_errors

NOW = datetime(2026, 8, 9, 15, 0, tzinfo=timezone.utc)


def test_production_rejects_empty_live_ledger() -> None:
    assert _production_input_errors([], now=NOW, max_age_hours=168.0) == [
        "production export rejects an empty live signal ledger"
    ]


def test_production_rejects_stale_live_ledger() -> None:
    errors = _production_input_errors(
        [{"captured_at": "2026-07-12T23:04:32+00:00"}],
        now=NOW,
        max_age_hours=168.0,
    )
    assert len(errors) == 1
    assert "ledger is stale" in errors[0]


def test_production_accepts_fresh_live_ledger() -> None:
    signals = [{"captured_at": "2026-08-09T14:30:00Z"}]
    assert _production_input_errors(signals, now=NOW, max_age_hours=168.0) == []


def test_production_rejects_missing_invalid_or_future_capture_time() -> None:
    for value in (None, "", "not-a-date"):
        errors = _production_input_errors(
            [{"captured_at": value}], now=NOW, max_age_hours=168.0
        )
        assert "missing or invalid captured_at" in errors[0]

    future = _production_input_errors(
        [{"captured_at": "2026-08-09T18:00:00Z"}],
        now=NOW,
        max_age_hours=168.0,
    )
    assert "in the future" in future[0]


def test_production_rejects_nonpositive_max_age() -> None:
    signals = [{"captured_at": "2026-08-09T14:30:00Z"}]
    assert _production_input_errors(signals, now=NOW, max_age_hours=0) == [
        "--max-age-hours must be greater than zero in production mode"
    ]

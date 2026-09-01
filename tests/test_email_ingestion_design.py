from datetime import datetime, timezone
from pathlib import Path

import pytest

from centinelas.ingest.email import (
    EmailSourceProfile,
    JsonlIdentityLedger,
    accepted_result_to_raw_item,
    canonicalize_url,
    normalize_rfc822,
    parse_google_alert_results,
)


RAW = b"""From: Google Alerts <googlealerts-noreply@google.com>\r
To: operator@example.test\r
Bcc: hidden@example.test\r
Subject: Puerto Rico infrastructure\r
Message-ID: <fixture-1@example.test>\r
Content-Type: text/html; charset=utf-8\r
\r
<html><body><h2>Agency notice</h2><a href=\"https://example.gov/notice?utm_source=alerts\">Notice</a><img src=\"https://tracker.invalid/pixel\"><script>bad()</script></body></html>
"""


def test_profile_is_disabled_and_private() -> None:
    profile = EmailSourceProfile(
        source_profile_id="google_alerts_primary",
        account_alias="fixture",
        gmail_search="from:(googlealerts-noreply@google.com)",
    )
    profile.assert_safe()
    assert profile.enabled is False
    assert profile.auto_promote is False
    assert profile.federation_export_allowed is False


def test_unsafe_profile_is_rejected() -> None:
    profile = EmailSourceProfile(
        source_profile_id="unsafe",
        account_alias="fixture",
        gmail_search="all",
        enabled=True,
    )
    with pytest.raises(ValueError, match="disabled"):
        profile.assert_safe()


def test_normalization_blocks_remote_content_and_marks_bcc() -> None:
    record = normalize_rfc822(
        RAW,
        account_alias="fixture",
        source_profile_id="google_alerts_primary",
        run_id="run-1",
        provider_message_id="gmail-1",
        fetched_at=datetime(2026, 8, 4, tzinfo=timezone.utc),
    )
    assert "tracker.invalid" not in record.sanitized_text
    assert "bad()" not in record.sanitized_text
    assert record.recipients_bcc_present is True
    assert record.federation_export_allowed is False


def test_alert_requires_operator_acceptance() -> None:
    record = normalize_rfc822(
        RAW,
        account_alias="fixture",
        source_profile_id="google_alerts_primary",
        run_id="run-1",
        provider_message_id="gmail-1",
    )
    results = parse_google_alert_results(record)
    assert len(results) == 1
    assert results[0].displayed_title == "Notice"
    assert results[0].displayed_url == "https://example.gov/notice?utm_source=alerts"
    assert "tracker.invalid" not in results[0].displayed_url
    with pytest.raises(ValueError, match="operator acceptance"):
        accepted_result_to_raw_item(results[0], record)
    accepted = results[0].model_copy(update={"review_status": "accepted_as_lead"})
    raw, lineage = accepted_result_to_raw_item(accepted, record)
    assert raw.evidence_tier == "T4"
    assert lineage.auto_promoted is False
    assert "utm_source" not in raw.source_url


def test_durable_exact_identity_ledger(tmp_path: Path) -> None:
    ledger = JsonlIdentityLedger(tmp_path / "seen.jsonl")
    assert not ledger.contains("fixture", "gmail-1")
    ledger.append("fixture", "gmail-1", "run-1")
    assert ledger.contains("fixture", "gmail-1")


def test_url_canonicalization_strips_tracking() -> None:
    assert canonicalize_url("HTTPS://EXAMPLE.GOV//a?utm_source=x&id=4#fragment") == "https://example.gov/a?id=4"

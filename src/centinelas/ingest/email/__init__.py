"""Feature-disabled email discovery adapter."""

from .adapter import EmailSourceProfile, GmailClientProtocol, JsonlIdentityLedger, OfflineFakeGmailClient
from .models import AlertResultRecord, EmailMessageRecord, GmailSyncCheckpoint, GmailSyncReceipt, RawItemLineage
from .processing import accepted_result_to_raw_item, canonicalize_url, normalize_rfc822, parse_google_alert_results

__all__ = [
    "AlertResultRecord", "EmailMessageRecord", "EmailSourceProfile", "GmailClientProtocol",
    "GmailSyncCheckpoint", "GmailSyncReceipt", "JsonlIdentityLedger", "OfflineFakeGmailClient",
    "RawItemLineage", "accepted_result_to_raw_item", "canonicalize_url", "normalize_rfc822",
    "parse_google_alert_results",
]

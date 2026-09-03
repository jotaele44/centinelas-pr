"""Private email-ingestion records.

These models are source records, not verified Centinelas signals. Public export is
explicitly denied by default and callers must derive a redacted RawItem through
``conversion.py`` after operator acceptance.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class EmailAttachmentRecord(BaseModel):
    schema_version: Literal["email_attachment_record.v0.1"] = "email_attachment_record.v0.1"
    attachment_record_id: str
    email_record_id: str
    provider_attachment_id: str | None = None
    filename_original: str | None = None
    filename_sanitized: str
    mime_type_declared: str | None = None
    mime_type_detected: str | None = None
    size_bytes: int = Field(ge=0)
    content_sha256: str | None = None
    disposition: Literal["attachment", "inline", "unknown"] = "unknown"
    malware_scan_status: Literal["not_scanned", "clean", "suspicious", "blocked", "scan_failed"] = "not_scanned"
    extraction_status: Literal["not_requested", "queued", "extracted", "unsupported", "failed"] = "not_requested"
    federation_export_allowed: bool = False


class EmailMessageRecord(BaseModel):
    schema_version: Literal["email_message_record.v0.1"] = "email_message_record.v0.1"
    email_record_id: str
    provider: Literal["gmail"] = "gmail"
    account_alias: str
    provider_message_id: str
    provider_thread_id: str | None = None
    internet_message_id: str | None = None
    history_id: str | None = None
    subject: str = ""
    sender_name: str | None = None
    sender_address: str
    reply_to: list[str] = Field(default_factory=list)
    recipients_to: list[str] = Field(default_factory=list)
    recipients_cc: list[str] = Field(default_factory=list)
    recipients_bcc_present: bool = False
    provider_internal_date: datetime
    header_date: datetime | None = None
    fetched_at: datetime
    label_ids: list[str] = Field(default_factory=list)
    label_names: list[str] = Field(default_factory=list)
    unread: bool = False
    starred: bool = False
    spam: bool = False
    trash: bool = False
    mime_type: str = "message/rfc822"
    text_plain: str | None = None
    text_html: str | None = None
    sanitized_text: str = ""
    snippet: str | None = None
    raw_rfc822_sha256: str | None = None
    normalized_envelope_sha256: str
    normalized_content_sha256: str
    attachment_manifest_sha256: str | None = None
    source_profile_id: str
    ingestion_run_id: str
    processing_status: Literal["fetched", "normalized", "duplicate", "filtered", "review_pending", "converted", "failed"] = "fetched"
    failure_code: str | None = None
    failure_detail: str | None = None
    contains_personal_mailbox_data: bool = True
    federation_export_allowed: bool = False
    retention_class: Literal["metadata_only", "normalized_content", "raw_message_retained"] = "normalized_content"

    @field_validator("federation_export_allowed")
    @classmethod
    def private_by_default(cls, value: bool) -> bool:
        if value:
            raise ValueError("raw email records cannot be federation-exportable")
        return value


class AlertResultRecord(BaseModel):
    schema_version: Literal["alert_result_record.v0.1"] = "alert_result_record.v0.1"
    alert_result_id: str
    email_record_id: str
    alert_name: str | None = None
    result_position: int = Field(ge=0)
    displayed_title: str
    displayed_url: str | None = None
    resolved_url: str | None = None
    displayed_source_name: str | None = None
    excerpt: str | None = None
    result_published_at_text: str | None = None
    result_published_at: datetime | None = None
    parser_name: str = "google_alerts_offline"
    parser_version: str = "0.1.0"
    parse_confidence: float = Field(ge=0.0, le=1.0)
    link_resolution_status: Literal["not_attempted", "resolved", "blocked", "invalid", "failed"] = "not_attempted"
    review_status: Literal["unreviewed", "accepted_as_lead", "duplicate", "irrelevant", "rejected"] = "unreviewed"


class RawItemLineage(BaseModel):
    schema_version: Literal["raw_item_lineage.v0.1"] = "raw_item_lineage.v0.1"
    raw_item_id: str
    source_adapter: Literal["gmail"] = "gmail"
    source_record_type: Literal["alert_result"] = "alert_result"
    source_record_id: str
    source_message_id_hash: str
    ingestion_run_id: str
    derivation_version: str = "0.1.0"
    operator_accepted: bool
    auto_promoted: Literal[False] = False


class GmailSyncCheckpoint(BaseModel):
    schema_version: Literal["gmail_sync_checkpoint.v0.1"] = "gmail_sync_checkpoint.v0.1"
    source_profile_id: str
    account_alias: str
    last_successful_history_id: str | None = None
    last_successful_sync_at: datetime | None = None
    last_reconciliation_at: datetime | None = None
    last_run_id: str | None = None
    consecutive_failures: int = Field(default=0, ge=0)


class GmailSyncReceipt(BaseModel):
    schema_version: Literal["gmail_sync_receipt.v0.1"] = "gmail_sync_receipt.v0.1"
    run_id: str
    source_profile_id: str
    started_at: datetime
    completed_at: datetime
    mode: Literal["dry_run", "incremental_history", "bounded_reconciliation"]
    query_sha256: str
    checkpoint_before_hash: str
    checkpoint_after_hash: str
    messages_discovered: int = Field(ge=0)
    messages_fetched: int = Field(ge=0)
    messages_normalized: int = Field(ge=0)
    messages_duplicate: int = Field(ge=0)
    alert_results_created: int = Field(ge=0)
    raw_items_created: int = Field(ge=0)
    review_items_created: int = Field(ge=0)
    failures: int = Field(ge=0)
    private_manifest_sha256: str
    public_summary_sha256: str
    status: Literal["success", "partial", "failed"]

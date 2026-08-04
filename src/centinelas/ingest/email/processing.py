"""Offline MIME normalization, Google Alert extraction, URL hygiene, and conversion."""
from __future__ import annotations

import hashlib
import html
import re
from datetime import datetime, timezone
from email import policy
from email.parser import BytesParser
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from bs4 import BeautifulSoup

from centinelas.models import RawItem

from .models import AlertResultRecord, EmailMessageRecord, RawItemLineage

_TRACKING = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "gclid", "fbclid", "mc_cid", "mc_eid"}


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def canonicalize_url(value: str) -> str:
    parsed = urlparse(value.strip())
    query = urlencode([(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True) if k.lower() not in _TRACKING])
    return urlunparse((parsed.scheme.lower(), parsed.netloc.lower(), re.sub(r"/{2,}", "/", parsed.path), "", query, ""))


def sanitize_html(value: str) -> str:
    soup = BeautifulSoup(value, "html.parser")
    for node in soup(["script", "style", "img", "iframe", "object", "embed"]):
        node.decompose()
    return "\n".join(line.strip() for line in soup.get_text("\n").splitlines() if line.strip())


def normalize_rfc822(raw: bytes, *, account_alias: str, source_profile_id: str, run_id: str, provider_message_id: str, fetched_at: datetime | None = None) -> EmailMessageRecord:
    message = BytesParser(policy=policy.default).parsebytes(raw)
    plain_parts: list[str] = []
    html_parts: list[str] = []
    for part in message.walk():
        if part.get_content_disposition() == "attachment":
            continue
        if part.get_content_type() == "text/plain":
            plain_parts.append(part.get_content())
        elif part.get_content_type() == "text/html":
            html_parts.append(part.get_content())
    plain = "\n".join(plain_parts) or None
    html_body = "\n".join(html_parts) or None
    sanitized = plain or sanitize_html(html_body or "")
    sender = message.get("From", "unknown@example.invalid")
    envelope = "|".join([message.get("Message-ID", ""), message.get("Subject", ""), sender])
    return EmailMessageRecord(
        email_record_id=sha256_text(f"{account_alias}|{provider_message_id}")[:24],
        account_alias=account_alias,
        provider_message_id=provider_message_id,
        internet_message_id=message.get("Message-ID"),
        subject=message.get("Subject", ""),
        sender_address=sender,
        recipients_bcc_present=message.get("Bcc") is not None,
        provider_internal_date=fetched_at or datetime.now(timezone.utc),
        fetched_at=fetched_at or datetime.now(timezone.utc),
        text_plain=plain,
        text_html=html_body,
        sanitized_text=sanitized,
        raw_rfc822_sha256=hashlib.sha256(raw).hexdigest(),
        normalized_envelope_sha256=sha256_text(envelope),
        normalized_content_sha256=sha256_text(sanitized),
        source_profile_id=source_profile_id,
        ingestion_run_id=run_id,
        processing_status="normalized",
    )


def parse_google_alert_results(record: EmailMessageRecord) -> list[AlertResultRecord]:
    """Template-tolerant offline parser: each absolute URL line becomes a review lead."""
    text = html.unescape(record.sanitized_text)
    urls = re.findall(r"https?://[^\s<>\"]+", text)
    results: list[AlertResultRecord] = []
    for position, observed in enumerate(dict.fromkeys(urls)):
        url = canonicalize_url(observed.rstrip(".,);"))
        if not url:
            continue
        preceding = text[: text.find(observed)].splitlines()
        title = next((line.strip() for line in reversed(preceding) if line.strip()), record.subject)
        results.append(AlertResultRecord(
            alert_result_id=sha256_text(f"{record.email_record_id}|{position}|{url}")[:24],
            email_record_id=record.email_record_id,
            result_position=position,
            displayed_title=title[:500],
            displayed_url=observed,
            resolved_url=url,
            displayed_source_name=urlparse(url).netloc,
            excerpt=None,
            parse_confidence=0.70,
            link_resolution_status="resolved",
        ))
    return results


def accepted_result_to_raw_item(result: AlertResultRecord, message: EmailMessageRecord) -> tuple[RawItem, RawItemLineage]:
    if result.review_status != "accepted_as_lead":
        raise ValueError("operator acceptance is required before RawItem conversion")
    url = result.resolved_url or result.displayed_url
    if not url:
        raise ValueError("accepted result requires a source URL")
    published_at = result.result_published_at or message.header_date or message.provider_internal_date
    raw = RawItem(
        item_id=RawItem.make_id(canonicalize_url(url), published_at),
        source_url=canonicalize_url(url),
        source_name=result.displayed_source_name or "Google Alerts",
        title=result.displayed_title,
        body_text=result.excerpt or "",
        published_at=published_at,
        captured_at=message.fetched_at,
        evidence_tier="T4",
    )
    lineage = RawItemLineage(
        raw_item_id=raw.item_id,
        source_record_id=result.alert_result_id,
        source_message_id_hash=sha256_text(message.provider_message_id),
        ingestion_run_id=message.ingestion_run_id,
        operator_accepted=True,
    )
    return raw, lineage

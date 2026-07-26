"""Discovery-only space and remote-sensing pipeline for Centinelas."""
from __future__ import annotations

import hashlib
import json
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urljoin, urlsplit, urlunsplit

CATEGORY = "SPACE_AND_REMOTE_SENSING"
SUBCATEGORIES = frozenset({
    "SATELLITE_DATASET_RELEASE", "MISSION_ARCHIVE_RELEASE", "DECLASSIFIED_SPACE_RECORD",
    "ORBITAL_EPHEMERIS_UPDATE", "WEATHER_SATELLITE_ARCHIVE", "INFRARED_SENSOR_RECORD",
    "SHUTTLE_VIDEO_OR_TELEMETRY", "SPACE_SURVEILLANCE_RECORD", "FOIA_READING_ROOM_RELEASE",
    "SCIENTIFIC_REPROCESSING",
})
FORBIDDEN_CONFIRMATION = re.compile(r"\b(confirm(?:s|ed|ation)?|proves?|verified uap|alien craft)\b", re.I)
MAX_CAPTURE_BYTES = 2_000_000


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical_url(url: str) -> str:
    parts = urlsplit(url.strip())
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        raise ValueError(f"unsupported URL: {url!r}")
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path or "/", parts.query, ""))


def idempotency_key(item: dict[str, Any]) -> str:
    material = "|".join(str(item.get(k) or "") for k in
                        ("canonical_url", "catalog_identifier", "dataset_version", "published_at"))
    return sha256_bytes(material.encode())


def validate_lead(lead: dict[str, Any]) -> None:
    required = {
        "lead_id", "category", "subcategory", "source_id", "source_url", "discovered_at",
        "title", "discovery_provenance", "access_status", "temporal_coverage",
        "geographic_coverage", "sensor", "potential_case_links", "downstream_route",
        "evidence_tier", "confidence_score", "review_status", "content_fingerprint",
    }
    missing = sorted(required - lead.keys())
    if missing:
        raise ValueError(f"missing required fields: {missing}")
    if lead["category"] != CATEGORY or lead["subcategory"] not in SUBCATEGORIES:
        raise ValueError("invalid category or subcategory")
    if lead.get("raw_binary_storage_prohibited") is not True:
        raise ValueError("raw binary storage prohibition must be true")
    if lead.get("confirmation_claim_prohibited") is not True:
        raise ValueError("confirmation claim prohibition must be true")
    if FORBIDDEN_CONFIRMATION.search(f"{lead.get('title', '')} {lead.get('summary', '')}"):
        raise ValueError("discovery lead contains prohibited confirmation language")
    sensor = lead.get("sensor") or {}
    if sensor.get("sensor_type") == "infrared_warning" and sensor.get("capability_known"):
        if lead.get("evidence_tier") != "T1" or not sensor.get("capability_source_ref"):
            raise ValueError("DSP/infrared capability claims require T1 evidence and a source reference")


@dataclass
class RunLedger:
    input_count: int = 0
    emitted: int = 0
    duplicate: int = 0
    out_of_scope: int = 0
    failed: int = 0
    unchanged: int = 0
    failures: list[dict[str, Any]] = field(default_factory=list)

    def account(self) -> None:
        total = self.emitted + self.duplicate + self.out_of_scope + self.failed + self.unchanged
        if total != self.input_count:
            raise AssertionError(f"unaccounted rows: input={self.input_count} disposition={total}")


class DedupStore:
    """Reversible dedup index; duplicates retain a pointer to the retained lead."""
    def __init__(self) -> None:
        self._retained: dict[str, str] = {}

    def register(self, fingerprint: str, lead_id: str) -> str | None:
        retained = self._retained.get(fingerprint)
        if retained:
            return retained
        self._retained[fingerprint] = lead_id
        return None


class BaseAdapter:
    method = "manual"

    def receipt(self, *, source_url: str, body: bytes, status: int | None = 200,
                parser_version: str = "1.0.0", **extra: Any) -> dict[str, Any]:
        if len(body) > MAX_CAPTURE_BYTES:
            raise ValueError("raw payload exceeds Centinelas capture limit; route downstream")
        return {
            "adapter_id": self.__class__.__name__, "retrieval_method": self.method,
            "retrieved_at": utc_now(), "http_status": status,
            "content_sha256": sha256_bytes(body), "parser_version": parser_version,
            **extra,
        }


class RSSAtomAdapter(BaseAdapter):
    method = "rss"

    def parse(self, body: bytes, base_url: str) -> list[dict[str, Any]]:
        root = ET.fromstring(body)
        nodes = root.findall(".//item") or root.findall(".//{*}entry")
        items = []
        for node in nodes:
            title = (node.findtext("title") or node.findtext("{*}title") or "").strip()
            link = node.findtext("link") or node.findtext("{*}link")
            if not link:
                link_node = node.find("{*}link")
                link = link_node.get("href") if link_node is not None else None
            items.append({"title": title, "canonical_url": canonical_url(urljoin(base_url, link or ""))})
        return items


class APICatalogAdapter(BaseAdapter):
    method = "api"

    def parse(self, body: bytes) -> list[dict[str, Any]]:
        obj = json.loads(body)
        if isinstance(obj, list):
            return obj
        for key in ("results", "items", "features", "records"):
            if isinstance(obj.get(key), list):
                return obj[key]
        raise ValueError("catalog response has no supported item array")


class HTMLChangeAdapter(BaseAdapter):
    method = "html_change"

    def fingerprint(self, body: bytes) -> str:
        return sha256_bytes(re.sub(rb"\s+", b" ", body).strip())


class SitemapAdapter(BaseAdapter):
    method = "sitemap"

    def parse(self, body: bytes) -> list[dict[str, str | None]]:
        root = ET.fromstring(body)
        rows = []
        for entry in root.findall(".//{*}url"):
            loc = entry.find("{*}loc")
            if loc is not None:
                rows.append({"canonical_url": canonical_url(loc.text or ""),
                             "lastmod": entry.findtext("{*}lastmod") or None})
        return rows


class ManualReceiptAdapter(BaseAdapter):
    method = "manual"


def build_lead(*, source_id: str, source_url: str, title: str, subcategory: str,
               body: bytes, receipt: dict[str, Any], summary: str | None = None,
               evidence_tier: str = "T1", sensor: dict[str, Any] | None = None,
               case_links: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    url = canonical_url(source_url)
    fingerprint = sha256_bytes(body)
    lead = {
        "schema_version": "1.0.0", "lead_id": f"CENT-SPACE-{datetime.now().year}-{fingerprint[:6].upper()}",
        "category": CATEGORY, "subcategory": subcategory, "signal_type": "space_data_discovery",
        "source_id": source_id, "source_url": source_url, "canonical_url": url,
        "title": title, "summary": summary, "published_at": None, "discovered_at": utc_now(),
        "last_verified_at": utc_now(), "discovery_provenance": receipt,
        "access_status": "public_direct",
        "temporal_coverage": {"coverage_type": "unknown", "start": None, "end": None,
                              "precision": "unknown", "timezone_basis": "unknown", "uncertainty_seconds": None},
        "geographic_coverage": {"coverage_type": "unknown", "geometry": None,
                                "jurisdictions": [], "global": False,
                                "spatial_resolution_m": None, "location_uncertainty_m": None},
        "sensor": sensor or {"platform": None, "platform_class": "unknown", "sensor_name": None,
                              "sensor_type": "unknown", "spectral_or_measurement_domain": None,
                              "capability_known": False, "capability_source_ref": None},
        "potential_case_links": case_links or [],
        "downstream_route": {"primary": "satellite-observations-pr", "secondary": ["ovnis-pr"] if case_links else [],
                             "correlation_target": "thehub-pr", "route_status": "new", "routing_reason": None},
        "evidence_tier": evidence_tier, "confidence_score": 95 if evidence_tier == "T1" else 80,
        "review_status": "new", "content_fingerprint": fingerprint,
        "dedup_key": idempotency_key({"canonical_url": url}),
        "raw_binary_storage_prohibited": True, "confirmation_claim_prohibited": True, "notes": None,
    }
    validate_lead(lead)
    return lead


def route_receipt(lead: dict[str, Any], status: str = "queued") -> dict[str, Any]:
    validate_lead(lead)
    return {"lead_id": lead["lead_id"], "route": lead["downstream_route"]["primary"],
            "status": status, "idempotency_key": lead["dedup_key"], "routed_at": utc_now(),
            "payload_sha256": sha256_bytes(json.dumps(lead, sort_keys=True).encode())}


def enrich_federation_attributes(signal: dict[str, Any]) -> dict[str, Any]:
    keys = ("category", "subcategory", "access_status", "temporal_coverage",
            "geographic_coverage", "sensor", "potential_case_links", "downstream_route",
            "content_fingerprint", "confirmation_claim_prohibited")
    return {key: signal.get(key) for key in keys if key in signal}

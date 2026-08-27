"""Discovery-only space and remote-sensing pipeline for Centinelas."""

from __future__ import annotations

import hashlib
import json
import re
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlsplit, urlunsplit

CATEGORY = "SPACE_AND_REMOTE_SENSING"
SUBCATEGORIES = frozenset(
    {
        "SATELLITE_DATASET_RELEASE",
        "MISSION_ARCHIVE_RELEASE",
        "DECLASSIFIED_SPACE_RECORD",
        "ORBITAL_EPHEMERIS_UPDATE",
        "WEATHER_SATELLITE_ARCHIVE",
        "INFRARED_SENSOR_RECORD",
        "SHUTTLE_VIDEO_OR_TELEMETRY",
        "SPACE_SURVEILLANCE_RECORD",
        "FOIA_READING_ROOM_RELEASE",
        "SCIENTIFIC_REPROCESSING",
    }
)
FORBIDDEN_ASSERTION = re.compile(
    r"\b(confirm(?:s|ed|ation)?|proves?|verified uap|alien craft|definitive uap|"
    r"sensor detected the (?:uap|object)|no detection proves)\b",
    re.I,
)
MAX_CAPTURE_BYTES = 2_000_000
BINARY_SIGNATURES = (
    b"\x89PNG\r\n\x1a\n",
    b"\xff\xd8\xff",
    b"GIF87a",
    b"GIF89a",
    b"RIFF",
    b"PK\x03\x04",
    b"%PDF-",
    b"II*\x00",
    b"MM\x00*",
    b"\x00\x00\x00\x18ftyp",
)
ALLOWED_CAPTURE_TYPES = {
    "application/json",
    "application/xml",
    "application/atom+xml",
    "application/rss+xml",
    "text/html",
    "text/plain",
    "text/xml",
    "text/csv",
}
ROUTE_STATUSES = frozenset(
    {"new", "queued", "accepted", "rejected", "acquired", "normalized", "correlated"}
)
REQUIRED_LEAD_FIELDS = frozenset(
    {
        "schema_version",
        "lead_id",
        "category",
        "subcategory",
        "signal_type",
        "source_id",
        "raw_source_url",
        "source_url",
        "canonical_url",
        "title",
        "summary",
        "published_at",
        "dataset_version",
        "catalog_identifier",
        "discovered_at",
        "last_verified_at",
        "discovery_provenance",
        "access_status",
        "temporal_coverage",
        "geographic_coverage",
        "sensor",
        "potential_case_links",
        "downstream_route",
        "evidence_tier",
        "confidence_score",
        "review_status",
        "content_fingerprint",
        "dedup_key",
        "raw_binary_storage_prohibited",
        "confirmation_claim_prohibited",
        "analyst_assertion",
        "negative_inference",
        "synthetic",
        "notes",
    }
)
RECEIPT_EVIDENCE_FIELDS = frozenset(
    {
        "adapter_id",
        "retrieval_method",
        "retrieved_at",
        "http_status",
        "content_type",
        "content_sha256",
        "parser_version",
        "source_url",
    }
)
UNSAFE_XML_DECLARATION = re.compile(rb"<!\s*(?:DOCTYPE|ENTITY)\b", re.IGNORECASE)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical_url(url: str) -> str:
    parts = urlsplit(url.strip())
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        raise ValueError(f"unsupported URL: {url!r}")
    return urlunsplit(
        (parts.scheme.lower(), parts.netloc.lower(), parts.path or "/", parts.query, "")
    )


def idempotency_key(item: dict[str, Any]) -> str:
    identity = {
        key: item.get(key)
        for key in (
            "canonical_url",
            "catalog_identifier",
            "dataset_version",
            "published_at",
        )
    }
    material = json.dumps(identity, sort_keys=True, separators=(",", ":"))
    return sha256_bytes(material.encode())


def _parse_xml(body: bytes) -> ET.Element:
    if len(body) > MAX_CAPTURE_BYTES:
        raise ValueError("XML payload exceeds Centinelas capture limit")
    if b"\x00" in body or UNSAFE_XML_DECLARATION.search(body):
        raise ValueError("XML DTD and entity declarations are prohibited")
    try:
        return ET.fromstring(body)
    except ET.ParseError as exc:
        raise ValueError(f"invalid XML: {exc}") from exc


def _append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def validate_lead(lead: dict[str, Any]) -> None:
    missing = sorted(REQUIRED_LEAD_FIELDS - lead.keys())
    if missing:
        raise ValueError(f"missing required fields: {missing}")
    if lead["schema_version"] != "1.0.0":
        raise ValueError("unsupported schema version")
    if not re.fullmatch(r"CENT-SPACE-\d{4}-[A-F0-9]{16}", str(lead["lead_id"])):
        raise ValueError("invalid lead_id")
    if lead["category"] != CATEGORY or lead["subcategory"] not in SUBCATEGORIES:
        raise ValueError("invalid category or subcategory")
    if lead["signal_type"] != "space_data_discovery":
        raise ValueError("invalid signal type")
    if not isinstance(lead["title"], str) or not lead["title"].strip():
        raise ValueError("title must be a non-empty string")
    normalized_source_url = canonical_url(str(lead["source_url"]))
    if (
        lead["source_url"] != normalized_source_url
        or lead["canonical_url"] != normalized_source_url
    ):
        raise ValueError("source URL fields must contain the same canonical URL")
    if lead.get("raw_binary_storage_prohibited") is not True:
        raise ValueError("raw binary storage prohibition must be true")
    if lead.get("confirmation_claim_prohibited") is not True:
        raise ValueError("confirmation claim prohibition must be true")
    assertion = lead.get("analyst_assertion")
    if assertion and FORBIDDEN_ASSERTION.search(str(assertion)):
        raise ValueError("analyst assertion contains prohibited confirmation language")
    if not re.fullmatch(r"[a-f0-9]{64}", str(lead["content_fingerprint"])):
        raise ValueError("invalid content fingerprint")
    if not re.fullmatch(r"[a-f0-9]{64}", str(lead["dedup_key"])):
        raise ValueError("invalid dedup key")
    expected_dedup_key = idempotency_key(
        {
            "canonical_url": lead["canonical_url"],
            "catalog_identifier": lead["catalog_identifier"],
            "dataset_version": lead["dataset_version"],
            "published_at": lead["published_at"],
        }
    )
    if lead["dedup_key"] != expected_dedup_key:
        raise ValueError("dedup key does not match the complete item identity")
    expected_lead_id = (
        f"CENT-SPACE-{str(lead['discovered_at'])[:4]}-{expected_dedup_key[:16].upper()}"
    )
    if lead["lead_id"] != expected_lead_id:
        raise ValueError("lead ID does not match the complete item identity")
    if not isinstance(lead["synthetic"], bool):
        raise ValueError("synthetic must be a boolean")
    provenance = lead.get("discovery_provenance")
    if not isinstance(provenance, dict):
        raise ValueError("discovery provenance must be an object")
    missing_receipt = sorted(RECEIPT_EVIDENCE_FIELDS - provenance.keys())
    if missing_receipt:
        raise ValueError(f"missing receipt evidence fields: {missing_receipt}")
    if provenance.get("source_url") != normalized_source_url:
        raise ValueError("receipt source URL does not match the lead")
    if provenance.get("content_sha256") != lead["content_fingerprint"]:
        raise ValueError("receipt content hash does not match the lead")
    confidence = lead.get("confidence_score")
    if not isinstance(confidence, int) or not 0 <= confidence <= 100:
        raise ValueError("confidence_score must be an integer from 0 to 100")
    route = lead.get("downstream_route") or {}
    if (
        route.get("primary") != "satellite-observations-pr"
        or route.get("correlation_target") != "thehub-pr"
    ):
        raise ValueError("invalid downstream boundary")
    if route.get("route_status") not in ROUTE_STATUSES:
        raise ValueError("invalid route status")
    for link in lead.get("potential_case_links") or []:
        if link.get("producer") != "ovnis-pr" or link.get("not_a_confirmation") is not True:
            raise ValueError("case links must be ovnis-pr reference-only candidates")
    sensor = lead.get("sensor") or {}
    infrared_claim = sensor.get("sensor_type") == "infrared_warning" and any(
        sensor.get(key) not in (None, False, "", [], {})
        for key in ("capability_known", "coverage_claim", "detection_claim", "sensitivity_claim")
    )
    if infrared_claim and (
        lead.get("evidence_tier") != "T1" or not sensor.get("capability_source_ref")
    ):
        raise ValueError("DSP/infrared claims require T1 evidence and a source reference")
    if lead.get("negative_inference") not in (None, False):
        raise ValueError("discovery leads cannot make negative inferences")


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

    def persist(self, path: str | Path, run_id: str) -> None:
        self.account()
        _append_jsonl(Path(path), {"run_id": run_id, "recorded_at": utc_now(), **asdict(self)})


class DedupStore:
    """Reversible persistent dedup index; duplicate records retain their disposition."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path else None
        self._retained: dict[str, str] = {}
        if self.path:
            for row in _load_jsonl(self.path):
                if row.get("disposition") == "retained":
                    key = row.get("dedup_key") or row.get("fingerprint")
                    if key:
                        self._retained[str(key)] = row["lead_id"]

    def register(self, dedup_key: str, lead_id: str) -> str | None:
        retained = self._retained.get(dedup_key)
        if retained:
            if self.path:
                _append_jsonl(
                    self.path,
                    {
                        "dedup_key": dedup_key,
                        "lead_id": lead_id,
                        "disposition": "duplicate",
                        "retained_lead_id": retained,
                        "recorded_at": utc_now(),
                    },
                )
            return retained
        self._retained[dedup_key] = lead_id
        if self.path:
            _append_jsonl(
                self.path,
                {
                    "dedup_key": dedup_key,
                    "lead_id": lead_id,
                    "disposition": "retained",
                    "retained_lead_id": None,
                    "recorded_at": utc_now(),
                },
            )
        return None


class SourceHealthStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def record(
        self, source_id: str, *, status: str, success: bool, failure_class: str | None = None
    ) -> None:
        _append_jsonl(
            self.path,
            {
                "source_id": source_id,
                "status": status,
                "checked_at": utc_now(),
                "success": success,
                "failure_class": failure_class,
            },
        )


class FailureLedger:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def record(
        self, *, run_id: str, source_id: str, failure_class: str, detail: str, retryable: bool
    ) -> None:
        _append_jsonl(
            self.path,
            {
                "run_id": run_id,
                "source_id": source_id,
                "failure_class": failure_class,
                "detail": detail,
                "retryable": retryable,
                "recorded_at": utc_now(),
            },
        )


class RoutingReceiptStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def record(self, receipt: dict[str, Any]) -> None:
        _append_jsonl(self.path, receipt)


class BaseAdapter:
    method = "manual"

    def receipt(
        self,
        *,
        source_url: str,
        body: bytes,
        status: int | None = 200,
        parser_version: str = "1.0.0",
        content_type: str = "text/plain",
        **extra: Any,
    ) -> dict[str, Any]:
        normalized_type = content_type.split(";", 1)[0].strip().lower()
        if len(body) > MAX_CAPTURE_BYTES:
            raise ValueError("raw payload exceeds Centinelas capture limit; route downstream")
        if (
            normalized_type not in ALLOWED_CAPTURE_TYPES
            or body.startswith(BINARY_SIGNATURES)
            or b"\x00" in body[:1024]
        ):
            raise ValueError("binary payload is prohibited in Centinelas; route downstream")
        overlap = sorted(RECEIPT_EVIDENCE_FIELDS & extra.keys())
        if overlap:
            raise ValueError(f"receipt metadata cannot override evidence fields: {overlap}")
        return {
            "adapter_id": self.__class__.__name__,
            "retrieval_method": self.method,
            "retrieved_at": utc_now(),
            "http_status": status,
            "content_type": normalized_type,
            "content_sha256": sha256_bytes(body),
            "parser_version": parser_version,
            "source_url": canonical_url(source_url),
            **extra,
        }


class RSSAtomAdapter(BaseAdapter):
    method = "rss"

    def parse(self, body: bytes, base_url: str) -> list[dict[str, Any]]:
        root = _parse_xml(body)
        nodes = root.findall(".//item") or root.findall(".//{*}entry")
        items = []
        for node in nodes:
            title = (node.findtext("title") or node.findtext("{*}title") or "").strip()
            link = node.findtext("link") or node.findtext("{*}link")
            if not link:
                link_node = node.find("{*}link")
                link = link_node.get("href") if link_node is not None else None
            if link:
                items.append(
                    {"title": title, "canonical_url": canonical_url(urljoin(base_url, link))}
                )
        return items


class APICatalogAdapter(BaseAdapter):
    method = "api"

    def parse(self, body: bytes) -> list[dict[str, Any]]:
        obj = json.loads(body)
        if isinstance(obj, list):
            return obj
        if not isinstance(obj, dict):
            raise ValueError("catalog response must be an object or array")
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
        root = _parse_xml(body)
        rows = []
        for entry in root.findall(".//{*}url"):
            loc = entry.find("{*}loc")
            if loc is not None and (loc.text or "").strip():
                rows.append(
                    {
                        "canonical_url": canonical_url(loc.text or ""),
                        "lastmod": entry.findtext("{*}lastmod") or None,
                    }
                )
        return rows


class ManualReceiptAdapter(BaseAdapter):
    method = "manual"


def build_lead(
    *,
    source_id: str,
    source_url: str,
    title: str,
    subcategory: str,
    body: bytes,
    receipt: dict[str, Any],
    summary: str | None = None,
    evidence_tier: str = "T1",
    sensor: dict[str, Any] | None = None,
    case_links: list[dict[str, Any]] | None = None,
    catalog_identifier: str | None = None,
    dataset_version: str | None = None,
    published_at: str | None = None,
    access_status: str = "public_direct",
    synthetic: bool = True,
) -> dict[str, Any]:
    url = canonical_url(source_url)
    fingerprint = sha256_bytes(body)
    dedup_key = idempotency_key(
        {
            "canonical_url": url,
            "catalog_identifier": catalog_identifier,
            "dataset_version": dataset_version,
            "published_at": published_at,
        }
    )
    discovered_at = utc_now()
    lead: dict[str, Any] = {
        "schema_version": "1.0.0",
        "lead_id": f"CENT-SPACE-{discovered_at[:4]}-{dedup_key[:16].upper()}",
        "category": CATEGORY,
        "subcategory": subcategory,
        "signal_type": "space_data_discovery",
        "source_id": source_id,
        "raw_source_url": source_url,
        "source_url": url,
        "canonical_url": url,
        "title": title,
        "summary": summary,
        "published_at": published_at,
        "dataset_version": dataset_version,
        "catalog_identifier": catalog_identifier,
        "discovered_at": discovered_at,
        "last_verified_at": discovered_at,
        "discovery_provenance": receipt,
        "access_status": access_status,
        "temporal_coverage": {
            "coverage_type": "unknown",
            "start": None,
            "end": None,
            "precision": "unknown",
            "timezone_basis": "unknown",
            "uncertainty_seconds": None,
        },
        "geographic_coverage": {
            "coverage_type": "unknown",
            "geometry": None,
            "jurisdictions": [],
            "global": False,
            "spatial_resolution_m": None,
            "location_uncertainty_m": None,
        },
        "sensor": sensor
        or {
            "platform": None,
            "platform_class": "unknown",
            "sensor_name": None,
            "sensor_type": "unknown",
            "spectral_or_measurement_domain": None,
            "capability_known": False,
            "capability_source_ref": None,
            "coverage_claim": None,
            "detection_claim": None,
            "sensitivity_claim": None,
        },
        "potential_case_links": case_links or [],
        "downstream_route": {
            "primary": "satellite-observations-pr",
            "secondary": ["ovnis-pr"] if case_links else [],
            "correlation_target": "thehub-pr",
            "route_status": "new",
            "routing_reason": None,
        },
        "evidence_tier": evidence_tier,
        "confidence_score": 95 if evidence_tier == "T1" else 80,
        "review_status": "new",
        "content_fingerprint": fingerprint,
        "dedup_key": dedup_key,
        "raw_binary_storage_prohibited": True,
        "confirmation_claim_prohibited": True,
        "analyst_assertion": None,
        "negative_inference": False,
        "synthetic": synthetic,
        "notes": None,
    }
    validate_lead(lead)
    return lead


def route_receipt(lead: dict[str, Any], status: str = "queued") -> dict[str, Any]:
    validate_lead(lead)
    if status not in ROUTE_STATUSES:
        raise ValueError("invalid route receipt status")
    return {
        "lead_id": lead["lead_id"],
        "route": lead["downstream_route"]["primary"],
        "status": status,
        "idempotency_key": lead["dedup_key"],
        "routed_at": utc_now(),
        "payload_sha256": sha256_bytes(json.dumps(lead, sort_keys=True).encode()),
    }


def enrich_federation_attributes(signal: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "category",
        "subcategory",
        "raw_source_url",
        "access_status",
        "temporal_coverage",
        "geographic_coverage",
        "sensor",
        "potential_case_links",
        "downstream_route",
        "content_fingerprint",
        "confirmation_claim_prohibited",
        "raw_binary_storage_prohibited",
        "analyst_assertion",
        "negative_inference",
        "dedup_key",
    )
    return {key: signal.get(key) for key in keys if key in signal}

"""Receipt-first acquisition for Puerto Rico pre-official source families.

The records produced here preserve source-native identity and date semantics.
They are discovery candidates: this module never binds a source record to a
canonical matter or to a record owned by another federation repository.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urljoin, urlsplit
from zoneinfo import ZoneInfo

import httpx
import yaml
from bs4 import BeautifulSoup

REPO_ROOT = Path(__file__).resolve().parents[3]
CONFIG_PATH = Path(__file__).with_name("puerto_rico_sources.yaml")
REGISTRY_PATH = REPO_ROOT / "data" / "reference" / "puerto_rico_source_registry.csv"
SCHEMA_PATH = REPO_ROOT / "schemas" / "puerto_rico_source_record.schema.json"
PR_TZ = ZoneInfo("America/Puerto_Rico")
SUCCESS_STATES = {"SUCCESS_WITH_ROWS", "SUCCESS_EMPTY"}
REQUIRED_FAMILIES = {"PREB", "AAA", "COR3", "LEGISLATIVE"}
_SPANISH_MONTHS = {
    "ene": 1,
    "feb": 2,
    "mar": 3,
    "abr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "ago": 8,
    "sep": 9,
    "set": 9,
    "oct": 10,
    "nov": 11,
    "dic": 12,
}
_HEADERS = {
    "Accept": "application/json, text/html, application/xhtml+xml, text/plain, */*",
    "Accept-Encoding": "identity",
    "User-Agent": (
        "Mozilla/5.0 (compatible; Centinelas/0.1; +https://github.com/jotaele44/centinelas-pr)"
    ),
}


@dataclass(frozen=True)
class SourceResponse:
    content: bytes
    status_code: int
    final_url: str
    content_type: str
    content_encoding: str
    redirect_statuses: tuple[int, ...]
    headers: dict[str, str]


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def sha256_path(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def json_bytes(value: Any, *, pretty: bool = False) -> bytes:
    separators = None if pretty else (",", ":")
    indent = 2 if pretty else None
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=separators,
            indent=indent,
        )
        + "\n"
    ).encode("utf-8")


def write_bytes_atomic(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_bytes(content)
    temporary.replace(path)


def load_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict) or not isinstance(payload.get("sources"), list):
        raise ValueError("Puerto Rico source config must contain a sources list")
    return payload


def _fetch(client: httpx.Client, url: str) -> SourceResponse:
    response = client.get(url)
    return SourceResponse(
        content=response.content,
        status_code=response.status_code,
        final_url=str(response.url),
        content_type=response.headers.get("content-type", ""),
        content_encoding=response.headers.get("content-encoding", ""),
        redirect_statuses=tuple(item.status_code for item in response.history),
        headers={key.casefold(): value for key, value in response.headers.items()},
    )


def _slug(value: str) -> str:
    folded = unicodedata.normalize("NFKD", value)
    ascii_value = "".join(char for char in folded if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", "-", ascii_value.casefold()).strip("-") or "source"


def _iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _parse_iso_datetime(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return _iso_utc(parsed)


def _parse_english_datetime(value: str) -> str | None:
    for pattern in ("%B %d, %Y %I:%M %p", "%B %d, %Y"):
        try:
            return _iso_utc(datetime.strptime(value.strip(), pattern).replace(tzinfo=PR_TZ))
        except ValueError:
            continue
    return None


def _parse_spanish_datetime(value: str, time_value: str | None = None) -> str | None:
    folded = unicodedata.normalize("NFKD", value.casefold())
    ascii_value = "".join(char for char in folded if not unicodedata.combining(char))
    match = re.search(
        r"\b(\d{1,2})\s+(?:de\s+)?([a-z]{3,10})\.?\s+(?:de\s+)?(\d{4})\b",
        ascii_value,
    )
    if not match:
        return None
    day, month_name, year = match.groups()
    month = _SPANISH_MONTHS.get(month_name[:3])
    if month is None:
        return None
    hour = minute = 0
    if time_value:
        time_match = re.search(r"\b(\d{1,2}):(\d{2})\s*([AP]M)\b", time_value, re.I)
        if time_match:
            hour = int(time_match.group(1)) % 12
            if time_match.group(3).upper() == "PM":
                hour += 12
            minute = int(time_match.group(2))
    try:
        return _iso_utc(datetime(int(year), month, int(day), hour, minute, tzinfo=PR_TZ))
    except ValueError:
        return None


def _record_id(source_id: str, source_record_id: str) -> str:
    digest = hashlib.sha256(f"{source_id}|{source_record_id}".encode()).hexdigest()
    return f"CENT-PR-{digest[:24]}"


def _base_record(
    source: dict[str, Any],
    *,
    source_record_id: str,
    identity_basis: str,
    source_url: str,
    title_raw: str,
    body_raw: str,
    published_at: str | None,
    event_at: str | None,
    source_fields_raw: dict[str, Any],
) -> dict[str, Any]:
    source_id = str(source["source_registry_id"])
    return {
        "schema_version": "1.0.0",
        "record_id": _record_id(source_id, source_record_id),
        "source_registry_id": source_id,
        "source_family": source["family"],
        "source_manifestation": source["manifestation"],
        "source_record_id_raw": source_record_id,
        "identity_basis": identity_basis,
        "identity_effect": "NONE",
        "binding_state": "UNRESOLVED",
        "candidate_cardinality": "UNRESOLVED",
        "source_url": source_url,
        "title_raw": title_raw,
        "body_raw": body_raw,
        "published_at": published_at,
        "event_at": event_at,
        "captured_at": None,
        "evidence_tier": source.get("tier", "T2"),
        "source_fields_raw": source_fields_raw,
        "raw_response_path": None,
        "raw_response_sha256": None,
        "is_synthetic": False,
    }


def parse_preb_notices(
    source: dict[str, Any], content: bytes, request_url: str
) -> list[dict[str, Any]]:
    soup = BeautifulSoup(content, "html.parser")
    source_nodes = soup.select("article.post-item")
    records: list[dict[str, Any]] = []
    for article in source_nodes:
        raw_classes = article.get("class")
        classes = [str(value) for value in raw_classes] if isinstance(raw_classes, list) else []
        post_class = next((value for value in classes if re.fullmatch(r"post-\d+", value)), None)
        title_node = article.select_one(".post-title a")
        if post_class is None or title_node is None:
            continue
        link = urljoin(request_url, str(title_node.get("href") or ""))
        date_raw = article.select_one(".date_label")
        date_text = date_raw.get_text(" ", strip=True) if date_raw else ""
        cleaned_date = re.sub(r"\d+America/Puerto_Rico", " ", date_text)
        excerpt = article.select_one(".post-excerpt")
        title = title_node.get_text(" ", strip=True)
        body = excerpt.get_text(" ", strip=True) if excerpt else ""
        records.append(
            _base_record(
                source,
                source_record_id=post_class.removeprefix("post-"),
                identity_basis="OFFICIAL_STABLE_ID",
                source_url=link,
                title_raw=title,
                body_raw=body,
                published_at=_parse_spanish_datetime(cleaned_date),
                event_at=None,
                source_fields_raw={"date_label": date_text, "post_class": post_class},
            )
        )
    if len(records) != len(source_nodes):
        raise ValueError(
            f"PREB notice identity coverage mismatch: nodes={len(source_nodes)}, "
            f"records={len(records)}"
        )
    return records


def parse_aaa_press(
    source: dict[str, Any], content: bytes, request_url: str
) -> list[dict[str, Any]]:
    soup = BeautifulSoup(content, "html.parser")
    source_nodes = soup.select(".w-dyn-item")
    records: list[dict[str, Any]] = []
    for item in source_nodes:
        title_node = item.select_one("a.h3-titulo-link")
        if title_node is None or not title_node.get("href"):
            continue
        link = urljoin(request_url, str(title_node["href"]))
        date_node = item.select_one(".h2-fecha-publicacion")
        date_raw = date_node.get_text(" ", strip=True) if date_node else ""
        title = title_node.get_text(" ", strip=True)
        records.append(
            _base_record(
                source,
                source_record_id=urlsplit(link).path,
                identity_basis="SOURCE_URL",
                source_url=link,
                title_raw=title,
                body_raw="",
                published_at=_parse_english_datetime(date_raw),
                event_at=None,
                source_fields_raw={"publication_date": date_raw},
            )
        )
    if len(records) != len(source_nodes):
        raise ValueError(
            f"AAA press identity coverage mismatch: nodes={len(source_nodes)}, "
            f"records={len(records)}"
        )
    return records


def parse_cor3_press(
    source: dict[str, Any], content: bytes, request_url: str
) -> list[dict[str, Any]]:
    payload = json.loads(content)
    if not isinstance(payload, list):
        raise ValueError("COR3 press response must be an array")
    records: list[dict[str, Any]] = []
    for row in payload:
        if not isinstance(row, dict) or row.get("id") is None:
            continue
        raw_properties = row.get("internal_properties")
        properties = json.loads(raw_properties) if isinstance(raw_properties, str) else {}
        if not isinstance(properties, dict):
            properties = {}
        title = str(
            properties.get("display_name_es")
            or properties.get("display_name_en")
            or f"COR3 press release {row['id']}"
        )
        records.append(
            _base_record(
                source,
                source_record_id=str(row["id"]),
                identity_basis="OFFICIAL_STABLE_ID",
                source_url=f"{source['public_listing_url']}#page-{row['id']}",
                title_raw=title,
                body_raw=raw_properties if isinstance(raw_properties, str) else "",
                published_at=_parse_iso_datetime(row.get("display_date")),
                event_at=None,
                source_fields_raw=dict(row),
            )
        )
    if len(records) != len(payload):
        raise ValueError(
            f"COR3 press identity coverage mismatch: rows={len(payload)}, records={len(records)}"
        )
    return records


def parse_cor3_active_rfps(
    source: dict[str, Any], content: bytes, request_url: str
) -> list[dict[str, Any]]:
    payload = json.loads(content)
    if not isinstance(payload, dict) or not isinstance(payload.get("theRows"), list):
        raise ValueError("COR3 active RFP response must contain a theRows array")
    source_rows = payload["theRows"]
    records: list[dict[str, Any]] = []
    for row in source_rows:
        if not isinstance(row, dict):
            continue
        source_record_id = row.get("id") or row.get("rfpNumber") or row.get("fileName")
        if source_record_id is None:
            continue
        title = str(row.get("title") or row.get("rfpNumber") or source_record_id)
        file_name = row.get("fileName")
        link = (
            urljoin("https://recovery.pr.gov/tpbackend_prod/documents/", str(file_name))
            if file_name
            else f"{source['public_listing_url']}#rfp-{source_record_id}"
        )
        body = json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        records.append(
            _base_record(
                source,
                source_record_id=str(source_record_id),
                identity_basis="OFFICIAL_STABLE_ID",
                source_url=link,
                title_raw=title,
                body_raw=body,
                published_at=_parse_iso_datetime(row.get("publishedDate")),
                event_at=_parse_iso_datetime(row.get("expirationDate")),
                source_fields_raw=dict(row),
            )
        )
    if len(records) != len(source_rows):
        raise ValueError(
            f"COR3 RFP identity coverage mismatch: rows={len(source_rows)}, records={len(records)}"
        )
    return records


def parse_senate_calendar(
    source: dict[str, Any], content: bytes, request_url: str
) -> list[dict[str, Any]]:
    soup = BeautifulSoup(content, "html.parser")
    source_nodes = soup.select("a.cl_item[href]")
    records: list[dict[str, Any]] = []
    for item in source_nodes:
        link = urljoin(request_url, str(item["href"]))
        query_id = parse_qs(urlsplit(link).query).get("id", [])
        if not query_id:
            continue
        title_node = item.select_one(".cl_hdr")
        date_node = item.select_one(".cl_date")
        info_node = item.select_one(".cl_info")
        title = title_node.get_text(" ", strip=True) if title_node else ""
        date_raw = date_node.get_text(" ", strip=True) if date_node else ""
        info_raw = info_node.get_text(" ", strip=True) if info_node else ""
        records.append(
            _base_record(
                source,
                source_record_id=query_id[0],
                identity_basis="OFFICIAL_STABLE_ID",
                source_url=link,
                title_raw=title,
                body_raw=info_raw,
                published_at=None,
                event_at=_parse_spanish_datetime(date_raw, info_raw),
                source_fields_raw={"calendar_date": date_raw, "calendar_info": info_raw},
            )
        )
    if len(records) != len(source_nodes):
        raise ValueError(
            f"Senate calendar identity coverage mismatch: nodes={len(source_nodes)}, "
            f"records={len(records)}"
        )
    return records


def parse_house_calendar(
    source: dict[str, Any], content: bytes, request_url: str
) -> list[dict[str, Any]]:
    soup = BeautifulSoup(content, "html.parser")
    source_nodes = soup.select(".rst-item-events")
    records: list[dict[str, Any]] = []
    for item in source_nodes:
        link_node = item.select_one("a.rst-item-events-thumb[href]")
        if link_node is None:
            continue
        link = urljoin(request_url, str(link_node["href"]))
        event_ids = parse_qs(urlsplit(link).query).get("event_id", [])
        if not event_ids:
            continue
        title_node = link_node.select_one("h2") or link_node.select_one(".event-type")
        title = title_node.get_text(" ", strip=True) if title_node else ""
        paragraphs = [
            node.get_text(" ", strip=True) for node in item.select(".rst-item-events-info p")
        ]
        date_raw = next(
            (value.split(":", 1)[1].strip() for value in paragraphs if value.startswith("Fecha:")),
            "",
        )
        time_node = item.select_one(".time-event")
        time_raw = time_node.get_text(" ", strip=True) if time_node else ""
        event_type_node = link_node.select_one(".event-type")
        records.append(
            _base_record(
                source,
                source_record_id=event_ids[0],
                identity_basis="OFFICIAL_STABLE_ID",
                source_url=link,
                title_raw=title,
                body_raw="; ".join(paragraphs + ([time_raw] if time_raw else [])),
                published_at=None,
                event_at=_parse_spanish_datetime(date_raw, time_raw),
                source_fields_raw={
                    "event_date": date_raw,
                    "event_time": time_raw,
                    "event_type": event_type_node.get_text(" ", strip=True)
                    if event_type_node
                    else "",
                },
            )
        )
    if len(records) != len(source_nodes):
        raise ValueError(
            f"House calendar identity coverage mismatch: nodes={len(source_nodes)}, "
            f"records={len(records)}"
        )
    return records


PARSERS = {
    "preb_notices": parse_preb_notices,
    "aaa_press": parse_aaa_press,
    "cor3_press": parse_cor3_press,
    "cor3_active_rfps": parse_cor3_active_rfps,
    "senate_calendar": parse_senate_calendar,
    "house_calendar": parse_house_calendar,
}


def _next_html_url(source: dict[str, Any], content: bytes, request_url: str) -> str | None:
    selector = source.get("next_selector")
    if not selector:
        return None
    node = BeautifulSoup(content, "html.parser").select_one(str(selector))
    return urljoin(request_url, str(node["href"])) if node and node.get("href") else None


def _request_url(source: dict[str, Any], captured_at: datetime, offset: int = 0) -> str:
    capture_date = captured_at.astimezone(PR_TZ).strftime("%Y/%m/%d")
    return str(source["url"]).format(offset=offset, capture_date=capture_date)


def _raw_relative_path(
    source_index: int, source: dict[str, Any], request_index: int, url: str
) -> Path:
    extension = ".json" if str(source["parser"]).startswith("cor3_") else ".html"
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:12]
    directory = f"{source_index:02d}-{_slug(str(source['name']))[:60]}"
    return Path(directory) / f"{request_index:04d}-{digest}{extension}"


def capture_source(
    source: dict[str, Any],
    *,
    source_index: int,
    raw_dir: Path,
    captured_at: datetime,
    client: httpx.Client,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    parser_name = str(source.get("parser"))
    parser = PARSERS.get(parser_name)
    if parser is None:
        raise ValueError(f"unknown Puerto Rico source parser: {parser_name}")

    receipt: dict[str, Any] = {
        "source_index": source_index,
        "source_registry_id": source.get("source_registry_id"),
        "name": source.get("name"),
        "family": source.get("family"),
        "manifestation": source.get("manifestation"),
        "url": _request_url(source, captured_at),
        "parser": parser_name,
        "bound": source.get("bound"),
        "retrieved_at": _iso_utc(captured_at),
        "status": "UNRESOLVED",
        "parser_error": None,
        "pagination_complete": False,
        "pagination_stop_reason": None,
        "available_records": None,
        "entries_seen": 0,
        "entries_filtered": 0,
        "entries_without_identity": 0,
        "accepted_entries": 0,
        "duplicates_suppressed": 0,
        "emitted_items": 0,
        "newest_published_at": None,
        "newest_event_at": None,
        "freshness_state": "UNRESOLVED",
        "requests": [],
    }
    records: list[dict[str, Any]] = []
    seen_record_ids: set[str] = set()
    visited_urls: set[str] = set()
    max_requests = int(source.get("max_requests", 1))
    offset = 0
    expected_rowcount: int | None = None
    retrieved_rowcount = 0
    request_url = _request_url(source, captured_at, offset)

    try:
        while request_url:
            if request_url in visited_urls:
                raise ValueError(f"pagination loop detected at {request_url}")
            if len(receipt["requests"]) >= max_requests:
                receipt["status"] = "TRUNCATED"
                receipt["pagination_stop_reason"] = "max_requests_reached_with_more_available"
                break
            visited_urls.add(request_url)
            response = _fetch(client, request_url)
            relative_path = _raw_relative_path(
                source_index, source, len(receipt["requests"]) + 1, request_url
            )
            write_bytes_atomic(raw_dir / relative_path, response.content)
            request_receipt = {
                "request_index": len(receipt["requests"]) + 1,
                "url": request_url,
                "http_status": response.status_code,
                "final_url": response.final_url,
                "redirect_statuses": list(response.redirect_statuses),
                "content_type": response.content_type,
                "content_encoding": response.content_encoding,
                "response_content_byte_scope": "decoded_http_entity_body",
                "response_content_bytes": len(response.content),
                "response_content_sha256": sha256_bytes(response.content),
                "raw_content_path": relative_path.as_posix(),
                "rowcount": response.headers.get("rowcount"),
            }
            receipt["requests"].append(request_receipt)
            if not 200 <= response.status_code < 300:
                receipt["status"] = "HTTP_ERROR"
                receipt["pagination_stop_reason"] = "http_error"
                break

            parsed_records = parser(source, response.content, request_url)
            if not parsed_records and not source.get("allow_empty", False):
                raise ValueError("source parser returned zero rows for a non-empty-required source")
            receipt["entries_seen"] += len(parsed_records)
            for record in parsed_records:
                source_record_id = str(record.get("source_record_id_raw") or "")
                if not source_record_id:
                    receipt["entries_without_identity"] += 1
                    continue
                receipt["accepted_entries"] += 1
                if record["record_id"] in seen_record_ids:
                    receipt["duplicates_suppressed"] += 1
                    continue
                seen_record_ids.add(record["record_id"])
                record["captured_at"] = _iso_utc(captured_at)
                record["raw_response_path"] = relative_path.as_posix()
                record["raw_response_sha256"] = request_receipt["response_content_sha256"]
                records.append(record)
                receipt["emitted_items"] += 1

            if parser_name == "cor3_press":
                raw_rowcount = response.headers.get("rowcount")
                if raw_rowcount is None or not raw_rowcount.isdigit():
                    raise ValueError("COR3 press response lacks an integer rowcount header")
                rowcount = int(raw_rowcount)
                if expected_rowcount is None:
                    expected_rowcount = rowcount
                    receipt["available_records"] = rowcount
                elif rowcount != expected_rowcount:
                    raise ValueError(
                        f"COR3 rowcount changed during capture: {expected_rowcount} -> {rowcount}"
                    )
                retrieved_rowcount += len(parsed_records)
                if retrieved_rowcount >= rowcount:
                    receipt["pagination_complete"] = True
                    receipt["pagination_stop_reason"] = "rowcount_reached"
                    request_url = ""
                elif not parsed_records:
                    raise ValueError("COR3 press pagination returned an empty page before rowcount")
                else:
                    offset += 1
                    request_url = _request_url(source, captured_at, offset)
            elif source.get("next_selector"):
                next_url = _next_html_url(source, response.content, request_url)
                if next_url:
                    request_url = next_url
                else:
                    receipt["pagination_complete"] = True
                    receipt["pagination_stop_reason"] = "no_next_link"
                    request_url = ""
            else:
                receipt["pagination_complete"] = True
                receipt["pagination_stop_reason"] = "single_request"
                request_url = ""
    except Exception as exc:
        receipt["status"] = "PARSE_ERROR"
        receipt["parser_error"] = f"{type(exc).__name__}: {exc}"
        receipt["pagination_stop_reason"] = receipt["pagination_stop_reason"] or "exception"

    if receipt["status"] == "UNRESOLVED":
        receipt["status"] = "SUCCESS_WITH_ROWS" if records else "SUCCESS_EMPTY"
    published = sorted(
        str(record["published_at"]) for record in records if record.get("published_at")
    )
    events = sorted(str(record["event_at"]) for record in records if record.get("event_at"))
    receipt["newest_published_at"] = published[-1] if published else None
    receipt["newest_event_at"] = events[-1] if events else None
    if receipt["status"] not in SUCCESS_STATES:
        receipt["freshness_state"] = "FAILED"
    elif not records and source.get("empty_semantics") == "CURRENT_EMPTY":
        receipt["freshness_state"] = "CURRENT_EMPTY"
    elif published:
        receipt["freshness_state"] = "CAPTURE_CURRENT_SOURCE_DATES_EXPOSED"
    else:
        receipt["freshness_state"] = "CAPTURE_CURRENT_SOURCE_DATES_NOT_EXPOSED"
    return records, receipt


def capture_all(
    config: dict[str, Any],
    *,
    raw_dir: Path,
    captured_at: datetime,
    timeout_seconds: float,
    selected_source_ids: set[str] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    records: list[dict[str, Any]] = []
    receipts: list[dict[str, Any]] = []
    with httpx.Client(
        headers=_HEADERS,
        timeout=timeout_seconds,
        follow_redirects=True,
        trust_env=True,
    ) as client:
        for index, source in enumerate(config["sources"], start=1):
            if (
                selected_source_ids is not None
                and source.get("source_registry_id") not in selected_source_ids
            ):
                continue
            source_records, receipt = capture_source(
                source,
                source_index=index,
                raw_dir=raw_dir,
                captured_at=captured_at,
                client=client,
            )
            records.extend(source_records)
            receipts.append(receipt)
    return records, receipts


def _safe_raw_path(raw_dir: Path, relative: Any) -> Path | None:
    if not isinstance(relative, str):
        return None
    candidate = Path(relative)
    if candidate.is_absolute() or ".." in candidate.parts or candidate.as_posix() != relative:
        return None
    return raw_dir / candidate


def snapshot_errors(receipt: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    raw_output_meta = receipt.get("output")
    output_meta: dict[str, Any] = raw_output_meta if isinstance(raw_output_meta, dict) else {}
    output_path = Path(output_meta.get("path", "")) if output_meta else None
    if output_path is None or not output_path.is_file():
        errors.append("record output is unavailable")
        records: list[dict[str, Any]] = []
    else:
        if output_meta.get("bytes") != output_path.stat().st_size:
            errors.append("record output byte count does not match")
        if output_meta.get("sha256") != sha256_path(output_path):
            errors.append("record output SHA256 does not match")
        records = [
            json.loads(line)
            for line in output_path.read_text(encoding="utf-8").splitlines()
            if line
        ]
        if output_meta.get("records") != len(records):
            errors.append("record output count does not match")

    source_rows = receipt.get("sources", {}).get("rows", [])
    raw_dir = Path(receipt.get("sources", {}).get("raw_directory", ""))
    if not raw_dir.is_dir():
        errors.append("raw response directory is unavailable")
    referenced: set[str] = set()
    for source in source_rows if isinstance(source_rows, list) else []:
        for request in source.get("requests", []) if isinstance(source, dict) else []:
            relative = request.get("raw_content_path")
            raw_path = _safe_raw_path(raw_dir, relative)
            if raw_path is None:
                errors.append("raw response path is unsafe or invalid")
                continue
            referenced.add(str(relative))
            if not raw_path.is_file():
                errors.append(f"raw response is missing: {relative}")
            elif request.get("response_content_bytes") != raw_path.stat().st_size or request.get(
                "response_content_sha256"
            ) != sha256_path(raw_path):
                errors.append(f"raw response does not match receipt: {relative}")
    if raw_dir.is_dir():
        actual = {
            path.relative_to(raw_dir).as_posix() for path in raw_dir.rglob("*") if path.is_file()
        }
        if actual != referenced:
            errors.append("raw response directory has unbound or missing members")
    record_ids = [record.get("record_id") for record in records]
    if len(record_ids) != len(set(record_ids)):
        errors.append("record output contains duplicate record IDs")
    emitted = sum(
        int(source.get("emitted_items", 0)) for source in source_rows if isinstance(source, dict)
    )
    if emitted != len(records):
        errors.append("source emitted-record arithmetic does not close")
    return errors


def build_receipt(
    *,
    config_path: Path,
    config_before: dict[str, Any],
    config_after: dict[str, Any],
    out: Path,
    raw_dir: Path,
    records: list[dict[str, Any]],
    source_receipts: list[dict[str, Any]],
    repository_head: str | None,
    started_at: str,
    completed_at: str,
    schema_errors: list[str],
) -> dict[str, Any]:
    families = {str(row.get("family")) for row in source_receipts}
    source_conservation = len(source_receipts) == len(config_before["sources"])
    entry_conservation = all(
        row["entries_seen"]
        == row["entries_filtered"] + row["entries_without_identity"] + row["accepted_entries"]
        and row["accepted_entries"] == row["duplicates_suppressed"] + row["emitted_items"]
        for row in source_receipts
    )
    gates = {
        "nonempty_records": bool(records),
        "no_synthetic_records": not any(row.get("is_synthetic") for row in records),
        "schema_valid_records": not schema_errors,
        "unique_record_ids": len(records) == len({row["record_id"] for row in records}),
        "source_config_stable": config_before == config_after,
        "repository_head_bound": bool(repository_head),
        "source_conservation": source_conservation,
        "required_families_covered": families >= REQUIRED_FAMILIES,
        "terminal_sources": all(row["status"] != "UNRESOLVED" for row in source_receipts),
        "no_source_failures": all(row["status"] in SUCCESS_STATES for row in source_receipts),
        "pagination_complete": all(row["pagination_complete"] for row in source_receipts),
        "entry_conservation": entry_conservation,
        "emitted_record_conservation": sum(row["emitted_items"] for row in source_receipts)
        == len(records),
        "unique_source_registry_ids": len(source_receipts)
        == len({row["source_registry_id"] for row in source_receipts}),
        "unique_source_manifestations": len(source_receipts)
        == len({(row["family"], row["manifestation"]) for row in source_receipts}),
    }
    receipt: dict[str, Any] = {
        "schema_version": "pr_source_tranche_receipt.v1",
        "classification": "PASS" if all(gates.values()) else "FAIL",
        "claim_scope": "configured Puerto Rico pre-official source manifestations",
        "exhaustion_scope": "bounded by each source receipt; not universal source exhaustion",
        "repository": "jotaele44/centinelas-pr",
        "repository_head": repository_head,
        "capture_started_at": started_at,
        "capture_completed_at": completed_at,
        "output": {
            "path": str(out.resolve()),
            "bytes": out.stat().st_size,
            "sha256": sha256_path(out),
            "records": len(records),
            "schema_errors": schema_errors,
        },
        "source_config": {
            "path": str(config_path.resolve()),
            "before": config_before,
            "after": config_after,
            "stable": config_before == config_after,
        },
        "sources": {
            "configured": len(config_before["sources"]),
            "receipts": len(source_receipts),
            "families": sorted(families),
            "raw_directory": str(raw_dir.resolve()),
            "rows": source_receipts,
        },
        "gates": gates,
    }
    verification = snapshot_errors(receipt)
    receipt["verification_errors"] = verification
    receipt["gates"]["snapshot_self_verifies"] = not verification
    receipt["classification"] = "PASS" if all(receipt["gates"].values()) else "FAIL"
    return receipt


def config_state(path: Path) -> dict[str, Any]:
    supporting_files = [path, REGISTRY_PATH, SCHEMA_PATH]
    return {
        "schema_version": load_config(path).get("schema_version"),
        "files": [
            {
                "path": str(file.relative_to(REPO_ROOT)),
                "bytes": file.stat().st_size,
                "sha256": sha256_path(file),
            }
            for file in supporting_files
        ],
        "sources": load_config(path)["sources"],
    }

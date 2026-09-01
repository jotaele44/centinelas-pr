from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any, Callable
from urllib.parse import urljoin


class ParserDriftError(ValueError):
    pass


@dataclass(frozen=True)
class ParsedRecord:
    source_key: str
    title: str
    detail_url: str
    download_url: str | None = None
    archival_identifier: str | None = None
    document_date: str | None = None
    metadata: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_key": self.source_key,
            "title": self.title,
            "detail_url": self.detail_url,
            "download_url": self.download_url,
            "archival_identifier": self.archival_identifier,
            "document_date": self.document_date,
            "metadata": self.metadata or {},
        }


class _LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[dict[str, str]] = []
        self._current: dict[str, str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        values = {key: value or "" for key, value in attrs}
        self._current = {
            "href": values.get("href", ""),
            "class": values.get("class", ""),
            "data-id": values.get("data-id", ""),
            "text": "",
        }

    def handle_data(self, data: str) -> None:
        if self._current is not None:
            self._current["text"] += data

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._current is not None:
            self._current["text"] = " ".join(self._current["text"].split())
            self.links.append(self._current)
            self._current = None


def _stable_key(adapter_id: str, identifier: str, url: str) -> str:
    digest = hashlib.sha256(f"{adapter_id}\0{identifier}\0{url}".encode()).hexdigest()[:24]
    return f"{adapter_id}:{digest}"


def _require(records: list[ParsedRecord], adapter_id: str) -> list[dict[str, Any]]:
    if not records:
        raise ParserDriftError(f"{adapter_id} parser produced zero records")
    return [record.as_dict() for record in records]


def _html_links(body: bytes) -> list[dict[str, str]]:
    parser = _LinkParser()
    parser.feed(body.decode("utf-8", errors="replace"))
    return parser.links


def _parse_html_index(
    body: bytes,
    *,
    adapter_id: str,
    base_url: str,
    include: Callable[[dict[str, str]], bool],
) -> tuple[list[dict[str, Any]], bool]:
    records: list[ParsedRecord] = []
    for link in _html_links(body):
        if not link["href"] or not include(link):
            continue
        url = urljoin(base_url, link["href"])
        title = link["text"] or link["data-id"] or url.rsplit("/", 1)[-1]
        identifier = link["data-id"] or re.sub(r"\W+", "-", title.lower()).strip("-")
        records.append(
            ParsedRecord(
                source_key=_stable_key(adapter_id, identifier, url),
                title=title,
                detail_url=url,
                download_url=url if url.lower().endswith(".pdf") else None,
                archival_identifier=identifier or None,
            )
        )
    return _require(records, adapter_id), False


def parse_nara_ndc(body: bytes) -> tuple[list[dict[str, Any]], bool]:
    return _parse_html_index(
        body,
        adapter_id="nara_ndc",
        base_url="https://www.archives.gov",
        include=lambda link: "release" in (link["href"] + " " + link["text"]).lower(),
    )


def parse_nara_catalog(body: bytes) -> tuple[list[dict[str, Any]], bool]:
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise ParserDriftError("nara_catalog returned non-JSON content") from exc
    rows = payload.get("records") or payload.get("results") or payload.get("opaResponse", {}).get("results", {}).get("result")
    if not isinstance(rows, list):
        raise ParserDriftError("nara_catalog record array missing")
    records: list[ParsedRecord] = []
    for row in rows:
        identifier = str(row.get("naId") or row.get("id") or "").strip()
        title = str(row.get("title") or row.get("description") or "").strip()
        url = str(row.get("url") or row.get("detailUrl") or "").strip()
        if not identifier or not title:
            continue
        if not url:
            url = f"https://catalog.archives.gov/id/{identifier}"
        records.append(
            ParsedRecord(
                source_key=_stable_key("nara_catalog", identifier, url),
                title=title,
                detail_url=url,
                archival_identifier=identifier,
                document_date=str(row.get("date") or "") or None,
                metadata={"record_group": row.get("recordGroupNumber")},
            )
        )
    has_next = bool(payload.get("next") or payload.get("nextPage"))
    return _require(records, "nara_catalog"), has_next


def parse_cia_reading_room(body: bytes) -> tuple[list[dict[str, Any]], bool]:
    return _parse_html_index(
        body,
        adapter_id="cia_reading_room",
        base_url="https://www.cia.gov",
        include=lambda link: "/readingroom/document/" in link["href"] or link["href"].lower().endswith(".pdf"),
    )


def parse_nsa_releases(body: bytes) -> tuple[list[dict[str, Any]], bool]:
    return _parse_html_index(
        body,
        adapter_id="nsa_releases",
        base_url="https://www.nsa.gov",
        include=lambda link: link["href"].lower().endswith(".pdf") or "release" in link["class"].lower(),
    )


def parse_dia_reading_room(body: bytes) -> tuple[list[dict[str, Any]], bool]:
    return _parse_html_index(
        body,
        adapter_id="dia_reading_room",
        base_url="https://www.dia.mil",
        include=lambda link: link["href"].lower().endswith(".pdf") or "download" in link["class"].lower(),
    )


def parse_nhhc_collection(body: bytes) -> tuple[list[dict[str, Any]], bool]:
    return _parse_html_index(
        body,
        adapter_id="nhhc",
        base_url="https://www.history.navy.mil",
        include=lambda link: any(token in link["href"].lower() for token in ("archives", "collection", ".pdf")),
    )


def parse_doe_aec_index(body: bytes) -> tuple[list[dict[str, Any]], bool]:
    return _parse_html_index(
        body,
        adapter_id="doe_aec",
        base_url="https://www.energy.gov",
        include=lambda link: link["href"].lower().endswith(".pdf") or "reading-room" in link["href"].lower(),
    )


def parse_blue_book_catalog(body: bytes) -> tuple[list[dict[str, Any]], bool]:
    return _parse_html_index(
        body,
        adapter_id="air_force_blue_book",
        base_url="https://www.archives.gov",
        include=lambda link: any(token in (link["href"] + " " + link["text"]).lower() for token in ("blue book", "ufo", ".pdf")),
    )


PARSER_REGISTRY: dict[str, Callable[[bytes], tuple[list[dict[str, Any]], bool]]] = {
    "nara_ndc": parse_nara_ndc,
    "nara_catalog": parse_nara_catalog,
    "cia_reading_room": parse_cia_reading_room,
    "nsa_releases": parse_nsa_releases,
    "dia_reading_room": parse_dia_reading_room,
    "nhhc": parse_nhhc_collection,
    "doe_aec": parse_doe_aec_index,
    "air_force_blue_book": parse_blue_book_catalog,
}

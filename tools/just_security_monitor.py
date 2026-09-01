#!/usr/bin/env python3
"""Stateful bounded monitor for Just Security Puerto Rico-relevant material."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote_plus

import httpx

from just_security_monitor_core import (
    LIVING_URLS,
    SEARCH_URL,
    SOURCE_ID,
    TAG_URL,
    acquire_article_receipts,
    content_fingerprint,
    fetch_url,
    now_utc,
    poll_relevant_feeds,
    reconcile_listing,
    snapshot_listing,
)

EXPANDED_TERMS = (
    "Puerto Rico",
    "Puerto Rican",
    "Commonwealth of Puerto Rico",
    "PROMESA",
    "Financial Oversight and Management Board",
    "Roosevelt Roads",
    "Fort Buchanan",
    "Vieques",
    "Ramey Air Force Base",
    "Insular Cases",
    "Jones Act",
    "SOUTHCOM Puerto Rico",
    "FOMB Puerto Rico",
)
USER_AGENT = "Centinelas-PR/0.1 (+https://github.com/jotaele44/centinelas-pr)"


def _load_state(path: Path) -> dict:
    if not path.exists():
        return {
            "schema_version": "just_security_monitor_state.v0.1",
            "items": {},
            "listings": {},
            "living": {},
        }
    return json.loads(path.read_text(encoding="utf-8"))


def _append_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def _item_events(state: dict, items: list[dict], run_id: str) -> list[dict]:
    events = []
    for item in items:
        url = item["canonical_url"]
        previous = state["items"].get(url)
        if previous is None:
            events.append(
                {
                    "event_type": "NEW_RELEVANT_ITEM",
                    "run_id": run_id,
                    "item": item,
                    "auto_promote_to_verified": False,
                }
            )
        elif (
            item.get("content_sha256")
            and previous.get("content_sha256") not in (None, item["content_sha256"])
        ):
            events.append(
                {
                    "event_type": "ARTICLE_VERSION_CHANGE",
                    "run_id": run_id,
                    "item": item,
                    "previous_content_sha256": previous.get("content_sha256"),
                    "auto_promote_to_verified": False,
                }
            )
        state["items"][url] = item
    return events


def _living_events(
    client: httpx.Client,
    state: dict,
    run_id: str,
) -> tuple[list[dict], list[dict]]:
    events: list[dict] = []
    receipts: list[dict] = []
    for url in LIVING_URLS:
        body, receipt = fetch_url(client, url)
        receipts.append(receipt)
        if body is None or receipt.get("http_status") != 200:
            continue
        current_hash = content_fingerprint(body)
        previous = state["living"].get(url, {})
        if previous.get("content_sha256") not in (None, current_hash):
            events.append(
                {
                    "event_type": "LIVING_PAGE_VERSION_CHANGE",
                    "run_id": run_id,
                    "url": url,
                    "previous_content_sha256": previous.get("content_sha256"),
                    "content_sha256": current_hash,
                    "auto_promote_to_verified": False,
                }
            )
        state["living"][url] = {
            "content_sha256": current_hash,
            "last_checked_at": receipt["retrieved_at"],
        }
    return events, receipts


def _listing_result_urls(*snapshots: dict) -> list[str]:
    """Union listing URLs in first-seen order; ordering is provenance, not identity."""
    urls: list[str] = []
    seen: set[str] = set()
    for snapshot in snapshots:
        for url in snapshot.get("result_urls", []):
            if url in seen:
                continue
            seen.add(url)
            urls.append(url)
    return urls


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--state",
        type=Path,
        default=Path("data/monitoring/just_security/state.json"),
    )
    parser.add_argument(
        "--events",
        type=Path,
        default=Path("data/monitoring/just_security/events.jsonl"),
    )
    parser.add_argument(
        "--runs",
        type=Path,
        default=Path("data/monitoring/just_security/runs.jsonl"),
    )
    parser.add_argument(
        "--snapshot",
        type=Path,
        default=Path("data/monitoring/just_security/latest_snapshot.json"),
    )
    parser.add_argument("--no-detail", action="store_true")
    parser.add_argument("--strict-search", action="store_true")
    parser.add_argument("--expanded-audit", action="store_true")
    args = parser.parse_args(argv)

    state = _load_state(args.state)
    run_id = "JUSTSEC-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    events: list[dict] = []

    with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=30.0) as client:
        items, feed_run = poll_relevant_feeds(client, fetch_detail=not args.no_detail)
        events.extend(_item_events(state, items, run_id))

        tag = snapshot_listing(client, "PUERTO_RICO_TAG_ARCHIVE", TAG_URL)
        search = snapshot_listing(client, "PUERTO_RICO_LITERAL_SEARCH", SEARCH_URL)
        events.extend(reconcile_listing(state, tag, run_id))
        events.extend(reconcile_listing(state, search, run_id))

        expanded: list[dict] = []
        if args.expanded_audit:
            for term in EXPANDED_TERMS:
                url = "https://www.justsecurity.org/?s=" + quote_plus(term)
                result = snapshot_listing(client, f"EXPANDED_SEARCH:{term}", url)
                expanded.append(result)
                events.extend(reconcile_listing(state, result, run_id))

        listing_urls = _listing_result_urls(tag, search, *expanded)
        article_receipts = acquire_article_receipts(client, listing_urls)
        article_failures = sum(1 for receipt in article_receipts if receipt["state"] != "PASS")

        living_events, living_receipts = _living_events(client, state, run_id)
        events.extend(living_events)

    feed_closed = (
        feed_run["certification"] == "PASS"
        and feed_run["counts"].get("unresolved", 0) == 0
        and feed_run["counts"].get("detail_failures", 0) == 0
    )
    certification = (
        "PASS"
        if (
            tag["certification"] == "PASS"
            and search["certification"] == "PASS"
            and feed_closed
            and article_failures == 0
        )
        else "PROVISIONAL"
    )
    snapshot = {
        "schema_version": "just_security_snapshot.v0.1",
        "run_id": run_id,
        "source_id": SOURCE_ID,
        "recorded_at": now_utc(),
        "tag_archive": tag,
        "literal_search": search,
        "expanded_searches": expanded,
        "listing_article_receipts": article_receipts,
        "feed": feed_run,
        "living_page_receipts": living_receipts,
        "certification": certification,
        "claim_boundary": (
            "No search/tag manifestation is asserted to equal the complete "
            "Puerto Rico-relevant publisher universe."
        ),
    }

    for path in (args.state, args.snapshot):
        path.parent.mkdir(parents=True, exist_ok=True)
    args.state.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.snapshot.write_text(
        json.dumps(snapshot, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _append_jsonl(args.events, events)
    _append_jsonl(
        args.runs,
        [
            {
                "run_id": run_id,
                "recorded_at": now_utc(),
                "event_count": len(events),
                "tag_certification": tag["certification"],
                "search_certification": search["certification"],
                "feed_certification": feed_run["certification"],
                "listing_article_failures": article_failures,
                **feed_run["counts"],
            }
        ],
    )

    print(
        json.dumps(
            {
                "run_id": run_id,
                "events": len(events),
                "tag": tag["certification"],
                "search": search["certification"],
                "feed": feed_run["certification"],
                "listing_article_failures": article_failures,
                **feed_run["counts"],
            },
            sort_keys=True,
        )
    )
    return 2 if args.strict_search and search["certification"] != "PASS" else 0


if __name__ == "__main__":
    raise SystemExit(main())

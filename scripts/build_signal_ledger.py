#!/usr/bin/env python3
"""Bridge the live intake engine into the federation signal ledger.

The engine (src/centinelas) ingests real RSS feeds and classifies items, but
its output (`ClassifiedItem`) never reached `data/signals/` — the federation
export could only read the synthetic seed ledger, so `--mode production` was
permanently refused. This bridge closes that gap:

    RSS + Federal Register + listing scrapers -> Puerto Rico relevance filter
        -> publication-age window -> per-source cap -> classify + enrich
        -> signal rows -> data/signals/live_signals.jsonl

Every emitted row is a REAL public signal (`is_synthetic: false`) captured
from the configured sources at run time (one matter per item). The ledger polls the same three intake layers as `centinelas run`:
RSS/Atom feeds (including the DRNA permit and notice categories), the Federal
Register API (USACE/EPA, Puerto Rico) and the listing scrapers (OGPe, JP, ASG,
EPA Region 2 NPDES). A per-source cap keeps any single high-volume feed from
crowding the Puerto Rico permit sources out of a bounded ledger: the old
first-N cut over RSS alone dropped every DRNA feed, because they are listed
last in sources.yaml.

Two filters run before the cap, so a source's slots go to items that belong in
a Puerto Rico pre-officialization ledger, and both report what they dropped:

  * Relevance. Feeds marked `scope: global` in sources.yaml (international
    media, US-wide OSHA) feed the universal engine's six-domain routing, but the
    ledger is exported with jurisdiction PR, so their items are kept only when
    the title or body names Puerto Rico (`PR_TERMS`). Every other source is
    Puerto Rico scoped by construction and is never filtered on vocabulary.
  * Age. Items published more than `--max-age-days` ago (default 90) are not
    emerging signals. Items dated in the FUTURE are kept: the ASG and OGPe
    listings date an entry by its bid opening or hearing, which is exactly the
    pending event this ledger exists to surface.

A dropped item is a ledger-scope decision, not evidence that nothing happened;
`centinelas run` still ingests and routes it. Other pre-officialization families in the registry
(legislative calendars, municipal agendas, ...) remain future intake.

Mapping (ClassifiedItem -> signal.schema.json):
  signal_id        CENT-SIG-<item_id>
  matter_id        CENT-MAT-<item_id>          (1:1 item->matter at this stage)
  signal_type      <primary label, lowercased>_signal
  beat             <primary label, lowercased>
  signal_stage     rfp_open / officialization_pending when classify/enrich.py
                   detects an open solicitation / an announced award, else
                   raw_observation
  agencies         enrich.extract_agencies, plus the contracting agency parsed
                   from ASG bid listing titles
  entities         enrich.extract_recipients (the awardee, not the funder)
  estimated_value  enrich.extract_estimated_value
  municipalities   [] (nothing in this repo resolves them for ledger rows yet)
  source_id        CENT-SRC-RSS-<feed slug>    (rows added to the source registry)
  confidence_score confidence * 100
  evidence_tier    verbatim (same T1-T4 enum)
  is_synthetic     false

Usage:
    python scripts/build_signal_ledger.py                 # live poll + classify
    python scripts/build_signal_ledger.py --per-source 10 --limit 300
    python scripts/build_signal_ledger.py --rss-only --limit 100   # previous behaviour
    python scripts/build_signal_ledger.py --max-age-days 0 --keep-global   # no filters
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from centinelas.classify.classifier import build_classified_item  # noqa: E402
from centinelas.ingest import rss  # noqa: E402
from centinelas.ingest.federal_register import poll_federal_register  # noqa: E402
from centinelas.ingest.web import poll_scrape_sources  # noqa: E402
from centinelas.models import ClassifiedItem  # noqa: E402

DEFAULT_OUT = REPO_ROOT / "data" / "signals" / "live_signals.jsonl"
DEFAULT_MAX_AGE_DAYS = 90

# Accent-folded, lower-case substrings that tie an item from a `scope: global`
# feed to Puerto Rico. Deliberately short: municipality names such as "San Juan"
# or "Ponce" are ambiguous outside the island and would admit unrelated items.
PR_TERMS = (
    "puerto rico",
    "puerto rican",
    "puertorrique",
    "boricua",
    "borinquen",
    "vieques",
    "culebra",
)

# Listing sources whose titles name the contracting agency in a fixed position.
# ASG's bid listing renders each entry as "<bid id> — <procedure> — <agency>",
# e.g. "27J-07773 — Subasta Formal — Compañía de Fomento Industrial- (PRIDCO)".
# classify/enrich.py matches agencies by keyword against a short list that
# names none of these, so without this every ASG row reached the export with no
# agency and no involves_agency relationship.
_ASG_LISTING_SOURCES = frozenset({"ASG — Licitaciones (Subastas)"})
_TITLE_SEPARATOR = re.compile(r"\s+[—–]\s+")
_TRAILING_ACRONYM = re.compile(r"\(([A-Z][A-Z0-9&]{1,11})\)\s*$")


def _clean_listing_agency(segment: str) -> str | None:
    """The agency as the listing names it, without inferring identity.

    A parenthesised acronym the listing itself gives is used ("Compañía de
    Fomento Industrial- (PRIDCO)" and "PRIDCO" both become "PRIDCO"); centralized
    ASG procurement ("ASG- Contratos Centralizados") becomes "ASG". Any other
    name is kept as written: two spellings of one agency are NOT merged here,
    because name similarity is not proof of identity.
    """
    text = segment.strip()
    match = _TRAILING_ACRONYM.search(text)
    if match:
        return match.group(1)
    text = re.sub(r"[\s\-–—]+$", "", text)
    if re.match(r"^ASG(?:$|[\s\-–])", text):
        return "ASG"
    return text or None


def _listing_agencies(source_name: str, title: str) -> list[str]:
    if source_name not in _ASG_LISTING_SOURCES:
        return []
    parts = _TITLE_SEPARATOR.split(title or "")
    if len(parts) < 3:
        return []
    agency = _clean_listing_agency(parts[-1])
    return [agency] if agency else []


# classify/enrich.py stage vocabulary -> schemas/signal.schema.json enum. An
# announced award is not yet an official record, so it is "pending
# officialization", never a finalized stage.
_STAGE_MAP = {
    "rfp_open": "rfp_open",
    "award_announced": "officialization_pending",
}


def feed_source_id(feed_name: str) -> str:
    """Deterministic registry id for a feed — mirrored in source_registry.csv."""
    slug = re.sub(r"[^A-Z0-9]+", "-", feed_name.upper()).strip("-")
    return f"CENT-SRC-RSS-{slug}"


def source_name_to_id() -> dict[str, str]:
    return {src["name"]: feed_source_id(src["name"]) for src in rss._load_sources()}


def item_to_signal(item: ClassifiedItem, source_ids: dict[str, str]) -> dict:
    primary = item.labels[0].value.lower() if item.labels else "unclassified"
    return {
        "signal_id": f"CENT-SIG-{item.item_id}",
        "matter_id": f"CENT-MAT-{item.item_id}",
        "signal_type": f"{primary}_signal",
        "title": item.title,
        "summary": (item.body_text or "")[:500],
        "source_id": source_ids.get(item.source_name, feed_source_id(item.source_name)),
        "source_url": item.source_url,
        "captured_at": item.captured_at.isoformat(),
        "published_at": item.published_at.isoformat(),
        "signal_stage": _STAGE_MAP.get(item.signal_stage or "", "raw_observation"),
        "beat": primary,
        "municipalities": list(item.municipalities),
        "agencies": list(
            dict.fromkeys([*item.agencies, *_listing_agencies(item.source_name, item.title)])
        ),
        "entities": list(item.recipients),
        "estimated_value": item.estimated_value,
        "deadline_date": None,
        "urgency_score": None,
        "confidence_score": round(item.confidence * 100, 1),
        "evidence_tier": item.evidence_tier,
        "handoff_status": "raw",
        "is_synthetic": False,
        "labels": [label.value for label in item.labels],
    }


def collect_raw_items(rss_only: bool = False) -> list:
    """Poll every intake layer and merge, deduping by item_id in first-seen order."""
    layers = [rss.poll_all()]
    if not rss_only:
        layers += [poll_federal_register(), poll_scrape_sources()]
    seen: set[str] = set()
    merged: list = []
    for items in layers:
        for item in items:
            if item.item_id not in seen:
                seen.add(item.item_id)
                merged.append(item)
    return merged


def _fold(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text or "")
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch)).casefold()


def global_source_names() -> set[str]:
    """Names of feeds marked `scope: global` in the engine's source config."""
    return {
        src["name"] for src in rss._load_sources()
        if src.get("name") and str(src.get("scope", "")).strip().lower() == "global"
    }


def is_pr_relevant(item, global_sources: set[str]) -> bool:
    """True unless the item comes from a global feed and never names Puerto Rico."""
    if item.source_name not in global_sources:
        return True
    text = _fold(f"{item.title} {item.body_text}")
    return any(term in text for term in PR_TERMS)


def filter_items(
    items: list,
    *,
    global_sources: set[str] | None = None,
    max_age_days: float | None = DEFAULT_MAX_AGE_DAYS,
    now: datetime | None = None,
) -> tuple[list, dict[str, int]]:
    """Apply the relevance and age filters; return kept items and drop counts.

    ``global_sources=None`` disables the relevance filter; ``max_age_days`` of
    None or 0 disables the age window. Future-dated items always pass the age
    window (see the module docstring).
    """
    cutoff = None
    if max_age_days:
        cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=max_age_days)
    kept: list = []
    dropped = {"not_pr_relevant": 0, "older_than_window": 0}
    for item in items:
        if global_sources is not None and not is_pr_relevant(item, global_sources):
            dropped["not_pr_relevant"] += 1
        elif cutoff is not None and item.published_at < cutoff:
            dropped["older_than_window"] += 1
        else:
            kept.append(item)
    return kept, dropped


def cap_items(items: list, per_source: int | None = None, total: int | None = None) -> list:
    """Bound the ledger without letting one source crowd out the rest.

    Keeps at most ``per_source`` items from each source (in poll order), then
    takes items round-robin across sources until ``total`` is reached, so a
    total cap removes items from the largest sources first rather than dropping
    whole sources that happen to be polled last.
    """
    by_source: dict[str, list] = {}
    for item in items:
        bucket = by_source.setdefault(item.source_name, [])
        if per_source is None or len(bucket) < per_source:
            bucket.append(item)
    queues = list(by_source.values())
    out: list = []
    depth = 0
    while any(depth < len(q) for q in queues):
        for q in queues:
            if depth < len(q):
                if total is not None and len(out) >= total:
                    return out
                out.append(q[depth])
        depth += 1
    return out


def build_ledger(
    limit: int | None = None,
    per_source: int | None = None,
    rss_only: bool = False,
    max_age_days: float | None = DEFAULT_MAX_AGE_DAYS,
    keep_global: bool = False,
) -> list[dict]:
    raw_items = collect_raw_items(rss_only=rss_only)
    if not raw_items:
        raise SystemExit("FAIL — no feeds returned items; refusing to write an empty live ledger")
    polled = len(raw_items)
    raw_items, dropped = filter_items(
        raw_items,
        global_sources=None if keep_global else global_source_names(),
        max_age_days=max_age_days,
    )
    print(
        f"intake: polled={polled} kept={len(raw_items)} "
        f"dropped_not_pr_relevant={dropped['not_pr_relevant']} "
        f"dropped_older_than_window={dropped['older_than_window']}"
    )
    if not raw_items:
        raise SystemExit(
            "FAIL — every polled item was filtered out; refusing to write an empty live ledger"
        )
    raw_items = cap_items(raw_items, per_source=per_source, total=limit or None)
    source_ids = source_name_to_id()
    return [item_to_signal(build_classified_item(raw), source_ids) for raw in raw_items]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Materialize real signals into the federation ledger.")
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--limit", type=int, default=None, help="total row cap")
    ap.add_argument("--per-source", type=int, default=None, help="row cap per source")
    ap.add_argument("--rss-only", action="store_true",
                    help="poll RSS feeds only (skip Federal Register and scrapers)")
    ap.add_argument("--max-age-days", type=float, default=DEFAULT_MAX_AGE_DAYS,
                    help="drop items published more than this many days ago; 0 disables "
                         f"(default: {DEFAULT_MAX_AGE_DAYS})")
    ap.add_argument("--keep-global", action="store_true",
                    help="keep items from `scope: global` feeds that do not name Puerto Rico")
    args = ap.parse_args(argv)

    signals = build_ledger(
        limit=args.limit, per_source=args.per_source, rss_only=args.rss_only,
        max_age_days=args.max_age_days, keep_global=args.keep_global,
    )
    synthetic = [s for s in signals if s.get("is_synthetic")]
    if synthetic:
        raise SystemExit(f"bridge bug: {len(synthetic)} rows flagged synthetic")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        for sig in signals:
            fh.write(json.dumps(sig, ensure_ascii=False, sort_keys=True) + "\n")
    beats: dict[str, int] = {}
    for sig in signals:
        beats[sig["beat"]] = beats.get(sig["beat"], 0) + 1
    enriched = sum(1 for s in signals if s["agencies"] or s["entities"] or s["estimated_value"])
    print(
        f"wrote {out} — {len(signals)} real signals, beats={dict(sorted(beats.items()))}, "
        f"with_enrichment={enriched}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

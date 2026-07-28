#!/usr/bin/env python3
"""Run low-rate, metadata-only federal-record source canaries.

The command never downloads linked document binaries. It retains robots, policy,
and index responses plus deterministic ledgers for two independent enumerations.
A fetched policy page is evidence of availability, not a legal interpretation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
import urllib.error
import urllib.request
import urllib.robotparser
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from centinelas.releases.parsers import PARSER_REGISTRY, ParserDriftError

USER_AGENT = "centinelas-pr-controlled-canary/1.0 (+public archival metadata only)"


@dataclass(frozen=True)
class SourceCanary:
    adapter_id: str
    index_url: str
    robots_url: str
    policy_url: str


SOURCES: tuple[SourceCanary, ...] = (
    SourceCanary(
        "nara_ndc",
        "https://www.archives.gov/declassification/ndc/releases?page=1&page_size=100",
        "https://www.archives.gov/robots.txt",
        "https://www.archives.gov/global-pages/privacy.html",
    ),
    SourceCanary(
        "nara_catalog",
        "https://catalog.archives.gov/api/v1/records?page=1&page_size=100",
        "https://catalog.archives.gov/robots.txt",
        "https://www.archives.gov/global-pages/privacy.html",
    ),
    SourceCanary(
        "cia_reading_room",
        "https://www.cia.gov/readingroom/search/site?page=1&page_size=100",
        "https://www.cia.gov/robots.txt",
        "https://www.cia.gov/site-policies/",
    ),
    SourceCanary(
        "nsa_releases",
        "https://www.nsa.gov/Helpful-Links/NSA-FOIA/Declassification-Transparency-Initiatives/?page=1&page_size=100",
        "https://www.nsa.gov/robots.txt",
        "https://www.nsa.gov/Privacy-Program/",
    ),
    SourceCanary(
        "dia_reading_room",
        "https://www.dia.mil/FOIA/FOIA-Electronic-Reading-Room/?page=1&page_size=100",
        "https://www.dia.mil/robots.txt",
        "https://www.dia.mil/FOIA/",
    ),
    SourceCanary(
        "nhhc",
        "https://www.history.navy.mil/research/archives/digital-exhibits-highlights.html?page=1&page_size=100",
        "https://www.history.navy.mil/robots.txt",
        "https://www.history.navy.mil/about-us/privacy-policy.html",
    ),
    SourceCanary(
        "doe_aec",
        "https://www.energy.gov/nnsa/foia-reading-room?page=1&page_size=100",
        "https://www.energy.gov/robots.txt",
        "https://www.energy.gov/about-us/web-policies",
    ),
    SourceCanary(
        "air_force_blue_book",
        "https://www.archives.gov/research/military/air-force/ufos?page=1&page_size=100",
        "https://www.archives.gov/robots.txt",
        "https://www.archives.gov/global-pages/privacy.html",
    ),
)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_digest(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return sha256(payload)


def fetch(url: str, *, timeout: float) -> tuple[int, str, bytes]:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/json;q=0.9,*/*;q=0.1",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return int(response.status), response.geturl(), response.read()
    except urllib.error.HTTPError as exc:
        return int(exc.code), exc.geturl(), exc.read()


def robots_decision(source: SourceCanary, body: bytes) -> tuple[bool, str]:
    parser = urllib.robotparser.RobotFileParser()
    parser.set_url(source.robots_url)
    parser.parse(body.decode("utf-8", errors="replace").splitlines())
    allowed = parser.can_fetch(USER_AGENT, source.index_url)
    return allowed, "allowed" if allowed else "denied"


def write_bytes(root: Path, adapter_id: str, run_number: int, name: str, body: bytes) -> None:
    target = root / adapter_id / f"run-{run_number}" / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(body)


def run_source(
    source: SourceCanary,
    root: Path,
    *,
    delay: float,
    timeout: float,
) -> dict[str, Any]:
    parser = PARSER_REGISTRY[source.adapter_id]
    policy_runs: list[dict[str, Any]] = []
    enumerations: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []

    for run_number in (1, 2):
        if run_number > 1:
            time.sleep(delay)
        robots_status, robots_final_url, robots_body = fetch(
            source.robots_url,
            timeout=timeout,
        )
        write_bytes(root, source.adapter_id, run_number, "robots.txt", robots_body)
        policy_status, policy_final_url, policy_body = fetch(
            source.policy_url,
            timeout=timeout,
        )
        write_bytes(root, source.adapter_id, run_number, "policy.html", policy_body)

        robots_allowed = False
        robots_note = "robots fetch failed"
        if 200 <= robots_status < 300:
            robots_allowed, robots_note = robots_decision(source, robots_body)
        policy_available = 200 <= policy_status < 300 and bool(policy_body.strip())
        policy_runs.append(
            {
                "run": run_number,
                "robots_url": robots_final_url,
                "robots_status": robots_status,
                "robots_sha256": sha256(robots_body),
                "robots_allowed": robots_allowed,
                "robots_note": robots_note,
                "policy_url": policy_final_url,
                "policy_status": policy_status,
                "policy_sha256": sha256(policy_body),
                "policy_page_available": policy_available,
                "manual_terms_review_required": True,
                "policy_disposition": (
                    "policy page captured; no legal conclusion made"
                    if policy_available
                    else "policy page unavailable"
                ),
            }
        )

        if not robots_allowed:
            failures.append(
                {"run": run_number, "class": "ROBOTS_DENIAL", "detail": robots_note}
            )
            continue
        if not policy_available:
            failures.append(
                {
                    "run": run_number,
                    "class": "POLICY_PAGE_UNAVAILABLE",
                    "detail": str(policy_status),
                }
            )
            continue

        time.sleep(delay)
        status, final_url, body = fetch(source.index_url, timeout=timeout)
        write_bytes(root, source.adapter_id, run_number, "index.raw", body)
        response: dict[str, Any] = {
            "run": run_number,
            "request_url": source.index_url,
            "final_url": final_url,
            "status": status,
            "raw_response_sha256": sha256(body),
            "byte_size": len(body),
            "pages_requested": 1,
            "documents_downloaded": 0,
        }
        if not 200 <= status < 300:
            failures.append(
                {"run": run_number, "class": "HTTP_BLOCK", "detail": str(status)}
            )
            enumerations.append(response)
            continue
        try:
            records, has_next = parser(body)
        except ParserDriftError as exc:
            failures.append(
                {"run": run_number, "class": "PARSER_DRIFT", "detail": str(exc)}
            )
            response["parser_error"] = str(exc)
            enumerations.append(response)
            continue

        normalized = sorted(records, key=lambda row: row["source_key"])
        write_bytes(
            root,
            source.adapter_id,
            run_number,
            "records.json",
            (json.dumps(normalized, indent=2, sort_keys=True) + "\n").encode(),
        )
        response.update(
            {
                "record_count": len(normalized),
                "has_next": bool(has_next),
                "inventory_digest": canonical_digest(
                    [row["source_key"] for row in normalized]
                ),
                "parser_output_digest": canonical_digest(normalized),
            }
        )
        enumerations.append(response)

    successful = [row for row in enumerations if row.get("parser_output_digest")]
    deterministic = (
        len(successful) == 2
        and successful[0]["inventory_digest"] == successful[1]["inventory_digest"]
        and successful[0]["parser_output_digest"]
        == successful[1]["parser_output_digest"]
    )
    if len(successful) == 2 and not deterministic:
        failures.append(
            {
                "class": "NONDETERMINISTIC_INVENTORY",
                "detail": "two-run digests differ",
            }
        )

    recommendation = "DISABLE"
    if deterministic and not failures:
        recommendation = "ELIGIBLE_FOR_LIMITED_METADATA_MONITORING_AFTER_MANUAL_POLICY_REVIEW"
    elif all(
        row["class"] not in {"ROBOTS_DENIAL", "POLICY_PAGE_UNAVAILABLE"}
        for row in failures
    ):
        recommendation = "DISABLE_PENDING_PARSER_OR_ACCESS_REMEDIATION"

    result = {
        "adapter_id": source.adapter_id,
        "explicitly_enabled_for_canary": True,
        "rate_limit_seconds": delay,
        "policy_runs": policy_runs,
        "enumerations": enumerations,
        "deterministic": deterministic,
        "failures": failures,
        "recommendation": recommendation,
        "manual_policy_review_required": True,
        "no_document_publication": True,
        "no_bulk_acquisition": True,
    }
    ledger_path = root / source.adapter_id / "canary-ledger.json"
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    ledger_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("canary-output"))
    parser.add_argument("--delay", type=float, default=2.0)
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, Any]] = []
    for source in SOURCES:
        try:
            results.append(
                run_source(source, args.out, delay=args.delay, timeout=args.timeout)
            )
        except Exception as exc:  # continue with the remaining source canaries
            results.append(
                {
                    "adapter_id": source.adapter_id,
                    "explicitly_enabled_for_canary": True,
                    "deterministic": False,
                    "failures": [{"class": type(exc).__name__, "detail": str(exc)}],
                    "recommendation": "DISABLE",
                    "manual_policy_review_required": True,
                    "no_document_publication": True,
                    "no_bulk_acquisition": True,
                }
            )

    policy_ledger = [
        {
            "adapter_id": row["adapter_id"],
            "policy_runs": row.get("policy_runs", []),
            "recommendation": row["recommendation"],
        }
        for row in results
    ]
    eligible_label = (
        "ELIGIBLE_FOR_LIMITED_METADATA_MONITORING_AFTER_MANUAL_POLICY_REVIEW"
    )
    reproducibility = {
        "all_sources_deterministic": all(row.get("deterministic") for row in results),
        "eligible_sources": [
            row["adapter_id"]
            for row in results
            if row["recommendation"] == eligible_label
        ],
        "disabled_sources": [
            row["adapter_id"]
            for row in results
            if row["recommendation"] != eligible_label
        ],
        "manual_policy_review_required": True,
        "ledger_digest": canonical_digest(results),
        "documents_downloaded": 0,
        "baseline_mutated": False,
    }
    (args.out / "per-source-canary-ledger.json").write_text(
        json.dumps(results, indent=2, sort_keys=True) + "\n"
    )
    (args.out / "robots-and-terms-ledger.json").write_text(
        json.dumps(policy_ledger, indent=2, sort_keys=True) + "\n"
    )
    (args.out / "two-run-reproducibility-certificate.json").write_text(
        json.dumps(reproducibility, indent=2, sort_keys=True) + "\n"
    )
    print(json.dumps(reproducibility, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

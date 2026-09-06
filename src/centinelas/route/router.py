"""Maps ClassifiedItem labels to targets and builds deterministic payloads."""

from __future__ import annotations

from datetime import timezone

from centinelas.classify.labels import HUB_REPO, LABEL_TO_REPO
from centinelas.classify.rules import (
    is_critical_signal,
    permit_subtypes,
    water_utility_subtypes,
)
from centinelas.models import ClassifiedItem

_FINANCE_ENRICHED_REPOS = {"moneysweep-pr"}
_WATER_TAGGED_REPOS = {"aguayluz-pr", HUB_REPO}
_LOCATION_TAGGED_REPOS = {"ovnis-pr"}


def _stable_routed_at(item: ClassifiedItem) -> str:
    """Bind routing payloads to the stable capture observation.

    The transport envelope records the actual emission time outside message
    identity. Keeping a fresh wall-clock value inside the payload would give the
    same logical item different payload hashes and message IDs on every replay.
    """

    captured = item.captured_at
    if captured.tzinfo is None:
        captured = captured.replace(tzinfo=timezone.utc)
    return captured.astimezone(timezone.utc).isoformat()


def build_payload(item: ClassifiedItem, target_repo: str) -> dict:
    """Build one deterministic target payload.

    MoneySweep receives finance/location enrichment, AguaYLuz receives the
    water/permit taxonomy, and OVNIS receives resolved municipality candidates.
    Unknown values remain explicit empty or null fields where target contracts
    already require stable shape.
    """

    payload = {
        "schema_version": "1.0",
        "item_id": item.item_id,
        "source_url": item.source_url,
        "source_name": item.source_name,
        "title": item.title,
        "body_text": item.body_text,
        "published_at": item.published_at.isoformat(),
        "captured_at": item.captured_at.isoformat(),
        "evidence_tier": item.evidence_tier,
        "labels": [label.value for label in item.labels],
        "confidence": item.confidence,
        "classifier_reasoning": item.classifier_reasoning,
        "routed_to": target_repo,
        "routed_at": _stable_routed_at(item),
        "is_critical": is_critical_signal(f"{item.title} {item.body_text}"),
    }
    if target_repo in _FINANCE_ENRICHED_REPOS:
        payload.update(
            {
                "municipalities": list(item.municipalities),
                "recipients": list(item.recipients),
                "agencies": list(item.agencies),
                "estimated_value": item.estimated_value,
                "signal_stage": item.signal_stage,
                "beat": item.beat,
            }
        )
    if target_repo in _WATER_TAGGED_REPOS:
        text = f"{item.title} {item.body_text}"
        tags = water_utility_subtypes(text)
        for tag in permit_subtypes(text):
            if tag not in tags:
                tags.append(tag)
        payload["domain_tags"] = tags
    if target_repo in _LOCATION_TAGGED_REPOS:
        payload["municipalities"] = list(item.municipalities)
    return payload


def resolve_targets(item: ClassifiedItem) -> list[str]:
    """Return deduplicated domain targets, excluding the always-present Hub."""

    repos: list[str] = []
    seen: set[str] = set()
    for label in item.labels:
        repo = LABEL_TO_REPO.get(label)
        if repo and repo not in seen:
            repos.append(repo)
            seen.add(repo)
    return repos


def route(item: ClassifiedItem) -> dict[str, dict]:
    """Return deterministic payloads for domain targets and TheHub."""

    result = {repo: build_payload(item, repo) for repo in resolve_targets(item)}
    result[HUB_REPO] = build_payload(item, HUB_REPO)
    return result

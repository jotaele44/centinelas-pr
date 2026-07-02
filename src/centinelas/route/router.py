"""Maps ClassifiedItem labels → target repos and builds dispatch payloads."""

from __future__ import annotations

from datetime import datetime, timezone

from centinelas.classify.labels import HUB_REPO, LABEL_TO_REPO, DomainLabel
from centinelas.models import ClassifiedItem


def build_payload(item: ClassifiedItem, target_repo: str) -> dict:
    """Build the JSON payload for a target repo's intake/ folder."""
    return {
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
        "routed_at": datetime.now(timezone.utc).isoformat(),
    }


def resolve_targets(item: ClassifiedItem) -> list[str]:
    """Return list of target repo names for the item (excludes thehub — always dispatched separately)."""
    repos: list[str] = []
    seen: set[str] = set()
    for label in item.labels:
        repo = LABEL_TO_REPO.get(label)
        if repo and repo not in seen:
            repos.append(repo)
            seen.add(repo)
    return repos


def route(item: ClassifiedItem) -> dict[str, dict]:
    """
    Return mapping of {repo_name: payload} for all targets including thehub.
    thehub always receives every item regardless of labels.
    """
    targets = resolve_targets(item)
    result: dict[str, dict] = {}

    for repo in targets:
        result[repo] = build_payload(item, repo)

    # Hub always gets a copy — full payload with all labels
    result[HUB_REPO] = build_payload(item, HUB_REPO)

    return result

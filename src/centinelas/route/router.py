"""Maps ClassifiedItem labels → target repos and builds dispatch payloads."""

from __future__ import annotations

from datetime import datetime, timezone

from centinelas.classify.labels import HUB_REPO, LABEL_TO_REPO
from centinelas.classify.rules import (
    is_critical_signal,
    permit_subtypes,
    water_utility_subtypes,
)
from centinelas.models import ClassifiedItem
from centinelas.project_leads import build_project_lead, qualifies_project_lead

# Targets that consume the pre-officialization finance/location enrichment.
# Only the MoneySweep anchor needs it (to build a *located* finance candidate);
# its intake contract declares the fields. The Hub stays on its base contract
# and receives the fused finance/location result later via canonical federation
# packages. Other domain repos keep the lean base payload.
_FINANCE_ENRICHED_REPOS = {"moneysweep-pr"}

# Targets that consume the water/utility sub-taxonomy tags.
_WATER_TAGGED_REPOS = {"aguayluz-pr", HUB_REPO}

# Targets that consume resolved PR municipalities.
_LOCATION_TAGGED_REPOS = {"ovnis-pr"}

# A project lead is deliberately shared with these participants.  The envelope
# has identity_effect=NONE: it is a common investigation key, not proof that any
# MoneySweep record and SpiderWeb asset are the same entity/project.
_PROJECT_LEAD_REPOS = {"moneysweep-pr", "spiderweb-pr", HUB_REPO}


def build_payload(item: ClassifiedItem, target_repo: str) -> dict:
    """Build the JSON payload for a target repo's intake folder."""
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
        "routed_at": datetime.now(timezone.utc).isoformat(),
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

    if target_repo in _PROJECT_LEAD_REPOS:
        lead = build_project_lead(item)
        if lead is not None:
            payload["project_lead"] = lead
    return payload


def resolve_targets(item: ClassifiedItem) -> list[str]:
    """Return domain target repos for an item (Hub is dispatched separately).

    Normal signals preserve label-driven routing.  A qualifying finance-anchored
    project lead additionally fans out to SpiderWeb so fiscal and physical lanes
    investigate the same immutable lead independently.
    """
    repos: list[str] = []
    seen: set[str] = set()
    for label in item.labels:
        repo = LABEL_TO_REPO.get(label)
        if repo and repo not in seen:
            repos.append(repo)
            seen.add(repo)

    if qualifies_project_lead(item):
        for repo in ("moneysweep-pr", "spiderweb-pr"):
            if repo not in seen:
                repos.append(repo)
                seen.add(repo)
    return repos


def route(item: ClassifiedItem) -> dict[str, dict]:
    """Return {repo_name: payload} for all targets including TheHub."""
    targets = resolve_targets(item)
    result: dict[str, dict] = {}

    for repo in targets:
        result[repo] = build_payload(item, repo)

    # Hub always gets a copy.  For project leads it receives discovery provenance
    # only; producer-returned federation assertions remain authoritative for their
    # domains and are correlated later by TheHub.
    result[HUB_REPO] = build_payload(item, HUB_REPO)

    return result

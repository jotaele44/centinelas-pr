"""Maps ClassifiedItem labels → target repos and builds dispatch payloads."""

from __future__ import annotations

from datetime import datetime, timezone

from centinelas.classify.labels import HUB_REPO, LABEL_TO_REPO
from centinelas.classify.rules import is_critical_signal, water_utility_subtypes
from centinelas.models import ClassifiedItem

# Targets that consume the pre-officialization finance/location enrichment.
# Only the MoneySweep anchor needs it (to build a *located* finance candidate);
# its intake contract declares the fields. The Hub stays on its base contract
# (thehub.schema.json) and receives the fused finance/location result later via
# the canonical federation packages, not this raw enrichment. Other domain repos
# keep the lean base payload.
_FINANCE_ENRICHED_REPOS = {"moneysweep-pr"}

# Targets that consume the water/utility sub-taxonomy tags. aguayluz-pr (the
# water/power/outage node) uses them to recognize *which* utility beat a signal
# is about; the Hub gets them for cross-repo correlation. Other repos keep the
# lean base payload.
_WATER_TAGGED_REPOS = {"aguayluz-pr", HUB_REPO}

# Targets that consume the resolved PR municipalities. ovnis-pr (the anomalous
# case corpus) is Puerto Rico-scoped and requires a location_name on every case;
# passing the already-resolved municipalities lets its intake derive that
# location instead of quarantining an otherwise valid signal. This reuses the
# classifier's existing enrichment (item.municipalities) — no new resolution.
_LOCATION_TAGGED_REPOS = {"ovnis-pr"}


def build_payload(item: ClassifiedItem, target_repo: str) -> dict:
    """Build the JSON payload for a target repo's intake/ folder.

    The MoneySweep anchor additionally receives the pre-officialization
    finance/location enrichment when the classifier populated it, so it can
    build a *located* finance candidate. The fields are always present for that
    target (empty when unknown) so its intake contract is stable. Every other
    target — including the Hub — keeps the base payload shape.
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
        "routed_at": datetime.now(timezone.utc).isoformat(),
        # Life-safety flag: emergency/evacuation/boil-water/hurricane-warning language
        # in the signal. Lets downstream producers + the Hub fast-track it into the
        # ASAP push/SMS tier instead of a batched brief.
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
        # Fine-grained water/utility beat tags (potable_water, boil_water,
        # reservoir_drought, power_grid, …) so aguayluz can route within its domain.
        payload["domain_tags"] = water_utility_subtypes(f"{item.title} {item.body_text}")
    if target_repo in _LOCATION_TAGGED_REPOS:
        # Resolved PR municipalities so ovnis can set a case location_name.
        # Always present (empty when unknown) so its intake contract is stable.
        payload["municipalities"] = list(item.municipalities)
    return payload


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

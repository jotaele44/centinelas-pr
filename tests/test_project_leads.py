from datetime import datetime, timezone

from centinelas.classify.labels import DomainLabel, HUB_REPO
from centinelas.models import ClassifiedItem
from centinelas.project_leads import project_lead_id, qualifies_project_lead
from centinelas.route.router import resolve_targets, route


def _item(*, item_id: str, title: str, body: str = "", stage=None, labels=None):
    return ClassifiedItem(
        item_id=item_id,
        source_url=f"https://example.com/{item_id}",
        source_name="Regression",
        title=title,
        body_text=body,
        published_at=datetime(2026, 8, 17, 12, 0, tzinfo=timezone.utc),
        captured_at=datetime(2026, 8, 17, 12, 1, tzinfo=timezone.utc),
        labels=labels or [DomainLabel.FINANCIAL],
        confidence=0.95,
        classifier_reasoning="regression",
        signal_stage=stage,
    )


def test_project_announcement_fans_same_lead_to_money_spider_and_hub():
    item = _item(
        item_id="los-rosales-observed-banner",
        title="Programa de reparaciones y recuperación - Residencial Los Rosales",
        body="Contrato 2025-000139; FEMA 4339; PW 9663; inversion $56,432.84",
        stage="announced",
    )
    assert qualifies_project_lead(item)
    targets = resolve_targets(item)
    assert targets == ["moneysweep-pr", "spiderweb-pr"]

    payloads = route(item)
    expected = project_lead_id(item)
    assert payloads["moneysweep-pr"]["project_lead"]["lead_id"] == expected
    assert payloads["spiderweb-pr"]["project_lead"]["lead_id"] == expected
    assert payloads[HUB_REPO]["project_lead"]["lead_id"] == expected
    for repo in ("moneysweep-pr", "spiderweb-pr", HUB_REPO):
        assert payloads[repo]["project_lead"]["identity_effect"] == "NONE"


def test_non_project_financial_signal_preserves_existing_discovery_route():
    item = _item(
        item_id="ordinary-finance-news",
        title="Agency publishes quarterly expenditure totals",
        body="The report summarizes spending for the quarter.",
        stage=None,
    )
    assert not qualifies_project_lead(item)
    assert resolve_targets(item) == ["moneysweep-pr"]
    payloads = route(item)
    assert "project_lead" not in payloads["moneysweep-pr"]
    assert "project_lead" not in payloads[HUB_REPO]


def test_project_terms_without_financial_label_do_not_promote_identity_or_fanout():
    item = _item(
        item_id="geo-project-mention",
        title="Mapping project documents coastal geology",
        body="Research project report.",
        labels=[DomainLabel.GEO_GEOLOGY],
    )
    assert not qualifies_project_lead(item)
    assert resolve_targets(item) == ["spiderweb-pr"]


def test_lead_id_is_deterministic_and_item_scoped():
    a = _item(item_id="same-item", title="Project contract announced", stage="announced")
    b = _item(item_id="same-item", title="Different normalized title", stage="announced")
    c = _item(item_id="other-item", title="Project contract announced", stage="announced")
    assert project_lead_id(a) == project_lead_id(b)
    assert project_lead_id(a) != project_lead_id(c)

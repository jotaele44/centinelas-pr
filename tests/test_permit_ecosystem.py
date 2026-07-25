"""Tests for the Puerto Rico permit-ecosystem intake:

- DRNA/federal permit vocabulary routes ENVIRONMENTAL -> aguayluz-pr
- permit sub-taxonomy tags and their merge into domain_tags
- Federal Register API connector (mapping + config gating, network mocked)
"""

from datetime import datetime, timezone

from centinelas.classify.labels import HUB_REPO, DomainLabel
from centinelas.classify.rules import keyword_classify, permit_subtypes
from centinelas.ingest import federal_register as fr
from centinelas.models import ClassifiedItem
from centinelas.route.router import build_payload, route


def _classified(title, body="", labels=None):
    return ClassifiedItem(
        item_id="p1", source_url="https://example.pr/x", source_name="Test",
        title=title, body_text=body,
        published_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
        captured_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
        labels=labels or [DomainLabel.ENVIRONMENTAL], confidence=0.8,
    )


# ── Classification vocabulary ────────────────────────────────────────────────

def test_permit_terms_route_environmental():
    for text in [
        "Deslinde de la zona maritimo terrestre aprobado en Cabo Rojo",
        "DRNA publica Declaracion de Impacto Ambiental para proyecto costero",
        "Aviso de vista publica sobre permiso de calidad de agua",
        "Revision publica del reglamento de zona costanera",
        "EPA issues NPDES permit; Corps of Engineers Section 404 review",
    ]:
        assert DomainLabel.ENVIRONMENTAL in keyword_classify(text), text


def test_accented_permit_terms_match():
    # PR source text carries accents; folding lets them hit the ASCII keywords.
    assert DomainLabel.ENVIRONMENTAL in keyword_classify(
        "Certificación de deslinde de la zona marítimo terrestre")
    assert DomainLabel.ENVIRONMENTAL in keyword_classify(
        "Inyección subterránea y calidad del aire")


def test_procurement_permit_still_financial():
    # A DRNA RFP/subasta remains a money signal (multi-label is fine).
    labels = keyword_classify("DRNA publica subasta y RFP para obra de dragado")
    assert DomainLabel.FINANCIAL in labels


def test_generic_words_do_not_false_trigger_environmental():
    # Guard against the over-broad tokens we deliberately excluded:
    # "día"/"días" (day), a generic work "permiso", a non-coastal "Section 10".
    assert DomainLabel.ENVIRONMENTAL not in keyword_classify(
        "El evento ocurrira en los proximos dias")
    assert DomainLabel.ENVIRONMENTAL not in keyword_classify(
        "Solicito un permiso para ausentarme del trabajo por unos dias")
    assert DomainLabel.ENVIRONMENTAL not in keyword_classify(
        "Section 10 of the corporate bylaws was amended")


# ── Permit sub-taxonomy ──────────────────────────────────────────────────────

def test_permit_subtypes_detected_and_ordered():
    tags = permit_subtypes(
        "Vista publica sobre deslinde de zona maritimo terrestre; "
        "Declaracion de Impacto Ambiental; permiso de calidad de aire")
    assert "coastal_zmt" in tags
    assert "environmental_impact" in tags
    assert "air_quality" in tags
    assert "public_hearing" in tags
    # deterministic order follows _PERMIT_TAGS insertion
    order = ["coastal_zmt", "environmental_impact", "air_quality", "water_permit",
             "wells_injection", "underground_tanks", "land_contamination",
             "public_hearing", "procurement_permit", "regulation"]
    assert tags == sorted(tags, key=order.index)


def test_non_permit_text_has_no_permit_subtypes():
    assert permit_subtypes("The stock market rallied on earnings") == []


def test_permit_tags_merged_into_domain_tags_for_aguayluz_and_hub():
    item = _classified("Deslinde ZMT aprobado", "vista publica sobre impacto ambiental")
    payloads = route(item)
    for repo in ("aguayluz-pr", HUB_REPO):
        assert payloads[repo]["domain_tags"] == [
            "coastal_zmt", "environmental_impact", "public_hearing"]


def test_water_and_permit_tags_coexist_deduped():
    # Water tags come first, permit tags appended; no duplicates.
    item = _classified("PRASA boil water advisory", "deslinde de zona maritimo terrestre")
    tags = build_payload(item, "aguayluz-pr")["domain_tags"]
    assert tags[:2] == ["potable_water", "boil_water"]
    assert "coastal_zmt" in tags
    assert len(tags) == len(set(tags))


def test_non_water_repos_still_have_no_domain_tags():
    item = _classified("Deslinde ZMT aprobado", labels=[DomainLabel.ENVIRONMENTAL])
    assert "domain_tags" not in build_payload(item, "moneysweep-pr")


# ── Federal Register connector ───────────────────────────────────────────────

_FR_RESPONSE = {
    "count": 2,
    "results": [
        {
            "document_number": "2026-12939",
            "title": "Clean Water State Revolving Fund; Puerto Rico allocation",
            "publication_date": "2026-05-05",
            "html_url": "https://www.federalregister.gov/documents/2026/05/05/2026-12939/cwsrf",
            "abstract": "EPA notice affecting Puerto Rico water infrastructure.",
            "type": "Notice",
        },
        {
            "document_number": "2026-06808",
            "title": "Section 404 permit program update",
            "publication_date": "2026-04-09",
            "html_url": "https://www.federalregister.gov/documents/2026/04/09/2026-06808/s404",
            "abstract": "Army Corps of Engineers dredge-and-fill permit action.",
            "type": "Rule",
        },
    ],
}


def test_federal_register_maps_results_to_raw_items(monkeypatch):
    captured = {}

    def fake_get_json(params):
        captured["params"] = params
        return _FR_RESPONSE

    monkeypatch.setattr(fr, "_get_json", fake_get_json)
    items = fr.poll_federal_register()

    assert len(items) == 2
    first = items[0]
    assert first.source_url.endswith("/cwsrf")
    assert first.source_name == "Federal Register — Notice"
    assert first.evidence_tier == "T1"
    assert first.published_at == datetime(2026, 5, 5, tzinfo=timezone.utc)
    assert "Puerto Rico" in first.title

    # config from sources.yaml drives the query params
    params = dict(captured["params"])
    assert params["conditions[term]"] == "Puerto Rico"
    agencies = [v for k, v in captured["params"] if k == "conditions[agencies][]"]
    assert "engineers-corps" in agencies
    assert "environmental-protection-agency" in agencies


def test_federal_register_items_classify_environmental(monkeypatch):
    monkeypatch.setattr(fr, "_get_json", lambda params: _FR_RESPONSE)
    for item in fr.poll_federal_register():
        assert DomainLabel.ENVIRONMENTAL in keyword_classify(
            f"{item.title} {item.body_text}"), item.title


def test_federal_register_disabled_returns_empty(monkeypatch):
    monkeypatch.setattr(fr, "_load_config", lambda: {"enabled": False})
    # _get_json must never be called when disabled
    monkeypatch.setattr(fr, "_get_json", lambda params: (_ for _ in ()).throw(
        AssertionError("network should not be hit when disabled")))
    assert fr.poll_federal_register() == []


def test_federal_register_network_failure_is_swallowed(monkeypatch):
    def boom(params):
        raise RuntimeError("connection reset")

    monkeypatch.setattr(fr, "_get_json", boom)
    assert fr.poll_federal_register() == []

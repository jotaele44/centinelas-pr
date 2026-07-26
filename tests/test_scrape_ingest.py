"""Tests for the HTML listing scrapers (OGPe / Junta de Planificación / EPA).

No test touches the network: every case monkeypatches ``web._fetch_html``, the
single seam the listing layer uses for HTTP (same pattern as the Federal
Register connector's ``_get_json``). The HTML fixtures reproduce the real DOM
shapes — Webflow CMS collections with tab panes and hidden bindings, and EPA's
permit table.
"""

from datetime import datetime, timezone
from pathlib import Path

from centinelas.classify.labels import DomainLabel
from centinelas.classify.rules import keyword_classify, permit_subtypes
from centinelas.ingest import web

FIXTURES = Path(__file__).parent / "fixtures"
WEBFLOW_HTML = (FIXTURES / "webflow_listing.html").read_text()
EPA_HTML = (FIXTURES / "epa_npdes_table.html").read_text()

OGPE_TABS = ["Vistas Públicas", "Documentos Ambientales"]


def _webflow_source(**overrides):
    source = {
        "name": "Test Webflow",
        "url": "https://jp.pr.gov/vistas-publicas",
        "parser": "webflow_cms",
        "tier": "T1",
    }
    source.update(overrides)
    return source


def _epa_source(**overrides):
    source = {
        "name": "EPA Region 2 — Puerto Rico NPDES Permits",
        "url": "https://www.epa.gov/npdes-permits/puerto-rico-npdes-permits",
        "parser": "html_table",
        "tier": "T1",
        "title_columns": ["Facility or Permit Name", "Permit Number", "Permit Status"],
        "date_column": "Public Notice Date",
    }
    source.update(overrides)
    return source


def _titles(items):
    return [i.title for i in items]


# ── Webflow CMS extraction ───────────────────────────────────────────────────

def test_webflow_extracts_entries_with_titles_and_dates(monkeypatch):
    monkeypatch.setattr(web, "_fetch_html", lambda url: WEBFLOW_HTML)
    items = web.scrape_listing(_webflow_source())

    assert len(items) > 1
    assert all(i.source_name == "Test Webflow" for i in items)
    assert all(i.evidence_tier == "T1" for i in items)

    castaner = next(i for i in items if "Castañer" in i.title)
    assert castaner.title == "VP - Poblado Castañer"
    assert castaner.published_at == datetime(2026, 7, 24, tzinfo=timezone.utc)


def test_date_div_sharing_the_title_class_does_not_become_the_title(monkeypatch):
    # On jp.pr.gov the date div also carries .vista-publica-title, so a naive
    # title selector returns "July 24, 2026". The title must win instead.
    monkeypatch.setattr(web, "_fetch_html", lambda url: WEBFLOW_HTML)
    items = web.scrape_listing(_webflow_source())
    assert not any(t.startswith("July 24, 2026") for t in _titles(items))


def test_hidden_webflow_bindings_are_excluded(monkeypatch):
    monkeypatch.setattr(web, "_fetch_html", lambda url: WEBFLOW_HTML)
    items = web.scrape_listing(_webflow_source())

    resolution = next(i for i in items if "JPE-2026-006" in i.title)
    # A w-condition-invisible badge and a w-dyn-bind-empty placeholder sit in the
    # markup but are invisible to a reader, so they must not reach the body.
    assert "DEROGADO" not in resolution.body_text
    assert "This is some text inside of a div block" not in resolution.body_text


def test_links_are_absolutized(monkeypatch):
    monkeypatch.setattr(web, "_fetch_html", lambda url: WEBFLOW_HTML)
    items = web.scrape_listing(_webflow_source())

    castaner = next(i for i in items if "Castañer" in i.title)
    assert castaner.source_url == "https://jp.pr.gov/files/JP/aviso-castaner.pdf"


def test_linkless_entries_get_unique_source_urls(monkeypatch):
    # Two link-less entries share a date; only the per-title slug keeps their
    # item_ids (sha256 of url+published_at) distinct.
    monkeypatch.setattr(web, "_fetch_html", lambda url: WEBFLOW_HTML)
    items = web.scrape_listing(_webflow_source())

    linkless = [i for i in items if "#" in i.source_url]
    assert len(linkless) >= 2
    assert len({i.source_url for i in linkless}) == len(linkless)
    assert len({i.item_id for i in linkless}) == len(linkless)


def test_subtitle_and_municipality_land_in_body(monkeypatch):
    # The project/applicant and municipality lines are what let the classifier
    # and the municipality enrichment locate a hearing.
    monkeypatch.setattr(web, "_fetch_html", lambda url: WEBFLOW_HTML)
    items = web.scrape_listing(_webflow_source(tabs=OGPE_TABS))

    vista = next(i for i in items if i.title == "2025-663228-PU-438754")
    assert "Toa Baja" in vista.body_text
    assert "Lymares Pérez" in vista.body_text
    assert vista.published_at == datetime(2026, 7, 31, 9, 30, tzinfo=timezone.utc)


# ── Tab curation (the noise decision) ────────────────────────────────────────

def test_tab_curation_excludes_manuals_and_videos(monkeypatch):
    monkeypatch.setattr(web, "_fetch_html", lambda url: WEBFLOW_HTML)
    items = web.scrape_listing(_webflow_source(tabs=OGPE_TABS))
    titles = " ".join(_titles(items))

    # Permit signals from the configured panes are ingested...
    assert "2025-663228-PU-438754" in titles
    assert "EXPANSIÓN LATERAL SISTEMA DE RELLENO SANITARIO DE ARROYO" in titles
    # ...while the how-to panes are not.
    assert "Manual" not in titles
    assert "Video Tutorial" not in titles


def test_without_tabs_every_item_on_the_page_is_read(monkeypatch):
    monkeypatch.setattr(web, "_fetch_html", lambda url: WEBFLOW_HTML)
    curated = web.scrape_listing(_webflow_source(tabs=OGPE_TABS))
    everything = web.scrape_listing(_webflow_source())
    assert len(everything) > len(curated)
    assert any("Manual" in t for t in _titles(everything))


# ── EPA table extraction ─────────────────────────────────────────────────────

def test_epa_table_rows_become_items(monkeypatch):
    monkeypatch.setattr(web, "_fetch_html", lambda url: EPA_HTML)
    items = web.scrape_listing(_epa_source())

    # Three data rows; the trailing all-empty row is skipped.
    assert len(items) == 3
    puerto_nuevo = items[0]
    assert puerto_nuevo.title == (
        "Puerto Nuevo Regional Wastewater Treatment Plant — PR0021555 — Final")
    assert puerto_nuevo.published_at == datetime(2021, 6, 2, tzinfo=timezone.utc)


def test_epa_body_carries_municipality_and_comment_deadline(monkeypatch):
    monkeypatch.setattr(web, "_fetch_html", lambda url: EPA_HTML)
    items = web.scrape_listing(_epa_source())

    draft = next(i for i in items if "Palo Seco" in i.title)
    assert "Location: Cataño" in draft.body_text
    assert "Public Notice Comment Period End Date: 4/14/2026" in draft.body_text
    assert "Permit Status: Draft" in draft.title or "Draft" in draft.title


def test_epa_row_link_is_absolutized(monkeypatch):
    monkeypatch.setattr(web, "_fetch_html", lambda url: EPA_HTML)
    items = web.scrape_listing(_epa_source())

    aguadilla = next(i for i in items if "Aguadilla" in i.title)
    assert aguadilla.source_url == "https://www.epa.gov/npdes-permits/aguadilla-rwwtp"


# ── poll_scrape_sources: gating, isolation, dedup ────────────────────────────

def test_layer_disabled_returns_empty_without_fetching(monkeypatch):
    monkeypatch.setattr(web, "_load_scrape_config", lambda: {"enabled": False})
    monkeypatch.setattr(web, "_fetch_html", lambda url: (_ for _ in ()).throw(
        AssertionError("network must not be touched when scraping is disabled")))
    assert web.poll_scrape_sources() == []


def test_disabled_source_is_skipped(monkeypatch):
    # USACE ships enabled:false because its CDN blocks programmatic clients.
    monkeypatch.setattr(web, "_load_scrape_config", lambda: {
        "enabled": True,
        "sources": [
            _webflow_source(name="Enabled"),
            _webflow_source(name="Disabled", enabled=False),
        ],
    })
    monkeypatch.setattr(web, "_fetch_html", lambda url: WEBFLOW_HTML)

    items = web.poll_scrape_sources()
    assert {i.source_name for i in items} == {"Enabled"}


def test_one_failing_source_does_not_abort_the_others(monkeypatch):
    def flaky(url):
        if "broken" in url:
            raise RuntimeError("connection reset")
        return WEBFLOW_HTML

    monkeypatch.setattr(web, "_load_scrape_config", lambda: {
        "enabled": True,
        "sources": [
            _webflow_source(name="Broken", url="https://broken.example/list"),
            _webflow_source(name="Healthy"),
        ],
    })
    monkeypatch.setattr(web, "_fetch_html", flaky)

    items = web.poll_scrape_sources()
    assert items and {i.source_name for i in items} == {"Healthy"}


def test_unreachable_page_yields_no_items(monkeypatch):
    monkeypatch.setattr(web, "_fetch_html", lambda url: None)
    assert web.scrape_listing(_webflow_source()) == []


def test_unknown_parser_is_ignored(monkeypatch):
    monkeypatch.setattr(web, "_fetch_html", lambda url: WEBFLOW_HTML)
    assert web.scrape_listing(_webflow_source(parser="does-not-exist")) == []


def test_items_are_deduped_across_sources(monkeypatch):
    # Same page configured twice → identical item_ids collapse.
    monkeypatch.setattr(web, "_load_scrape_config", lambda: {
        "enabled": True,
        "sources": [_webflow_source(name="A"), _webflow_source(name="B")],
    })
    monkeypatch.setattr(web, "_fetch_html", lambda url: WEBFLOW_HTML)

    items = web.poll_scrape_sources()
    assert len({i.item_id for i in items}) == len(items)


# ── Tie-in with the phase-1 classification vocabulary ────────────────────────

def test_scraped_hearing_classifies_environmental_with_permit_tags(monkeypatch):
    monkeypatch.setattr(web, "_fetch_html", lambda url: WEBFLOW_HTML)
    items = web.scrape_listing(_webflow_source())

    vista = next(i for i in items if "deslinde" in i.title.lower())
    text = f"{vista.title} {vista.body_text}"
    assert DomainLabel.ENVIRONMENTAL in keyword_classify(text)
    tags = permit_subtypes(text)
    assert "coastal_zmt" in tags
    assert "public_hearing" in tags


def test_section_context_lets_a_case_numbered_hearing_classify(monkeypatch):
    # The real failure this guards: OGPe/JP hearings are titled with only a case
    # number or short code, so without the section label folded into the body
    # they carry no classifiable word and never reach the permit lane.
    monkeypatch.setattr(web, "_fetch_html", lambda url: WEBFLOW_HTML)

    bare = web.scrape_listing(_webflow_source())
    unlabelled = next(i for i in bare if i.title == "VP - Poblado Castañer")
    assert DomainLabel.ENVIRONMENTAL not in keyword_classify(
        f"{unlabelled.title} {unlabelled.body_text}")

    labelled_source = _webflow_source(section="Vista pública de la Junta de Planificación")
    labelled = web.scrape_listing(labelled_source)
    hearing = next(i for i in labelled if i.title == "VP - Poblado Castañer")
    assert hearing.body_text.startswith("Vista pública de la Junta de Planificación")
    text = f"{hearing.title} {hearing.body_text}"
    assert DomainLabel.ENVIRONMENTAL in keyword_classify(text)
    assert "public_hearing" in permit_subtypes(text)


def test_tab_name_is_folded_in_as_section(monkeypatch):
    # For tabbed pages the section comes from the pane itself, so an OGPe hearing
    # titled with a bare case number still says what it is.
    monkeypatch.setattr(web, "_fetch_html", lambda url: WEBFLOW_HTML)
    items = web.scrape_listing(_webflow_source(tabs=OGPE_TABS))

    vista = next(i for i in items if i.title == "2025-663228-PU-438754")
    assert vista.body_text.startswith("Vistas Públicas")
    assert DomainLabel.ENVIRONMENTAL in keyword_classify(
        f"{vista.title} {vista.body_text}")

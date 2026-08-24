"""Tests for the HTML listing scrapers (OGPe / Junta de Planificación / EPA / ASG).

No test touches the network: every case monkeypatches ``web._fetch_html``, the
single seam the listing layer uses for HTTP (same pattern as the Federal
Register connector's ``_get_json``). The HTML fixtures reproduce the real DOM
shapes — Webflow CMS collections with tab panes and hidden bindings, EPA's
permit table, and ASG's Bootstrap cards.
"""

from datetime import datetime, timezone
from pathlib import Path

from centinelas.classify.labels import DomainLabel
from centinelas.classify.rules import keyword_classify, permit_subtypes
from centinelas.ingest import web
from centinelas.models import RawItem

FIXTURES = Path(__file__).parent / "fixtures"
WEBFLOW_HTML = (FIXTURES / "webflow_listing.html").read_text()
EPA_HTML = (FIXTURES / "epa_npdes_table.html").read_text()
ASG_SUBASTAS_HTML = (FIXTURES / "asg_subastas.html").read_text()
ASG_DETAIL_HTML = (FIXTURES / "asg_subasta_detail.html").read_text()
ASG_NOTICIAS_HTML = (FIXTURES / "asg_noticias.html").read_text()

OGPE_TABS = ["Vistas Públicas", "Documentos Ambientales"]

# Two entries carrying no date node at all — the case whose identity must not
# depend on when we happened to poll.
UNDATED_HTML = """
<html><body><div class="w-dyn-items">
  <div class="w-dyn-item"><div class="noticia-title">Vista pública sin fecha</div></div>
  <div class="w-dyn-item"><div class="noticia-title">Otra vista pública sin fecha</div></div>
</div></body></html>
"""

# Minimal RSS index + notice page for the rss_detail parser. The pubDate is
# RFC-822, the format real feeds use.
RSS_INDEX = """<?xml version="1.0"?>
<rss version="2.0"><channel>
  <item>
    <title>SAJ-2023-00283(AJC)</title>
    <link>https://example.mil/notices/saj-2023-00283</link>
    <pubDate>Wed, 01 Oct 2025 14:48:00 GMT</pubDate>
  </item>
</channel></rss>
"""
RSS_NOTICE = (
    "<html><body><p>Joint public notice for a Section 404 permit in "
    "Puerto Rico, San Juan Harbor.</p></body></html>"
)


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


def test_undated_entry_keeps_a_stable_id_across_polls(monkeypatch):
    # Regression: item_id used to hash url + now() when a date could not be
    # parsed, so the same unchanged entry got a fresh id on every poll. Because
    # the pipeline names files by item_id, those records accumulated in the
    # queue and in each target repo's intake/ instead of overwriting.
    monkeypatch.setattr(web, "_fetch_html", lambda url: UNDATED_HTML)

    first = {i.title: i.item_id for i in web.scrape_listing(_webflow_source())}
    second = {i.title: i.item_id for i in web.scrape_listing(_webflow_source())}

    assert first and first == second


def test_undated_entries_with_different_titles_get_different_ids(monkeypatch):
    # The stable-id fallback must not collapse distinct undated rows into one.
    monkeypatch.setattr(web, "_fetch_html", lambda url: UNDATED_HTML)
    items = web.scrape_listing(_webflow_source())

    assert len(items) == 2
    assert len({i.item_id for i in items}) == 2


def test_dated_entry_id_is_unchanged_by_the_fallback(monkeypatch):
    # Entries whose date parses keep exactly the url+date identity they had, so
    # nothing already ingested churns.
    monkeypatch.setattr(web, "_fetch_html", lambda url: WEBFLOW_HTML)
    castaner = next(
        i for i in web.scrape_listing(_webflow_source()) if "Castañer" in i.title)

    assert castaner.item_id == RawItem.make_id(
        castaner.source_url, datetime(2026, 7, 24, tzinfo=timezone.utc))


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


# ── rss_detail (stub feed → per-notice fetch) ────────────────────────────────

def _rss_detail_source(**overrides):
    source = {
        "name": "USACE Jacksonville — Regulatory Public Notices",
        "url": "https://example.mil/rss",
        "parser": "rss_detail",
        "tier": "T1",
        "match_any": ["puerto rico", "antilles"],
    }
    source.update(overrides)
    return source


def _rss_fetch(url):
    return RSS_INDEX if url.endswith("/rss") else RSS_NOTICE


def test_rss_detail_parses_rfc822_pubdate(monkeypatch):
    # The feed's RFC-822 pubDate is not among _DATE_FORMATS, so a string parse
    # returned None and every notice fell back to now() — both wrong as a date
    # and unstable as an identity.
    monkeypatch.setattr(web, "_fetch_html", _rss_fetch)
    items = web.scrape_listing(_rss_detail_source())

    assert len(items) == 1
    notice = items[0]
    assert notice.published_at == datetime(2025, 10, 1, 14, 48, tzinfo=timezone.utc)
    assert notice.item_id == RawItem.make_id(notice.source_url, notice.published_at)
    assert "Puerto Rico" in notice.body_text


def test_rss_detail_filters_by_match_any(monkeypatch):
    monkeypatch.setattr(
        web, "_fetch_html",
        lambda url: RSS_INDEX if url.endswith("/rss")
        else "<html><body><p>A notice about Tampa Bay, Florida.</p></body></html>")
    assert web.scrape_listing(_rss_detail_source()) == []


# ── asg_cards (Bootstrap card listings + optional per-entry date fetch) ──────

def _asg_subastas_source(**overrides):
    source = {
        "name": "ASG — Licitaciones (Subastas)",
        "url": "https://asg.pr.gov/subastas?order_by=-creado",
        "parser": "asg_cards",
        "tier": "T1",
        "section": "Licitación de la Administración de Servicios Generales",
        "item_selector": ".card-media-info",
        "title_selectors": [
            ".subasta-card-number", ".subasta-card-method", ".subasta-card-agency",
        ],
        "body_selectors": [
            ".subasta-card-purpose", ".subasta-card-agency", ".subasta-card-method",
        ],
        "link_selector": "a[href]",
        "detail_date_label": "Acto de Apertura",
        "max_pages": 1,
    }
    source.update(overrides)
    return source


def _asg_noticias_source(**overrides):
    source = {
        "name": "ASG — Noticias",
        "url": "https://asg.pr.gov/noticias/",
        "parser": "asg_cards",
        "tier": "T2",
        "section": "Noticia de la Administración de Servicios Generales",
        "item_selector": "article.blog-card, article.blog-featured",
        "title_selectors": [".blog-card-title", ".blog-featured-body h2"],
        "date_selector": ".blog-card-meta span:last-of-type",
        "body_selectors": ["p"],
        "link_selector": "a.blog-link",
        "max_pages": 1,
    }
    source.update(overrides)
    return source


def _asg_fetch(url):
    """Listing pages vs. bid detail pages, the way the live site splits them."""
    return ASG_DETAIL_HTML if "/subastas2" in url else ASG_SUBASTAS_HTML


def test_asg_card_title_carries_number_method_and_agency(monkeypatch):
    # A bid card's own heading is a bare code ("26J-14214-R1"). Joining the
    # method and agency in is what gives the title anything to read.
    monkeypatch.setattr(web, "_fetch_html", _asg_fetch)
    items = web.scrape_listing(_asg_subastas_source())

    assert len(items) == 3
    bid = next(i for i in items if i.title.startswith("26J-14214-R1"))
    assert bid.title == (
        "26J-14214-R1 — Subasta Formal — "
        "DEPARTAMENTO DE CORRECCION Y REHABILITACION (DCR)"
    )
    assert "ACONDICIONADORES DE AIRE" in bid.body_text
    assert bid.evidence_tier == "T1"


def test_asg_card_links_are_absolutized(monkeypatch):
    monkeypatch.setattr(web, "_fetch_html", _asg_fetch)
    items = web.scrape_listing(_asg_subastas_source())

    bid = next(i for i in items if i.title.startswith("26J-10309"))
    assert bid.source_url == "https://asg.pr.gov/subastas26J-10309"


def test_asg_bid_date_comes_from_the_labelled_milestone(monkeypatch):
    # The detail page lists "Reunión Pre Subasta" (3 Feb) BEFORE "Acto de
    # Apertura" (24 Feb), so taking the page's first date would be wrong.
    monkeypatch.setattr(web, "_fetch_html", _asg_fetch)
    items = web.scrape_listing(_asg_subastas_source())

    assert all(i.published_at == datetime(2026, 2, 24, tzinfo=timezone.utc) for i in items)


def test_asg_bid_id_is_stable_across_polls(monkeypatch):
    monkeypatch.setattr(web, "_fetch_html", _asg_fetch)
    first = web.scrape_listing(_asg_subastas_source())
    second = web.scrape_listing(_asg_subastas_source())

    assert {i.item_id for i in first} == {i.item_id for i in second}
    assert len({i.item_id for i in first}) == 3
    bid = first[0]
    assert bid.item_id == RawItem.make_id(bid.source_url, bid.published_at)


def test_asg_max_pages_bounds_the_crawl(monkeypatch):
    # The live bid index runs to 64 pages and each entry costs a second request
    # for its date, so an unbounded sweep would be ~1,700 fetches per poll.
    listing_urls = []

    def counting_fetch(url):
        if "/subastas2" in url:
            return ASG_DETAIL_HTML
        listing_urls.append(url)
        return ASG_SUBASTAS_HTML

    monkeypatch.setattr(web, "_fetch_html", counting_fetch)
    web.scrape_listing(_asg_subastas_source(max_pages=2))

    assert listing_urls == [
        "https://asg.pr.gov/subastas?order_by=-creado",
        "https://asg.pr.gov/subastas?order_by=-creado&page=2",
    ]


def test_asg_pagination_preserves_the_configured_sort():
    # Dropping order_by would paginate an unsorted index, so page 2 of a routine
    # poll would no longer be the second-newest batch of bids.
    assert web._page_url("https://asg.pr.gov/subastas?order_by=-creado", 3) == (
        "https://asg.pr.gov/subastas?order_by=-creado&page=3"
    )


def test_asg_crawl_stops_when_a_page_yields_nothing(monkeypatch):
    # max_pages is an upper bound, not a page count: a listing shorter than the
    # bound must not keep requesting empty pages to reach it.
    fetched = []

    def two_page_index(url):
        fetched.append(url)
        return "<html><body></body></html>" if "page=" in url else ASG_NOTICIAS_HTML

    monkeypatch.setattr(web, "_fetch_html", two_page_index)
    items = web.scrape_listing(_asg_noticias_source(max_pages=9))

    assert len(items) == 3  # page 1 only
    assert len(fetched) == 2  # page 1, then one empty page, then stop


def test_asg_noticias_are_dated_from_the_card_without_a_detail_fetch(monkeypatch):
    def listing_only(url):
        assert url.startswith("https://asg.pr.gov/noticias/"), f"unexpected fetch: {url}"
        return ASG_NOTICIAS_HTML

    monkeypatch.setattr(web, "_fetch_html", listing_only)
    items = web.scrape_listing(_asg_noticias_source())

    mercadito = next(i for i in items if "Mercadito" in i.title)
    assert mercadito.published_at == datetime(2025, 5, 23, tzinfo=timezone.utc)
    assert mercadito.source_url == "https://asg.pr.gov/noticias/la-gsa-lanza-mercadito"


def test_asg_featured_lead_story_is_not_dropped(monkeypatch):
    # The promoted story is <article class="blog-featured"> with a plain <h2>,
    # not <article class="blog-card"> with a .blog-card-title. Matching only the
    # card shape silently loses whichever story ASG is currently featuring.
    monkeypatch.setattr(web, "_fetch_html", lambda url: ASG_NOTICIAS_HTML)
    items = web.scrape_listing(_asg_noticias_source())

    assert len(items) == 3
    featured = next(i for i in items if "OEA" in i.title)
    assert featured.published_at == datetime(2025, 12, 8, tzinfo=timezone.utc)
    assert featured.source_url.endswith("/noticias/la-oea-concede-premio-a-la-plataforma-de-compras")


def test_spanish_dates_parse_in_both_long_and_abbreviated_forms():
    # strptime's %B reads month names through the C locale, so every Spanish
    # date fell through _DATE_FORMATS and left the entry undated.
    assert web._parse_date("24 de febrero de 2026") == datetime(2026, 2, 24, tzinfo=timezone.utc)
    assert web._parse_date("08 Dic 2025") == datetime(2025, 12, 8, tzinfo=timezone.utc)
    # "setiembre" is the Puerto Rican spelling of "septiembre".
    assert web._parse_date("1 de setiembre de 2024") == datetime(2024, 9, 1, tzinfo=timezone.utc)
    # A date sharing its cell with a time, as ASG renders bid milestones.
    assert web._parse_date("24 de febrero de 2026    3:00 PM") == datetime(
        2026, 2, 24, tzinfo=timezone.utc)
    # English formats must keep working, and nonsense must stay None.
    assert web._parse_date("July 24, 2026") == datetime(2026, 7, 24, tzinfo=timezone.utc)
    assert web._parse_date("31 de febrero de 2026") is None
    assert web._parse_date("no es una fecha") is None


def test_asg_bid_without_a_reachable_detail_page_still_yields_an_item(monkeypatch):
    # A bid whose detail page 500s (the live site does this) must not take the
    # whole listing down with it.
    monkeypatch.setattr(
        web, "_fetch_html",
        lambda url: None if "/subastas2" in url else ASG_SUBASTAS_HTML)
    items = web.scrape_listing(_asg_subastas_source())

    assert len(items) == 3
    # Undated entries hash against the sentinel, so they stay stable rather than
    # minting a new id on every poll.
    assert all(i.item_id == RawItem.make_id(f"{i.source_url}|{i.title}", web._UNDATED)
               for i in items)


def test_asg_bid_classifies_into_the_procurement_lane(monkeypatch):
    monkeypatch.setattr(web, "_fetch_html", _asg_fetch)
    items = web.scrape_listing(_asg_subastas_source())

    bid = next(i for i in items if i.title.startswith("26J-14214-R1"))
    assert bid.body_text.startswith("Licitación de la Administración de Servicios Generales")
    assert "procurement_permit" in permit_subtypes(f"{bid.title} {bid.body_text}")


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

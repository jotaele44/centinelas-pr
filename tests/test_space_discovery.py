import pytest

from centinelas.space_discovery import (
    APICatalogAdapter,
    DedupStore,
    HTMLChangeAdapter,
    ManualReceiptAdapter,
    RSSAtomAdapter,
    RunLedger,
    SitemapAdapter,
    build_lead,
    route_receipt,
    validate_lead,
)

RSS = b"<rss><channel><item><title>Release</title><link>https://example.test/a</link></item></channel></rss>"
SITEMAP = b'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>https://example.test/a</loc><lastmod>2026-07-26</lastmod></url></urlset>'


def sample_lead(summary=None, sensor=None, tier="T1"):
    adapter = ManualReceiptAdapter()
    body = b"canonical metadata"
    return build_lead(
        source_id="CENT-SRC-SPACE-TEST",
        source_url="https://example.test/item",
        title="Dataset release",
        subcategory="SATELLITE_DATASET_RELEASE",
        body=body,
        receipt=adapter.receipt(source_url="https://example.test/item", body=body),
        summary=summary,
        sensor=sensor,
        evidence_tier=tier,
    )


def test_all_adapter_families_and_content_hashes():
    assert RSSAtomAdapter().parse(RSS, "https://example.test/")[0]["title"] == "Release"
    assert APICatalogAdapter().parse(b'{"results":[{"id":1}]}') == [{"id": 1}]
    assert HTMLChangeAdapter().fingerprint(b"a   b") == HTMLChangeAdapter().fingerprint(b"a b")
    assert SitemapAdapter().parse(SITEMAP)[0]["lastmod"] == "2026-07-26"
    receipt = ManualReceiptAdapter().receipt(source_url="https://example.test", body=b"x")
    assert len(receipt["content_sha256"]) == 64


def test_determinism_dedup_route_and_accounting():
    first, second = sample_lead(), sample_lead()
    assert first["content_fingerprint"] == second["content_fingerprint"]
    assert first["dedup_key"] == second["dedup_key"]
    store = DedupStore()
    assert store.register(first["content_fingerprint"], first["lead_id"]) is None
    assert store.register(second["content_fingerprint"], second["lead_id"]) == first["lead_id"]
    assert route_receipt(first)["route"] == "satellite-observations-pr"
    RunLedger(input_count=6, emitted=1, duplicate=1, out_of_scope=1, failed=1, unchanged=2).account()


def test_no_raw_binary_and_no_confirmation_language():
    with pytest.raises(ValueError, match="capture limit"):
        ManualReceiptAdapter().receipt(source_url="https://example.test", body=b"x" * 2_000_001)
    with pytest.raises(ValueError, match="confirmation"):
        sample_lead(summary="This confirms an alien craft")


def test_dsp_capability_requires_t1_reference():
    sensor = {
        "platform": "DSP",
        "platform_class": "satellite",
        "sensor_name": "DSP",
        "sensor_type": "infrared_warning",
        "spectral_or_measurement_domain": "infrared",
        "capability_known": True,
        "capability_source_ref": None,
    }
    with pytest.raises(ValueError, match="T1"):
        sample_lead(sensor=sensor, tier="T2")
    sensor["capability_source_ref"] = "primary-technical-record"
    validate_lead(sample_lead(sensor=sensor, tier="T1"))


def test_malformed_and_no_case_link_fixture():
    with pytest.raises(ValueError):
        APICatalogAdapter().parse(b'{"unexpected":[]}')
    lead = sample_lead()
    assert lead["potential_case_links"] == []
    assert lead["downstream_route"]["secondary"] == []

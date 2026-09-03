import json
from pathlib import Path

import pytest

from centinelas.space_discovery import (
    REQUIRED_LEAD_FIELDS,
    APICatalogAdapter,
    DedupStore,
    FailureLedger,
    HTMLChangeAdapter,
    ManualReceiptAdapter,
    RoutingReceiptStore,
    RSSAtomAdapter,
    RunLedger,
    SitemapAdapter,
    SourceHealthStore,
    build_lead,
    idempotency_key,
    route_receipt,
    validate_lead,
)

RSS = b"<rss><channel><item><title>Release</title><link>https://example.test/a</link></item></channel></rss>"
SITEMAP = b'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>https://example.test/a</loc><lastmod>2026-07-26</lastmod></url></urlset>'


def sample_lead(
    summary=None,
    sensor=None,
    tier="T1",
    *,
    source_url="https://example.test/item",
    body=b"canonical metadata",
    synthetic=True,
    **kwargs,
):
    adapter = ManualReceiptAdapter()
    return build_lead(
        source_id="CENT-SRC-SPACE-TEST",
        source_url=source_url,
        title="Dataset release",
        subcategory="SATELLITE_DATASET_RELEASE",
        body=body,
        receipt=adapter.receipt(source_url=source_url, body=body),
        summary=summary,
        sensor=sensor,
        evidence_tier=tier,
        synthetic=synthetic,
        **kwargs,
    )


def test_all_adapter_families_and_content_hashes():
    assert RSSAtomAdapter().parse(RSS, "https://example.test/")[0]["title"] == "Release"
    assert APICatalogAdapter().parse(b'{"results":[{"id":1}]}') == [{"id": 1}]
    assert HTMLChangeAdapter().fingerprint(b"a   b") == HTMLChangeAdapter().fingerprint(b"a b")
    assert SitemapAdapter().parse(SITEMAP)[0]["lastmod"] == "2026-07-26"
    receipt = ManualReceiptAdapter().receipt(source_url="https://example.test", body=b"x")
    assert len(receipt["content_sha256"]) == 64
    assert receipt["source_url"] == "https://example.test/"


def test_determinism_persistent_dedup_route_and_accounting(tmp_path):
    first, second = sample_lead(), sample_lead()
    assert first["content_fingerprint"] == second["content_fingerprint"]
    assert first["dedup_key"] == second["dedup_key"]
    assert len(first["lead_id"].rsplit("-", 1)[1]) == 16

    dedup_path = tmp_path / "dedup.jsonl"
    store = DedupStore(dedup_path)
    assert store.register(first["dedup_key"], first["lead_id"]) is None
    assert store.register(second["dedup_key"], second["lead_id"]) == first["lead_id"]
    assert DedupStore(dedup_path).register(second["dedup_key"], "later") == first["lead_id"]

    receipt = route_receipt(first)
    RoutingReceiptStore(tmp_path / "routes.jsonl").record(receipt)
    assert (
        json.loads((tmp_path / "routes.jsonl").read_text().splitlines()[0])["route"]
        == "satellite-observations-pr"
    )

    ledger = RunLedger(input_count=6, emitted=1, duplicate=1, out_of_scope=1, failed=1, unchanged=2)
    ledger.persist(tmp_path / "runs.jsonl", "run-1")
    assert json.loads((tmp_path / "runs.jsonl").read_text())["input_count"] == 6


def test_source_health_and_failure_persistence(tmp_path):
    SourceHealthStore(tmp_path / "health.jsonl").record("SRC", status="active", success=True)
    FailureLedger(tmp_path / "failures.jsonl").record(
        run_id="run-1", source_id="SRC", failure_class="parse", detail="bad XML", retryable=True
    )
    assert "SRC" in (tmp_path / "health.jsonl").read_text()
    assert "bad XML" in (tmp_path / "failures.jsonl").read_text()


def test_no_raw_binary_and_no_confirmation_language():
    adapter = ManualReceiptAdapter()
    with pytest.raises(ValueError, match="capture limit"):
        adapter.receipt(source_url="https://example.test", body=b"x" * 2_000_001)
    with pytest.raises(ValueError, match="binary payload"):
        adapter.receipt(
            source_url="https://example.test",
            body=b"\x89PNG\r\n\x1a\nsmall",
            content_type="image/png",
        )

    lead = sample_lead(summary="Official archive confirms publication of the dataset")
    validate_lead(lead)  # source wording is not treated as an analyst UAP claim
    lead["analyst_assertion"] = "This confirms an alien craft"
    with pytest.raises(ValueError, match="analyst assertion"):
        validate_lead(lead)


def test_dsp_claims_require_t1_reference_and_no_negative_inference():
    sensor = {
        "platform": "DSP",
        "platform_class": "satellite",
        "sensor_name": "DSP",
        "sensor_type": "infrared_warning",
        "spectral_or_measurement_domain": "infrared",
        "capability_known": False,
        "capability_source_ref": None,
        "coverage_claim": "covered the incident",
        "detection_claim": None,
        "sensitivity_claim": None,
    }
    with pytest.raises(ValueError, match="T1"):
        sample_lead(sensor=sensor, tier="T2")
    sensor["capability_source_ref"] = "primary-technical-record"
    validate_lead(sample_lead(sensor=sensor, tier="T1"))

    lead = sample_lead()
    lead["negative_inference"] = "absence proves no event"
    with pytest.raises(ValueError, match="negative inference"):
        validate_lead(lead)


def test_idempotency_uses_version_catalog_and_publication():
    base = {
        "canonical_url": "https://example.test/data",
        "catalog_identifier": "A",
        "dataset_version": "1",
        "published_at": "2026-01-01T00:00:00Z",
    }
    assert idempotency_key(base) != idempotency_key({**base, "dataset_version": "2"})
    assert idempotency_key(base) != idempotency_key({**base, "catalog_identifier": "B"})


def test_item_identity_is_separate_from_payload_identity(tmp_path):
    first = sample_lead(source_url="https://example.test/a", body=b"same bytes")
    second = sample_lead(source_url="https://example.test/b", body=b"same bytes")
    changed = sample_lead(source_url="https://example.test/a", body=b"changed bytes")

    assert first["content_fingerprint"] == second["content_fingerprint"]
    assert first["dedup_key"] != second["dedup_key"]
    assert first["lead_id"] != second["lead_id"]
    assert first["dedup_key"] == changed["dedup_key"]
    assert first["lead_id"] == changed["lead_id"]
    assert first["content_fingerprint"] != changed["content_fingerprint"]

    store = DedupStore(tmp_path / "dedup.jsonl")
    assert store.register(first["dedup_key"], first["lead_id"]) is None
    assert store.register(second["dedup_key"], second["lead_id"]) is None
    assert store.register(changed["dedup_key"], changed["lead_id"]) == first["lead_id"]


def test_schema_required_fields_match_runtime_gate():
    schema_path = Path(__file__).resolve().parents[1] / "schemas/space_data_lead.schema.json"
    schema = json.loads(schema_path.read_text())
    assert set(schema["required"]) == REQUIRED_LEAD_FIELDS

    lead = sample_lead()
    for field in REQUIRED_LEAD_FIELDS:
        malformed = {key: value for key, value in lead.items() if key != field}
        with pytest.raises(ValueError, match="missing required fields"):
            validate_lead(malformed)

    unexpected = sample_lead()
    unexpected["unreviewed_extension"] = "not part of the frozen contract"
    with pytest.raises(ValueError, match="unexpected fields"):
        validate_lead(unexpected)

    malformed_route = sample_lead()
    malformed_route["downstream_route"]["unreviewed_extension"] = True
    with pytest.raises(ValueError, match="downstream route fields"):
        validate_lead(malformed_route)


def test_xml_parsers_reject_unsafe_or_oversized_payloads():
    dtd = b'<!DOCTYPE rss [<!ENTITY x "expanded">]><rss><channel/></rss>'
    for parse in (
        lambda body: RSSAtomAdapter().parse(body, "https://example.test/"),
        SitemapAdapter().parse,
    ):
        with pytest.raises(ValueError, match="DTD and entity"):
            parse(dtd)
        with pytest.raises(ValueError, match="capture limit"):
            parse(b"<rss>" + b"x" * 2_000_000 + b"</rss>")


def test_receipt_evidence_cannot_be_overridden_or_detached():
    adapter = ManualReceiptAdapter()
    with pytest.raises(ValueError, match="cannot override evidence"):
        adapter.receipt(
            source_url="https://example.test/item",
            body=b"actual",
            content_sha256="0" * 64,
        )

    lead = sample_lead(source_url=" HTTPS://EXAMPLE.TEST/item ")
    assert lead["raw_source_url"] == " HTTPS://EXAMPLE.TEST/item "
    assert lead["source_url"] == "https://example.test/item"
    lead["discovery_provenance"]["content_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="content hash"):
        validate_lead(lead)


def test_identity_key_and_lead_id_are_recomputed_during_validation():
    lead = sample_lead()
    lead["dedup_key"] = "0" * 64
    with pytest.raises(ValueError, match="dedup key does not match"):
        validate_lead(lead)

    lead = sample_lead()
    lead["lead_id"] = "CENT-SPACE-2026-0000000000000000"
    with pytest.raises(ValueError, match="lead ID does not match"):
        validate_lead(lead)


def test_malformed_no_case_link_and_case_authority_fixture():
    with pytest.raises(ValueError):
        APICatalogAdapter().parse(b'{"unexpected":[]}')
    lead = sample_lead()
    assert lead["potential_case_links"] == []
    assert lead["downstream_route"]["secondary"] == []

    case_link = {
        "producer": "ovnis-pr",
        "case_id": "OVNIS-TEST",
        "link_basis": ["time_overlap"],
        "link_strength": "candidate",
        "not_a_confirmation": True,
    }
    linked = sample_lead(case_links=[case_link])
    validate_lead(linked)
    assert linked["downstream_route"]["secondary"] == ["ovnis-pr"]

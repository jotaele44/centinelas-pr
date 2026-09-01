from centinelas.releases.source_endpoints import SOURCE_ENDPOINTS


def test_remediated_official_endpoints_are_registered():
    assert SOURCE_ENDPOINTS["nsa_releases"].policy_url == "https://www.nsa.gov/Site-Policies/"
    assert SOURCE_ENDPOINTS["doe_aec"].index_url == (
        "https://www.energy.gov/nnsa/nnsa-foia-library?page=1&page_size=100"
    )


def test_disabled_sources_preserve_no_bypass_dispositions():
    assert "DO_NOT_BYPASS" in SOURCE_ENDPOINTS["nara_catalog"].remediation_note
    assert "DO_NOT_BYPASS" in SOURCE_ENDPOINTS["cia_reading_room"].remediation_note
    assert "NO_BYPASS" in SOURCE_ENDPOINTS["nhhc"].remediation_note


def test_no_source_is_enabled_for_pilot_by_default():
    assert all(not source.enabled_for_pilot for source in SOURCE_ENDPOINTS.values())

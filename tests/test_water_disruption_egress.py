"""Fail-closed outbound water-disruption delivery authorization."""
import pytest
from fastapi import HTTPException

from server.backend.water_disruption_api import (
    _approved_consumer_target,
    _deliver_to_approved_target,
)


@pytest.mark.parametrize("url", [
    "http://example.org", "https://127.0.0.1", "https://169.254.169.254",
    "https://localhost", "https://service.local", "https://example.org.evil.test",
    "https://example.org@evil.test", "https://example.org:8443",
    "https://example.org/admin", "https://example.org?redirect=1",
    "https://example.org#fragment", "file:///etc/passwd",
])
def test_denies_untrusted_and_malformed_origins(monkeypatch, url):
    monkeypatch.setenv("CENTINELAS_WATER_DISRUPTION_CONSUMER_ORIGINS", "https://example.org")
    with pytest.raises(HTTPException) as exc:
        _approved_consumer_target(url)
    assert exc.value.status_code == 503


def test_defaults_to_disabled(monkeypatch):
    monkeypatch.delenv("CENTINELAS_WATER_DISRUPTION_CONSUMER_ORIGINS", raising=False)
    with pytest.raises(HTTPException):
        _approved_consumer_target("https://example.org")


def test_exact_authorized_https_origin(monkeypatch):
    monkeypatch.setenv("CENTINELAS_WATER_DISRUPTION_CONSUMER_ORIGINS", "https://example.org")
    assert _approved_consumer_target("https://example.org") == "https://example.org/water-disruption/intake"


def test_network_transport_blocks_proxies_and_redirects(monkeypatch):
    import urllib.request
    captured = {}
    class FakeOpener:
        def open(self, request, timeout):
            captured["timeout"] = timeout
            captured["url"] = request.full_url
            return "ok"
    def fake_build(*handlers):
        assert isinstance(handlers[0], urllib.request.ProxyHandler)
        assert handlers[0].proxies == {}
        assert handlers[1].redirect_request(None, None, 302, "", {}, "https://evil.test") is None
        return FakeOpener()
    monkeypatch.setattr(urllib.request, "build_opener", fake_build)
    req = urllib.request.Request("https://example.org/water-disruption/intake")
    assert _deliver_to_approved_target(req) == "ok"
    assert captured == {"timeout": 10, "url": req.full_url}

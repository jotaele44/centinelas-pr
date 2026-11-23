from __future__ import annotations

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from server.backend import auth


def _request(host: str, authorization: str | None = None) -> Request:
    headers = []
    if authorization is not None:
        headers.append((b"authorization", authorization.encode("utf-8")))
    return Request(
        {
            "type": "http",
            "method": "POST",
            "scheme": "http",
            "path": "/",
            "raw_path": b"/",
            "query_string": b"",
            "headers": headers,
            "client": (host, 12345),
            "server": ("127.0.0.1", 8000),
        }
    )


@pytest.mark.parametrize(
    "address",
    [
        "localhost",
        "127.0.0.1",
        "10.42.0.5",
        "172.17.0.1",
        "192.168.10.5",
        "169.254.10.5",
        "::1",
        "fc00::1",
        "fe80::1",
    ],
)
def test_unconfigured_write_guard_allows_explicit_local_networks(
    monkeypatch: pytest.MonkeyPatch, address: str
) -> None:
    monkeypatch.setattr(auth, "WRITE_TOKEN", "")
    auth.require_write_access(_request(address))


@pytest.mark.parametrize(
    "address",
    ["", "testclient", "example.com", "8.8.8.8", "192.0.2.10", "198.51.100.10", "203.0.113.10"],
)
def test_unconfigured_write_guard_refuses_nonlocal_addresses(
    monkeypatch: pytest.MonkeyPatch, address: str
) -> None:
    monkeypatch.setattr(auth, "WRITE_TOKEN", "")
    with pytest.raises(HTTPException) as exc:
        auth.require_write_access(_request(address))
    assert exc.value.status_code == 403
    assert exc.value.detail == auth.LOCAL_WRITE_REQUIRED_DETAIL


def test_configured_write_guard_requires_exact_bearer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auth, "WRITE_TOKEN", "correct-token")
    with pytest.raises(HTTPException) as exc:
        auth.require_write_access(_request("127.0.0.1", "Bearer wrong-token"))
    assert exc.value.status_code == 401
    auth.require_write_access(_request("8.8.8.8", "Bearer correct-token"))

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


def test_unconfigured_write_guard_allows_loopback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auth, "WRITE_TOKEN", "")
    auth.require_write_access(_request("127.0.0.1"))


def test_unconfigured_write_guard_allows_private_network(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auth, "WRITE_TOKEN", "")
    auth.require_write_access(_request("192.168.10.5"))


def test_unconfigured_write_guard_refuses_public_address(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auth, "WRITE_TOKEN", "")
    with pytest.raises(HTTPException) as exc:
        auth.require_write_access(_request("8.8.8.8"))
    assert exc.value.status_code == 403


def test_configured_write_guard_requires_exact_bearer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auth, "WRITE_TOKEN", "correct-token")
    with pytest.raises(HTTPException) as exc:
        auth.require_write_access(_request("127.0.0.1", "Bearer wrong-token"))
    assert exc.value.status_code == 401
    auth.require_write_access(_request("8.8.8.8", "Bearer correct-token"))

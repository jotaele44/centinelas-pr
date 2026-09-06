"""Repository-operation write boundary for the Centinelas local backend."""
from __future__ import annotations

import ipaddress
import os
import secrets

from fastapi import Depends, HTTPException, Request

WRITE_TOKEN = os.environ.get("CENTINELAS_WRITE_TOKEN", "")


def _is_local_network(host: str) -> bool:
    if host == "localhost":
        return True
    if not host:
        return False
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return ip.is_loopback or ip.is_private or ip.is_link_local


def require_write_access(request: Request) -> None:
    """Require the repository token, or local-network containment when unset.

    Credential-free development remains possible on loopback/private networks.
    Setting CENTINELAS_WRITE_TOKEN upgrades the same routes to bearer-token mode.
    Public-address writes are always refused when no token is configured.
    """
    if WRITE_TOKEN:
        scheme, _, presented = request.headers.get("authorization", "").partition(" ")
        if scheme.lower() != "bearer" or not secrets.compare_digest(presented, WRITE_TOKEN):
            raise HTTPException(status_code=401, detail="Missing or invalid Centinelas write token")
        return
    host = request.client.host if request.client else ""
    if not _is_local_network(host):
        raise HTTPException(
            status_code=403,
            detail="Centinelas writes require a local client while CENTINELAS_WRITE_TOKEN is unset",
        )


WRITE_GUARD = [Depends(require_write_access)]

"""Repository-operation write boundary for the Centinelas local backend."""
from __future__ import annotations

import ipaddress
import os
import secrets

from fastapi import Depends, HTTPException, Request

WRITE_TOKEN = os.environ.get("CENTINELAS_WRITE_TOKEN", "")
LOCAL_WRITE_REQUIRED_DETAIL = (
    "Centinelas writes require a local client while CENTINELAS_WRITE_TOKEN is unset"
)
_LOCAL_NETWORKS = tuple(
    ipaddress.ip_network(network)
    for network in (
        "127.0.0.0/8",
        "10.0.0.0/8",
        "172.16.0.0/12",
        "192.168.0.0/16",
        "169.254.0.0/16",
        "::1/128",
        "fc00::/7",
        "fe80::/10",
    )
)


def _is_local_network(host: str) -> bool:
    if host == "localhost":
        return True
    if not host:
        return False
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return any(network.version == ip.version and ip in network for network in _LOCAL_NETWORKS)


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
            detail=LOCAL_WRITE_REQUIRED_DETAIL,
        )


WRITE_GUARD = [Depends(require_write_access)]

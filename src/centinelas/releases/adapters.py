from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Protocol
from urllib.parse import urlencode


class HttpTransport(Protocol):
    def __call__(self, url: str, headers: dict[str, str]) -> tuple[int, dict[str, str], bytes]: ...


@dataclass(frozen=True)
class SourceDefinition:
    adapter_id: str
    agency: str
    base_url: str
    query_path: str
    page_parameter: str = "page"
    page_size_parameter: str = "page_size"
    page_size: int = 100
    enabled_by_default: bool = False
    robots_review_required: bool = True
    terms_review_required: bool = True


@dataclass(frozen=True)
class RawResponseReceipt:
    adapter_id: str
    request_url: str
    request_sha256: str
    status: int
    response_sha256: str
    byte_size: int
    cache_hit: bool
    page: int


SOURCE_REGISTRY: dict[str, SourceDefinition] = {
    "nara_ndc": SourceDefinition("nara_ndc", "NARA", "https://www.archives.gov", "/declassification/ndc/releases"),
    "nara_catalog": SourceDefinition("nara_catalog", "NARA", "https://catalog.archives.gov", "/api/v1/records"),
    "cia_reading_room": SourceDefinition("cia_reading_room", "CIA", "https://www.cia.gov", "/readingroom/search/site"),
    "nsa_releases": SourceDefinition("nsa_releases", "NSA", "https://www.nsa.gov", "/Helpful-Links/NSA-FOIA/Declassification-Transparency-Initiatives/"),
    "dia_reading_room": SourceDefinition("dia_reading_room", "DIA", "https://www.dia.mil", "/FOIA/FOIA-Electronic-Reading-Room/"),
    "nhhc": SourceDefinition("nhhc", "NHHC", "https://www.history.navy.mil", "/research/archives/digital-exhibits-highlights.html"),
    "doe_aec": SourceDefinition("doe_aec", "DOE", "https://www.energy.gov", "/nnsa/foia-reading-room"),
    "air_force_blue_book": SourceDefinition("air_force_blue_book", "USAF", "https://www.archives.gov", "/research/military/air-force/ufos"),
}


class AdapterPolicyError(RuntimeError):
    pass


class HttpCache:
    def __init__(self, root: Path) -> None:
        self.root = root
        root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def key(url: str) -> str:
        return hashlib.sha256(url.encode()).hexdigest()

    def read(self, url: str) -> bytes | None:
        path = self.root / f"{self.key(url)}.bin"
        return path.read_bytes() if path.exists() else None

    def write(self, url: str, body: bytes) -> None:
        target = self.root / f"{self.key(url)}.bin"
        temp = target.with_suffix(".tmp")
        temp.write_bytes(body)
        temp.replace(target)


class RateLimiter:
    def __init__(self, minimum_interval_seconds: float = 1.0, sleeper: Callable[[float], None] = time.sleep) -> None:
        self.minimum_interval_seconds = minimum_interval_seconds
        self.sleeper = sleeper
        self._last_request_at: float | None = None

    def wait(self, clock: Callable[[], float] = time.monotonic) -> None:
        now = clock()
        if self._last_request_at is not None:
            remaining = self.minimum_interval_seconds - (now - self._last_request_at)
            if remaining > 0:
                self.sleeper(remaining)
        self._last_request_at = clock()


class PublicReleaseAdapter:
    def __init__(
        self,
        definition: SourceDefinition,
        transport: HttpTransport,
        state_dir: Path,
        *,
        explicitly_enabled: bool = False,
        robots_approved: bool = False,
        terms_approved: bool = False,
        limiter: RateLimiter | None = None,
    ) -> None:
        self.definition = definition
        self.adapter_id = definition.adapter_id
        self.transport = transport
        self.state_dir = state_dir
        self.cache = HttpCache(state_dir / "http-cache" / definition.adapter_id)
        self.limiter = limiter or RateLimiter()
        self.explicitly_enabled = explicitly_enabled
        self.robots_approved = robots_approved
        self.terms_approved = terms_approved
        self.receipts: list[RawResponseReceipt] = []

    @property
    def checkpoint_path(self) -> Path:
        return self.state_dir / "checkpoints" / f"{self.adapter_id}.json"

    def _enforce_policy(self) -> None:
        if not self.explicitly_enabled:
            raise AdapterPolicyError(f"{self.adapter_id} is disabled; explicit source enablement is required")
        if self.definition.robots_review_required and not self.robots_approved:
            raise AdapterPolicyError(f"{self.adapter_id} robots review has not been approved")
        if self.definition.terms_review_required and not self.terms_approved:
            raise AdapterPolicyError(f"{self.adapter_id} terms review has not been approved")

    def _load_checkpoint(self) -> int:
        if not self.checkpoint_path.exists():
            return 1
        return int(json.loads(self.checkpoint_path.read_text()).get("next_page", 1))

    def _save_checkpoint(self, next_page: int) -> None:
        self.checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.checkpoint_path.with_suffix(".tmp")
        temp.write_text(json.dumps({"next_page": next_page}, sort_keys=True) + "\n")
        temp.replace(self.checkpoint_path)

    def _request(self, url: str, page: int) -> bytes:
        cached = self.cache.read(url)
        if cached is not None:
            status, body, cache_hit = 200, cached, True
        else:
            self.limiter.wait()
            status, _headers, body = self.transport(url, {"User-Agent": "centinelas-pr-public-archive-monitor/1.0"})
            cache_hit = False
            if status == 200:
                self.cache.write(url, body)
        self.receipts.append(
            RawResponseReceipt(
                adapter_id=self.adapter_id,
                request_url=url,
                request_sha256=hashlib.sha256(url.encode()).hexdigest(),
                status=status,
                response_sha256=hashlib.sha256(body).hexdigest(),
                byte_size=len(body),
                cache_hit=cache_hit,
                page=page,
            )
        )
        if status != 200:
            raise RuntimeError(f"{self.adapter_id} HTTP {status} for page {page}")
        return body

    def enumerate_pages(self, parse_page: Callable[[bytes], tuple[list[dict[str, Any]], bool]]) -> Iterable[dict[str, Any]]:
        self._enforce_policy()
        page = self._load_checkpoint()
        while True:
            query = urlencode({self.definition.page_parameter: page, self.definition.page_size_parameter: self.definition.page_size})
            url = f"{self.definition.base_url}{self.definition.query_path}?{query}"
            records, has_next = parse_page(self._request(url, page))
            for record in records:
                yield {"adapter_id": self.adapter_id, "agency": self.definition.agency, **record}
            self._save_checkpoint(page + 1)
            if not has_next:
                break
            page += 1

    def write_receipts(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(json.dumps(asdict(row), sort_keys=True) + "\n" for row in self.receipts))


def build_adapter(
    adapter_id: str,
    transport: HttpTransport,
    state_dir: Path,
    **policy: Any,
) -> PublicReleaseAdapter:
    try:
        definition = SOURCE_REGISTRY[adapter_id]
    except KeyError as exc:
        raise ValueError(f"unknown source adapter: {adapter_id}") from exc
    return PublicReleaseAdapter(definition, transport, state_dir, **policy)

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Iterable, Protocol

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

BASELINE_CUTOFF = "2026-07-27T23:59:59-04:00"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def deterministic_id(prefix: str, *parts: object) -> str:
    canonical = "\0".join(str(part).strip() for part in parts)
    return f"{prefix}_{hashlib.sha256(canonical.encode()).hexdigest()[:32]}"


class ReleaseState(StrEnum):
    NEW_DOCUMENT = "NEW_DOCUMENT"
    NEW_DIGITIZATION = "NEW_DIGITIZATION"
    NEW_RELEASE_VERSION = "NEW_RELEASE_VERSION"
    LESS_REDACTED_VERSION = "LESS_REDACTED_VERSION"
    MORE_REDACTED_VERSION = "MORE_REDACTED_VERSION"
    NEW_ATTACHMENT = "NEW_ATTACHMENT"
    METADATA_REVISION = "METADATA_REVISION"
    CORPUS_RELOCATION = "CORPUS_RELOCATION"
    WITHDRAWN_OBJECT = "WITHDRAWN_OBJECT"
    FALSE_DELTA = "FALSE_DELTA"
    BASELINE_DUPLICATE = "BASELINE_DUPLICATE"
    PRIOR_DELTA_DUPLICATE = "PRIOR_DELTA_DUPLICATE"


class AcquisitionReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    receipt_id: str = Field(pattern=r"^receipt_[a-f0-9]{32}$")
    adapter_id: str
    source_url: HttpUrl
    observed_at: datetime
    http_status: int = Field(ge=100, le=599)
    mime_type: str
    file_signature: str
    byte_size: int = Field(ge=0)
    content_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    page_count: int = Field(ge=0)
    attachment_count: int = Field(default=0, ge=0)
    error: str | None = None


class FederalDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: str = Field(pattern=r"^doc_[a-f0-9]{32}$")
    originating_agency: str
    custodial_agency: str | None = None
    repository: str
    collection_id: str | None = None
    record_group: str | None = None
    series: str | None = None
    archival_identifier: str | None = None
    title: str
    document_date_start: str | None = None
    document_date_end: str | None = None
    document_type: str
    jurisdiction: str = "PR"
    canonical_identity_basis: list[str]
    confidence: float = Field(ge=0, le=1)
    lineage: dict[str, Any]
    synthetic: bool = False
    created_at: datetime
    extracted_at: datetime


class FederalDocumentRelease(BaseModel):
    model_config = ConfigDict(extra="forbid")

    release_id: str = Field(pattern=r"^relv_[a-f0-9]{32}$")
    document_id: str = Field(pattern=r"^doc_[a-f0-9]{32}$")
    source_id: str = Field(pattern=r"^src_[a-f0-9]{32}$")
    released_at: datetime | None = None
    first_observed_at: datetime
    baseline_cutoff: str = BASELINE_CUTOFF
    release_state: ReleaseState
    access_url: HttpUrl
    content_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    byte_size: int = Field(ge=0)
    mime_type: str
    page_count: int = Field(ge=0)
    text_layer_present: bool
    ocr_status: str
    redaction_state: str
    attachment_count: int = Field(default=0, ge=0)
    parent_release_id: str | None = None
    acquisition_receipt_id: str = Field(pattern=r"^receipt_[a-f0-9]{32}$")
    lineage: dict[str, Any]
    synthetic: bool = False
    created_at: datetime
    extracted_at: datetime

    @model_validator(mode="after")
    def enforce_cutoff(self) -> "FederalDocumentRelease":
        if self.baseline_cutoff != BASELINE_CUTOFF:
            raise ValueError(f"baseline_cutoff must remain {BASELINE_CUTOFF}")
        return self


class DocumentFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    finding_id: str = Field(pattern=r"^find_[a-f0-9]{32}$")
    document_id: str = Field(pattern=r"^doc_[a-f0-9]{32}$")
    release_id: str = Field(pattern=r"^relv_[a-f0-9]{32}$")
    page_start: int = Field(ge=1)
    page_end: int = Field(ge=1)
    finding_type: str
    matched_form: str | None = None
    canonical_entity: str | None = None
    municipalities: list[str] = Field(default_factory=list)
    facilities: list[str] = Field(default_factory=list)
    coordinates: list[dict[str, float]] = Field(default_factory=list)
    subject_categories: list[str] = Field(default_factory=list)
    context_summary: str
    evidence_tier: str = "T1"
    automated_confidence: float = Field(ge=0, le=1)
    reviewer_confidence: float = Field(ge=0, le=1)
    review_status: str
    cointelpro_disposition: str = "NOT_COINTELPRO"
    citation: dict[str, Any]
    lineage: dict[str, Any]
    synthetic: bool = False
    created_at: datetime
    extracted_at: datetime


class BaselineManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    corpus_id: str = "prdm-census-2026-07-27"
    cutoff: str = BASELINE_CUTOFF
    state: str = "FROZEN"
    source_inventory_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    object_count: int = Field(ge=0)
    page_count: int = Field(ge=0)

    @model_validator(mode="after")
    def frozen_contract(self) -> "BaselineManifest":
        if self.cutoff != BASELINE_CUTOFF or self.state != "FROZEN":
            raise ValueError("the July 27 baseline is immutable and must remain FROZEN")
        return self


class DeltaManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    delta_id: str = Field(pattern=r"^prdm-delta-[0-9]{4}$")
    baseline_corpus_id: str = "prdm-census-2026-07-27"
    previous_delta_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    observed_from: datetime
    observed_through: datetime
    source_inventory_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    normalized_corpus_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    objects_discovered: int = Field(ge=0)
    objects_acquired: int = Field(ge=0)
    objects_inaccessible: int = Field(ge=0)
    findings: int = Field(ge=0)


class ReleaseAdapter(Protocol):
    adapter_id: str

    def enumerate(self) -> Iterable[dict[str, Any]]: ...


class SyntheticReleaseAdapter:
    """Offline-safe fixture adapter for deterministic tests."""

    adapter_id = "SYNTHETIC_RELEASE_FIXTURE"

    def __init__(self, records: Iterable[dict[str, Any]]) -> None:
        self._records = tuple(records)

    def enumerate(self) -> Iterable[dict[str, Any]]:
        return iter(self._records)


def classify_release(
    *,
    known_document: bool,
    old_sha256: str | None,
    new_sha256: str | None,
    old_url: str | None = None,
    new_url: str | None = None,
    old_redaction_count: int | None = None,
    new_redaction_count: int | None = None,
    old_attachment_count: int = 0,
    new_attachment_count: int = 0,
    metadata_changed: bool = False,
    withdrawn: bool = False,
    in_baseline: bool = False,
) -> ReleaseState:
    if withdrawn:
        return ReleaseState.WITHDRAWN_OBJECT
    if not known_document:
        return ReleaseState.NEW_DOCUMENT
    if old_sha256 and new_sha256 and old_sha256 == new_sha256:
        if old_url != new_url:
            return ReleaseState.CORPUS_RELOCATION
        if metadata_changed:
            return ReleaseState.METADATA_REVISION
        return ReleaseState.BASELINE_DUPLICATE if in_baseline else ReleaseState.PRIOR_DELTA_DUPLICATE
    if new_attachment_count > old_attachment_count:
        return ReleaseState.NEW_ATTACHMENT
    if old_redaction_count is not None and new_redaction_count is not None:
        if new_redaction_count < old_redaction_count:
            return ReleaseState.LESS_REDACTED_VERSION
        if new_redaction_count > old_redaction_count:
            return ReleaseState.MORE_REDACTED_VERSION
    if metadata_changed and old_sha256 == new_sha256:
        return ReleaseState.METADATA_REVISION
    if old_sha256 is None and new_sha256:
        return ReleaseState.NEW_DIGITIZATION
    if new_sha256 is None:
        return ReleaseState.FALSE_DELTA
    return ReleaseState.NEW_RELEASE_VERSION


def write_immutable_manifest(path: Path, manifest: BaseModel) -> None:
    payload = manifest.model_dump(mode="json")
    encoded = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if path.exists():
        existing = json.loads(path.read_text())
        if existing != payload:
            raise FileExistsError(f"refusing to mutate immutable manifest: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(encoded)

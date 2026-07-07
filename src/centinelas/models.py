from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, field_validator

from centinelas.classify.labels import DomainLabel

EvidenceTier = Literal["T1", "T2", "T3", "T4"]
DispatchStatus = Literal["ok", "failed", "skipped"]


class RawItem(BaseModel):
    item_id: str          # sha256(source_url + published_at.isoformat())
    source_url: str
    source_name: str
    title: str
    body_text: str
    published_at: datetime
    captured_at: datetime
    evidence_tier: EvidenceTier = "T2"

    @staticmethod
    def make_id(url: str, published_at: datetime) -> str:
        payload = f"{url}|{published_at.isoformat()}"
        return hashlib.sha256(payload.encode()).hexdigest()[:16]

    @field_validator("item_id")
    @classmethod
    def id_nonempty(cls, v: str) -> str:
        if not v:
            raise ValueError("item_id must not be empty")
        return v


class ClassifiedItem(RawItem):
    labels: list[DomainLabel]
    confidence: float        # 0.0–1.0
    classifier_reasoning: str = ""

    # Optional pre-officialization finance/location enrichment. When the
    # classifier can extract them these travel with the item so the
    # MoneySweep anchor can build a *located* pre-official finance candidate
    # without re-parsing. All degrade gracefully to empty — downstream
    # consumers re-derive municipality from title/body_text when absent.
    municipalities: list[str] = []
    agencies: list[str] = []
    estimated_value: float | None = None
    signal_stage: str | None = None
    beat: str | None = None

    @field_validator("confidence")
    @classmethod
    def confidence_range(cls, v: float) -> float:
        if not (0.0 <= v <= 1.0):
            raise ValueError("confidence must be in [0, 1]")
        return v


class DispatchRecord(BaseModel):
    item_id: str
    dispatched_to: list[str]
    dispatched_at: datetime
    status: DispatchStatus
    error: str | None = None

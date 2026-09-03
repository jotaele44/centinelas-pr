"""Disabled Gmail adapter contracts and offline fake client.

No production Gmail API dependency is imported here. A future live client must
implement ``GmailClientProtocol`` and remain feature-disabled until separately
approved.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, Field

from .models import GmailSyncCheckpoint


class EmailSourceProfile(BaseModel):
    schema_version: str = "email_source_profile.v0.1"
    source_profile_id: str
    enabled: bool = False
    provider: str = "gmail"
    account_alias: str
    gmail_search: str
    required_labels: list[str] = Field(default_factory=list)
    excluded_labels: list[str] = Field(default_factory=list)
    maximum_messages_per_run: int = Field(default=250, ge=1, le=1000)
    download_raw_rfc822: bool = False
    download_attachments: str = "metadata_only"
    default_evidence_tier: str = "T4"
    default_signal_stage: str = "raw_observation"
    require_operator_review: bool = True
    auto_promote: bool = False
    federation_export_allowed: bool = False

    def assert_safe(self) -> None:
        if self.enabled:
            raise ValueError("v0.1 design adapter must remain disabled")
        if self.download_raw_rfc822:
            raise ValueError("raw RFC822 download is prohibited in v0.1")
        if self.download_attachments != "metadata_only":
            raise ValueError("attachments must remain metadata-only")
        if self.auto_promote or self.federation_export_allowed:
            raise ValueError("email records cannot auto-promote or federate")


class GmailClientProtocol(Protocol):
    def search_message_ids(self, query: str, limit: int) -> list[str]:
        raise NotImplementedError

    def get_message(self, message_id: str) -> dict:
        raise NotImplementedError

    def history(self, start_history_id: str) -> Iterable[dict]:
        raise NotImplementedError


class OfflineFakeGmailClient:
    """Fixture-only client. It never performs network or mailbox writes."""

    def __init__(self, messages: list[dict]) -> None:
        self._messages = {str(item["id"]): item for item in messages}

    @classmethod
    def from_json(cls, path: Path) -> OfflineFakeGmailClient:
        return cls(json.loads(path.read_text(encoding="utf-8")))

    def search_message_ids(self, query: str, limit: int) -> list[str]:
        del query
        return list(self._messages)[:limit]

    def get_message(self, message_id: str) -> dict:
        return dict(self._messages[message_id])

    def history(self, start_history_id: str) -> Iterable[dict]:
        del start_history_id
        return []


class JsonlIdentityLedger:
    """Durable exact-identity ledger for local private workspaces."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def contains(self, account_alias: str, provider_message_id: str) -> bool:
        key = self.make_key(account_alias, provider_message_id)
        if not self.path.exists():
            return False
        return any(json.loads(line).get("key") == key for line in self.path.read_text().splitlines() if line)

    def append(self, account_alias: str, provider_message_id: str, run_id: str) -> str:
        key = self.make_key(account_alias, provider_message_id)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"key": key, "run_id": run_id}, sort_keys=True) + "\n")
        return key

    @staticmethod
    def make_key(account_alias: str, provider_message_id: str) -> str:
        return hashlib.sha256(f"{account_alias}|{provider_message_id}".encode()).hexdigest()


def load_checkpoint(path: Path, profile: EmailSourceProfile) -> GmailSyncCheckpoint:
    if path.exists():
        return GmailSyncCheckpoint.model_validate_json(path.read_text(encoding="utf-8"))
    return GmailSyncCheckpoint(source_profile_id=profile.source_profile_id, account_alias=profile.account_alias)

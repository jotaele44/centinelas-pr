from pathlib import Path

import pytest

from centinelas.releases import (
    BaselineManifest,
    ReleaseState,
    SyntheticReleaseAdapter,
    classify_release,
    write_immutable_manifest,
)


def test_release_state_matrix():
    digest = "a" * 64
    assert classify_release(known_document=False, old_sha256=None, new_sha256=digest) == ReleaseState.NEW_DOCUMENT
    assert classify_release(known_document=True, old_sha256=digest, new_sha256=digest, in_baseline=True) == ReleaseState.BASELINE_DUPLICATE
    assert classify_release(known_document=True, old_sha256=digest, new_sha256=digest, old_url="a", new_url="b") == ReleaseState.CORPUS_RELOCATION
    assert classify_release(known_document=True, old_sha256="a" * 64, new_sha256="b" * 64, old_redaction_count=4, new_redaction_count=2) == ReleaseState.LESS_REDACTED_VERSION
    assert classify_release(known_document=True, old_sha256="a" * 64, new_sha256="b" * 64, old_redaction_count=2, new_redaction_count=4) == ReleaseState.MORE_REDACTED_VERSION
    assert classify_release(known_document=True, old_sha256="a" * 64, new_sha256="b" * 64, old_attachment_count=0, new_attachment_count=1) == ReleaseState.NEW_ATTACHMENT
    assert classify_release(known_document=True, old_sha256=digest, new_sha256=digest, metadata_changed=True) == ReleaseState.METADATA_REVISION
    assert classify_release(known_document=True, old_sha256=digest, new_sha256=None, withdrawn=True) == ReleaseState.WITHDRAWN_OBJECT


def test_baseline_manifest_cannot_be_mutated(tmp_path: Path):
    path = tmp_path / "baseline.json"
    baseline = BaselineManifest(source_inventory_sha256="a" * 64, object_count=1, page_count=2)
    write_immutable_manifest(path, baseline)
    write_immutable_manifest(path, baseline)
    changed = BaselineManifest(source_inventory_sha256="b" * 64, object_count=1, page_count=2)
    with pytest.raises(FileExistsError):
        write_immutable_manifest(path, changed)


def test_synthetic_adapter_is_repeatable():
    adapter = SyntheticReleaseAdapter([{"id": "one"}, {"id": "two"}])
    assert list(adapter.enumerate()) == list(adapter.enumerate())

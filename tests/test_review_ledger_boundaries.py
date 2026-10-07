import pytest
from fastapi import HTTPException

from server.backend import main


@pytest.mark.parametrize("record_id", ["../outside", "..\\outside", "/absolute", "", ".", ".."])
def test_record_paths_reject_unsafe_ids(tmp_path, record_id):
    with pytest.raises(HTTPException) as exc:
        main._record_path(tmp_path, record_id)
    assert exc.value.status_code == 422


def test_item_api_rejects_symlink_escape(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    ledger = tmp_path / "classified"
    ledger.mkdir()
    secret = tmp_path / "outside.json"
    secret.write_text('{"item_id":"outside"}')
    (ledger / "escape.json").symlink_to(secret)
    monkeypatch.setattr(main, "CLASSIFIED_DIR", ledger)
    with TestClient(main.app) as client:
        response = client.get("/items/escape")
    assert response.status_code == 422
    assert main._load_dir(ledger) == []


def test_directory_reader_skips_nonobject_records(tmp_path):
    for index, content in enumerate(['null', '[]', '42', '"text"', '{"item_id":"valid"}', '{']):
        (tmp_path / f"{index}.json").write_text(content)
    assert main._load_dir(tmp_path) == [{"item_id": "valid"}]

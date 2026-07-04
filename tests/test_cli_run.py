"""Regression test: `centinelas run` must persist classified items, not just
dispatch records, so downstream consumers (e.g. the pipeline API) can read them
regardless of whether items came through `run` or the separate `classify` step."""

from datetime import datetime, timezone

from typer.testing import CliRunner

from centinelas.cli import app
from centinelas.classify.labels import DomainLabel
from centinelas.models import RawItem

runner = CliRunner()


def _raw_item(item_id: str) -> RawItem:
    now = datetime.now(timezone.utc)
    return RawItem(
        item_id=item_id,
        source_url=f"https://example.com/{item_id}",
        source_name="Test Source",
        title="Test Title",
        body_text="Test body",
        published_at=now,
        captured_at=now,
    )


def test_run_persists_classified_items(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    classified_dir = tmp_path / ".centinelas" / "classified"

    def fake_poll_all():
        return [_raw_item("run-cli-001")]

    def fake_classify(item):
        return [DomainLabel.ENVIRONMENTAL], 0.9, "test reasoning"

    monkeypatch.setattr("centinelas.ingest.rss.poll_all", fake_poll_all)
    monkeypatch.setattr("centinelas.classify.classifier.classify", fake_classify)

    result = runner.invoke(app, ["run", "--dry-run"])

    assert result.exit_code == 0, result.output
    written = list(classified_dir.glob("*.json"))
    assert len(written) == 1
    assert written[0].name == "run-cli-001.json"

    from centinelas.models import ClassifiedItem
    item = ClassifiedItem.model_validate_json(written[0].read_text())
    assert item.item_id == "run-cli-001"
    assert item.labels == [DomainLabel.ENVIRONMENTAL]

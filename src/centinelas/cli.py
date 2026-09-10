"""Centinelas CLI - ingest, classify, route, run, status."""

from __future__ import annotations

import logging
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(
    name="centinelas",
    help="Online intelligence intake and local-first routing engine.",
    no_args_is_help=True,
)
console = Console()

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


def _merge_items(*item_lists: list) -> list:
    """Concatenate RawItem lists, deduplicating by item_id in first-seen order."""

    seen: set[str] = set()
    merged: list = []
    for items in item_lists:
        for item in items:
            if item.item_id not in seen:
                seen.add(item.item_id)
                merged.append(item)
    return merged


@app.command()
def ingest(
    output: Path = typer.Option(
        Path(".centinelas/queue"),
        "--output",
        "-o",
        help="Directory to write raw items JSON",
    ),
    limit: int = typer.Option(0, "--limit", "-n", help="Max items (0 = unlimited)"),
) -> None:
    """Poll configured acquisition connectors and write RawItems locally."""

    from centinelas.ingest.federal_register import poll_federal_register
    from centinelas.ingest.rss import poll_all
    from centinelas.ingest.web import poll_scrape_sources

    output.mkdir(parents=True, exist_ok=True)
    items = _merge_items(poll_all(), poll_federal_register(), poll_scrape_sources())
    if limit:
        items = items[:limit]

    for item in items:
        path = output / f"{item.item_id}.json"
        path.write_text(item.model_dump_json(indent=2))

    console.print(f"[green]Ingested {len(items)} items -> {output}[/green]")


@app.command()
def classify(
    queue: Path = typer.Option(
        Path(".centinelas/queue"),
        "--queue",
        "-q",
        help="Directory containing RawItem JSON files",
    ),
    output: Path = typer.Option(
        Path(".centinelas/classified"),
        "--output",
        "-o",
        help="Directory to write ClassifiedItem JSON files",
    ),
    classifier_backend: str | None = typer.Option(
        None,
        "--classifier-backend",
        help="local (default) or explicitly enabled anthropic adapter",
    ),
) -> None:
    """Classify queued items; deterministic local rules are authoritative."""

    from centinelas.classify.classifier import build_classified_item
    from centinelas.models import RawItem

    output.mkdir(parents=True, exist_ok=True)
    files = list(queue.glob("*.json"))

    if not files:
        console.print("[yellow]No items in queue.[/yellow]")
        raise typer.Exit()

    for path in files:
        raw = RawItem.model_validate_json(path.read_text())
        classified = build_classified_item(raw, backend=classifier_backend)
        out_path = output / path.name
        out_path.write_text(classified.model_dump_json(indent=2))

    console.print(f"[green]Classified {len(files)} items -> {output}[/green]")


@app.command()
def route(
    classified: Path = typer.Option(
        Path(".centinelas/classified"),
        "--classified",
        "-c",
        help="Directory containing ClassifiedItem JSON files",
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Report the target plan without staging envelopes"
    ),
) -> None:
    """Stage validated local artifact envelopes for target repositories."""

    from centinelas.models import ClassifiedItem
    from centinelas.route.dispatch import dispatch

    files = list(classified.glob("*.json"))
    if not files:
        console.print("[yellow]No classified items to dispatch.[/yellow]")
        raise typer.Exit()

    table = Table("item_id", "labels", "staged_for", "status")
    for path in files:
        item = ClassifiedItem.model_validate_json(path.read_text())
        record = dispatch(item, dry_run=dry_run)
        label_str = ", ".join(label.value for label in item.labels)
        table.add_row(
            record.item_id[:12],
            label_str,
            ", ".join(record.dispatched_to),
            (
                f"[green]{record.status}[/green]"
                if record.status == "ok"
                else f"[red]{record.status}[/red]"
            ),
        )

    console.print(table)
    prefix = "[dim][dry-run][/dim] " if dry_run else ""
    console.print(f"{prefix}[green]Processed {len(files)} local routes[/green]")


@app.command()
def run(
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Run without staging local exchange envelopes"
    ),
    limit: int = typer.Option(0, "--limit", "-n", help="Max items per stage"),
    classified_output: Path = typer.Option(
        Path(".centinelas/classified"),
        "--classified-output",
        help="Directory to write ClassifiedItem JSON files",
    ),
    classifier_backend: str | None = typer.Option(
        None,
        "--classifier-backend",
        help="local (default) or explicitly enabled anthropic adapter",
    ),
) -> None:
    """Run acquisition, classification, and local-first routing."""

    from centinelas.classify.classifier import build_classified_item
    from centinelas.ingest.federal_register import poll_federal_register
    from centinelas.ingest.rss import poll_all
    from centinelas.ingest.web import poll_scrape_sources
    from centinelas.models import ClassifiedItem
    from centinelas.route.dispatch import dispatch

    console.print("[bold]centinelas run[/bold] - full pipeline")

    console.print("  [cyan]ingest[/cyan]...")
    items = _merge_items(poll_all(), poll_federal_register(), poll_scrape_sources())
    if limit:
        items = items[:limit]
    console.print(f"  ingested {len(items)} raw items")

    console.print("  [cyan]classify[/cyan]...")
    classified_output.mkdir(parents=True, exist_ok=True)
    classified: list[ClassifiedItem] = []
    for raw in items:
        item = build_classified_item(raw, backend=classifier_backend)
        classified.append(item)
        (classified_output / f"{item.item_id}.json").write_text(
            item.model_dump_json(indent=2)
        )
    console.print(f"  classified {len(classified)} items -> {classified_output}")

    console.print(
        f"  [cyan]route[/cyan]{'[dim] (dry-run)[/dim]' if dry_run else ''}..."
    )
    ok = sum(
        1 for item in classified if dispatch(item, dry_run=dry_run).status == "ok"
    )
    console.print(f"  locally staged {ok}/{len(classified)} items successfully")

    console.print("[bold green]Pipeline complete.[/bold green]")


@app.command()
def status(
    queue: Path = typer.Option(Path(".centinelas/queue"), "--queue"),
    classified: Path = typer.Option(Path(".centinelas/classified"), "--classified"),
) -> None:
    """Show local queue depth and classified item counts."""

    raw_count = len(list(queue.glob("*.json"))) if queue.exists() else 0
    classified_count = (
        len(list(classified.glob("*.json"))) if classified.exists() else 0
    )

    console.print(f"Raw queue:    [bold]{raw_count}[/bold] items")
    console.print(f"Classified:   [bold]{classified_count}[/bold] items")


if __name__ == "__main__":
    app()

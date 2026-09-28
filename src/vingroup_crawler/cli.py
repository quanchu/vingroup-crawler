from __future__ import annotations

from datetime import date
from pathlib import Path

import typer
from dotenv import load_dotenv
from rich.console import Console

from .analyzer import analyze_article
from .crawler import fetch_html
from .discovery import discover_articles
from .errors import AnalysisError, CrawlerError
from .output import remove_legacy_outputs, write_outputs
from .registry import CrawlRegistry

app = typer.Typer(add_completion=False, help="Crawl Vingroup articles in a publication-date range.")
console = Console()
error_console = Console(stderr=True)


@app.command()
def main(
    start_value: str = typer.Option(
        ...,
        "--from",
        help="Inclusive start date (YYYY-MM-DD).",
    ),
    end_value: str = typer.Option(
        ...,
        "--to",
        help="Inclusive end date (YYYY-MM-DD).",
    ),
) -> None:
    """Discover, analyze, and save Vietnamese and English Vingroup articles."""
    load_dotenv()
    try:
        start = date.fromisoformat(start_value)
        end = date.fromisoformat(end_value)
    except ValueError as exc:
        error_console.print("[red]Error:[/red] --from and --to must use YYYY-MM-DD")
        raise typer.Exit(code=2) from exc
    if end < start:
        error_console.print("[red]Error:[/red] --to must be on or after --from")
        raise typer.Exit(code=2)
    output_dir = Path("output")
    try:
        remove_legacy_outputs(output_dir)
        registry = CrawlRegistry(output_dir / "crawled_articles.csv")
        discovered, articles, discovery_failures = discover_articles(start, end, fetch=fetch_html)
    except (CrawlerError, OSError, ValueError) as exc:
        error_console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    skipped = succeeded = failed = 0
    failure_messages: list[str] = []
    for item, message in discovery_failures:
        registry.discovered(item)
        registry.failed(item, message)
        failed += 1
        failure_messages.append(f"{item.language}/{item.article_id}: {message}")

    for item in discovered:
        if registry.is_success(item.language, item.article_id):
            skipped += 1
            continue
        registry.discovered(item)
        article = articles[(item.language, item.article_id)]
        try:
            analysis, sections = analyze_article(article)
            markdown_path, json_path = write_outputs(
                article,
                analysis,
                sections,
                language=item.language,
                output_dir=output_dir,
            )
            registry.success(item, markdown_path, json_path)
            succeeded += 1
            console.print(f"[green]Saved[/green] {item.language}/{item.article_id}")
        except (AnalysisError, OSError, ValueError) as exc:
            registry.failed(item, str(exc))
            failed += 1
            failure_messages.append(f"{item.language}/{item.article_id}: {exc}")

    console.print(
        f"Discovered: {len(discovered) + len(discovery_failures)} | "
        f"Skipped: {skipped} | Successful: {succeeded} | Failed: {failed}"
    )
    for message in failure_messages:
        error_console.print(f"[red]Failed:[/red] {message}")
    if failed:
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()

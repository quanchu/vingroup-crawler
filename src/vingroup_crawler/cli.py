from __future__ import annotations

import os
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import typer
from dotenv import load_dotenv
from rich.console import Console

from .analyzer import analyze_article
from .crawler import fetch_html
from .discovery import discover_articles
from .errors import AnalysisError, CrawlerError
from .output import load_crawled_article, remove_legacy_outputs, write_analysis_outputs, write_crawl_outputs
from .providers import create_provider, resolve_model
from .registry import AnalysisRegistry, CrawlRegistry

app = typer.Typer(add_completion=False, help="Crawl Vingroup articles and analyze cached sources with multiple LLM providers.")
console = Console()
error_console = Console(stderr=True)
DEFAULT_LOOKBACK_DAYS = 30


def _today() -> date:
    return datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).date()


def _range(start_value: str | None, end_value: str | None) -> tuple[date, date]:
    try:
        end = date.fromisoformat(end_value) if end_value else _today()
        start = date.fromisoformat(start_value) if start_value else end - timedelta(days=DEFAULT_LOOKBACK_DAYS)
    except ValueError as exc:
        raise ValueError("--from and --to must use YYYY-MM-DD") from exc
    if end < start:
        raise ValueError("--to must be on or after --from")
    return start, end


@app.command()
def crawl(
    start_value: str | None = typer.Option(None, "--from", help="Inclusive start; defaults to 30 days before --to."),
    end_value: str | None = typer.Option(None, "--to", help="Inclusive end; defaults to today in Vietnam."),
) -> None:
    """Discover and cache original articles without calling an LLM."""
    load_dotenv()
    try:
        start, end = _range(start_value, end_value)
        output_dir = Path("output")
        remove_legacy_outputs(output_dir)
        registry = CrawlRegistry(output_dir / "crawled_articles.csv")
        discovered, articles, discovery_failures = discover_articles(start, end, fetch=fetch_html)
    except (CrawlerError, OSError, ValueError) as exc:
        error_console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    skipped = succeeded = failed = 0
    failures: list[str] = []
    for item, message in discovery_failures:
        registry.failed(item, message)
        failed += 1
        failures.append(f"{item.language}/{item.article_id}: {message}")
    for item in discovered:
        if registry.is_success(item.language, item.article_id):
            skipped += 1
            continue
        registry.discovered(item)
        try:
            markdown, source_json = write_crawl_outputs(
                articles[(item.language, item.article_id)], language=item.language, output_dir=output_dir
            )
            registry.success(item, markdown, source_json)
            succeeded += 1
            console.print(f"[green]Crawled[/green] {item.language}/{item.article_id}")
        except (OSError, ValueError) as exc:
            registry.failed(item, str(exc))
            failed += 1
            failures.append(f"{item.language}/{item.article_id}: {exc}")
    console.print(f"Discovered: {len(discovered) + len(discovery_failures)} | Skipped: {skipped} | Crawled: {succeeded} | Failed: {failed}")
    for message in failures:
        error_console.print(f"[red]Failed:[/red] {message}")
    if failed:
        raise typer.Exit(code=1)


@app.command()
def analyze(
    provider_name: str | None = typer.Option(
        None,
        "--provider",
        help="openai, anthropic, gemini, ollama, or local-openai.",
    ),
    model_name: str | None = typer.Option(None, "--model", help="Exact provider model ID."),
    start_value: str | None = typer.Option(None, "--from", help="Optional cached publication-date lower bound."),
    end_value: str | None = typer.Option(None, "--to", help="Optional cached publication-date upper bound."),
    language: str | None = typer.Option(None, "--language", help="Limit to vi or en."),
    article_ids: list[str] = typer.Option([], "--id", help="Cached article ID to analyze; repeat for multiple IDs."),
    analyze_all: bool = typer.Option(False, "--all", help="Analyze all cached articles matching other filters."),
    force: bool = typer.Option(False, "--force", help="Redo an existing analysis for the same provider/model."),
) -> None:
    """Analyze cached original articles; never recrawl them."""
    load_dotenv()
    provider_name = (provider_name or os.getenv("LLM_PROVIDER", "openai")).lower()
    if language not in {None, "vi", "en"}:
        error_console.print("[red]Error:[/red] --language must be vi or en")
        raise typer.Exit(code=2)
    if analyze_all == bool(article_ids):
        error_console.print("[red]Error:[/red] provide one or more --id values, or use --all")
        raise typer.Exit(code=2)
    if any(not value.isdigit() for value in article_ids):
        error_console.print("[red]Error:[/red] every --id must be numeric")
        raise typer.Exit(code=2)
    selected_ids = set(article_ids)
    try:
        start = date.fromisoformat(start_value) if start_value else None
        end = date.fromisoformat(end_value) if end_value else None
        if start and end and end < start:
            raise ValueError("--to must be on or after --from")
        selected_model = resolve_model(provider_name, model_name)
        crawl_registry = CrawlRegistry(Path("output/crawled_articles.csv"))
        analysis_registry = AnalysisRegistry(Path("output/analyses.csv"))
    except (AnalysisError, OSError, ValueError) as exc:
        error_console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    rows = []
    for row in crawl_registry.successful_rows():
        published = date.fromisoformat(row["publication_date"])
        if language and row["language"] != language:
            continue
        if selected_ids and row["article_id"] not in selected_ids:
            continue
        if start and published < start:
            continue
        if end and published > end:
            continue
        rows.append(row)
    rows.sort(key=lambda row: (row["publication_date"], row["language"], int(row["article_id"])))
    found_ids = {row["article_id"] for row in rows}
    missing_ids = sorted(selected_ids - found_ids, key=int)
    if missing_ids:
        error_console.print(
            f"[red]Error:[/red] requested IDs are not available in the selected cached sources: "
            f"{', '.join(missing_ids)}"
        )
        raise typer.Exit(code=1)
    if not rows:
        console.print("Cached selected: 0 | Skipped: 0 | Analyzed: 0 | Failed: 0")
        return
    try:
        adapter = create_provider(provider_name)
    except AnalysisError as exc:
        error_console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    skipped = succeeded = failed = 0
    failures: list[str] = []
    for row in rows:
        key = (
            row["language"],
            row["article_id"],
            provider_name,
            selected_model,
            adapter.endpoint,
        )
        if not force and analysis_registry.is_success(key):
            skipped += 1
            continue
        analysis_registry.start(key)
        try:
            article = load_crawled_article(Path(row["source_json_path"]))
            result, sections = analyze_article(article, provider=adapter, model=selected_model)
            proposed, analysis_json = write_analysis_outputs(
                article, result, sections, language=row["language"], provider=provider_name,
                model=selected_model, endpoint=adapter.endpoint, output_dir=Path("output"),
            )
            analysis_registry.success(key, proposed, analysis_json)
            succeeded += 1
            console.print(f"[green]Analyzed[/green] {row['language']}/{row['article_id']} with {provider_name}/{selected_model}")
        except (AnalysisError, OSError, ValueError) as exc:
            analysis_registry.failed(key, str(exc))
            failed += 1
            failures.append(f"{row['language']}/{row['article_id']}: {exc}")
    console.print(f"Cached selected: {len(rows)} | Skipped: {skipped} | Analyzed: {succeeded} | Failed: {failed}")
    for message in failures:
        error_console.print(f"[red]Failed:[/red] {message}")
    if failed:
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

import typer
from dotenv import load_dotenv
from rich.console import Console

from .analyzer import analyze_article
from .crawler import fetch_html
from .discovery import article_language, discover_urls
from .errors import AnalysisError, CrawlerError
from .extractor import extract_article_id
from .output import load_crawled_article, remove_legacy_outputs, write_analysis_outputs, write_crawl_outputs
from .providers import create_provider, resolve_model
from .registry import AnalysisRegistry, CrawlRegistry

app = typer.Typer(add_completion=False, help="Crawl Vingroup articles and analyze cached sources with multiple LLM providers.")
console = Console()
error_console = Console(stderr=True)
@app.command()
def crawl(
    url: str | None = typer.Option(None, "--url", help="One Vingroup news article URL."),
    file: Path | None = typer.Option(None, "--file", help="Text file containing one article URL per line."),
) -> None:
    """Crawl one URL or a text file of URLs without calling an LLM."""
    load_dotenv()
    if (url is None) == (file is None):
        error_console.print("[red]Error:[/red] provide exactly one of --url or --file")
        raise typer.Exit(code=2)
    cached_skipped = 0
    try:
        selected = [url] if url is not None else [
            line.strip() for line in file.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
        if not selected:
            raise ValueError("The URL file contains no article URLs")
        output_dir = Path("output")
        remove_legacy_outputs(output_dir)
        registry = CrawlRegistry(output_dir / "crawled_articles.csv")
        pending = []
        for selected_url in selected:
            language = article_language(selected_url)
            article_id = extract_article_id(selected_url)
            if article_id and registry.is_success(language, article_id):
                cached_skipped += 1
            else:
                pending.append(selected_url)
        discovered, articles, discovery_failures = discover_urls(pending, fetch=fetch_html)
    except (CrawlerError, OSError, ValueError) as exc:
        error_console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    skipped, succeeded, failed = cached_skipped, 0, 0
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
    console.print(f"Selected: {len(discovered) + len(discovery_failures) + cached_skipped} | Skipped: {skipped} | Crawled: {succeeded} | Failed: {failed}")
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
    article_id: str | None = typer.Option(None, "--id", help="One cached article ID to analyze."),
    file: Path | None = typer.Option(None, "--file", help="Text file with one article ID or Vingroup news URL per line."),
    analyze_all: bool = typer.Option(False, "--all", help="Analyze all cached articles matching other filters."),
    force: bool = typer.Option(False, "--force", help="Redo an existing analysis for the same provider/model."),
) -> None:
    """Analyze cached original articles; never recrawl them."""
    load_dotenv()
    provider_name = (provider_name or os.getenv("LLM_PROVIDER", "openai")).lower()
    if language not in {None, "vi", "en"}:
        error_console.print("[red]Error:[/red] --language must be vi or en")
        raise typer.Exit(code=2)
    if sum((article_id is not None, file is not None, analyze_all)) != 1:
        error_console.print("[red]Error:[/red] provide exactly one of --id, --file, or --all")
        raise typer.Exit(code=2)
    if article_id is not None and not article_id.isdigit():
        error_console.print("[red]Error:[/red] --id must be numeric")
        raise typer.Exit(code=2)
    selected_ids = {article_id} if article_id is not None else set()
    selected_keys: set[tuple[str, str]] = set()
    if file is not None:
        try:
            lines = file.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            error_console.print(f"[red]Error:[/red] {exc}")
            raise typer.Exit(code=1) from exc
        for line_number, line in enumerate(lines, 1):
            value = line.strip()
            if not value or value.startswith("#"):
                continue
            if value.isdigit():
                selected_ids.add(value)
            else:
                try:
                    selected_language = article_language(value)
                    selected_article_id = extract_article_id(value)
                    if not selected_article_id:
                        raise CrawlerError("Article URL has no numeric ID")
                    selected_keys.add((selected_language, selected_article_id))
                except CrawlerError as exc:
                    error_console.print(f"[red]Error:[/red] {file}:{line_number}: {exc}")
                    raise typer.Exit(code=2) from exc
        if not selected_ids and not selected_keys:
            error_console.print("[red]Error:[/red] the selection file contains no article IDs or URLs")
            raise typer.Exit(code=2)
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
        if not analyze_all and row["article_id"] not in selected_ids and (row["language"], row["article_id"]) not in selected_keys:
            continue
        if start and published < start:
            continue
        if end and published > end:
            continue
        rows.append(row)
    rows.sort(key=lambda row: (row["publication_date"], row["language"], int(row["article_id"])))
    found_ids = {row["article_id"] for row in rows}
    missing_ids = sorted(selected_ids - found_ids, key=int)
    found_keys = {(row["language"], row["article_id"]) for row in rows}
    missing_keys = sorted(selected_keys - found_keys, key=lambda key: (key[0], int(key[1])))
    missing = missing_ids + [f"{lang}/{article_id}" for lang, article_id in missing_keys]
    if missing and file is None:
        error_console.print(
            "[red]Error:[/red] requested articles are not available in the selected cached sources: "
            + ", ".join(missing)
        )
        raise typer.Exit(code=1)
    if not rows:
        console.print(f"Cached selected: 0 | Skipped: 0 | Analyzed: 0 | Failed: {len(missing)}")
        for requested in missing:
            error_console.print(f"[red]Missing cached article:[/red] {requested}")
        if missing:
            raise typer.Exit(code=1)
        return
    try:
        adapter = create_provider(provider_name)
    except AnalysisError as exc:
        error_console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    skipped = succeeded = 0
    failed = len(missing)
    failures = [f"not available in selected cached sources: {requested}" for requested in missing]
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

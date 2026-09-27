from __future__ import annotations

import typer
from dotenv import load_dotenv
from rich.console import Console

from .analyzer import analyze_article
from .crawler import fetch_html
from .errors import AnalysisError, CrawlerError
from .extractor import extract_article
from .output import write_outputs

app = typer.Typer(add_completion=False, help="Crawl and analyze one Vingroup article.")
console = Console()
error_console = Console(stderr=True)


@app.command()
def main(
    url: str = typer.Argument(
        ...,
        metavar="URL",
        help="A vingroup.net or www.vingroup.net article URL.",
    ),
) -> None:
    """Crawl one Vingroup article URL, write Markdown and JSON, then exit."""
    load_dotenv()
    try:
        html, resolved_url = fetch_html(url)
        article = extract_article(html, resolved_url)
        analysis, sections = analyze_article(article)
        markdown_path, json_path = write_outputs(article, analysis, sections)
    except (CrawlerError, AnalysisError) as exc:
        error_console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from exc
    except OSError as exc:
        error_console.print(f"[red]Error writing output:[/red] {exc}")
        raise typer.Exit(code=1) from exc
    console.print(f"Markdown: {markdown_path}")
    console.print(f"JSON: {json_path}")


if __name__ == "__main__":
    app()

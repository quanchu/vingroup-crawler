from __future__ import annotations

import json
import os
import re
import tempfile
from hashlib import sha256
from html import escape
from pathlib import Path

from .models import Article, ModelAnalysis
from .validation import section_text

VIP_COLOR = "#ffd6e7"
QUOTE_COLOR = "#fff3a3"
INDIRECT_COLOR = "#d9f7d9"


def base_name(article: Article) -> str:
    if not article.article_id or not article.article_id.isdigit():
        raise ValueError("A canonical numeric Vingroup article ID is required for output")
    return article.article_id


def render_markdown(article: Article) -> str:
    lines = [f"# {article.title}", "", f"Source: {article.source_url}"]
    if article.publication_date:
        lines.append(f"Publication date: {article.publication_date}")
    lines.append("")
    for index, paragraph in enumerate(article.paragraphs, 1):
        if index in article.headings:
            lines.extend([f"## {article.headings[index]}", ""])
        lines.extend([paragraph, ""])
    return "\n".join(lines).rstrip() + "\n"


def _highlight_source(text: str, analysis: ModelAnalysis) -> str:
    rendered = escape(text)
    # Wrap quotes first so VIP names inside quotes can be nested safely.
    quotes = sorted(
        {quote.original_quote for quote in analysis.quote_changes if quote.original_quote},
        key=len,
        reverse=True,
    )
    for quote in quotes:
        for fragment in quote.split("\n"):
            if not fragment:
                continue
            escaped_quote = escape(fragment)
            rendered = rendered.replace(
                escaped_quote,
                f'<mark style="background-color: {QUOTE_COLOR};">{escaped_quote}</mark>',
            )
    people = sorted(analysis.people, key=lambda person: len(person.name), reverse=True)
    for person in people:
        escaped_name = escape(person.name)
        title = "VIP" if person.assessment == "VIP" else "VIP review"
        if person.title_as_stated:
            title += f" — {person.title_as_stated}"
        rendered = rendered.replace(
            escaped_name,
            f'<mark style="background-color: {VIP_COLOR};" title="{escape(title, quote=True)}">'
            f"{escaped_name}</mark>",
        )
    return rendered


def render_proposed_markdown(
    article: Article,
    analysis: ModelAnalysis,
    *,
    provider: str | None = None,
    model: str | None = None,
    endpoint: str | None = None,
) -> str:
    """Render source text with proposed sections, quote changes, and VIP highlights."""
    lines = [
        f"# {article.title}",
        "",
        f"Source: {article.source_url}",
    ]
    if article.publication_date:
        lines.append(f"Publication date: {article.publication_date}")
    if provider and model:
        lines.extend([f"Analysis provider: {provider}", f"Analysis model: {model}"])
        if endpoint:
            lines.append(f"Analysis endpoint: {endpoint}")
    lines.extend([
        "",
        "<p><strong>Legend:</strong> "
        f'<mark style="background-color: {VIP_COLOR};">VIP</mark> '
        f'<mark style="background-color: {QUOTE_COLOR};">Direct quote</mark> '
        f'<span style="background-color: {INDIRECT_COLOR};">Suggested indirect wording</span></p>',
        "",
    ])

    quotes_by_section: dict[int, list] = {}
    for quote in analysis.quote_changes:
        quotes_by_section.setdefault(quote.section_index, []).append(quote)

    for section_index, section in enumerate(analysis.sections, 1):
        lines.extend([f"## {section.heading}", ""])
        source = section_text(section, article.paragraphs)
        for paragraph in source.split("\n"):
            if paragraph:
                lines.extend([_highlight_source(paragraph, analysis), ""])
        for quote in quotes_by_section.get(section_index, []):
            if quote.proposed_indirect:
                lines.extend([
                    f'<div style="background-color: {INDIRECT_COLOR}; padding: 0.75em;">',
                    f"<strong>Suggested indirect wording ({escape(quote.quote_id)}):</strong> "
                    f"{escape(quote.proposed_indirect)}",
                    "</div>",
                    "",
                ])
            else:
                lines.extend([
                    '<div style="background-color: #eeeeee; padding: 0.75em;">',
                    f"<strong>{escape(quote.quote_id)} requires review:</strong> {escape(quote.notes)}",
                    "</div>",
                    "",
                ])
    return "\n".join(lines).rstrip() + "\n"


def public_analysis(
    article: Article,
    analysis: ModelAnalysis,
    sections: list[dict],
    *,
    provider: str | None = None,
    model: str | None = None,
    endpoint: str | None = None,
) -> dict:
    result = {
        "source_url": article.source_url,
        "article_title": article.title,
        "publication_date": article.publication_date,
        "output_mode": "section_map",
        "paragraph_count": len(article.paragraphs),
        "paragraphs": None,
        "sections": sections,
        "people": [person.model_dump() for person in analysis.people],
        "quote_changes": [quote.model_dump() for quote in analysis.quote_changes],
    }
    if provider and model:
        result["analysis_provider"] = provider
        result["analysis_model"] = model
        if endpoint:
            result["analysis_endpoint"] = endpoint
    return result


def _write_temp(directory: Path, suffix: str, content: str) -> Path:
    descriptor, name = tempfile.mkstemp(prefix=".vingroup-", suffix=suffix, dir=directory)
    path = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return path


def _model_directory(provider: str, model: str, endpoint: str) -> Path:
    provider_piece = re.sub(r"[^a-z0-9._-]+", "-", provider.lower()).strip("-") or "provider"
    model_piece = re.sub(r"[^a-zA-Z0-9._-]+", "-", model).strip("-")[:64] or "model"
    digest = sha256(f"{model}\0{endpoint}".encode("utf-8")).hexdigest()[:8]
    return Path(provider_piece) / f"{model_piece}-{digest}"


def _install_group(items: list[tuple[Path, Path]]) -> None:
    installed: list[Path] = []
    backups: dict[Path, Path] = {}
    try:
        for temporary, destination in items:
            if destination.exists():
                backup = destination.with_name(f".{destination.name}.backup")
                backup.unlink(missing_ok=True)
                os.replace(destination, backup)
                backups[destination] = backup
            os.replace(temporary, destination)
            installed.append(destination)
    except Exception:
        for temporary, _ in items:
            temporary.unlink(missing_ok=True)
        for path in installed:
            path.unlink(missing_ok=True)
        for destination, backup in backups.items():
            if backup.exists():
                os.replace(backup, destination)
        raise
    for backup in backups.values():
        backup.unlink(missing_ok=True)


def write_crawl_outputs(
    article: Article,
    *,
    language: str,
    output_dir: Path = Path("output"),
) -> tuple[Path, Path]:
    if language not in {"vi", "en"}:
        raise ValueError("language must be 'vi' or 'en'")
    stem = base_name(article)
    markdown_dir = output_dir / language / "markdown"
    source_dir = output_dir / language / "crawled"
    markdown_dir.mkdir(parents=True, exist_ok=True)
    source_dir.mkdir(parents=True, exist_ok=True)
    markdown_path = markdown_dir / f"{stem}.md"
    source_path = source_dir / f"{stem}.json"
    markdown_temp = _write_temp(markdown_dir, ".md.tmp", render_markdown(article))
    source_temp = _write_temp(
        source_dir,
        ".source.json.tmp",
        json.dumps(article.model_dump(), ensure_ascii=False, indent=2) + "\n",
    )
    _install_group([(markdown_temp, markdown_path), (source_temp, source_path)])
    return markdown_path.resolve(), source_path.resolve()


def load_crawled_article(path: Path) -> Article:
    try:
        return Article.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"Invalid crawled article source {path}: {exc}") from exc


def write_analysis_outputs(
    article: Article,
    analysis: ModelAnalysis,
    sections: list[dict],
    *,
    language: str,
    provider: str,
    model: str,
    endpoint: str,
    output_dir: Path = Path("output"),
) -> tuple[Path, Path]:
    stem = base_name(article)
    model_dir = _model_directory(provider, model, endpoint)
    proposed_dir = output_dir / language / "proposed" / model_dir
    json_dir = output_dir / language / "analysis" / model_dir
    proposed_dir.mkdir(parents=True, exist_ok=True)
    json_dir.mkdir(parents=True, exist_ok=True)
    proposed_path = proposed_dir / f"{stem}.md"
    json_path = json_dir / f"{stem}.json"
    proposed_temp = _write_temp(
        proposed_dir,
        ".proposed.md.tmp",
        render_proposed_markdown(
            article, analysis, provider=provider, model=model, endpoint=endpoint
        ),
    )
    json_temp = _write_temp(
        json_dir,
        ".analysis.json.tmp",
        json.dumps(
            public_analysis(
                article,
                analysis,
                sections,
                provider=provider,
                model=model,
                endpoint=endpoint,
            ),
            ensure_ascii=False,
            indent=2,
        ) + "\n",
    )
    _install_group([(proposed_temp, proposed_path), (json_temp, json_path)])
    return proposed_path.resolve(), json_path.resolve()


def remove_legacy_outputs(output_dir: Path = Path("output")) -> None:
    """Remove only flat artifacts created by the pre-language layout."""
    if not output_dir.exists():
        return
    for pattern in ("*.md", "*.json"):
        for path in output_dir.glob(pattern):
            if path.name != "crawled_articles.json":
                path.unlink()

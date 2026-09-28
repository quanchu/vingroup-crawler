from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from .models import Article, ModelAnalysis


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


def public_analysis(article: Article, analysis: ModelAnalysis, sections: list[dict]) -> dict:
    return {
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


def write_outputs(
    article: Article,
    analysis: ModelAnalysis,
    sections: list[dict],
    *,
    language: str,
    output_dir: Path = Path("output"),
) -> tuple[Path, Path]:
    if language not in {"vi", "en"}:
        raise ValueError("language must be 'vi' or 'en'")
    markdown_dir = output_dir / language / "markdown"
    json_dir = output_dir / language / "json"
    markdown_dir.mkdir(parents=True, exist_ok=True)
    json_dir.mkdir(parents=True, exist_ok=True)
    stem = base_name(article)
    md_path = markdown_dir / f"{stem}.md"
    json_path = json_dir / f"{stem}.json"
    md_temp = _write_temp(markdown_dir, ".md.tmp", render_markdown(article))
    json_text = json.dumps(public_analysis(article, analysis, sections), ensure_ascii=False, indent=2) + "\n"
    json_temp: Path | None = None
    installed: list[Path] = []
    backups: dict[Path, Path] = {}
    try:
        json_temp = _write_temp(json_dir, ".json.tmp", json_text)
        for destination in (md_path, json_path):
            if destination.exists():
                backup = destination.with_name(f".{destination.name}.backup")
                backup.unlink(missing_ok=True)
                os.replace(destination, backup)
                backups[destination] = backup
        os.replace(md_temp, md_path)
        installed.append(md_path)
        os.replace(json_temp, json_path)
        installed.append(json_path)
    except Exception:
        md_temp.unlink(missing_ok=True)
        if json_temp:
            json_temp.unlink(missing_ok=True)
        for path in installed:
            path.unlink(missing_ok=True)
        for destination, backup in backups.items():
            if backup.exists():
                os.replace(backup, destination)
        raise
    for backup in backups.values():
        backup.unlink(missing_ok=True)
    return md_path.resolve(), json_path.resolve()


def remove_legacy_outputs(output_dir: Path = Path("output")) -> None:
    """Remove only flat artifacts created by the pre-language layout."""
    if not output_dir.exists():
        return
    for pattern in ("*.md", "*.json"):
        for path in output_dir.glob(pattern):
            if path.name != "crawled_articles.json":
                path.unlink()

from __future__ import annotations

import json
import os
import re
import tempfile
import unicodedata
from pathlib import Path

from .models import Article, ModelAnalysis


def _safe_piece(value: str) -> str:
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-zA-Z0-9]+", "-", ascii_value).strip("-").lower()[:80]


def base_name(article: Article) -> str:
    slug = _safe_piece(article.slug or article.title) or "article"
    ident = _safe_piece(article.article_id or "")
    return f"{ident}-{slug}" if ident and ident not in slug.split("-") else slug


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
    output_dir: Path = Path("output"),
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = base_name(article)
    counter = 1
    while True:
        candidate = stem if counter == 1 else f"{stem}-{counter}"
        md_path = output_dir / f"{candidate}.md"
        json_path = output_dir / f"{candidate}.json"
        if not md_path.exists() and not json_path.exists():
            break
        counter += 1
    md_temp = _write_temp(output_dir, ".md.tmp", render_markdown(article))
    json_text = json.dumps(public_analysis(article, analysis, sections), ensure_ascii=False, indent=2) + "\n"
    json_temp: Path | None = None
    installed: list[Path] = []
    try:
        json_temp = _write_temp(output_dir, ".json.tmp", json_text)
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
        raise
    return md_path.resolve(), json_path.resolve()


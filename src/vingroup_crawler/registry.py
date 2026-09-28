from __future__ import annotations

import csv
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from .models import DiscoveredArticle

CRAWL_FIELDS = ("language", "article_id", "source_url", "publication_date", "status", "markdown_path", "source_json_path", "error", "updated_at")
OLD_FIELDS = ("language", "article_id", "source_url", "publication_date", "status", "markdown_path", "proposed_markdown_path", "json_path", "error", "updated_at")
OLDER_FIELDS = tuple(field for field in OLD_FIELDS if field != "proposed_markdown_path")
ANALYSIS_FIELDS = ("language", "article_id", "provider", "model", "status", "proposed_markdown_path", "analysis_json_path", "error", "updated_at")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _atomic_csv(path: Path, fields: tuple[str, ...], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=f".{path.stem}-", suffix=".tmp", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


class CrawlRegistry:
    def __init__(self, path: Path = Path("output/crawled_articles.csv")) -> None:
        self.path = path
        self.rows: dict[tuple[str, str], dict[str, str]] = {}
        if not path.exists():
            return
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            columns = tuple(reader.fieldnames or ())
            if columns not in {CRAWL_FIELDS, OLD_FIELDS, OLDER_FIELDS}:
                raise ValueError(f"Unexpected crawl registry columns in {path}")
            for old in reader:
                row = {
                    "language": old["language"], "article_id": old["article_id"],
                    "source_url": old["source_url"], "publication_date": old["publication_date"],
                    "status": old["status"] if columns == CRAWL_FIELDS else "discovered",
                    "markdown_path": old.get("markdown_path", ""),
                    "source_json_path": old.get("source_json_path", ""),
                    "error": old.get("error", ""), "updated_at": old.get("updated_at", ""),
                }
                self.rows[(row["language"], row["article_id"])] = row

    def is_success(self, language: str, article_id: str) -> bool:
        row = self.rows.get((language, article_id))
        return bool(row and row["status"] == "success" and row["source_json_path"])

    def successful_rows(self) -> list[dict[str, str]]:
        return [row for row in self.rows.values() if self.is_success(row["language"], row["article_id"])]

    def discovered(self, item: DiscoveredArticle) -> None:
        key = (item.language, item.article_id)
        if self.is_success(*key):
            return
        existing = self.rows.get(key, {})
        self.rows[key] = {
            "language": item.language, "article_id": item.article_id,
            "source_url": item.source_url, "publication_date": item.publication_date,
            "status": "discovered", "markdown_path": existing.get("markdown_path", ""),
            "source_json_path": existing.get("source_json_path", ""), "error": "", "updated_at": _now(),
        }
        self.save()

    def success(self, item: DiscoveredArticle, markdown: Path, source_json: Path) -> None:
        self._set(item, "success", markdown_path=str(markdown), source_json_path=str(source_json), error="")

    def failed(self, item: DiscoveredArticle, error: str) -> None:
        if (item.language, item.article_id) not in self.rows:
            self.discovered(item)
        self._set(item, "failed", error=error)

    def _set(self, item: DiscoveredArticle, status: str, **values: str) -> None:
        self.rows[(item.language, item.article_id)].update(values, status=status, updated_at=_now())
        self.save()

    def save(self) -> None:
        rows = [self.rows[key] for key in sorted(self.rows, key=lambda value: (value[0], int(value[1])))]
        _atomic_csv(self.path, CRAWL_FIELDS, rows)


class AnalysisRegistry:
    def __init__(self, path: Path = Path("output/analyses.csv")) -> None:
        self.path = path
        self.rows: dict[tuple[str, str, str, str], dict[str, str]] = {}
        if path.exists():
            with path.open("r", encoding="utf-8", newline="") as handle:
                reader = csv.DictReader(handle)
                if tuple(reader.fieldnames or ()) != ANALYSIS_FIELDS:
                    raise ValueError(f"Unexpected analysis registry columns in {path}")
                for row in reader:
                    key = (row["language"], row["article_id"], row["provider"], row["model"])
                    self.rows[key] = dict(row)

    def is_success(self, key: tuple[str, str, str, str]) -> bool:
        row = self.rows.get(key)
        return bool(row and row["status"] == "success")

    def start(self, key: tuple[str, str, str, str]) -> None:
        language, article_id, provider, model = key
        existing = self.rows.get(key, {})
        self.rows[key] = {
            "language": language, "article_id": article_id, "provider": provider, "model": model,
            "status": "processing", "proposed_markdown_path": existing.get("proposed_markdown_path", ""),
            "analysis_json_path": existing.get("analysis_json_path", ""), "error": "", "updated_at": _now(),
        }
        self.save()

    def success(self, key: tuple[str, str, str, str], proposed: Path, analysis_json: Path) -> None:
        self.rows[key].update(status="success", proposed_markdown_path=str(proposed), analysis_json_path=str(analysis_json), error="", updated_at=_now())
        self.save()

    def failed(self, key: tuple[str, str, str, str], error: str) -> None:
        self.rows[key].update(status="failed", error=error, updated_at=_now())
        self.save()

    def save(self) -> None:
        _atomic_csv(self.path, ANALYSIS_FIELDS, [self.rows[key] for key in sorted(self.rows)])

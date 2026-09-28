from __future__ import annotations

import csv
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from .models import DiscoveredArticle

FIELDS = (
    "language", "article_id", "source_url", "publication_date", "status",
    "markdown_path", "json_path", "error", "updated_at",
)


class CrawlRegistry:
    def __init__(self, path: Path = Path("output/crawled_articles.csv")) -> None:
        self.path = path
        self.rows: dict[tuple[str, str], dict[str, str]] = {}
        if path.exists():
            with path.open("r", encoding="utf-8", newline="") as handle:
                reader = csv.DictReader(handle)
                if tuple(reader.fieldnames or ()) != FIELDS:
                    raise ValueError(f"Unexpected crawl registry columns in {path}")
                for row in reader:
                    self.rows[(row["language"], row["article_id"])] = dict(row)

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")

    def is_success(self, language: str, article_id: str) -> bool:
        row = self.rows.get((language, article_id))
        return bool(row and row["status"] == "success")

    def discovered(self, item: DiscoveredArticle) -> None:
        key = (item.language, item.article_id)
        existing = self.rows.get(key)
        if existing and existing["status"] == "success":
            return
        self.rows[key] = {
            "language": item.language,
            "article_id": item.article_id,
            "source_url": item.source_url,
            "publication_date": item.publication_date,
            "status": "discovered",
            "markdown_path": existing["markdown_path"] if existing else "",
            "json_path": existing["json_path"] if existing else "",
            "error": "",
            "updated_at": self._now(),
        }
        self.save()

    def success(self, item: DiscoveredArticle, markdown: Path, json_path: Path) -> None:
        self._set(item, "success", markdown_path=str(markdown), json_path=str(json_path), error="")

    def failed(self, item: DiscoveredArticle, error: str) -> None:
        self._set(item, "failed", error=error)

    def _set(self, item: DiscoveredArticle, status: str, **values: str) -> None:
        row = self.rows[(item.language, item.article_id)]
        row.update(values)
        row["status"] = status
        row["updated_at"] = self._now()
        self.save()

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, name = tempfile.mkstemp(prefix=".crawl-registry-", suffix=".tmp", dir=self.path.parent)
        temporary = Path(name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=FIELDS)
                writer.writeheader()
                for key in sorted(self.rows, key=lambda value: (value[0], int(value[1]))):
                    writer.writerow(self.rows[key])
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise

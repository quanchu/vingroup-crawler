import csv

from vingroup_crawler.models import DiscoveredArticle
from vingroup_crawler.registry import CrawlRegistry


def test_registry_is_atomic_and_resumable(tmp_path):
    path = tmp_path / "crawled_articles.csv"
    item = DiscoveredArticle(language="en", article_id="12", source_url="https://vingroup.net/en/x",
                             publication_date="2026-01-02")
    registry = CrawlRegistry(path)
    registry.discovered(item)
    registry.success(item, tmp_path / "12.md", tmp_path / "12.json")
    reloaded = CrawlRegistry(path)
    assert reloaded.is_success("en", "12")
    assert not list(tmp_path.glob(".crawl-registry-*"))
    with path.open(encoding="utf-8", newline="") as handle:
        row = next(csv.DictReader(handle))
    assert row["status"] == "success"

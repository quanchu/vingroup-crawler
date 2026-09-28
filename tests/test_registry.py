import csv

from vingroup_crawler.models import DiscoveredArticle
from vingroup_crawler.registry import AnalysisRegistry, CrawlRegistry


def test_registry_is_atomic_and_resumable(tmp_path):
    path = tmp_path / "crawled_articles.csv"
    item = DiscoveredArticle(language="en", article_id="12", source_url="https://vingroup.net/en/x",
                             publication_date="2026-01-02")
    registry = CrawlRegistry(path)
    registry.discovered(item)
    registry.success(item, tmp_path / "12.md", tmp_path / "12-source.json")
    reloaded = CrawlRegistry(path)
    assert reloaded.is_success("en", "12")
    assert not list(tmp_path.glob(".crawl-registry-*"))
    with path.open(encoding="utf-8", newline="") as handle:
        row = next(csv.DictReader(handle))
    assert row["status"] == "success"
    assert row["source_json_path"].endswith("12-source.json")


def test_registry_migrates_previous_columns(tmp_path):
    path = tmp_path / "crawled_articles.csv"
    old_fields = ["language", "article_id", "source_url", "publication_date", "status",
                  "markdown_path", "json_path", "error", "updated_at"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=old_fields)
        writer.writeheader()
        writer.writerow({"language": "vi", "article_id": "9080", "source_url": "https://vingroup.net/x",
                         "publication_date": "2026-01-01", "status": "success", "markdown_path": "old.md",
                         "json_path": "old.json", "error": "", "updated_at": "2026-01-01T00:00:00+00:00"})
    registry = CrawlRegistry(path)
    assert not registry.is_success("vi", "9080")
    assert registry.rows[("vi", "9080")]["source_json_path"] == ""


def test_analysis_registry_keys_exact_provider_and_model(tmp_path):
    registry = AnalysisRegistry(tmp_path / "analyses.csv")
    key = ("vi", "9080", "anthropic", "claude-test", "https://api.anthropic.com")
    registry.start(key)
    registry.success(key, tmp_path / "proposed.md", tmp_path / "analysis.json")
    reloaded = AnalysisRegistry(tmp_path / "analyses.csv")
    assert reloaded.is_success(key)
    assert not reloaded.is_success(("vi", "9080", "anthropic", "another-model", "https://api.anthropic.com"))

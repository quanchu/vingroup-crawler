import csv

from typer.testing import CliRunner

from vingroup_crawler.cli import app
from vingroup_crawler.models import Article, DiscoveredArticle, ModelAnalysis


def test_cli_crawls_range_and_writes_registry(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    item = DiscoveredArticle(language="vi", article_id="9080", source_url="https://vingroup.net/x",
                             publication_date="2026-01-15")
    article = Article(source_url=item.source_url, title="Article", publication_date=item.publication_date,
                      paragraphs=["First meaningful paragraph.", "Second meaningful paragraph."],
                      article_id="9080", slug="article")
    analysis = ModelAnalysis.model_validate({"sections": [{"heading": "All", "section_type": "narrative",
        "start_paragraph": 1, "end_paragraph": 2, "start_char": None, "end_char": None}],
        "people": [], "quote_changes": []})
    sections = [{"heading": "All", "section_type": "narrative", "start_paragraph": 1,
                 "end_paragraph": 2, "beginning_words": "First meaningful paragraph.",
                 "ending_words": "Second meaningful paragraph."}]
    monkeypatch.setattr("vingroup_crawler.cli.discover_articles",
                        lambda start, end, fetch: ([item], {("vi", "9080"): article}, []))
    monkeypatch.setattr("vingroup_crawler.cli.analyze_article", lambda value: (analysis, sections))

    result = CliRunner().invoke(app, ["--from", "2026-01-01", "--to", "2026-01-31"])
    assert result.exit_code == 0, result.output
    assert (tmp_path / "output/vi/markdown/9080.md").exists()
    assert (tmp_path / "output/vi/json/9080.json").exists()
    with (tmp_path / "output/crawled_articles.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["status"] == "success"
    assert "Successful: 1" in result.output


def test_cli_rejects_reversed_range():
    result = CliRunner().invoke(app, ["--from", "2026-02-01", "--to", "2026-01-01"])
    assert result.exit_code == 2
    assert "--to must be on or after --from" in result.output


def test_cli_requires_date_options():
    result = CliRunner().invoke(app, [])
    assert result.exit_code == 2
    assert "Missing option" in result.output

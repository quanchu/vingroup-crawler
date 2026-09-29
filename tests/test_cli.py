import csv

from typer.testing import CliRunner

from vingroup_crawler.cli import app
from vingroup_crawler.models import Article, DiscoveredArticle, ModelAnalysis


def fixture_data():
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
    return item, article, analysis, sections


def crawl_fixture(monkeypatch, tmp_path):
    item, article, _, _ = fixture_data()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("vingroup_crawler.cli.discover_urls",
                        lambda urls, fetch: ([item], {("vi", "9080"): article}, []))
    result = CliRunner().invoke(app, ["crawl", "--url", "https://vingroup.net/tin-tuc-su-kien/bai-viet/9080/one"])
    assert result.exit_code == 0, result.output
    return item, article


def test_crawl_writes_only_original_source(monkeypatch, tmp_path):
    crawl_fixture(monkeypatch, tmp_path)
    assert (tmp_path / "output/vi/markdown/9080.md").exists()
    assert (tmp_path / "output/vi/crawled/9080.json").exists()
    assert not (tmp_path / "output/vi/proposed").exists()
    with (tmp_path / "output/crawled_articles.csv").open(encoding="utf-8", newline="") as handle:
        row = next(csv.DictReader(handle))
    assert row["status"] == "success"
    assert row["source_json_path"].endswith("output/vi/crawled/9080.json")


def test_crawl_accepts_url_file(monkeypatch, tmp_path):
    item, article, _, _ = fixture_data()
    monkeypatch.chdir(tmp_path)
    urls = ["https://vingroup.net/tin-tuc-su-kien/bai-viet/9080/one",
            "https://vingroup.net/en/news/detail/42/two"]
    (tmp_path / "urls.txt").write_text("# comment\n" + "\n".join(urls) + "\n", encoding="utf-8")
    seen = []

    def selected(values, fetch):
        seen.extend(values)
        return [item], {("vi", "9080"): article}, []

    monkeypatch.setattr("vingroup_crawler.cli.discover_urls", selected)
    result = CliRunner().invoke(app, ["crawl", "--file", "urls.txt"])
    assert result.exit_code == 0, result.output
    assert seen == urls
    assert (tmp_path / "output/vi/markdown/9080.md").exists()


def test_analyze_uses_cached_source_and_tracks_model(monkeypatch, tmp_path):
    crawl_fixture(monkeypatch, tmp_path)
    _, _, analysis, sections = fixture_data()
    monkeypatch.setattr(
        "vingroup_crawler.cli.create_provider",
        lambda name: type("Provider", (), {"endpoint": "https://example.test"})(),
    )
    monkeypatch.setattr("vingroup_crawler.cli.analyze_article",
                        lambda article, provider, model: (analysis, sections))
    monkeypatch.setattr("vingroup_crawler.cli.discover_urls",
                        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not crawl")))
    result = CliRunner().invoke(app, ["analyze", "--provider", "openai", "--model", "test/model", "--id", "9080"])
    assert result.exit_code == 0, result.output
    proposed = list((tmp_path / "output/vi/proposed/openai").glob("*/9080.md"))
    analyzed = list((tmp_path / "output/vi/analysis/openai").glob("*/9080.json"))
    assert len(proposed) == len(analyzed) == 1
    assert "Analysis model: test/model" in proposed[0].read_text(encoding="utf-8")
    with (tmp_path / "output/analyses.csv").open(encoding="utf-8", newline="") as handle:
        row = next(csv.DictReader(handle))
    assert row["provider"] == "openai" and row["model"] == "test/model"
    assert row["endpoint"] == "https://example.test"


def test_analyze_requires_explicit_article_selection():
    result = CliRunner().invoke(app, ["analyze", "--provider", "openai", "--model", "test/model"])
    assert result.exit_code == 2
    assert "provide one or more --id values, or use --all" in result.output


def test_analyze_rejects_ids_with_all():
    result = CliRunner().invoke(app, ["analyze", "--provider", "openai", "--model", "test/model",
                                             "--id", "9080", "--all"])
    assert result.exit_code == 2
    assert "provide one or more --id values, or use --all" in result.output


def test_analyze_rejects_non_numeric_id():
    result = CliRunner().invoke(app, ["analyze", "--provider", "openai", "--model", "test/model",
                                             "--id", "abc"])
    assert result.exit_code == 2
    assert "every --id must be numeric" in result.output


def test_analyze_reports_uncrawled_requested_id(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(app, ["analyze", "--provider", "openai", "--model", "test/model",
                                             "--id", "9999"])
    assert result.exit_code == 1
    assert "requested IDs are not available" in result.output


def test_crawl_requires_one_input():
    result = CliRunner().invoke(app, ["crawl"])
    assert result.exit_code == 2
    assert "provide exactly one of --url or --file" in result.output


def test_crawl_rejects_both_inputs():
    result = CliRunner().invoke(app, ["crawl", "--url", "https://vingroup.net/en/news/detail/42/two", "--file", "urls.txt"])
    assert result.exit_code == 2
    assert "provide exactly one of --url or --file" in result.output


def test_crawl_rejects_empty_url_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "urls.txt").write_text("# no URLs\n\n", encoding="utf-8")
    result = CliRunner().invoke(app, ["crawl", "--file", "urls.txt"])
    assert result.exit_code == 1
    assert "contains no article URLs" in result.output

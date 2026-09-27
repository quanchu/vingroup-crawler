import json
from pathlib import Path

from typer.testing import CliRunner

from vingroup_crawler.cli import app
from vingroup_crawler.models import Article, ModelAnalysis


def test_cli_accepts_url_argument_writes_pair_and_exits(monkeypatch, tmp_path):
    article = Article(source_url="https://vingroup.net/a", title="Article", publication_date="2025-01-02",
                      paragraphs=["First meaningful paragraph.", "Second meaningful paragraph."], slug="article")
    analysis = ModelAnalysis.model_validate({"sections": [{"heading": "All", "section_type": "narrative",
        "start_paragraph": 1, "end_paragraph": 2, "start_char": None, "end_char": None}],
        "people": [], "quote_changes": []})
    sections = [{"heading": "All", "section_type": "narrative", "start_paragraph": 1,
                 "end_paragraph": 2, "beginning_words": "First meaningful paragraph.",
                 "ending_words": "Second meaningful paragraph."}]
    monkeypatch.setattr("vingroup_crawler.cli.fetch_html", lambda url: ("<html/>", url))
    monkeypatch.setattr("vingroup_crawler.cli.extract_article", lambda html, url: article)
    monkeypatch.setattr("vingroup_crawler.cli.analyze_article", lambda value: (analysis, sections))

    def write(value, parsed, rendered):
        from vingroup_crawler.output import write_outputs
        return write_outputs(value, parsed, rendered, output_dir=tmp_path)
    monkeypatch.setattr("vingroup_crawler.cli.write_outputs", write)

    result = CliRunner().invoke(app, ["https://vingroup.net/a"])
    assert result.exit_code == 0, result.output
    assert "Markdown:" in result.output and "JSON:" in result.output
    assert len(list(tmp_path.glob("*.md"))) == 1
    payload = json.loads(next(tmp_path.glob("*.json")).read_text(encoding="utf-8"))
    assert payload["article_title"] == "Article"


def test_cli_error_leaves_no_output(monkeypatch, tmp_path):
    from vingroup_crawler.errors import CrawlerError
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("vingroup_crawler.cli.fetch_html", lambda url: (_ for _ in ()).throw(CrawlerError("bad page")))
    result = CliRunner().invoke(app, ["https://vingroup.net/a"])
    assert result.exit_code == 1
    assert "bad page" in result.output
    assert not Path("output").exists()


def test_cli_requires_url_argument():
    result = CliRunner().invoke(app, [])
    assert result.exit_code == 2
    assert "Missing argument 'URL'" in result.output

import json

from vingroup_crawler.models import Article, ModelAnalysis
from vingroup_crawler.output import render_proposed_markdown, write_analysis_outputs, write_crawl_outputs


def test_writes_cached_source_and_model_specific_analysis(tmp_path):
    article = Article(source_url="https://vingroup.net/bai-viet/456/du-an", title="Dự án mới", publication_date=None,
                      paragraphs=["Nội dung bài viết."], headings={}, article_id="456", slug="du-an")
    analysis = ModelAnalysis.model_validate({"sections": [{"heading": "Nội dung", "section_type": "narrative",
        "start_paragraph": 1, "end_paragraph": 1, "start_char": None, "end_char": None}],
        "people": [], "quote_changes": []})
    section = [{"heading": "Nội dung", "section_type": "narrative", "start_paragraph": 1,
                "end_paragraph": 1, "beginning_words": "Nội dung bài", "ending_words": "dung bài viết."}]
    crawl_paths = write_crawl_outputs(article, language="vi", output_dir=tmp_path)
    analysis_paths = write_analysis_outputs(article, analysis, section, language="vi", provider="openai",
                                             model="test/model", endpoint="https://api.example/v1",
                                             output_dir=tmp_path)
    assert crawl_paths[0] == (tmp_path / "vi/markdown/456.md").resolve()
    assert crawl_paths[1] == (tmp_path / "vi/crawled/456.json").resolve()
    assert "Dự án mới" in crawl_paths[0].read_text(encoding="utf-8")
    assert crawl_paths[0].read_text(encoding="utf-8").startswith('---\ntitle: "Dự án mới"\npublication_date: null\n')
    assert "## Nội dung" in analysis_paths[0].read_text(encoding="utf-8")
    payload = json.loads(analysis_paths[1].read_text(encoding="utf-8"))
    assert payload["paragraphs"] is None
    assert payload["paragraph_count"] == 1
    assert payload["analysis_provider"] == "openai"
    assert payload["analysis_model"] == "test/model"
    assert payload["analysis_endpoint"] == "https://api.example/v1"


def test_proposed_markdown_highlights_quotes_vips_and_indirect_wording():
    article = Article(
        source_url="https://vingroup.net/tin-tuc-su-kien/bai-viet/9080/x",
        title="Test",
        publication_date="2026-01-01",
        paragraphs=['Narrative introduction.', 'Nguyen Van A said, "We will invest 10 dollars."'],
        article_id="9080",
        slug="x",
    )
    analysis = ModelAnalysis.model_validate({
        "sections": [
            {"heading": "Introduction", "section_type": "narrative", "start_paragraph": 1,
             "end_paragraph": 1, "start_char": None, "end_char": None},
            {"heading": "Nguyen Van A on investment", "section_type": "quotation", "start_paragraph": 2,
             "end_paragraph": 2, "start_char": None, "end_char": None},
        ],
        "people": [{"name": "Nguyen Van A", "title_as_stated": "CEO", "organization": "Example",
                    "assessment": "VIP", "evidence": "Nguyen Van A said", "reason": None}],
        "quote_changes": [{"quote_id": "q1", "section_index": 2,
            "location": {"start_paragraph": 2, "end_paragraph": 2}, "speaker": "Nguyen Van A",
            "original_quote": '"We will invest 10 dollars."',
            "proposed_indirect": "Nguyen Van A said that the company would invest 10 dollars.",
            "status": "proposed", "notes": "Resolved we to the company."}],
    })
    rendered = render_proposed_markdown(article, analysis)
    assert rendered.startswith('---\ntitle: "Test"\npublication_date: "2026-01-01"\n')
    assert "## Introduction" in rendered
    assert "## Nguyen Van A on investment" in rendered
    assert 'background-color: #fff3a3' in rendered
    assert 'background-color: #ffd6e7' in rendered
    assert "Suggested indirect wording (q1)" in rendered
    assert "would invest 10 dollars" in rendered


def test_analysis_paths_distinguish_local_endpoints(tmp_path):
    article = Article(source_url="https://vingroup.net/bai-viet/456/x", title="T", publication_date=None,
                      paragraphs=["One complete paragraph."], article_id="456", slug="x")
    analysis = ModelAnalysis.model_validate({"sections": [{"heading": "All", "section_type": "narrative",
        "start_paragraph": 1, "end_paragraph": 1, "start_char": None, "end_char": None}],
        "people": [], "quote_changes": []})
    sections = [{"heading": "All", "section_type": "narrative", "start_paragraph": 1,
                 "end_paragraph": 1, "beginning_words": "One complete paragraph.",
                 "ending_words": "One complete paragraph."}]
    first = write_analysis_outputs(article, analysis, sections, language="vi", provider="local-openai",
                                   model="same-model", endpoint="http://host-a/v1", output_dir=tmp_path)
    second = write_analysis_outputs(article, analysis, sections, language="vi", provider="local-openai",
                                    model="same-model", endpoint="http://host-b/v1", output_dir=tmp_path)
    assert first != second

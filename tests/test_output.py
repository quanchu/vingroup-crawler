import json

from vingroup_crawler.models import Article, ModelAnalysis
from vingroup_crawler.output import write_outputs


def test_writes_utf8_pair_without_overwrite(tmp_path):
    article = Article(source_url="https://vingroup.net/a/456-du-an", title="Dự án mới", publication_date=None,
                      paragraphs=["Nội dung bài viết."], headings={}, article_id="456", slug="456-du-an")
    analysis = ModelAnalysis.model_validate({"sections": [{"heading": "Nội dung", "section_type": "narrative",
        "start_paragraph": 1, "end_paragraph": 1, "start_char": None, "end_char": None}],
        "people": [], "quote_changes": []})
    section = [{"heading": "Nội dung", "section_type": "narrative", "start_paragraph": 1,
                "end_paragraph": 1, "beginning_words": "Nội dung bài", "ending_words": "dung bài viết."}]
    first = write_outputs(article, analysis, section, output_dir=tmp_path)
    second = write_outputs(article, analysis, section, output_dir=tmp_path)
    assert first[0] != second[0]
    assert "Dự án mới" in first[0].read_text(encoding="utf-8")
    payload = json.loads(first[1].read_text(encoding="utf-8"))
    assert payload["paragraphs"] is None
    assert payload["paragraph_count"] == 1


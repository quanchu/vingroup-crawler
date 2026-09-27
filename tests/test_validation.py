import pytest

from vingroup_crawler.models import Article, ModelAnalysis
from vingroup_crawler.validation import validate_analysis


def article():
    return Article(source_url="https://vingroup.net/a", title="T", publication_date=None,
                   paragraphs=["Alpha beta gamma quote starts", "continues and finishes here", "Final narrative words."])


def analysis(**overrides):
    value = {
        "sections": [
            {"heading": "Opening", "section_type": "narrative", "start_paragraph": 1, "end_paragraph": 1,
             "start_char": None, "end_char": 17},
            {"heading": "Quote", "section_type": "quotation", "start_paragraph": 1, "end_paragraph": 2,
             "start_char": 17, "end_char": None},
            {"heading": "End", "section_type": "narrative", "start_paragraph": 3, "end_paragraph": 3,
             "start_char": None, "end_char": None},
        ],
        "people": [],
        "quote_changes": [{"quote_id": "q1", "section_index": 2,
            "location": {"start_paragraph": 1, "end_paragraph": 2}, "speaker": None,
            "original_quote": "quote starts\ncontinues", "proposed_indirect": "The statement started and continued.",
            "status": "proposed", "notes": "Speaker absent in excerpt."}],
    }
    value.update(overrides)
    return ModelAnalysis.model_validate(value)


def test_validates_character_boundaries_and_computes_edges():
    sections = validate_analysis(article(), analysis())
    assert sections[1]["beginning_words"] == "quote starts continues"
    assert sections[1]["ending_words"] == "and finishes here"
    assert sections[0]["end_char"] == 17
    assert "start_char" not in sections[0]


def test_rejects_gap():
    data = analysis()
    data.sections[1].start_char = 18
    with pytest.raises(ValueError, match="gap"):
        validate_analysis(article(), data)


def test_rejects_duplicate_people_and_bad_evidence():
    people = [
        {"name": "Jane Doe", "title_as_stated": None, "organization": None, "assessment": "VIP", "evidence": "missing", "reason": None},
        {"name": " jane  doe ", "title_as_stated": None, "organization": None, "assessment": "Review", "evidence": "Alpha beta", "reason": None},
    ]
    with pytest.raises(ValueError, match="duplicates"):
        validate_analysis(article(), analysis(people=people))


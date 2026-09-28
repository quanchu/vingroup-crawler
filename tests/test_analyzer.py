from types import SimpleNamespace

import pytest

from vingroup_crawler.analyzer import analyze_article
from vingroup_crawler.errors import AnalysisError
from vingroup_crawler.models import Article, ModelAnalysis
from vingroup_crawler.providers import StructuredResponseError


ARTICLE = Article(source_url="https://vingroup.net/a", title="Title", publication_date=None,
                  paragraphs=["A sufficiently long first paragraph.", "A sufficiently long second paragraph."])


def valid():
    return ModelAnalysis.model_validate({"sections": [{"heading": "All", "section_type": "narrative",
        "start_paragraph": 1, "end_paragraph": 2, "start_char": None, "end_char": None}],
        "people": [], "quote_changes": []})


class Responses:
    def __init__(self, values): self.values, self.calls = list(values), []
    def parse(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(output_parsed=self.values.pop(0), output=[])


def test_valid_response():
    responses = Responses([valid()])
    parsed, sections = analyze_article(ARTICLE, client=SimpleNamespace(responses=responses))
    assert parsed.sections[0].heading == "All"
    assert len(sections) == 1
    assert responses.calls[0]["text_format"] is ModelAnalysis


def test_retries_with_validation_errors():
    invalid = valid()
    invalid.sections[0].end_paragraph = 1
    responses = Responses([invalid, valid()])
    analyze_article(ARTICLE, client=SimpleNamespace(responses=responses))
    assert len(responses.calls) == 2
    assert "PREVIOUS OUTPUT FAILED" in responses.calls[1]["input"]


def test_exhausted_retry():
    invalid = valid()
    invalid.sections[0].end_paragraph = 1
    with pytest.raises(AnalysisError, match="repair attempt"):
        analyze_article(ARTICLE, client=SimpleNamespace(responses=Responses([invalid, invalid])))


def test_refusal():
    content = SimpleNamespace(type="refusal", refusal="No")
    response = SimpleNamespace(output_parsed=None, output=[SimpleNamespace(content=[content])])
    class Refusing:
        def parse(self, **kwargs): return response
    with pytest.raises(AnalysisError, match="refused"):
        analyze_article(ARTICLE, client=SimpleNamespace(responses=Refusing()))


def test_provider_structured_error_gets_repair_retry():
    class RepairingProvider:
        name = "ollama"
        endpoint = "http://localhost:11434"
        def __init__(self): self.inputs = []
        def generate(self, *, model, input_text):
            self.inputs.append(input_text)
            if len(self.inputs) == 1:
                raise StructuredResponseError("invalid JSON")
            return valid()

    provider = RepairingProvider()
    parsed, _ = analyze_article(ARTICLE, provider=provider, model="local-test")
    assert parsed.sections[0].heading == "All"
    assert "PREVIOUS OUTPUT FAILED" in provider.inputs[1]

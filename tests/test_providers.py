from types import SimpleNamespace

from vingroup_crawler.models import ModelAnalysis
from vingroup_crawler.providers import AnthropicProvider, GeminiProvider


def payload():
    return {"sections": [{"heading": "All", "section_type": "narrative", "start_paragraph": 1,
                          "end_paragraph": 1, "start_char": None, "end_char": None}],
            "people": [], "quote_changes": []}


def test_anthropic_provider_uses_forced_schema_tool():
    calls = []
    messages = SimpleNamespace(create=lambda **kwargs: (
        calls.append(kwargs) or SimpleNamespace(content=[SimpleNamespace(
            type="tool_use", name="submit_analysis", input=payload())])))
    result = AnthropicProvider(client=SimpleNamespace(messages=messages)).generate(model="claude-test", input_text="x")
    assert isinstance(result, ModelAnalysis)
    assert calls[0]["tool_choice"] == {"type": "tool", "name": "submit_analysis"}
    assert calls[0]["model"] == "claude-test"


def test_gemini_provider_uses_response_schema():
    calls = []
    models = SimpleNamespace(generate_content=lambda **kwargs: (
        calls.append(kwargs) or SimpleNamespace(parsed=payload(), text="")))
    result = GeminiProvider(client=SimpleNamespace(models=models)).generate(model="gemini-test", input_text="x")
    assert isinstance(result, ModelAnalysis)
    assert calls[0]["config"]["response_schema"] is ModelAnalysis
    assert calls[0]["model"] == "gemini-test"

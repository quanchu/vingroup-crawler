from types import SimpleNamespace

from vingroup_crawler.models import ModelAnalysis
import json

from vingroup_crawler.providers import (
    AnthropicProvider,
    GeminiProvider,
    LocalOpenAIProvider,
    OllamaProvider,
)


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


def test_ollama_provider_sends_native_json_schema(monkeypatch):
    calls = []

    class Response:
        def raise_for_status(self): pass
        def json(self): return {"message": {"content": json.dumps(payload())}}

    client = SimpleNamespace(post=lambda url, **kwargs: (calls.append((url, kwargs)) or Response()))
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434/")
    result = OllamaProvider(client=client).generate(model="qwen-test", input_text="x")
    assert isinstance(result, ModelAnalysis)
    assert calls[0][0] == "http://localhost:11434/api/chat"
    assert calls[0][1]["json"]["format"] == ModelAnalysis.model_json_schema()
    assert calls[0][1]["json"]["stream"] is False


def test_local_openai_falls_back_to_json_object(monkeypatch):
    formats = []

    def create(**kwargs):
        formats.append(kwargs["response_format"])
        if len(formats) == 1:
            raise RuntimeError("json_schema unsupported")
        message = SimpleNamespace(content=json.dumps(payload()))
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])

    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    monkeypatch.setenv("LOCAL_OPENAI_BASE_URL", "http://localhost:1234/v1/")
    result = LocalOpenAIProvider(client=client).generate(model="local-test", input_text="x")
    assert isinstance(result, ModelAnalysis)
    assert formats[0]["type"] == "json_schema"
    assert formats[1] == {"type": "json_object"}

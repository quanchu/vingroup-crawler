from __future__ import annotations

import os
from typing import Any, Protocol

import httpx
from pydantic import ValidationError

from .errors import AnalysisError
from .models import ModelAnalysis
from .prompt import ANALYSIS_INSTRUCTIONS


class AnalysisProvider(Protocol):
    name: str
    endpoint: str

    def generate(self, *, model: str, input_text: str) -> ModelAnalysis: ...


class StructuredResponseError(AnalysisError):
    """A provider response that can be repaired by sending validation feedback."""


class OpenAIProvider:
    name = "openai"

    def __init__(self, client: Any | None = None) -> None:
        if client is None and not os.getenv("OPENAI_API_KEY"):
            raise AnalysisError("OPENAI_API_KEY is missing")
        if client is None:
            from openai import OpenAI
            client = OpenAI()
        self.client = client
        self.endpoint = str(getattr(client, "base_url", "https://api.openai.com/v1")).rstrip("/")

    def generate(self, *, model: str, input_text: str) -> ModelAnalysis:
        try:
            response = self.client.responses.parse(
                model=model,
                instructions=ANALYSIS_INSTRUCTIONS,
                input=input_text,
                text_format=ModelAnalysis,
            )
        except Exception as exc:
            raise AnalysisError(f"OpenAI request failed: {exc}") from exc
        for item in getattr(response, "output", []) or []:
            for content in getattr(item, "content", []) or []:
                if getattr(content, "type", None) == "refusal":
                    raise AnalysisError(
                        f"OpenAI refused the analysis: {getattr(content, 'refusal', 'refused')}"
                    )
        parsed = getattr(response, "output_parsed", None)
        if parsed is None:
            raise AnalysisError("OpenAI returned no parseable structured analysis")
        return parsed


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, client: Any | None = None) -> None:
        if client is None and not os.getenv("ANTHROPIC_API_KEY"):
            raise AnalysisError("ANTHROPIC_API_KEY is missing")
        if client is None:
            from anthropic import Anthropic
            client = Anthropic()
        self.client = client
        self.endpoint = str(getattr(client, "base_url", "https://api.anthropic.com")).rstrip("/")

    def generate(self, *, model: str, input_text: str) -> ModelAnalysis:
        try:
            response = self.client.messages.create(
                model=model,
                max_tokens=8192,
                system=ANALYSIS_INSTRUCTIONS,
                messages=[{"role": "user", "content": input_text}],
                tools=[{
                    "name": "submit_analysis",
                    "description": "Submit the complete validated article analysis.",
                    "input_schema": ModelAnalysis.model_json_schema(),
                }],
                tool_choice={"type": "tool", "name": "submit_analysis"},
            )
        except Exception as exc:
            raise AnalysisError(f"Anthropic request failed: {exc}") from exc
        for block in getattr(response, "content", []) or []:
            if getattr(block, "type", None) == "tool_use" and getattr(block, "name", None) == "submit_analysis":
                try:
                    return ModelAnalysis.model_validate(block.input)
                except ValidationError as exc:
                    raise StructuredResponseError(f"Anthropic returned invalid structured data: {exc}") from exc
        raise StructuredResponseError("Anthropic returned no submit_analysis tool result")


class GeminiProvider:
    name = "gemini"

    def __init__(self, client: Any | None = None) -> None:
        if client is None and not os.getenv("GEMINI_API_KEY"):
            raise AnalysisError("GEMINI_API_KEY is missing")
        if client is None:
            from google import genai
            client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
        self.client = client
        self.endpoint = "https://generativelanguage.googleapis.com"

    def generate(self, *, model: str, input_text: str) -> ModelAnalysis:
        try:
            response = self.client.models.generate_content(
                model=model,
                contents=input_text,
                config={
                    "system_instruction": ANALYSIS_INSTRUCTIONS,
                    "response_mime_type": "application/json",
                    "response_schema": ModelAnalysis,
                },
            )
        except Exception as exc:
            raise AnalysisError(f"Gemini request failed: {exc}") from exc
        parsed = getattr(response, "parsed", None)
        if isinstance(parsed, ModelAnalysis):
            return parsed
        try:
            return ModelAnalysis.model_validate(parsed) if parsed is not None else ModelAnalysis.model_validate_json(response.text)
        except (ValidationError, ValueError, TypeError) as exc:
            raise StructuredResponseError(f"Gemini returned invalid structured data: {exc}") from exc


def _local_timeout() -> float:
    raw = os.getenv("LOCAL_LLM_TIMEOUT", "300")
    try:
        value = float(raw)
    except ValueError as exc:
        raise AnalysisError("LOCAL_LLM_TIMEOUT must be a positive number") from exc
    if value <= 0:
        raise AnalysisError("LOCAL_LLM_TIMEOUT must be a positive number")
    return value


class OllamaProvider:
    name = "ollama"

    def __init__(self, client: Any | None = None) -> None:
        self.endpoint = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
        self.client = client or httpx.Client(timeout=_local_timeout())

    def generate(self, *, model: str, input_text: str) -> ModelAnalysis:
        try:
            response = self.client.post(
                f"{self.endpoint}/api/chat",
                json={
                    "model": model,
                    "stream": False,
                    "messages": [
                        {"role": "system", "content": ANALYSIS_INSTRUCTIONS},
                        {"role": "user", "content": input_text},
                    ],
                    "format": ModelAnalysis.model_json_schema(),
                    "options": {"temperature": 0},
                },
            )
            response.raise_for_status()
        except (httpx.HTTPError, OSError) as exc:
            raise AnalysisError(f"Ollama request failed at {self.endpoint}: {exc}") from exc
        try:
            content = response.json()["message"]["content"]
            if not content:
                raise ValueError("empty message content")
            return ModelAnalysis.model_validate_json(content)
        except (KeyError, TypeError, ValueError, ValidationError) as exc:
            raise StructuredResponseError(f"Ollama returned invalid structured data: {exc}") from exc


class LocalOpenAIProvider:
    name = "local-openai"

    def __init__(self, client: Any | None = None) -> None:
        self.endpoint = os.getenv("LOCAL_OPENAI_BASE_URL", "http://127.0.0.1:1234/v1").rstrip("/")
        if client is None:
            from openai import OpenAI
            client = OpenAI(
                base_url=self.endpoint,
                api_key=os.getenv("LOCAL_OPENAI_API_KEY", "local"),
                timeout=_local_timeout(),
            )
        self.client = client

    def _request(self, model: str, input_text: str, response_format: dict[str, Any]) -> Any:
        return self.client.chat.completions.create(
            model=model,
            temperature=0,
            messages=[
                {"role": "system", "content": ANALYSIS_INSTRUCTIONS},
                {"role": "user", "content": input_text},
            ],
            response_format=response_format,
        )

    def generate(self, *, model: str, input_text: str) -> ModelAnalysis:
        strict_format = {
            "type": "json_schema",
            "json_schema": {
                "name": "article_analysis",
                "strict": True,
                "schema": ModelAnalysis.model_json_schema(),
            },
        }
        try:
            try:
                response = self._request(model, input_text, strict_format)
            except Exception:
                response = self._request(model, input_text, {"type": "json_object"})
        except Exception as exc:
            raise AnalysisError(f"Local OpenAI-compatible request failed at {self.endpoint}: {exc}") from exc
        try:
            content = response.choices[0].message.content
            if not content:
                raise ValueError("empty message content")
            return ModelAnalysis.model_validate_json(content)
        except (AttributeError, IndexError, TypeError, ValueError, ValidationError) as exc:
            raise StructuredResponseError(
                f"Local OpenAI-compatible server returned invalid structured data: {exc}"
            ) from exc


def create_provider(name: str, *, client: Any | None = None) -> AnalysisProvider:
    normalized = name.strip().lower()
    providers = {
        "openai": OpenAIProvider,
        "anthropic": AnthropicProvider,
        "gemini": GeminiProvider,
        "ollama": OllamaProvider,
        "local-openai": LocalOpenAIProvider,
    }
    if normalized not in providers:
        raise AnalysisError(
            f"Unsupported provider {name!r}; choose openai, anthropic, gemini, ollama, or local-openai"
        )
    return providers[normalized](client=client)


def resolve_model(provider: str, explicit: str | None) -> str:
    if explicit:
        return explicit
    generic = os.getenv("LLM_MODEL")
    model_variables = {
        "openai": "OPENAI_MODEL",
        "anthropic": "ANTHROPIC_MODEL",
        "gemini": "GEMINI_MODEL",
        "ollama": "OLLAMA_MODEL",
        "local-openai": "LOCAL_OPENAI_MODEL",
    }
    specific = os.getenv(model_variables.get(provider, "")) if provider in model_variables else None
    if specific or generic:
        return specific or generic or ""
    if provider == "openai":
        return os.getenv("OPENAI_MODEL", "gpt-6-sol")
    variable = model_variables.get(provider, "LLM_MODEL")
    raise AnalysisError(f"A model is required for {provider}; pass --model or set {variable}")

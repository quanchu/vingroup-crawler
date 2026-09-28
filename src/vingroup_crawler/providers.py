from __future__ import annotations

import os
from typing import Any, Protocol

from pydantic import ValidationError

from .errors import AnalysisError
from .models import ModelAnalysis
from .prompt import ANALYSIS_INSTRUCTIONS


class AnalysisProvider(Protocol):
    name: str

    def generate(self, *, model: str, input_text: str) -> ModelAnalysis: ...


class OpenAIProvider:
    name = "openai"

    def __init__(self, client: Any | None = None) -> None:
        if client is None and not os.getenv("OPENAI_API_KEY"):
            raise AnalysisError("OPENAI_API_KEY is missing")
        if client is None:
            from openai import OpenAI
            client = OpenAI()
        self.client = client

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
                    raise AnalysisError(f"Anthropic returned invalid structured data: {exc}") from exc
        raise AnalysisError("Anthropic returned no submit_analysis tool result")


class GeminiProvider:
    name = "gemini"

    def __init__(self, client: Any | None = None) -> None:
        if client is None and not os.getenv("GEMINI_API_KEY"):
            raise AnalysisError("GEMINI_API_KEY is missing")
        if client is None:
            from google import genai
            client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
        self.client = client

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
            raise AnalysisError(f"Gemini returned invalid structured data: {exc}") from exc


def create_provider(name: str, *, client: Any | None = None) -> AnalysisProvider:
    normalized = name.strip().lower()
    providers = {
        "openai": OpenAIProvider,
        "anthropic": AnthropicProvider,
        "gemini": GeminiProvider,
    }
    if normalized not in providers:
        raise AnalysisError(f"Unsupported provider {name!r}; choose openai, anthropic, or gemini")
    return providers[normalized](client=client)


def resolve_model(provider: str, explicit: str | None) -> str:
    if explicit:
        return explicit
    generic = os.getenv("LLM_MODEL")
    specific = os.getenv(f"{provider.upper()}_MODEL")
    if specific or generic:
        return specific or generic or ""
    if provider == "openai":
        return os.getenv("OPENAI_MODEL", "gpt-6-sol")
    raise AnalysisError(f"A model is required for {provider}; pass --model or set {provider.upper()}_MODEL")

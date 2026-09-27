from __future__ import annotations

import os
from typing import Any

from openai import OpenAI

from .errors import AnalysisError
from .models import Article, ModelAnalysis
from .prompt import ANALYSIS_INSTRUCTIONS, article_input
from .validation import validate_analysis


def _refusal(response: Any) -> str | None:
    for item in getattr(response, "output", []) or []:
        for content in getattr(item, "content", []) or []:
            if getattr(content, "type", None) == "refusal":
                return getattr(content, "refusal", None) or "The model refused the request"
    return None


def analyze_article(
    article: Article,
    *,
    client: Any | None = None,
    model: str | None = None,
) -> tuple[ModelAnalysis, list[dict]]:
    if client is None and not os.getenv("OPENAI_API_KEY"):
        raise AnalysisError("OPENAI_API_KEY is missing. Add it to .env or the environment.")
    api = client or OpenAI()
    selected_model = model or os.getenv("OPENAI_MODEL", "gpt-6-sol")
    validation_errors: list[str] | None = None
    last_error = "unknown validation failure"
    for attempt in range(2):
        try:
            response = api.responses.parse(
                model=selected_model,
                instructions=ANALYSIS_INSTRUCTIONS,
                input=article_input(article.title, article.paragraphs, article.headings, validation_errors),
                text_format=ModelAnalysis,
            )
        except Exception as exc:
            raise AnalysisError(f"OpenAI analysis request failed: {exc}") from exc
        refusal = _refusal(response)
        if refusal:
            raise AnalysisError(f"OpenAI refused to analyze the article: {refusal}")
        parsed = getattr(response, "output_parsed", None)
        if parsed is None:
            raise AnalysisError("OpenAI returned no parseable structured analysis")
        try:
            sections = validate_analysis(article, parsed)
            return parsed, sections
        except ValueError as exc:
            last_error = str(exc)
            validation_errors = [part.strip() for part in last_error.split(";")]
            if attempt == 0:
                continue
    raise AnalysisError(f"OpenAI analysis failed semantic validation after one repair attempt: {last_error}")


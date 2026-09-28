from __future__ import annotations

from typing import Any

from .errors import AnalysisError
from .models import Article, ModelAnalysis
from .prompt import article_input
from .providers import AnalysisProvider, create_provider, resolve_model
from .validation import validate_analysis


def analyze_article(
    article: Article,
    *,
    client: Any | None = None,
    provider: str | AnalysisProvider = "openai",
    model: str | None = None,
) -> tuple[ModelAnalysis, list[dict]]:
    adapter = create_provider(provider, client=client) if isinstance(provider, str) else provider
    selected_model = resolve_model(adapter.name, model)
    validation_errors: list[str] | None = None
    last_error = "unknown validation failure"
    for attempt in range(2):
        parsed = adapter.generate(
            model=selected_model,
            input_text=article_input(article.title, article.paragraphs, article.headings, validation_errors),
        )
        try:
            sections = validate_analysis(article, parsed)
            return parsed, sections
        except ValueError as exc:
            last_error = str(exc)
            validation_errors = [part.strip() for part in last_error.split(";")]
            if attempt == 0:
                continue
    raise AnalysisError(f"OpenAI analysis failed semantic validation after one repair attempt: {last_error}")

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Article(StrictModel):
    source_url: str
    title: str
    publication_date: str | None
    paragraphs: list[str]
    headings: dict[int, str] = Field(default_factory=dict)
    article_id: str | None = None
    slug: str | None = None


class Section(StrictModel):
    heading: str
    section_type: Literal["narrative", "quotation", "corporate_boilerplate"]
    start_paragraph: int
    end_paragraph: int
    start_char: int | None
    end_char: int | None


class Person(StrictModel):
    name: str
    title_as_stated: str | None
    organization: str | None
    assessment: Literal["VIP", "Review"]
    evidence: str
    reason: str | None


class QuoteLocation(StrictModel):
    start_paragraph: int
    end_paragraph: int


class QuoteChange(StrictModel):
    quote_id: str
    section_index: int
    location: QuoteLocation
    speaker: str | None
    original_quote: str | None
    proposed_indirect: str | None
    status: Literal["proposed", "review"]
    notes: str


class ModelAnalysis(StrictModel):
    sections: list[Section]
    people: list[Person]
    quote_changes: list[QuoteChange]


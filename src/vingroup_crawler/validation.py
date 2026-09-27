from __future__ import annotations

import re

from .models import Article, ModelAnalysis


def _bounds(section, paragraphs: list[str]) -> tuple[tuple[int, int], tuple[int, int]]:
    count = len(paragraphs)
    if not 1 <= section.start_paragraph <= section.end_paragraph <= count:
        raise ValueError(
            f"section paragraph range {section.start_paragraph}-{section.end_paragraph} is outside 1-{count}"
        )
    start_text = paragraphs[section.start_paragraph - 1]
    end_text = paragraphs[section.end_paragraph - 1]
    start = 0 if section.start_char is None else section.start_char
    end = len(end_text) if section.end_char is None else section.end_char
    if not 0 <= start <= len(start_text):
        raise ValueError(f"section start_char {start} is outside P{section.start_paragraph}")
    if not 0 <= end <= len(end_text):
        raise ValueError(f"section end_char {end} is outside P{section.end_paragraph}")
    if section.start_paragraph == section.end_paragraph and start >= end:
        raise ValueError("section has an empty or reversed character span")
    return (section.start_paragraph, start), (section.end_paragraph, end)


def section_text(section, paragraphs: list[str]) -> str:
    (_, start), (_, end) = _bounds(section, paragraphs)
    selected = paragraphs[section.start_paragraph - 1 : section.end_paragraph]
    if len(selected) == 1:
        return selected[0][start:end]
    selected[0] = selected[0][start:]
    selected[-1] = selected[-1][:end]
    return "\n".join(selected)


def edge_words(text: str, *, beginning: bool) -> str:
    words = re.findall(r"\S+", text)
    chosen = words[:3] if beginning else words[-3:]
    return " ".join(chosen)


def validate_analysis(article: Article, analysis: ModelAnalysis) -> list[dict]:
    errors: list[str] = []
    if not analysis.sections:
        errors.append("sections must not be empty")
    else:
        bounds: list[tuple[tuple[int, int], tuple[int, int]]] = []
        for index, section in enumerate(analysis.sections, 1):
            try:
                bounds.append(_bounds(section, article.paragraphs))
            except ValueError as exc:
                errors.append(f"section {index}: {exc}")
        if len(bounds) == len(analysis.sections):
            if bounds[0][0] != (1, 0):
                errors.append("section coverage must begin at character 0 of P1")
            if bounds[-1][1] != (len(article.paragraphs), len(article.paragraphs[-1])):
                errors.append("section coverage must end at the final character of the last paragraph")
            for i, (previous, current) in enumerate(zip(bounds, bounds[1:]), 1):
                prev_end, next_start = previous[1], current[0]
                contiguous = next_start == prev_end or (
                    next_start == (prev_end[0] + 1, 0)
                    and prev_end[1] == len(article.paragraphs[prev_end[0] - 1])
                )
                if not contiguous:
                    errors.append(f"sections {i} and {i + 1} overlap or leave a gap")

    full_text = "\n".join(article.paragraphs)
    seen_people: set[str] = set()
    for i, person in enumerate(analysis.people, 1):
        key = " ".join(person.name.casefold().split())
        if key in seen_people:
            errors.append(f"person {i} duplicates {person.name!r}")
        seen_people.add(key)
        if not person.evidence or person.evidence not in full_text:
            errors.append(f"person {i} evidence is not an exact article substring")
        if person.assessment == "Review" and not person.reason:
            errors.append(f"person {i} marked Review must explain why")

    quote_ids: set[str] = set()
    referenced_quote_sections: set[int] = set()
    for i, quote in enumerate(analysis.quote_changes, 1):
        if quote.quote_id in quote_ids:
            errors.append(f"quote {i} repeats quote_id {quote.quote_id!r}")
        quote_ids.add(quote.quote_id)
        if not 1 <= quote.section_index <= len(analysis.sections):
            errors.append(f"quote {i} section_index is out of range")
            continue
        section = analysis.sections[quote.section_index - 1]
        if section.section_type != "quotation":
            errors.append(f"quote {i} references a non-quotation section")
        else:
            referenced_quote_sections.add(quote.section_index)
        loc = quote.location
        if not (section.start_paragraph <= loc.start_paragraph <= loc.end_paragraph <= section.end_paragraph):
            errors.append(f"quote {i} location is outside its section")
        if not quote.original_quote:
            errors.append(f"quote {i} is missing exact original_quote text")
        else:
            try:
                selected = section_text(section, article.paragraphs)
            except ValueError:
                selected = ""
            if quote.original_quote not in selected:
                errors.append(f"quote {i} original_quote is not an exact substring of its quotation section")
        if quote.status == "proposed" and (not quote.original_quote or not quote.proposed_indirect):
            errors.append(f"quote {i} marked proposed requires original_quote and proposed_indirect")
        if quote.status == "review" and quote.proposed_indirect is not None:
            errors.append(f"quote {i} marked review must have null proposed_indirect")
    expected_quote_sections = {
        index for index, section in enumerate(analysis.sections, 1) if section.section_type == "quotation"
    }
    missing_sections = expected_quote_sections - referenced_quote_sections
    if missing_sections:
        errors.append(f"quotation sections missing quote_changes: {sorted(missing_sections)}")
    if errors:
        raise ValueError("; ".join(errors))

    public_sections: list[dict] = []
    for section in analysis.sections:
        text = section_text(section, article.paragraphs)
        item = section.model_dump(exclude_none=True)
        item["beginning_words"] = edge_words(text, beginning=True)
        item["ending_words"] = edge_words(text, beginning=False)
        # Keep the public field order aligned with the documented contract.
        public_sections.append({
            "heading": item["heading"],
            "section_type": item["section_type"],
            "start_paragraph": item["start_paragraph"],
            "end_paragraph": item["end_paragraph"],
            "beginning_words": item["beginning_words"],
            "ending_words": item["ending_words"],
            **({"start_char": item["start_char"]} if "start_char" in item else {}),
            **({"end_char": item["end_char"]} if "end_char" in item else {}),
        })
    return public_sections

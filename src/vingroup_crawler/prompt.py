ANALYSIS_INSTRUCTIONS = """
Analyze the supplied Vingroup article paragraphs. Return only data matching the schema.

Segmentation rules:
- Group adjacent paragraphs by idea and write concise factual headings in the article's language.
- Every distinct direct quotation MUST be its own quotation section, together with its immediate speaker attribution. A continuous quote spanning paragraphs stays together. Quotation marks around names, slogans, or terms do not count.
- Every reusable corporate profile MUST be its own corporate_boilerplate section. Separate profiles remain separate.
- Cover all article text exactly once, in order. Where a boundary occurs inside a paragraph, use zero-based Unicode start_char/end_char offsets; end_char is exclusive. Use null for offsets at whole-paragraph boundaries.

People rules:
- Include named high-level executives, government officials, acclaimed physicians/scientists, and similarly prominent people supported by the article.
- Copy name, title, organization, and a short evidence substring exactly. Do not infer facts. Deduplicate people case-insensitively.
- Use assessment Review and explain ambiguity in reason; otherwise use VIP and null reason.

Quote-change rules:
- Include every distinct direct quotation, with its exact original_quote and the 1-based index of its quotation section.
- proposed_indirect preserves speaker, meaning, modality, uncertainty, negation, conditions, numbers, and attribution, but omits the speaker's formal title/honorific. Resolve pronouns only from context and backshift only when appropriate.
- If speaker or referent is unclear, status is review and proposed_indirect is null. Do not invent facts.
""".strip()


def article_input(title: str, paragraphs: list[str], headings: dict[int, str], errors: list[str] | None = None) -> str:
    lines = [f"ARTICLE TITLE: {title}", "", "SOURCE HEADINGS (before paragraph):"]
    lines.extend(f"P{index}: {heading}" for index, heading in sorted(headings.items()))
    if not headings:
        lines.append("(none)")
    lines.extend(["", "NUMBERED BODY PARAGRAPHS:"])
    lines.extend(f"P{i}: {paragraph}" for i, paragraph in enumerate(paragraphs, 1))
    if errors:
        lines.extend(["", "YOUR PREVIOUS OUTPUT FAILED THESE CHECKS. REPAIR ALL OF THEM:"])
        lines.extend(f"- {error}" for error in errors)
    return "\n".join(lines)

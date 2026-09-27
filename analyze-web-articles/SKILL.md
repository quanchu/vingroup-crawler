---
name: analyze-web-articles
description: "Accept a vingroup.net article URL, isolate its body, and deliver one JSON file containing article segmentation, VIP named-entity extraction, and suggested indirect versions of direct quotations: headings, paragraph ranges, exact beginning and ending snippets, and optional character offsets for boundaries inside paragraphs. Keep each quotation and corporate boilerplate in its own section. When the user supplies full text, include the unchanged article paragraphs in that JSON."
---

# Analyze web articles

## Workflow

1. Accept an article URL as the primary input and open that URL directly. Do not search by article title. Restrict the source to `vingroup.net` or `www.vingroup.net`, checking the final hostname after redirects. If the user provides only a title, ask for the article URL. Record the resolved source URL, page title, and publication date when available. Do not guess missing text or substitute another article.
2. Isolate the article body using the title, date, byline, body, and ending. Exclude menus, cookie banners, sharing controls, related stories, comments, and the site's general footer. Preserve the original paragraph order, wording, punctuation, numbers, quotations, and existing meaningful headings. If extraction is uncertain, state exactly where.
3. Number body paragraphs P1, P2, and so on, excluding the title, date, navigation, and footer. Group adjacent paragraphs that develop one idea. Insert concise, factual headings in the article's language. For a short or single-topic article, use few headings rather than forcing sections.

   Apply these mandatory segmentation exceptions before ordinary topic-based grouping:

   - **Each quotation is its own section.** Keep a continuous quotation, including one spanning multiple paragraphs, together with its immediate speaker attribution. Do not combine it with another distinct quotation or surrounding narrative. A short quotation still gets a section. Use a factual heading identifying the speaker and/or subject without inventing an attribution. Quotation marks around a product name, slogan, or term alone do not trigger this exception.
   - **Each corporate boilerplate is its own section.** Isolate the complete reusable company profile from narrative and quotations. Preserve an existing About heading or generate a suitable heading. Keep separate company profiles in separate sections. This is a segmentation boundary only; do not produce a separate boilerplate analysis.
   - Preserve original paragraphs. When a quotation or boilerplate boundary falls inside a paragraph, add `start_char` and `end_char` to the affected section objects: zero-based Unicode character offsets within the start/end paragraphs, with `end_char` exclusive. Whole-paragraph sections omit offsets. Paragraph ranges may coincide in this case, but text spans must remain contiguous and nonoverlapping. If a quotation lies inside a boilerplate, isolate the quotation and retain the surrounding profile spans as boilerplate sections so both exceptions are honored.

   Every section must include `beginning_words` and `ending_words` for a sanity check. Copy exact short spans from the beginning and end of the section's original source text, not from its generated heading. Use the first and last three whitespace-delimited words by default, retaining punctuation, capitalization, accents, and original language; use the full span if it has fewer words. Respect character offsets when present. Never paraphrase these fields or insert ellipses not present in the source.

4. Choose the JSON output mode based on source text availability:

   - **Full-text mode:** If the user supplies article text or a file, put every original body paragraph in `paragraphs` in order, without paraphrasing, correcting, or omitting it. Keep the title and date in their own fields. Section indices refer to this array (one-based).
   - **Web-source section-map mode:** For a URL-only article, set `paragraphs` to `null` when full verbatim output is unavailable. Provide contiguous, nonoverlapping section ranges covering all body text exactly once; use character offsets for boundaries inside a paragraph. Do not present a section map as a full article copy.

5. For every distinct direct quotation, add a suggested indirect version in `quote_changes`. Keep the original quotation unchanged in the article paragraphs or section map; the suggestion is separate and must not replace it. Preserve the speaker, meaning, modality, uncertainty, negation, conditions, numbers, and attribution. In `proposed_indirect`, omit the speaker's formal title and honorific (for example, write `Nguyen Van A said ...`, not `Mr. Nguyen Van A, CEO, said ...`). Keep the complete title in the `people` fields, and do not alter the original quotation. Resolve first- and second-person pronouns from context (`we`/`our` may refer to a company or team); if a referent is unclear, set `status` to `review` and leave the proposal null. Use tense appropriate to when the statement was made, applying backshift only when grammatically and semantically appropriate. Adjust words such as `today`, `tomorrow`, and `here` only when the context establishes their meaning. Do not invent a speaker or facts.

6. Extract named people who plausibly qualify as VIPs. Include high-level corporate executives, government officials, and acclaimed physicians or scientists, as well as similarly prominent people relevant to the article. Preserve each person's name, title, organization, and a short article-local evidence excerpt exactly as stated. Do not infer a title or prominence that the article does not support. Distinguish a former or quoted title from a current title. Deduplicate repeated mentions. For an ambiguous case, include it with `assessment: "Review"` and explain why; do not silently discard it. Use `[]` when no qualifying person is named.

7. Create exactly one UTF-8 `<base>.json` file containing the segmentation, VIP entities, and quote suggestions. Use this shape:

   ```json
   {
     "source_url": "https://example.com/article",
     "article_title": "Article title",
     "publication_date": null,
     "output_mode": "section_map",
     "paragraph_count": 0,
     "paragraphs": null,
     "sections": [
       {
         "heading": "Section heading",
         "section_type": "narrative",
         "start_paragraph": 1,
         "end_paragraph": 2,
         "beginning_words": "Exact opening words",
         "ending_words": "Exact closing words"
       }
     ],
     "people": [
       {
         "name": "Name exactly as stated",
         "title_as_stated": "Title exactly as stated, or null",
         "organization": "Organization as stated, or null",
         "assessment": "VIP",
         "evidence": "Short exact excerpt from the article",
         "reason": null
       }
     ],
     "quote_changes": [
       {
         "quote_id": "q1",
         "section_index": 2,
         "location": {
           "start_paragraph": 3,
           "end_paragraph": 3
         },
         "speaker": "Name as stated, or null",
         "original_quote": "Exact quotation when available, otherwise null",
         "proposed_indirect": "Suggested indirect wording, or null if unresolved",
         "status": "proposed",
         "notes": "Brief explanation of tense, pronoun, or temporal-reference choices"
       }
     ]
   }
   ```

   Use `narrative`, `quotation`, or `corporate_boilerplate` for `section_type`. Add `start_char` and `end_char` only when a section boundary occurs inside a paragraph. Use JSON `null` for unavailable metadata. Use `VIP` or `Review` for `assessment`. Use `[]` when there are no qualifying people or direct quotations. Use `proposed` or `review` for quote-change status. Provide one downloadable JSON link.

8. Verify against the source. In full-text mode, compare `paragraphs` with the supplied article for exact text and order. Verify that sections cover all body text exactly once, using character offsets when supplied. Check every section's beginning and ending snippets against its source span. Check that every distinct quotation is isolated, continuous multi-paragraph quotes remain together, and every corporate boilerplate is isolated as a section. Check named people, titles, organizations, evidence, and ambiguity assessments against the article. Confirm valid JSON and ensure quote suggestions preserve the original meaning, use appropriate tense and pronouns, and omit formal speaker titles from `proposed_indirect`. Do not add a separate boilerplate classification.

## Output example

For a body with narrative paragraphs, a quoted executive statement, and a reusable company profile, return three or more section objects whose `section_type` values identify the boundaries. Keep the paragraph text unchanged when full-text mode is used.

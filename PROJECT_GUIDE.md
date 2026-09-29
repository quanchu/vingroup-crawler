# Vingroup Crawler: Detailed Project Guide

## 1. Purpose

This project is a Python 3.11 command-line application for collecting public Vingroup news articles and analyzing them with hosted or local language models.

The application deliberately separates two operations:

1. **Crawling** discovers articles, extracts their original text, and saves a provider-independent source record.
2. **Analysis** reads those saved source records and asks a selected LLM to propose article sections, identify VIPs, and convert direct quotations into suggested indirect wording.

This separation means an article only needs to be downloaded once. The same cached source can subsequently be analyzed by several models without contacting Vingroup again or changing the original text.

## 2. Installation

The project uses [`uv`](https://docs.astral.sh/uv/) for dependency and virtual-environment management.

```bash
uv sync
uv run playwright install chromium
cp .env.example .env
```

Playwright is only used when Vingroup responds with a Cloudflare JavaScript challenge. The normal download path uses `httpx`.

Never commit `.env`; it is ignored by Git. Add only the API keys and defaults needed for the providers you use.

## 3. Command-Line Workflow

### 3.1 Crawl articles

```bash
uv run vingroup-crawler crawl --url 'https://vingroup.net/en/news/detail/9087/green-gsm-officially-launches-all-electric-taxi-service-in-northern-mindanao-philippines'
uv run vingroup-crawler crawl --file article-urls.txt
```

The crawl command requires either one article URL or a UTF-8 text file with one article URL per line. Blank lines and `#` comments in the file are ignored. Only article URLs from these news sections are accepted:

- Vietnamese: `/vi/tin-tuc-su-kien` (article links may use `/tin-tuc-su-kien/bai-viet/{id}/...`)
- English: `/en/news` (article links use `/en/news/detail/{id}/...`)

It does not discover article URLs or call any LLM. For each input article, it writes the original Markdown and a structured JSON cache containing the exact extracted paragraphs and meaningful source headings.

### 3.2 Analyze selected cached articles

At least one repeatable `--id` or the explicit `--all` flag is required:

```bash
uv run vingroup-crawler analyze \
  --provider openai \
  --model gpt-6-sol \
  --id 9080 \
  --id 9081
```

Optional filters narrow the cached records further:

```bash
uv run vingroup-crawler analyze \
  --provider ollama \
  --model qwen3:14b \
  --id 9080 \
  --language vi \
  --from 2026-01-01 \
  --to 2026-01-31
```

Use `--all` only when every cached article matching the other filters should be analyzed. `--all` and `--id` are mutually exclusive. IDs must be numeric, and an uncrawled requested ID is reported as an error before a provider is initialized.

Completed analyses for the same language, article ID, provider, model, and endpoint are skipped. Use `--force` to repeat that exact analysis from the cached source.

## 4. Supported LLM Providers

All provider adapters produce the same strict `ModelAnalysis` Pydantic model. Provider output is never trusted merely because the remote API accepted a schema; every response also passes local semantic validation.

### OpenAI

```bash
uv run vingroup-crawler analyze --provider openai --model gpt-6-sol --id 9080
```

Uses the Responses API and Pydantic Structured Outputs. Configure `OPENAI_API_KEY` and optionally `OPENAI_MODEL`.

### Anthropic

```bash
uv run vingroup-crawler analyze --provider anthropic --model YOUR_CLAUDE_MODEL --id 9080
```

Uses a forced `submit_analysis` tool whose input schema is generated from `ModelAnalysis`. Configure `ANTHROPIC_API_KEY` and optionally `ANTHROPIC_MODEL`.

### Google Gemini

```bash
uv run vingroup-crawler analyze --provider gemini --model YOUR_GEMINI_MODEL --id 9080
```

Uses Gemini JSON response schemas. Configure `GEMINI_API_KEY` and optionally `GEMINI_MODEL`.

### Ollama

```bash
uv run vingroup-crawler analyze --provider ollama --model qwen3:14b --id 9080
```

Uses native `POST /api/chat` with the complete analysis schema in Ollama's `format` field. The default endpoint is `http://127.0.0.1:11434`. Override it with `OLLAMA_BASE_URL`; configure a default model with `OLLAMA_MODEL`.

The project does not run `ollama pull` or start the Ollama service. The requested model must already be installed and the service must already be available.

### Local OpenAI-Compatible Servers

```bash
uv run vingroup-crawler analyze \
  --provider local-openai \
  --model local-model \
  --id 9080
```

This adapter targets LM Studio, vLLM, and similar `/v1/chat/completions` implementations. It first requests strict JSON Schema output. If the server rejects that feature, it retries with JSON-object mode and still applies the full local validator.

The default endpoint is `http://127.0.0.1:1234/v1`. Configure `LOCAL_OPENAI_BASE_URL`, optional `LOCAL_OPENAI_API_KEY`, and optional `LOCAL_OPENAI_MODEL`. The harmless default key is `local` because many local servers require a nonempty value but do not authenticate it.

Local inference defaults to a 300-second request timeout. Change it with `LOCAL_LLM_TIMEOUT`.

## 5. Output Layout

Artifacts are separated by language, purpose, provider, model, and endpoint:

```text
output/
├── crawled_articles.csv
├── analyses.csv
├── vi/
│   ├── markdown/9080.md
│   ├── crawled/9080.json
│   ├── proposed/openai/gpt-6-sol-<hash>/9080.md
│   └── analysis/openai/gpt-6-sol-<hash>/9080.json
└── en/
    ├── markdown/9080.md
    ├── crawled/9080.json
    ├── proposed/ollama/qwen3-14b-<hash>/9080.md
    └── analysis/ollama/qwen3-14b-<hash>/9080.json
```

The directory hash is derived from both the exact model ID and provider endpoint. Therefore, identically named models served from two different local endpoints do not overwrite one another.

### Source artifacts

- `markdown/{id}.md` contains YAML front matter with title, source URL, and publication date, followed by original extracted headings and paragraphs.
- `crawled/{id}.json` is the canonical machine-readable `Article` cache used by every analysis run.

### Analysis artifacts

- `analysis/{provider}/{model-hash}/{id}.json` contains the section map, VIPs, quote suggestions, exact provider, exact model, and endpoint.
- `proposed/{provider}/{model-hash}/{id}.md` preserves source wording while adding proposed section headings, pink VIP highlights, yellow direct-quote highlights, and green indirect-wording suggestions.

The original Markdown and cached JSON are never replaced by LLM-generated text.

## 6. Registries and Resume Behavior

### `crawled_articles.csv`

Each row is keyed by language and Vingroup article ID. It records the source URL, publication date, crawl status, original Markdown path, cached JSON path, error, and update time.

A row is considered successfully crawled only when its source JSON path is present. Failed and interrupted records are eligible for a later retry.

### `analyses.csv`

Each row is keyed by:

```text
(language, article_id, provider, model, endpoint)
```

It records the proposed Markdown path, analysis JSON path, status, error, and update time. The endpoint is part of the key because local servers can host different weights or configurations under the same model name.

Both registries are rewritten through temporary files and atomic replacement. Output file groups use the same prepare-then-replace strategy, with rollback to previous files when installation fails.

## 7. Crawl Pipeline

The crawl command follows this sequence:

1. Read one URL or a text file of URLs.
2. Validate news detail routes and deduplicate by language and article ID.
3. Skip articles already cached successfully.
4. Fetch each remaining detail page and extract its publication date.
5. Isolate the article title, meaningful headings, and ordered body paragraphs.
6. Write original Markdown and canonical source JSON.
7. Update `crawled_articles.csv` after every article.

The extractor prefers known Vingroup article containers and falls back to scored semantic containers. Navigation, sharing controls, related stories, cookie UI, forms, advertising, and footer content are removed. Pages without enough confidently isolated body text are rejected rather than guessed.

## 8. Network and Cloudflare Safety

Only `http` and `https` URLs whose hostname is exactly `vingroup.net` or `www.vingroup.net` are accepted. Credentials, deceptive subdomains, and nonstandard ports are rejected.

The HTTP path enforces:

- validation of every redirect;
- a maximum of five redirects;
- connection and response timeouts;
- HTML content types;
- a 5 MiB response limit.

When the response indicates a Cloudflare challenge, the crawler opens a visible browser with a persistent crawler profile. Main-frame navigation is restricted to the allowed Vingroup hosts. Images, media, and fonts are blocked because they are unnecessary for extraction.

Browser settings are controlled by:

```dotenv
VINGROUP_BROWSER_CHANNEL=default
VINGROUP_BROWSER_HEADLESS=0
VINGROUP_BROWSER_PROFILE=.vingroup-browser-profile
```

On macOS the crawler uses the current default browser; elsewhere it uses Playwright Chromium. Set `VINGROUP_BROWSER_CHANNEL=chromium`, `chrome`, or `default` to override that choice. The selected browser must be Chromium compatible. The crawler uses a separate profile. The browser challenge timeout is two minutes. Set `VINGROUP_BROWSER_HEADLESS=1` only when no display is available.

## 9. Analysis Contract

The LLM receives numbered paragraphs and original source headings. It returns three groups:

- `sections`: contiguous coverage of the entire body;
- `people`: supported VIP or review candidates;
- `quote_changes`: direct quotations and suggested indirect wording.

Allowed section types are:

- `narrative`
- `quotation`
- `corporate_boilerplate`

Each distinct quotation must have its own quotation section. Reusable company profiles must be separated as corporate boilerplate. When a boundary occurs inside one paragraph, zero-based Unicode character offsets define the exact span.

## 10. Local Semantic Validation

After schema parsing, the application verifies:

- sections cover the complete article contiguously without gaps or overlaps;
- paragraph indices and character offsets are in bounds;
- quotation sections are referenced by quote-change records;
- original quotations are exact substrings of their sections;
- VIP evidence is an exact article substring;
- duplicate VIP names and quote IDs are rejected;
- review statuses have the required null proposal or explanation;
- proposed statuses contain both the original and indirect wording.

The application, not the LLM, computes each section's exact beginning and ending words.

If the provider reports a repairable structured-response error or local semantic validation fails, the analyzer sends the errors back to the same provider/model once. A second invalid result fails that article but does not stop remaining batch items.

## 11. Failure and Exit Behavior

Both crawl and analysis batches continue after individual item failures. At completion they print counts for selected, skipped, successful, and failed items.

- Exit code `0`: every attempted item succeeded or was already complete.
- Exit code `1`: at least one item failed, configuration is invalid, or a requested cached ID is unavailable.
- Exit code `2`: invalid CLI selection, such as combining `--id` with `--all` or supplying a nonnumeric ID.

Failures never trigger an automatic switch to another provider. A requested local analysis remains local.

## 12. Testing

Run the deterministic suite with:

```bash
uv run pytest
```

The normal suite mocks HTTP and every LLM provider. It covers URL security, redirects, content limits, extraction, listing discovery, date filtering, cached-source reuse, atomic output, registry migration, provider schemas, local endpoint separation, semantic retries, CLI selection, and output rendering.

The opt-in live extraction test requires an explicit URL:

```bash
VINGROUP_LIVE_URL='https://vingroup.net/.../bai-viet/...' \
  uv run pytest -m live
```

Normal tests do not call Vingroup or consume paid LLM API credits.

## 13. Module Map

- `cli.py`: command definitions and batch orchestration.
- `crawler.py`: secure HTTP fetching and Cloudflare browser fallback.
- `discovery.py`: validation and deduplication of supplied article URLs.
- `extractor.py`: Vingroup article-body and metadata extraction.
- `models.py`: strict source and analysis Pydantic models.
- `providers.py`: hosted and local LLM adapters.
- `analyzer.py`: provider-independent repair and semantic-validation loop.
- `validation.py`: section, VIP, and quotation invariants.
- `output.py`: source caches, Markdown rendering, analysis files, and atomic writes.
- `registry.py`: resumable crawl and analysis CSV state.
- `prompt.py`: provider-independent analysis instructions and numbered article input.

## 14. Known Operational Constraints

- Discovery depends on the current Vingroup listing and detail URL structures.
- Cloudflare can still reject browser automation based on network reputation or challenge policy.
- Local models vary substantially in JSON-schema adherence and Vietnamese-language quality.
- The OpenAI-compatible fallback can request valid JSON but cannot force every local server to honor the complete schema; local validation remains authoritative.
- Large articles and smaller local models may exhaust context windows or require longer inference timeouts.

When these constraints cause a failure, the original cached article remains available and previous successful analyses remain unchanged.

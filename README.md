# Vingroup Article Crawler

A Python 3.11 CLI that separately crawls Vietnamese and English Vingroup articles and analyzes cached source text with OpenAI, Anthropic, or Google Gemini.

## Setup

```bash
uv sync
uv run playwright install chromium
cp .env.example .env
```

Add the key for each provider you intend to use: `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, or `GEMINI_API_KEY`. Select defaults with `LLM_PROVIDER` and `LLM_MODEL`, or provider-specific variables such as `ANTHROPIC_MODEL`. OpenAI continues to default to `gpt-6-sol` when no model is configured; Anthropic and Gemini require an explicit model.

## Run

```bash
uv run vingroup-crawler crawl --from 2026-01-01 --to 2026-01-31
```

Dates use ISO `YYYY-MM-DD` format and are inclusive. `--to` defaults to today in `Asia/Ho_Chi_Minh`; `--from` defaults to 30 days before the effective upper bound. The crawl command never calls an LLM. It stores the exact extracted article model as JSON so later analyses do not need network access to Vingroup.

Analyze every cached article with a selected provider/model:

```bash
uv run vingroup-crawler analyze --provider openai --model gpt-6-sol --id 9080
uv run vingroup-crawler analyze --provider anthropic --model YOUR_CLAUDE_MODEL --id 9080 --id 9081
uv run vingroup-crawler analyze --provider gemini --model YOUR_GEMINI_MODEL --all
```

Repeat `--id` to analyze only specified cached articles. The command requires at least one `--id` unless `--all` is explicitly supplied; `--id` and `--all` cannot be combined. Use `--language`, `--from`, or `--to` as additional filters. Repeating the same provider/model skips completed results; add `--force` to redo them. Changing the model creates a separate result and always reads the cached original article.

Artifacts are named by Vingroup article ID and separated by language and format:

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
    ├── proposed/<provider>/<model-hash>/9080.md
    └── analysis/<provider>/<model-hash>/9080.json
```

The `markdown` and `crawled` artifacts are provider-independent source records. Each `proposed` artifact adds headings and highlights, while each analysis JSON includes `analysis_provider` and the exact `analysis_model`.

`crawled_articles.csv` tracks source acquisition. `analyses.csv` tracks every `(language, article ID, provider, model)` result and its files. Both processes continue after individual failures and exit nonzero when any item failed.

The crawler normally uses a lightweight HTTP request. If Vingroup returns a Cloudflare JavaScript challenge, it automatically opens the locally installed stable Chrome with a persistent local profile, falling back to Playwright's Chromium when Chrome is unavailable. Complete the challenge in that window if prompted; the crawler waits for up to two minutes. Set `VINGROUP_BROWSER_HEADLESS=1` only in environments where a visible browser is unavailable; Cloudflare may be less likely to accept a headless browser. Set `VINGROUP_BROWSER_CHANNEL=chromium` to skip the local Chrome preference.

## Test

```bash
uv run pytest
```

Normal tests are deterministic and network-free. To opt into the existing live extraction smoke test:

```bash
VINGROUP_LIVE_URL='https://vingroup.net/.../bai-viet/...' uv run pytest -m live
```

All providers return the same Pydantic schema and pass through the same local semantic validator and repair retry. OpenAI uses Responses Structured Outputs, Anthropic uses a forced schema tool, and Gemini uses a JSON response schema.

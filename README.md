# Vingroup Article Crawler

A Python 3.11 CLI that separately crawls Vietnamese and English Vingroup articles and analyzes cached source text with hosted or local LLMs.

For architecture, data flow, validation rules, registries, provider details, and troubleshooting context, see [PROJECT_GUIDE.md](PROJECT_GUIDE.md).

## Setup

```bash
uv sync
uv run playwright install chromium
cp .env.example .env
```

Add the key for each provider you intend to use: `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, or `GEMINI_API_KEY`. Select defaults with `LLM_PROVIDER` and `LLM_MODEL`, or provider-specific variables such as `ANTHROPIC_MODEL`. OpenAI continues to default to `gpt-6-sol` when no model is configured; Anthropic and Gemini require an explicit model.

Local analysis supports native Ollama and OpenAI-compatible servers such as LM Studio or vLLM. Start and manage the local server separately; the crawler does not download or launch models.

## Run

```bash
uv run vingroup-crawler crawl --url 'https://vingroup.net/en/news/detail/9087/green-gsm-officially-launches-all-electric-taxi-service-in-northern-mindanao-philippines'
uv run vingroup-crawler crawl --file article-urls.txt
```

The crawl command requires exactly one input: `--url` for one article, or `--file` for a UTF-8 text file with one article URL per line. It ignores blank lines and lines beginning with `#`. It never calls an LLM and stores each extracted article as JSON so later analyses do not need network access to Vingroup.

Only article URLs from the [Vietnamese news section](https://vingroup.net/vi/tin-tuc-su-kien) and [English news section](https://vingroup.net/en/news) are accepted. The crawler does not discover URLs from listing pages.

Analyze every cached article with a selected provider/model:

```bash
uv run vingroup-crawler analyze --provider openai --model gpt-6-sol --id 9080
uv run vingroup-crawler analyze --provider anthropic --model YOUR_CLAUDE_MODEL --id 9080 --id 9081
uv run vingroup-crawler analyze --provider gemini --model YOUR_GEMINI_MODEL --all
uv run vingroup-crawler analyze --provider ollama --model qwen3:14b --id 9080
uv run vingroup-crawler analyze --provider local-openai --model local-model --id 9080
```

Local defaults are `http://127.0.0.1:11434` for Ollama and `http://127.0.0.1:1234/v1` for OpenAI-compatible servers. Override them with `OLLAMA_BASE_URL` and `LOCAL_OPENAI_BASE_URL`. Local inference has a default 300-second timeout controlled by `LOCAL_LLM_TIMEOUT`.

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

The `markdown` and `crawled` artifacts are provider-independent source records. Each `proposed` artifact adds headings and highlights, while each analysis JSON includes `analysis_provider`, the exact `analysis_model`, and `analysis_endpoint`.

Both Markdown formats begin with YAML front matter containing `title`, `publication_date`, and `source_url`.

`crawled_articles.csv` tracks source acquisition. `analyses.csv` tracks every `(language, article ID, provider, model, endpoint)` result and its files. Both processes continue after individual failures and exit nonzero when any item failed.

The crawler normally uses a lightweight HTTP request. On a Cloudflare challenge it tries a headless browser without user interaction, waiting up to 30 seconds. Vingroup may still block automated access; in that case the command fails with a clear error. There is no reliable local bypass for a challenge enforced by the site. On macOS it uses the current default browser; elsewhere it uses Playwright Chromium. Set `VINGROUP_BROWSER_CHANNEL=chromium`, `chrome`, or `default` to override that choice. The selected browser must be Chromium compatible, and the crawler uses its own profile.

## Test

```bash
uv run pytest
```

Normal tests are deterministic and network-free. To opt into the existing live extraction smoke test:

```bash
VINGROUP_LIVE_URL='https://vingroup.net/.../bai-viet/...' uv run pytest -m live
```

All providers return the same Pydantic schema and pass through the same local semantic validator and repair retry. OpenAI uses Responses Structured Outputs, Anthropic uses a forced schema tool, Gemini uses a JSON response schema, Ollama receives the schema through its native `format` field, and local OpenAI-compatible servers use strict JSON schema with a JSON-object compatibility fallback.

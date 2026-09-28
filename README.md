# Vingroup Article Crawler

A Python 3.11 CLI that discovers Vietnamese and English Vingroup articles in a publication-date range, analyzes their structure, named VIPs, and direct quotations with OpenAI, then writes Markdown and JSON artifacts.

## Setup

```bash
uv sync
uv run playwright install chromium
cp .env.example .env
```

Add your OpenAI API key to `.env` (or export `OPENAI_API_KEY`). `OPENAI_MODEL` is optional and defaults to `gpt-6-sol`. The official OpenAI SDK reads environment-based API keys automatically.

## Run

```bash
uv run vingroup-crawler --from 2026-01-01 --to 2026-01-31
```

Both dates are required ISO dates and inclusive. The crawler walks the Vietnamese and English news listings, verifies each article's publication date from its detail page, and processes matching articles sequentially.

Artifacts are named by Vingroup article ID and separated by language and format:

```text
output/
├── crawled_articles.csv
├── vi/
│   ├── markdown/9080.md
│   └── json/9080.json
└── en/
    ├── markdown/9080.md
    └── json/9080.json
```

`crawled_articles.csv` records discovered, successful, and failed articles. Later runs skip successful IDs and retry failed ones. A batch continues after individual article failures, prints a summary, and exits nonzero when any article failed.

The crawler normally uses a lightweight HTTP request. If Vingroup returns a Cloudflare JavaScript challenge, it automatically opens the locally installed stable Chrome with a persistent local profile, falling back to Playwright's Chromium when Chrome is unavailable. Complete the challenge in that window if prompted; the crawler waits for up to two minutes. Set `VINGROUP_BROWSER_HEADLESS=1` only in environments where a visible browser is unavailable; Cloudflare may be less likely to accept a headless browser. Set `VINGROUP_BROWSER_CHANNEL=chromium` to skip the local Chrome preference.

## Test

```bash
uv run pytest
```

Normal tests are deterministic and network-free. To opt into the existing live extraction smoke test:

```bash
VINGROUP_LIVE_URL='https://vingroup.net/.../bai-viet/...' uv run pytest -m live
```

The analyzer uses the OpenAI Responses API with strict Pydantic Structured Outputs, following the [official Structured Outputs guide](https://developers.openai.com/api/docs/guides/structured-outputs).

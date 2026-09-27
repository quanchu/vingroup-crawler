# Vingroup Article Crawler

A Python 3.11 CLI that extracts one Vingroup article, analyzes its structure, named VIPs, and direct quotations with OpenAI, then writes the original article to Markdown and the analysis to JSON.

## Setup

```bash
uv sync
uv run playwright install chromium
cp .env.example .env
```

Add your OpenAI API key to `.env` (or export `OPENAI_API_KEY`). `OPENAI_MODEL` is optional and defaults to `gpt-6-sol`. The official OpenAI SDK reads environment-based API keys automatically.

## Run

```bash
uv run vingroup-crawler 'https://vingroup.net/.../bai-viet/...'
```

Pass one `https://vingroup.net/...` or `https://www.vingroup.net/...` article URL as the positional argument. On success, the command prints the two paths created under `output/` and exits. Existing output is preserved by adding a numeric suffix.

The crawler normally uses a lightweight HTTP request. If Vingroup returns a Cloudflare JavaScript challenge, it automatically opens the locally installed stable Chrome with a persistent local profile, falling back to Playwright's Chromium when Chrome is unavailable. Complete the challenge in that window if prompted; the crawler waits for up to two minutes. Set `VINGROUP_BROWSER_HEADLESS=1` only in environments where a visible browser is unavailable; Cloudflare may be less likely to accept a headless browser. Set `VINGROUP_BROWSER_CHANNEL=chromium` to skip the local Chrome preference.

## Test

```bash
uv run pytest
```

Normal tests are deterministic and network-free. To opt into the live extraction smoke test:

```bash
VINGROUP_LIVE_URL='https://vingroup.net/.../bai-viet/...' uv run pytest -m live
```

The analyzer uses the OpenAI Responses API with strict Pydantic Structured Outputs, following the [official Structured Outputs guide](https://developers.openai.com/api/docs/guides/structured-outputs).

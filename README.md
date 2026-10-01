# SEO Engine

Three tools in one app:

- **Content briefs:** takes the text of one web page and returns a brief telling the team how to
  make that page rank higher on Google and get cited by AI answer engines. It never rewrites
  the page.
- **Keyword gap:** compares your website with up to 4 competitor websites and shows the Google
  searches they appear for and you don't, which ones to target first, and where visits can be
  estimated. Plan, research and sources: [docs/KEYWORD-GAP-PLAN.md](docs/KEYWORD-GAP-PLAN.md).
- **Site snapshot:** one page about one website: link score and its history, popularity, where
  its pages show on Google, top pages, competitors, speed for real visitors, site age and
  technical basics. Free data only; every number names its source. Plan, research and sources:
  [docs/SITE-SNAPSHOT-PLAN.md](docs/SITE-SNAPSHOT-PLAN.md).

- What and why: [docs/PRD.md](docs/PRD.md)
- How: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- Current work: [PLAN.md](PLAN.md)

## Setup

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # then fill in keys
pytest
python scripts/check_live.py   # live check of every provider
```

## Run the app

```bash
make dev
```

This starts the backend (:8420) and the web app (:4280) together, installs the web packages on
the first run, and stops both on Ctrl+C. Open http://localhost:4280.

To run them in two terminals instead:

```bash
# terminal 1: backend on :8420
source .venv/bin/activate
uvicorn seo_engine.api.app:app --reload --port 8420

# terminal 2: frontend on :4280 (proxies /api to the backend)
cd web && npm install && npm run dev
```

Open http://localhost:4280. For a single-server setup, run `npm run build` in `web/` once;
the backend then serves the UI at http://localhost:8420.

## What it costs

Free data mode is the default: only DeepSeek LLM calls cost money (cents per brief, about one
cent per keyword gap analysis, under a cent per site snapshot).

| Data | Source | Cost |
| --- | --- | --- |
| Google results, People Also Ask | Serper.dev | 2,500 free credits (one-time); 1 credit per page of 10 results |
| Google results after that (briefs only) | Gemini grounding with Google Search | free tier |
| Demand | Bing Webmaster keyword API + Google autocomplete | free |
| Difficulty | computed from the top 10 + Tranco site ranks | free |
| Embeddings | Gemini | free tier |
| Site snapshot facts | Open PageRank (free key), Majestic Million, Tranco, Chrome UX Report (optional free key), RDAP, Wayback Machine | free |
| LLM | DeepSeek | paid, cents per brief |

Paid DataForSEO mode is available with `Settings(data_mode="dataforseo")`.

Serper credits per run:

- **Brief:** 2 credits per target phrase (the top 20 is 2 pages of 10), plus the phrase research
  checks. Since September 2025 Google returns 10 results per request.
- **Keyword gap:** about 2 credits per keyword checked: about 120 for the default 60
  keywords, plus up to 40 for the second pass (up to 20 related searches where competitors
  rank; `second_pass_keywords`). Fewer when results are cached the same day. Keyword gap **needs** `SERPER_API_KEY`:
  Gemini grounding gives no positions, so it cannot replace Serper here. Bing is optional; without
  it, search numbers show as unknown.
- **Site snapshot:** about 2 credits per keyword checked: up to 60 for the default 30. No second
  pass. Without `SERPER_API_KEY` the snapshot still shows the site facts and technical checks.
  `OPENPAGERANK_API_KEY` and `CRUX_API_KEY` are optional; without them those tiles say
  "not set up".

# SEO Engine

Takes the text of one web page and returns a brief telling the team how to make that page rank
higher on Google and get cited by AI answer engines. It never rewrites the page.

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
# terminal 1: backend on :8420
source .venv/bin/activate
uvicorn seo_engine.api.app:app --reload --port 8420

# terminal 2: frontend on :4280 (proxies /api to the backend)
cd web && npm install && npm run dev
```

Open http://localhost:4280. For a single-server setup, run `npm run build` in `web/` once;
the backend then serves the UI at http://localhost:8420.

## What it costs

Free data mode is the default: only DeepSeek LLM calls cost money (cents per brief).

| Data | Source | Cost |
| --- | --- | --- |
| Google results, People Also Ask | Serper.dev | 2,500 free queries (one-time) |
| Google results after that | Gemini grounding with Google Search | free tier |
| Demand | Bing Webmaster keyword API + Google autocomplete | free |
| Difficulty | computed from the top 10 + Tranco site ranks | free |
| Embeddings | Gemini | free tier |
| LLM | DeepSeek | paid, cents per brief |

Paid DataForSEO mode is available with `Settings(data_mode="dataforseo")`.

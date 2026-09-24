# CLAUDE.md

## What this project is

An engine that takes the text of one web page and returns a brief telling the team how to make that page rank higher on Google and get cited by AI answer engines. The brief contains target search phrases, title tag options, a meta description, must-cover topics, gaps, suggested headings, an intent warning, a coverage score, and a suggested SEO draft of the page. The draft uses only facts from the page; anything it cannot know is a visible `[ADD: …]` placeholder for the team to fill. The team reviews and publishes; the engine never publishes or silently changes the page.

Internal Gurzu tool first, built to product quality so it can become a product later.

## Read before working

- `docs/PRD.md`: what the engine must do and why. Read before adding or changing any feature.
- `docs/ARCHITECTURE.md`: agents, tools, algorithms, thresholds and data sources. Read before changing any tool, agent or formula.
- `PLAN.md`: current phase and next tasks. Work on the first unchecked task unless told otherwise, and tick tasks when done.

## Stack

- Python 3.12, Pydantic v2 for every input and output
- httpx for API calls, trafilatura for page cleaning, a headless browser only as fallback
- Free data by default (only LLM calls cost money): Serper.dev free credits for Google results, Gemini grounding with Google Search as fallback, Google autocomplete, Bing Webmaster keyword API for demand, Tranco list for site strength. DataForSEO is an optional paid provider (`data_mode = "dataforseo"`).
- DeepSeek for LLM calls, Gemini for embeddings (first picks; bake-off may change them)
- FastAPI backend (`src/seo_engine/api/`), React + TypeScript + Vite frontend (`web/`)
- LangGraph (phase 3 workflow; phase 2 uses a plain tool-calling loop)
- pytest for tests

## Folder layout

```text
src/seo_engine/
  models.py        Pydantic models (Run, Phrase, Page, TopicCount, Gap, Brief)
  config.py        run settings and defaults
  providers/       one interface per data source (search, keywords, fetcher, llm, embeddings)
  tools/           the 5 tools
  pipeline.py      fixed order: tools -> brief writer -> snippet check (serves the API)
  brief.py         Brief Writer LLM call + code-filled brief assembly
  api/             FastAPI app and file-based run store
  agent/           current: one agent + instructions using the 5 tools
  workflow/        only if evaluation requires it: LangGraph graph with more agents
evals/             20 test pages + hand-written gold briefs + run_evals.py
scripts/           check_live.py: live smoke test of every provider
web/               React + TypeScript (Vite) UI
runs/              saved runs from the API, git-ignored
tests/             unit tests, one file per tool
cache/             daily cache, git-ignored
```

## Commands

```bash
pip install -e ".[dev]"      # install
pytest                       # unit tests
python evals/run_evals.py    # quality check against the gold briefs
python scripts/check_live.py # live check of every provider (only DeepSeek costs, fractions of a cent)
uvicorn seo_engine.api.app:app --reload --port 8420   # backend on :8420
cd web && npm install && npm run dev      # frontend on :4280 (proxies /api)
```

## Rules

1. **Code counts, AI reads and writes.** Counting, scoring, fetching and rule checks are always plain code. LLMs only name topics, classify, judge and write text.
2. **Pydantic everywhere.** Every tool input and output, and every LLM response, is a validated Pydantic model. On a bad LLM response, retry once, then raise.
3. **Providers behind interfaces.** Tools never call a vendor API directly; they go through `providers/`. Switching vendors must change one file.
4. **Cache by day.** Every search, keyword and page-fetch call is cached by (inputs, date). Never pay twice for the same call on the same day.
5. **Log cost.** Every paid call adds its cost to `Run.cost_usd`.
6. **No invented facts.** The brief may only contain phrases, topics, counts and gaps that exist in the run state. Gaps are named, never filled with made-up facts. The suggested draft may only state facts found in the page text; every other specific (prices, numbers, names, integrations) is an `[ADD: …]` placeholder.
7. **One difficulty source per run.** In free mode, difficulty is computed by our code from the top 10 (`difficulty.py`); in DataForSEO mode, DataForSEO difficulty only. Never mix the two in one run.
8. **Respect robots.txt** when fetching competitor pages.
9. **Settings, not code.** Depth, cost and behaviour (phrases, pages, samples, country, site strength) come from `config.py`, never hard-coded.
10. **One agent until evaluation says otherwise.** The current design is one agent with 5 tools. Add an agent only when an evaluation result shows a specific problem it fixes (see `docs/ARCHITECTURE.md` §2a), and update that file first. Max 10 tools per agent, aim for 3 to 6.
11. **Free data first.** The only paid calls are LLM calls. Data sources must be free or keyless unless a setting opts into a paid provider.

## Style

- Small, pure functions; type hints everywhere.
- One test file per tool; tests must not hit paid APIs (use recorded fixtures).
- Secrets only in `.env`, never committed.

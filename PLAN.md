# PLAN

Work top to bottom. Tick a task only when its "done when" is true. Details for every task are in `docs/ARCHITECTURE.md`. Live smoke test: `python scripts/check_live.py`.

## Phase 0: Groundwork (week 1)

- [x] Create repo skeleton from the folder structure in `docs/ARCHITECTURE.md` §10, with `pyproject.toml`, `.env.example`, `.gitignore` (cache/, .env)
  - Done when: `pip install -e ".[dev]"` and `pytest` run cleanly on an empty test
- [x] Write `models.py` and `config.py` from `docs/ARCHITECTURE.md` §9
  - Done when: models import and validate a sample `Run`
- [ ] Get free keys (Serper.dev, Gemini, Bing Webmaster) and a small DeepSeek top-up; add to `.env` (free data mode, `docs/ARCHITECTURE.md` §4a)
  - Done when: `python scripts/check_live.py` passes for serp, grounding, bing, autocomplete, llm, embed, fetch
  - Status: DeepSeek and Gemini keys work (llm, embed, grounding, autocomplete, tranco, fetch pass); Serper and Bing keys still to add
- [ ] Build the eval set: 20 real pages from Gurzu and client sites (include at least 8 landing/product pages) in `evals/pages/`, one `.txt` each, first line `# site: <site> | type: <page type>`
  - Done when: 20 text files exist
- [ ] With the team, write a good brief for each page in `evals/gold_briefs/<same-name>.json` (`Brief` format): 1 to 3 phrases, 2 titles, 1 description, must-cover topics, gaps, headings, intent warning. Write them before seeing engine output.
  - Done when: 20 gold briefs exist

## Phase 1: Tools (weeks 1 to 2)

- [ ] `providers/search.py`: `SearchProvider` interface + DataForSEO implementation, daily cache, cost logging
  - Status: built and unit-tested on synthetic fixtures; optional paid mode, live check only if funded
- [ ] Free data providers: `serper.py`, `gemini_search.py` (grounding fallback), `autocomplete.py`, `bing.py`, `tranco.py`, and `difficulty.py` (§4a, §5.1)
  - Done when: a full keyword research run costs $0 in data calls and every phrase shows its demand evidence and computed difficulty
  - Done when: returns top N with page type and SERP features; second identical call same day costs nothing
- [ ] `providers/keywords.py`: volume, difficulty, intent (bulk), autocomplete, `ranked_keywords`
  - Status: built and unit-tested (30 candidates -> 1 bulk call); optional paid mode
  - Done when: 30 candidates return metrics in one bulk call
- [ ] `providers/fetcher.py`: httpx + trafilatura, robots.txt check, length check, headless fallback
  - Status: built and unit-tested; verified live on one page; needs the 20 eval pages
  - Done when: clean main text for all 20 eval pages and 20 competitor pages, including landing pages
- [x] `tools/serp_top.py`
- [ ] `tools/keyword_research.py`: four candidate sources, filter, cluster (>= 3 shared URLs), rank (`docs/ARCHITECTURE.md` §5.1)
  - Status: built and unit-tested offline; needs team rating on 10 eval pages
  - Done when: team rates most chosen phrases for 10 eval pages as usable; no phrase under the volume floor
- [ ] `tools/competitor_analysis.py`: five filters (§5.2) + Page Reader (small model) returning topics and page type
  - Status: built and unit-tested offline; needs live run on 10 phrases
  - Done when: kept/dropped lists with reasons for 10 phrases; valid JSON every time
- [ ] `tools/topic_coverage.py`: embedding merge, passage-level coverage, buckets (§5.3), score (§5.5)
  - Status: built; matches a hand count on a synthetic case; needs hand count on 3 real phrases and threshold tuning for Gemini embeddings
  - Done when: counts match a hand count on 3 phrases
- [x] `tools/snippet_check.py`: pixel width and length checks
  - Done when: known long and short titles pass and fail correctly
- [ ] Unit tests for every tool using recorded fixtures (no paid calls in tests)
  - Status: 45 tests green on synthetic fixtures; replace with recorded fixtures and log cost of one full run
  - Done when: `pytest` green; cost per full run logged and known

## App: API and web UI

- [x] `pipeline.py` + `brief.py`: fixed order over the 5 tools, Brief Writer, snippet check with one rewrite (`docs/ARCHITECTURE.md` §2c)
  - Done when: a fake-provider test produces a valid `Brief` whose counts all come from run state
- [x] FastAPI backend (§12): runs in background, file store, health and defaults endpoints
  - Done when: API tests pass with fake providers
- [x] React UI: new-brief form, run history, live progress, brief view (phrases, titles with pixel bars, description, checklist, must-cover, gaps, headings, competitors, score arithmetic), copy as Markdown
  - Done when: `npm run build` passes and a live run renders end to end
  - Status: live run on 24 Sep 2026 rendered end to end (example page: 3 phrases, 6 competitors, 8 must-cover, $0.025, ~1.6 min)

- [x] Suggested content (PRD §5.9): Draft Writer step with code checks (phrase in H1 and first 100 words, density, length, sections, FAQ) and `[ADD: …]` placeholders; gap-question relevance filter; stricter phrase fit check
  - Status: live emitii.com run 24 Sep 2026: 1,455-word draft, all SEO checks passed, 13 placeholders, no invented facts, $0.029 total
- [x] Readable report (PRD §5.10): `GET /api/runs/{id}/report.docx`, Word document laid out like the action plan with placeholders highlighted
- [ ] Eval: team reviews 5 drafts for invented facts and tone before relying on them

## App: Keyword Gap (branch `feature/keyword-gap`)

Our domain vs 1 to 4 competitors: keyword positions, estimated visits and top keywords to add. Steps, research and sources: `docs/KEYWORD-GAP-PLAN.md` (each step waits for owner approval).

- [x] Step 0: docs (PRD §5.11, ARCHITECTURE §13), `GapSettings`, keys, live tests (Serper page billing, AI Overview field, Bing)
  - Status: 1 credit per page of 10; `num: 20` returns only 10; no AI Overview field; Bing works. Fixed `bing.py` counting rows instead of weeks (rare phrases were 4-10x too high)
- [x] Step 1: site reader (`providers/sitemap.py`)
  - Status: 58 tests; live: gurzu.com 30 pages 6.4 s, emitii.com 6 pages 8.3 s (browser for JS homepage), moxo.com 30 pages 2.9 s. Also fixed: robots.txt now RFC 9309 (Protego); too_short pages cached when no browser retry
- [x] Step 2: keyword discovery (`tools/site_keywords.py`)
  - Status: tests in `tests/test_site_keywords.py`; live emitii.com vs moxo.com + clinked.com: 60 keywords, 26.8 s, $0.0044; same-day re-run identical at $0 (`DailyCachedLLM`). Business fit (0-3) filters before the Google check. Fixed: Bing ThrottleUser handling, API key redacted from Bing errors. Bing has numbers for only ~2% of B2B keywords (owner: free, honest labels)
- [x] Step 3: rank check with Serper pages (`tools/rank_check.py`, fixes `serper.py` `num: 20`)
  - Status: 17 tests; live: 60 keywords, 25.7 s, 120 credits (as calculated); ~19 results per keyword (pages hold ~9). Briefs now get 20 results for 2 credits (were 10 for 1)
- [x] Step 4: metrics (demand, rough Google estimate, difficulty band, intent, visits, clusters)
  - Status: `tools/keyword_metrics.py`, 16 hand-calculated tests; live difficulty hand check matches (25). Live: visits 0 or unknown for all sites on this set (Bing numbers only for broad keywords no site ranks for)
- [x] Step 5: gap categories and the order of keywords to add (`tools/keyword_gap.py`)
  - Status: 16 hand-calculated tests; live: 5 keywords to add for emitii.com (agency client portal cluster: both competitors rank #3-#8). 49 of 60 checked keywords had no site on page 1-2 (G13, possible second pass later)
- [x] Step 6: `gap_pipeline.py` and `/api/gaps` endpoints
  - Status: 27 tests (pipeline, CSV injection guard, API lifecycle, SSRF guard); shared `JsonStore` + background runner with briefs; live API run 3.1 s, 0 credits (cache)
- [x] Step 7: web UI: navigation, form, progress
  - Status: sidebar tool switch, `NewGap`/`GapView`/`GapResults`; build + lint pass; screenshots checked (light, dark, 390 px, running, failed). Domain colours validated with the dataviz palette validator. No cancel for a running analysis (G14)
- [x] Step 8: web UI: results dashboard
  - Status: site cards, overlap bars (instead of a 5-set Venn), top-keyword cards, sortable/filterable table with expandable Google results, competitor panels, method note; browser-checked light/dark/390 px, no console errors
- [ ] Step 9: live run, 5 positions checked by hand, guide chapter
- [x] Review round (3 reviewers, 52 findings) fixed: SSRF guard on every request, sitemap request cap, gzip bomb, transient robots failures not cached, www kept, overlapping sites rejected, atomic cache, UI paging/polling/a11y fixes, docs
- [x] G13 low yield: second pass (related searches where competitors rank; live Emitii: 10 more keywords, 5 with a site on page 1-2) and suggested competitors (live Gurzu: scnsoft.com, appinventiv.com, globant.com)
- [x] Second review round: DNS-rebinding-safe connections, `is_global` address check, browser traffic served by the guarded client (offline test: 0 connections to a blocked server), WebSocket hang and preconnect leak fixed, brand and second-pass fixes
- [ ] G14: a Cancel button for a running analysis (not started; owner decision)

## App: Site Snapshot (branch `feature/keyword-gap`)

Plan, research and owner decisions: `docs/SITE-SNAPSHOT-PLAN.md`.

- [x] Step 0: docs, `SnapshotSettings`, free live tests (Open PageRank key added; Chrome UX Report skipped for now)
- [x] Step 1: providers (Open PageRank, Majestic Million, CrUX, domain dates), 23 tests
- [x] Step 2: technical checks (10 checks, live on 4 sites)
- [x] Step 3: snapshot tool and pipeline (live on gurzu.com; list pages now skipped)
- [x] Step 4: API and store (`/api/snapshots`)
- [x] Step 5: web app (form, progress, results page, link-score chart)
- [x] Step 6: review (24 findings fixed), guide chapter 21, docs
- [ ] Owner: hand check of 3 positions and the site age (list in `docs/SITE-SNAPSHOT-PLAN.md`, Step 6)
  - Status: live gurzu.com vs 4 competitors: 99 s, 120 credits, $0.011; 2 keywords to add, 57 of 60 keywords with no site on pages 1-2 (G13). Guide chapter 20 done (checker: All good). Waiting: owner's hand check of 5 positions

## Web app: UI redesign "Clearview" (branch `feature/keyword-gap`)

Plan, research and owner decisions: `docs/UI-REDESIGN-PLAN.md`.

- [x] Step 0: tokens (light and dark), top bar with tool tabs, history tables on the start pages
- [x] Step 1: Site Snapshot in the new design
- [x] Step 2: Keyword Gap in the new design
- [x] Step 3: Briefs in the new design
- [x] Step 4: QA pass, keyboard and contrast checks, code review (15 problems fixed), guide chapter 22
- [ ] Owner: look through the app (`make dev`) and commit when happy

## Phase 2: One-agent prototype (weeks 3 to 4)

- [ ] `agent/`: one agent with the 5 consolidated tools and clear instructions; outputs a `Brief`
  - Done when: produces a brief for all 20 eval pages
- [ ] `evals/run_evals.py` checks, per page:
  - phrases: overlap with gold + team rating; none below the volume floor
  - must-cover topics: overlap with gold
  - gaps: code re-counts each gap; none covered by 20%+ of competitors
  - snippet: title width and description length pass
  - cost and time: within budget
- [ ] Model bake-off: 2 to 3 judgment models and 2 bulk models (shortlist in §6); pick cheapest within a few points of best
- [ ] Embedding bake-off on 100 hand-labelled passage/topic pairs
- [ ] Read every transcript: note skipped steps, wrong tool choices, inconsistent runs
- [ ] Stability test: same page run 3 times; phrases and must-cover lists should match

### Gate: blind review

- [ ] Team compares our briefs with a paid SEO tool's briefs on 10 pages, blind: mix both, hide the source, ask which brief they would rather act on, record the choice and one reason per page
  - If ours wins or ties: continue
  - If the paid tool wins: stop building, use the paid tool plus our phrase discovery
  - If transcripts show skipped steps or instability: go to phase 3
  - If one agent is reliable and cheap: phase 3 is optional

## Phase 3: Add agents only where the evaluation shows a problem (weeks 5 to 7)

Only do the tasks below that match a problem found in phase 2. Skip the rest.

- [ ] If steps are skipped or order changes: `workflow/` LangGraph state graph (§2b), parallel lanes per phrase, checkpointer, retry policy
  - Done when: killing a run midway resumes without repeating paid calls
- [ ] If phrase choice is weak: Query Scout agent (3 tools, max 3 rounds)
- [ ] If gaps are invented or missed: Gap Hunter agent (2 tools, max 3 rounds; demand evidence required)
- [ ] If brief quality is uneven: Brief Writer + Brief Checker loop (checker from a different model family; max 2 rewrites)
- [ ] Approval pause after node 1 when `phrase_selection = "approval"`
- [ ] Budget guard: reduce depth on time/cost limit, mark "reduced depth"
- [ ] AI citation sampling (§5.6): Gemini grounding + OpenAI/Anthropic web search; merged, tagged pool
  - Done when: citation frequency reported for 5 phrases with sample counts
- [ ] Re-run evals and blind review

## Phase 4: Search Console mode (after CEO approval)

- [ ] Read queries and positions for a page from Search Console
- [ ] Replace phrase discovery step A with positions 4 to 20 sorted by impressions
  - Done when: briefs for 5 existing Gurzu pages use real queries

## Later

- [x] URL input (fetch content from a link): "Import" in the web UI fills the text box for review; landing pages use a visible-text extractor and headless Chrome
- [ ] MCP server exposing the tools (for Emitii and other agents)
- [ ] Question tree view, fact interview, winnability badge, freshness gaps
- [ ] FastAPI service for other teams

## Pending decisions

- [ ] CEO approval: Search Console input mode
- [ ] Confirm AI sampling stays in phase 3
- [ ] Approve one-month paid SEO tool subscription as benchmark
- [ ] Repo and project name

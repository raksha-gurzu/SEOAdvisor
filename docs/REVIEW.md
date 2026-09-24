# Review: SEO Advisor (engine, API and web UI)

Reviewer role: SEO/GEO specialist, staff engineer and product designer. Review date: 24 September 2026.
Scope: `docs/PRD.md`, `docs/ARCHITECTURE.md`, `PLAN.md`, `README.md`, all code in `src/seo_engine/`, `tests/`, `web/src/`, `scripts/check_live.py`, the 7 stored runs in `runs/` and the day's provider cache in `cache/2026-09-24/`. Checks run: `pytest` (70 passed, offline), `ruff check` (clean), `npm run build` (passes). No paid calls were made.

How to read this: every finding has an ID (M = methodology, A = accuracy and trust, E = engineering, P = product and UX, PL = plan), a severity, evidence, why it matters, the change to make, the effort (S = under a day, M = 1 to 3 days, L = a week or more) and sources. Numbers in square brackets point to §7 References.

---

## 1. Executive summary

**Overall:** the engineering foundation is better than most prototypes at this stage (clean typed code, providers behind interfaces, code does the counting, honest `[ADD: …]` placeholders, a usable UI). But the **quality of the SEO advice is not yet trustworthy**, mainly because free mode is running without the two data sources it was designed around (a ranked Google SERP and a demand number), and the pipeline has no guard that notices when its output is broken.

- **Phrase choice is driven by noise, not demand.** In all 7 stored runs every phrase has volume 0 and "autocomplete" as its only demand evidence, so the demand term is a constant (`log10(2)`) and the "fit" term sits in a narrow 0.85 to 0.87 band. Ranking therefore reduces to computed difficulty, which is itself computed from a median of **5** pages that Gemini happened to cite (115 grounded calls on 24 Sep; median 5 pages, one call returned 0).
- **A critical bug made a zero-result search the main phrase for emitii.com.** "easy to use project management software" had 0 SERP items, so its difficulty became 0, its winnability 1.0, and the UI labelled it "Low competition" (run `363329bb0c2a`). The same empty result is cached for the whole day.
- **The noise filter can silently wipe out the brief.** In run `b889d43ab5ca` the LLM marked 151 of 152 topics as noise: 0 must-cover topics, 0 gaps, score 0, yet the run finished as "done" with a 7/8 checklist. In `f54961456cdb` 134 of 137 topics were removed, so the score of 84 rests on 2 topics.
- **Runs are not stable.** The same page text produced completely different phrase sets 4 minutes apart (`363329bb0c2a` vs `890ecbac1bf3`, and `2eb18fea7af3` vs `31f42fcdfc63`). Some code changed between runs that day, so this needs a controlled repeat, but nothing in the design makes runs repeatable (no LLM cache, no fixed seeds, near-tied scores).
- **Topic and gap advice drifts off-meaning.** Pooling three loosely related phrases brings in competitors about office decoration, hiring virtual assistants and enterprise AI governance, and gap questions such as "how to set up your workspace in photoshop" reach the brief. The suggested draft then asks the team to fill placeholders for features the product may not have (SSO, portfolio views, custom bots), which pushes towards search-engine-first content that Google's helpful-content guidance warns against [1][2].
- **Data provenance is mislabelled, and the Gemini fallback likely breaks its terms.** Pages cited by Gemini are shown as `google#N` and described as "pages that rank for your searches"; autocomplete presence is shown as "People search this on Google". The Gemini API terms forbid caching or analysing grounded results and require showing Google's Search Suggestions with them [3]. The SERP fallback caches and analyses grounded results and does not show the suggestions.
- **Engineering gaps that matter for trust:** runs are not linked to a code version (the first commit only landed during this review), no logging or LLM transcripts, no time or cost budget enforcement, any single provider error fails the whole run, and tests use only synthetic fixtures that would not have caught any of the live failures above.
- **The plan is out of order.** Features (draft, report, URL import) have moved ahead of the eval set and gold briefs, which do not exist yet. The phase 2 "one agent" prototype is unlikely to help; the fixed pipeline is the right backbone [4].

**Top 5 things to do next**

1. **Add hard quality gates and record the code version in each run** (A4, M1, M5, E1): no difficulty from fewer than 8 results; cap LLM noise at a share of topics; mark a run "needs review" when must-cover < 3, competitors < 5, or SERP data came from grounding. Done when the 7 stored runs would all be flagged or fixed by replay.
2. **Get real SERP and demand data for free** (M2, M3, A13): add the Serper key now (2,500 free queries is about 150 runs at the measured ~16 search calls per run), add the Bing Webmaster key, cut SERP calls per run, and stop using Gemini grounding as a cached SERP substitute (its terms forbid caching and analysing grounded results). Push the Search Console mode forward for existing pages (PL3).
3. **Build the eval set and a replay harness before any new feature** (PL1, §5): 20 pages, gold briefs written blind, raw provider responses frozen so every eval re-run costs only LLM tokens (about $0.60 for 20 pages).
4. **Make phrase and competitor selection meaning-aware and stable** (M6, A1): score phrases per their own SERP (do the ranking pages sell what we sell?), keep competitors per main phrase, cache LLM answers by day, and let users lock phrases so re-runs compare like with like.
5. **Verify the draft in code, and reframe it** (A2, M11, A3): check every sentence of the draft against the page text (number and name matching plus a second-model support check), drop the word-count target, let the team mark topics "doesn't apply to us", and clean mock UI text out of URL imports.

Findings by severity: **Critical 4, High 19, Medium 20, Low 10** (53 in total).

---

## 2. What's working well

Keep these; they are the right calls and several are better than common commercial tools.

- **"Code counts, AI reads and writes" is really implemented.** Counts, buckets, score, checklist and gaps are computed from run state (`brief.py`, `topic_coverage.py`); the LLM only names, labels and writes. This is the right architecture for trust.
- **Passage labelling by the LLM instead of embedding thresholds** was a good, measured decision (ARCHITECTURE §5.3 C records the overlap that made thresholds unusable). Few teams measure this before choosing.
- **Pydantic everywhere, with one validation retry** (`providers/llm.py:150-170`), and providers behind small `Protocol` interfaces with a daily cache. Swapping Serper, Gemini or DataForSEO is a one-file change, as intended.
- **`[ADD: …]` placeholders instead of invented facts.** In the four stored drafts, no number appears that is not in the page text (checked by script). Placeholders are highlighted in the UI and the .docx.
- **Explainability:** kept and dropped competitors with reasons, the score arithmetic, candidate phrases with reasons, and per-topic counts are all visible in Details. This is what makes the advice auditable.
- **Plain-language UI and report.** The action plan ("Target these searches", "Add these missing topics", "Answer questions others don't") is understandable to non-SEO users; the SERP preview with pixel-width check is a nice touch.
- **Sensible safety basics:** robots.txt is checked, keys never leave the backend (`/api/health` returns booleans only), the SPA route refuses paths outside `web/dist`, run IDs are validated before touching the file system.
- **Honest scoping in the PRD:** "No guaranteed top spot", "meta description drives clicks, not rank", "keywords meta tag is ignored", "Google states no special optimization is needed for AI Overviews" all match Google's documentation [5][6][7][8].
- **Cheap:** ~$0.02 to $0.04 per run as logged (the price table needs a check, E10) is well inside any reasonable budget.

---

## 3. Findings

### 3.1 Methodology (SEO and GEO)

#### M1. Empty or tiny SERP gives difficulty 0 and wins phrase selection
- **Severity:** Critical
- **Evidence:** `difficulty.py:45-46` returns `score=0` when there are no results; `keyword_research.py:346` turns difficulty 0 into winnability 1.0. Run `363329bb0c2a`: cluster `easy to use project management software`, `total_volume 0, difficulty 0, winnability 1.0`, SERP with 0 items, chosen as the **main** phrase for emitii.com and shown as "Low competition". Across the day's cache, grounded searches returned a median of 5 pages (min 0).
- **Why it matters:** a broad head term, which on a real Google top 10 is very likely contested by large software brands, was recommended as the easiest. This is the single most damaging kind of error for an SEO tool, and it is invisible to the user.
- **Change:** treat difficulty as unknown when fewer than `min_serp_items` (setting, start at 8) results exist; never let unknown difficulty pass the ceiling; show "not enough data" in the UI. Do not cache empty search responses for the whole day (cache them for minutes, or not at all). Add a regression test with an empty SERP.
- **Effort:** S
- **Sources:** none needed (logic bug).

#### M2. Free mode has no real demand signal, so ranking is driven by noise
- **Severity:** Critical
- **Evidence:** all 20 chosen phrases across the 7 runs have `volume 0, volume_source "autocomplete"` (Bing key not set). `keyword_research.py:345` makes demand `log10(2 + 0)` = 0.301 for every cluster. `fit` values sit between 0.85 and 0.87 (Gemini cosine similarity is compressed). So `score = fit × demand × winnability` is effectively `winnability`, i.e. `1 − computed difficulty`. Every candidate that appears in autocomplete passes the demand gate (`keyword_research.py:258, 266` mark all autocomplete suggestions as searched).
- **Why it matters:** Google says autocomplete predictions "reflect real searches" but are shaped by language, location, trending interest and policy removals, and that autocomplete "is not simply displaying the most common queries" and should not be compared with Trends [9]. "In autocomplete" means "someone searches this", not "enough people search this to be worth a page". The engine cannot currently tell a phrase with 20 searches a month from one with 20,000.
- **Change (all free):**
  1. Add the Bing Webmaster key now (free; needs one verified site) [10]. Treat Bing impressions as a relative signal, as the code already notes.
  2. Use an ordinal autocomplete signal instead of yes/no: position in the suggestion list and the shortest prefix that surfaces the phrase (a phrase suggested after typing 2 words is more common than one that needs 5). Cheap, same endpoint, cached.
  3. Apply for the Google Trends API alpha (announced July 2025, still limited to accepted testers in September 2026; it returns relative interest, not absolute volume) [11]. If access is granted, use it to compare candidate phrases; otherwise skip.
  4. For existing pages, use Search Console queries and impressions (free, real Google data) — see PL3 [12].
  5. When no numeric demand exists, stop multiplying by a constant: rank by fit and sense-match first (M6), then difficulty, and say "demand unknown" in the brief.
- **Effort:** M
- **Sources:** [9], [10], [11], [12]

#### M3. Gemini grounding is used as if it were Google's ranked top 10
- **Severity:** Critical
- **Evidence:** Serper has no key, so every run used `gemini-grounding` (`FallbackSearch`, `deps.py`). The provider's own docstring says it "is not the ranked organic list, has no People Also Ask, and titles are often just the domain" (`gemini_search.py:1-6`). Median 5 cited pages per call. Yet this list feeds: computed difficulty (M1, M4), SERP-overlap clustering (only 2 multi-member clusters in 7 runs, both trivial variants), intent verdict, competitor selection, and gap evidence. Gemini's own `webSearchQueries` are stored as `related_searches` and later shown as "related search" demand evidence (`gemini_search.py:381-387`), e.g. gap "project management software for marketing agencies" with evidence "related search: project management tool for agency" in run `890ecbac1bf3`.
- **Why it matters:** grounding returns the sources a model chose to cite for its answer, not Google's ranking [13]. Difficulty from 5 cited pages and clustering by shared cited URLs are not meaningful. Caching and analysing grounded results is also prohibited by the Gemini API terms (see A13) [3].
- **Change:**
  1. Put the Serper key in `.env` and make it the default path. At ~16 search calls per run (115 grounded calls for 7 runs plus live checks on 24 Sep), 2,500 free queries is roughly 150 runs; cut calls per run (E4) to stretch this further [14].
  2. Remove grounding from the SERP fallback chain (A13). When Serper credits run out, the run should stop with a clear message rather than silently degrade. Until that change lands: do not compute difficulty or clusters from grounding, label every competitor "cited by Gemini", and mark the run "reduced confidence".
  3. Stop labelling Gemini's search queries as "related searches"; call them "AI search queries" and never use them as the only evidence for a gap.
  4. If a second ranked source is needed after Serper's free credits: Brave Search API gives about $5 of free credit a month (roughly 1,000 queries), but since February 2026 it needs a card and is not Google [15]; Serper top-ups cost about $1 per 1,000 queries [14]. Both are owner decisions (§6).
- **Effort:** S (key + labels), M (fallback provider)
- **Sources:** [13], [3], [14], [15]

#### M4. Computed difficulty measures domain popularity, on a scale the ceilings were not set for
- **Severity:** High
- **Evidence:** `difficulty.py` maps each result's domain to a strength from its Tranco rank and averages. Tranco averages five domain lists over 30 days (Chrome UX Report, Cloudflare Radar, Farsight, Umbrella and Majestic); four measure traffic or DNS popularity and only Majestic counts linking subnets [16]. It says nothing about the specific ranking page. `tranco.py:candidates()` falls back to parent domains, so any page on a large platform (a `*.medium.com` blog, a `*.blogspot.com` site, a GitHub Pages site) gets the platform's strength. The ceilings `{"new": 30, "growing": 45, "established": 60}` are documented as "Difficulty ceiling (DataForSEO, tune)" (ARCHITECTURE §5.1) but are applied to the computed scale. The same thresholds decide the "Low / Medium / High competition" labels in the UI (`format.ts: competition()`).
- **Why it matters:** commercial difficulty scores are built from the link profiles of the top-ranking pages (Ahrefs KD uses the referring domains of the top 10 [17]); Tranco is a reasonable free proxy for domain strength, but mixing platform domains in and using uncalibrated cut-offs makes "Low competition" unreliable.
- **Change:**
  1. Use the Public Suffix List (e.g. `tldextract` with a bundled snapshot) and a small list of user-content platforms (medium.com, blogspot.com, substack.com, github.io, notion.site, wordpress.com) that count as small sites regardless of parent rank.
  2. Add a free link-based signal: Open PageRank (computed from Common Crawl's web graph, free for 30,000 domains a month, now run by Keywords Everywhere) or the quarterly Common Crawl host- and domain-level rank files (harmonic centrality and PageRank) loaded into the same SQLite store as Tranco [18][19]. Blend it with Tranco, document the formula, keep one difficulty source per run (rule 7) by treating the blend as the single computed source.
  3. Add cheap page-level signals already available from the SERP: how many top-10 titles contain the exact phrase, and how many are home pages vs deep pages (both correlate with how targeted the competition is).
  4. Calibrate the ceilings on the eval set against the team's judgement ("could a new site rank here?") and show difficulty as a band with a confidence note.
- **Effort:** M
- **Sources:** [16], [17], [18], [19]

#### M5. The LLM noise filter can remove almost every topic, and nothing notices
- **Severity:** Critical
- **Evidence:** `topic_coverage.py:261-273` sends all non-brand topics to `NOISE_SYSTEM` and marks as noise whatever comes back. Run `b889d43ab5ca`: 151 of 152 topics → noise (reasons such as "Off-intent (generic PM feature)" ×11, "Off-intent (reporting feature)", "Pricing/plan page boilerplate"), giving 0 must-cover, 0 gaps, score 0, yet status "done" and checklist 7/8. Run `f54961456cdb`: 134 of 137 → noise; score 84 from 2 topics. Run `890ecbac1bf3` kept 16 must-cover topics from a similar SERP, so the behaviour is erratic, not a property of the page.
- **Why it matters:** the must-cover list and score are the core of the brief. A filter that sometimes deletes everything turns the score into a coin flip and makes a perfect-looking but empty brief.
- **Change:**
  1. Split noise into two steps: boilerplate and brand names by code and a short word list (cookies, newsletter, login, contact, pricing table, navigation), then an LLM "off-intent" judgement that must justify itself against the main phrase and our page.
  2. Guard: if the LLM flags more than a set share (setting, start at 30%) of topics that at least 3 competitors cover, discard its answer, retry once with a stricter prompt, and if it still over-flags, keep the topics and add a run warning.
  3. Keep "off-intent" topics visible in a separate collapsed list in the UI so a person can see what was removed.
  4. Add a regression test that replays the `b889d43ab5ca` noise response.
- **Effort:** S
- **Sources:** none needed (logic and guardrail).

#### M6. Phrases and competitors drift away from what the page actually is
- **Severity:** High
- **Evidence:**
  - Run `363329bb0c2a` (emitii.com, a SaaS workspace) chose "virtual assistant for project management"; its SERP is staffing agencies (getmagic.com, prialto.com, boldly.com, timeetc.com), and must-cover then includes "benefits of hiring a virtual assistant" and "employee productivity".
  - Run `c366b302c657` chose "customize your workspace" and "make your workspace more productive"; competitors include `suzettegebhardt.com/decorating-your-office-at-work` and `viccarbe.com/…/9-office-tips`; gaps include "how to set up your workspace in photoshop".
  - Run `890ecbac1bf3` pooled three phrases and got a guide-heavy topic set about enterprise AI platforms: must-cover "enterprise compliance", "governance and security", "project portfolios" for an invite-only product page.
  - The fit check (`FIT_SYSTEM`, `keyword_research.py:35-40`) sees only the phrase and our page; it never sees what actually ranks. Competitors from all phrases are pooled (`competitor_analysis.py: pool_results`).
- **Why it matters:** Google ranks by the searcher's intent, which is visible only in the results. A phrase whose results sell a different thing (a hired person vs software, office furniture vs a software workspace) cannot be won by adding words, and topics pooled from it poison the must-cover list.
- **Change:**
  1. **SERP-aware fit:** after the SERP call, ask the bulk LLM one yes/no per phrase using the top 10 titles and snippets: "Do these results offer the same kind of thing as our page?" Drop phrases that fail. This is the check that would have caught every example above, for one cheap call.
  2. Build the competitor pool from the **main phrase** SERP first; add pages from secondary phrases only if they pass the same offering check and share the main phrase's dominant page type.
  3. Weight topic coverage by the main phrase (a topic covered only by secondary-phrase pages cannot be must-cover).
- **Effort:** M
- **Sources:** [1], [20] (needs met, intent)

#### M7. Gap detection admits irrelevant, duplicate and circular questions
- **Severity:** High
- **Evidence:** gaps in stored runs include "how to become an assistant project manager", "what is the best project management software" (a head term, not a gap), four near-identical "how to find products by photo/picture/image" (`f54961456cdb`), and Photoshop/Premiere/DaVinci workspace questions (`c366b302c657`). `pipeline.py:gather_evidence` adds the run's own cluster phrases as "search phrase" evidence, so a phrase can prove its own demand. The relevance check sees only the first 600 words of our page (`topic_coverage.py:318`). The evidence match uses cosine ≥ 0.88 (`config.py evidence_similarity`), in the very range the architecture document measured as unreliable for Gemini embeddings (matches 0.81 to 0.89, non-matches up to 0.84).
- **Why it matters:** gaps are the "information gain" part of the brief, the part that can make a page stand out [1]. Irrelevant or duplicated gaps waste the team's time and, via the draft's FAQ, end up as filler on the page.
- **Change:** dedupe questions by embedding (≥ 0.92) and keep the most common wording; never use our own phrases or Gemini's queries as the only evidence; require question form (PAA or autocomplete questions); run the relevance check with the page summary and the main phrase's SERP titles; replace the 0.88 cosine match with an LLM yes/no in the existing labelling call.
- **Effort:** S to M
- **Sources:** [1]

#### M8. The coverage score rewards repetition and contradicts the stuffing check
- **Severity:** Medium
- **Evidence:** `content_score` (`topic_coverage.py:136-157`) gives full credit at saturation 0.77, i.e. about 4 passages per topic (`n/(n+1.2)`), with the cap applied only to the total, not per topic. The stuffing warning fires when our passages exceed the 90th percentile of competitors (`:278`), which for most topics is 1 or 2 (run `890ecbac1bf3`: "'kanban boards' appears in 4 passages; 90% of competitors use at most 2"). So the page is told to reach ~4 passages per topic for a full score and warned when it has 3 or 4. Topics already heavily covered can offset missing ones.
- **Why it matters:** users will chase the number. A score that pays for repetition nudges towards keyword-stuffed, search-engine-first copy [2][1]. Vendor studies of content-score tools found only weak correlations with rankings (roughly 0.1 to 0.3), with no control for links or authority; the tools help mainly with the relevance "first gate" [21][22].
- **Change:** cap each topic's contribution: `min(s_t, s*)/s*` where `s*` is the saturation at the competitor median passage count for that topic (usually 1 to 2). Keep BM25-style saturation (k1 in the usual 1.2 to 2.0 range is fine [23]). Rename the score in the UI to "Topic coverage vs. the pages we compared" and show it next to, not above, the intent warning. Run the leave-one-out validation the architecture already describes before showing verdict words like "Strong".
- **Effort:** S
- **Sources:** [23], [21], [22], [2], [1]

#### M9. Long pages are judged on their first 3,000 words only
- **Severity:** Medium
- **Evidence:** `topic_coverage.py:217` truncates every page, including ours, to `llm_page_words = 3000` before labelling passages; the Page Reader and fit check use the same cut. Competitors in run `b889d43ab5ca` ran to 4,911 and 6,565 words.
- **Why it matters:** a topic covered in the second half of our page is reported as "your page doesn't mention it yet"; competitor coverage is undercounted for long guides.
- **Change:** never truncate our page; label competitors in chunks of ~25 passages per call (still one call per chunk, in parallel). Costs a few extra cents at most.
- **Effort:** S
- **Sources:** none needed.

#### M10. Title and description rules are too literal, and the checklist grades the LLM's own output
- **Severity:** Medium
- **Evidence:** the writer must put the exact main phrase first (`brief.py:26-36`, `snippet_check.py`); outputs read as keyword-ese in Title Case ("API for Virtual Try On: Add Visual Search | TryVisually", "Project Management With Chat: AI Workspace for Teams | Emitii"), and all three options start with the same words. The 8-item checklist (`brief.py:126-135`) checks the suggested title and H1, which the writer was just told to satisfy, so it almost always passes (8/8 in 3 of 7 runs); it never checks the page's current title or description.
- **Why it matters:** Google gives no character limit for titles ("truncated … as needed, typically to fit the device width"), warns that keyword-stuffed titles "can make your results look spammy", and builds the title link from the `<title>`, H1 and other text when the title is poor [5]. It says snippets are "primarily created from the page content itself", with the meta description used only when it describes the page better [6]. Studies found Google rewrote 61.6% of titles (Zyppy; titles of 51 to 60 characters rewritten least, and a matching H1 reduced rewrites), 76% in a Q1 2025 sample, and 63% to 71% of meta descriptions (2020 studies) [24][25]. Exact-first-position is a convention, not a rule; natural, specific titles are what survive rewriting.
- **Change:** accept close variants (plural, word order, stop words) for "phrase in title"; require diversity across the 3 options (no two sharing the first 4 words); use sentence case unless the site's style says otherwise; downgrade "phrase first in title" from pass/fail to a tip; in URL mode, check the **current** title, description and H1 (P2) so the checklist is an audit of the page, not of the suggestion. Keep the 600 px width check; note that Google's SERP font and truncation can change, so present it as "likely to fit".
- **Effort:** S
- **Sources:** [5], [6], [24], [25]

#### M11. The suggested draft pushes towards search-engine-first and scaled content
- **Severity:** High
- **Evidence:** `write_draft` sets a target word count from the competitor median (`brief.py:261-262`) and asks for every must-cover topic plus FAQ from gap questions. In run `890ecbac1bf3` the draft for an invite-only product page contains sections such as "Enterprise Compliance, Governance, and Security in an AI Workspace for Teams" made of lines like "For enterprise compliance, governance, and security details, [ADD: certifications, audit logs, SSO, roles, and retention controls]", and similar placeholders for portfolio views, custom bots and multi-model access. The FAQ opens with "How do you evaluate AI workspace platforms for an agency?". The docs still say the engine "never rewrites the page" (README, CLAUDE.md, PRD §1) while PRD §5.9 adds a full rewrite.
- **Why it matters:**
  - Google's helpful-content self-assessment asks "Are you writing to a particular word count because you've heard or read that Google has a preferred word count? (No, we don't.)" and "Are you mainly summarizing what others have to say without adding much value?" [1].
  - Its spam policy defines scaled content abuse as pages "generated for the primary purpose of manipulating search rankings and not helping users", including with generative AI [2][26].
  - The September 2025 rater guidelines rate main content that is "auto or AI generated … with little to no effort, little to no originality, and little to no added value" as Lowest [20].
  - A must-cover list copied from competitors, turned into sections, is close to "summarizing what others have to say". Placeholders that ask for features the product may not have push the team either to invent claims or to publish filler.
- **Change:**
  1. Let the team mark any must-cover topic or gap as "doesn't apply to us" before the draft is written (and remember the choice for re-runs).
  2. Drop the word-count target; state length as an observation ("competing pages run 1,200 to 2,300 words").
  3. Forbid the "For X, [ADD: …]" pattern in code: if a section is mostly placeholders, drop it and list the topic under "facts we need from you" instead.
  4. Add experience and trust prompts from E-E-A-T: who wrote it, first-hand use, screenshots, customer evidence, dates [20][1].
  5. Keep the draft behind a clearly labelled "starting point" until the 5-draft review in PLAN is done; update README, CLAUDE.md and PRD so they no longer say "never rewrites".
- **Effort:** M
- **Sources:** [1], [2], [26], [20]

#### M12. GEO / AI answer engines: promised, but the brief contains nothing specific for them
- **Severity:** Medium
- **Evidence:** PRD §1 promises help "to get cited by AI answer engines"; the only GEO-related work is scheduled for phase 3 (citation sampling). No output addresses how citable the page is.
- **Why it matters:**
  - Google says there are "no additional requirements to appear in AI Overviews or AI Mode, nor other special optimizations"; a page must be indexed and snippet-eligible [7]. Its May 2026 guide adds that "optimizing for generative AI search is … still SEO", that there is "no requirement to break your content into tiny pieces for AI", and that llms.txt files are ignored [27].
  - In the GEO paper's lab setting, adding quotations (+43%), statistics (+33%) and cited sources (+28%) raised a source's visibility in generated answers, while keyword stuffing lowered it (−9%) [28]. A 2026 review of 45 studies found these gains hold only when the source is already in the model's context; no technique showed a stable cross-platform effect, and topical relevance was the most reproducible lever [29]. Citations in AI answers also vary from run to run [30].
  - Ahrefs found that only 38% of pages cited in AI Overviews also rank in the top 10 (March 2026, down from about 76% in mid-2025), which it attributes to query fan-out: AI Overviews also cite pages ranking for related sub-questions [31].
  - So the evidence-backed GEO work is (a) stay eligible, (b) rank for the main phrase **and** its sub-questions (the gaps step), (c) include specific, sourced facts that are worth quoting. Special "AI formatting" is not supported by evidence.
- **Change:** do not add AI-specific rewriting rules. Add a small advisory "Evidence and specifics" checklist in code: numbers and claims on the page with a named source; a plain statement of what the product is and who it is for near the top; a visible author and last-updated date for articles; FAQ answers that make sense on their own. In URL mode also check eligibility blockers (M13). Keep AI citation measurement as repeated sampling (PL4), never a single observation.
- **Effort:** S to M
- **Sources:** [7], [27], [28], [29], [30], [31]

#### M13. Structured data and technical eligibility: out of scope is mostly right, but a few code-only checks are cheap and high value
- **Severity:** Medium
- **Evidence:** PRD §9 puts "schema markup, page structure blocks, author and date signals, crawler access" out of scope. The fetcher already parses JSON-LD types (`fetcher.py:_schema_type`) but only uses them for page type. The draft generates an FAQ section.
- **Why it matters:**
  - Google says the AI features need no special schema.org markup, only the normal technical requirements (indexed, snippet-eligible) [7].
  - FAQ rich results were limited to government and health sites in 2023 and were no longer shown at all from 7 May 2026 [32]. Google has also retired several other structured data features since 2025 [33].
  - So generating schema adds little, and keeping it out of scope is right. But structured data still gives eligibility for the remaining rich results (for example Product and Organization) and must match visible content [26].
  - A `noindex`, `nosnippet` or robots block silently makes every other recommendation useless.
- **Change:** keep schema *generation* out of scope, but in URL mode report in code:
  - indexability (`noindex`, `X-Robots-Tag`), `nosnippet` or `max-snippet`, a canonical pointing elsewhere, and a robots.txt block for Googlebot;
  - existing JSON-LD types, and whether they match the page type (Product or SoftwareApplication, Article, Organization).

  Present the draft's FAQ as content for readers. It no longer earns a rich result.
- **Effort:** S
- **Sources:** [7], [32], [33], [34]

#### M14. Intent classification mislabels listicles and mixes phrases
- **Severity:** Medium
- **Evidence:** the Page Reader labelled `saner.ai/blogs/best-ai-workspaces`, `gosearch.ai/blog/best-ai-collaboration-platforms` and `chanty.com/blog/project-management-tools` as "guide" (run `b889d43ab5ca`); URL rules (`page_types.py`) only see the Gemini "title", which is just the domain. The verdict pools read types across all phrases plus UGC from `serps[0]` (`pipeline.py:115-117`).
- **Why it matters:** "best X" listicles vs product pages is exactly the distinction the intent warning exists for (PRD §5.7).
- **Change:** run the title/URL rules on the fetched `<title>` and H1 before the LLM (code already has `LISTICLE`); add 5 to 10 few-shot examples to the Page Reader prompt as ARCHITECTURE §5.4 intended; compute the verdict per phrase from that phrase's own top 10 and show the main phrase's verdict.
- **Effort:** S
- **Sources:** ARCHITECTURE §5.4

#### M15. Topic "stuffing" warning flags natural product depth
- **Severity:** Low
- **Evidence:** "'kanban boards' appears in 4 passages; 90% of competitors use at most 2" on a product page with a board feature (`890ecbac1bf3`); the checklist item `no_stuffing` fails as a result.
- **Why it matters:** Google's keyword-stuffing policy is about repeating words unnaturally, not about describing a feature in depth [2].
- **Change:** keep the exact-phrase density check (draft), and turn topic repetition into a soft note only when ours exceeds the competitor maximum by 2 or more passages.
- **Effort:** S
- **Sources:** [2]

#### M16. SERP-overlap clustering only works with ranked results
- **Severity:** Low
- **Evidence:** 2 multi-member clusters in 7 runs, both trivial variants ("virtual assistant for/in project management").
- **Why it matters:** clustering phrases by shared top-10 URLs is sound with ranked SERPs; with 5 cited pages it silently does nothing.
- **Change:** enable clustering only when the SERP source is ranked; otherwise group by embedding similarity of phrases and say so.
- **Effort:** S
- **Sources:** none needed.

### 3.2 Accuracy and trust

#### A1. The same page produces different briefs
- **Severity:** High
- **Evidence:** page hash `c3118163` (emitii.com, 594 words): run `363329bb0c2a` chose "easy to use project management software / virtual assistant for project management / virtual assistant project management tools"; `890ecbac1bf3` four minutes later chose "project management with chat / ai workspace for teams / project management tool for agency" (zero overlap). Page hash `00668e32`: `2eb18fea7af3` and `31f42fcdfc63` also share no phrase. Caveat: the PLAN notes a "stricter phrase fit check" landed the same day, so part of this may be code change; a controlled repeat is needed.
- **Why it matters:** if two runs disagree, the team cannot tell advice from randomness, and "re-run after edits" (P3) cannot show progress. LLM outputs vary even at temperature 0: one study measured accuracy differences of up to 15% between identical runs, and 1,000 temperature-0 completions from one model produced 80 different outputs [35][36]. DeepSeek's thinking mode ignores `temperature` altogether [37].
- **Change:**
  1. Cache LLM responses by (model, prompt hash, day) like other calls: same-day re-runs become identical and free.
  2. Stabilise the seed step with self-consistency: 3 seed calls on the bulk model, keep phrases proposed at least twice [38].
  3. Break near-ties deterministically and show ties ("these 4 phrases scored within 5%").
  4. Let users **lock** chosen phrases for a page so later runs re-use them (also solves comparison, P3).
  5. Add the stability test to the eval plan (§5): Jaccard of phrases ≥ 0.67 over 3 uncached runs.
- **Effort:** M
- **Sources:** [35], [36], [37], [38]

#### A2. "No invented facts" in the draft is enforced only by the prompt
- **Severity:** High
- **Evidence:** `DRAFT_SYSTEM` (`brief.py:153-171`) instructs the model; code only counts placeholders. A script check of the 4 stored drafts found no new numbers, but the drafts reuse demo UI text as fact ("an update can show that a paid-social budget was approved …", from the product mock-up on emitii.com, see A3) and make general claims ("fewer handoffs and less status chasing") that the page does not state.
- **Why it matters:**
  - The PRD makes "never invents facts" a core promise. Prompt-only rules fail silently, and published false claims are a legal and reputational risk for client sites.
  - Verification works and can be automated. Chain-of-Verification raised FActScore from 55.9 to 71.4 on long-form text [39]. FActScore checks atomic facts against a source with under 2% error against human scores [40].
  - Even commercial generative search engines had only 51.5% of sentences fully supported by their citations [41].
- **Change:** after the draft, run a code check plus a verifier: (1) code extracts numbers, prices, percentages, product and company names, and flags any not found in the page text; (2) one bulk LLM call from a *different* family (Gemini Flash on the free tier is enough) labels each sentence "supported by page / general statement / unsupported"; (3) unsupported sentences are highlighted in the UI and .docx like placeholders. Record the unsupported-sentence rate as an eval metric.
- **Effort:** M
- **Sources:** [39], [40], [41], [42]

#### A3. URL import pulls product mock-up text into "page facts"
- **Severity:** High
- **Evidence:** run `b889d43ab5ca` page text (from the visible-text extractor) contains "Sita Rai moved "Launch email" to QA", "Icebox 3", "MON 14Content review", "Brand guide v3", "Client brief.pdf". The review textarea is collapsed by default (`NewRun.tsx`: "Review text" link).
- **Why it matters:** mock-up text becomes topics, passages and "facts" the draft is allowed to use (A2), and dilutes the coverage count.
- **Change:** in `visible_text`, drop blocks inside elements that look like app mock-ups (many short lines < 4 words, repeated UI tokens, `aria-hidden`, `role="img"`, elements with `inert`), and report the share of short lines. If more than ~30% of lines are under 4 words, open the review box automatically with a note: "This page has sample text from screenshots or demos; remove it before continuing."
- **Effort:** S
- **Sources:** none needed.

#### A4. Broken runs finish as "done" with no warning
- **Severity:** High
- **Evidence:** `b889d43ab5ca` (0 must-cover, score 0), `f54961456cdb` (score from 2 topics), `2eb18fea7af3` (4 competitors, 2 phrases), `363329bb0c2a` (main phrase with 0 SERP results) all have `status: "done"`. `run.notes` exist but the UI shows them only in Details.
- **Why it matters:** the user cannot tell a good brief from a broken one; one bad brief seen by a client destroys trust in all of them.
- **Change:** add a `quality` block to `Run` computed by code: list of failed gates (SERP source not ranked; < 8 SERP items for any chosen phrase; < 5 competitors or < 3 domains; noise share > 30%; must-cover < 3; gaps all from one source; draft unsupported sentences > 0). Status becomes `done` or `needs_review`; the UI shows a banner with plain reasons at the top of the brief.
- **Effort:** S
- **Sources:** none needed.

#### A5. Data provenance is mislabelled in the UI and report
- **Severity:** High
- **Evidence:** `competitor_analysis.py:172` sets `source=f"google#{item.rank}"` for every competitor, including Gemini-cited pages; the UI shows "#3". Copy says "Most pages that rank for your searches cover these" (`Brief.tsx:50`), "People search this on Google" for autocomplete presence (`format.ts: demandText`), "Asked on Google (People also ask)" or "Searched on Google" for gap evidence (including Gemini's own queries), and "Search data is free" (`Details.tsx:113`).
- **Why it matters:** the brief states things the data does not show. This breaks the product's own rule 6 ("no invented facts") at the presentation layer.
- **Change:** carry `source` through (`google-serper`, `gemini-cited`, `dataforseo`) and word the UI from it: "Pages Gemini cited when searching Google for …", "Appears in Google's search suggestions", "AI search query". Add a small "Where this data comes from" line under each step.
- **Effort:** S
- **Sources:** [13]

#### A6. Prompt injection from competitor pages
- **Severity:** Medium
- **Evidence:** fetched competitor text goes straight into the Page Reader and passage-labelling prompts (`competitor_analysis.py:61-69`, `topic_coverage.py:435-448`) with no delimiting or instruction to ignore embedded instructions. Topic names from those calls flow into the Brief Writer and Draft Writer prompts and then onto the client's page.
- **Why it matters:** indirect prompt injection through retrieved web content is a known, practical attack [43] and the top item in OWASP's LLM risks [44]. Impact here is limited (outputs are short, schema-validated topic lists, and the draft never sees competitor text), but a hostile page could still plant a "topic" such as a competitor's slogan or a URL into a client's brief.
- **Change:** wrap untrusted text in clear delimiters and tell the model it is data; drop hidden text (already done in `visible_text`, not in trafilatura output); validate topics in code (1 to 6 words, no URLs, no imperative verbs like "ignore/visit/click", no brand tokens); log any rejected topic. Keep the rule that the writers only see topic names, never competitor text.
- **Effort:** S
- **Sources:** [43], [44]

#### A7. No evaluation set, gold briefs or calibrated thresholds yet
- **Severity:** High
- **Evidence:** `evals/pages/` and `evals/gold_briefs/` contain only `.gitkeep`; `evals/run_evals.py` does not exist; every threshold in `config.py` is marked "tune".
- **Why it matters:** without a fixed eval set, every change (including the fixes in this review) can make things better on one page and worse on five others, and nobody will know.
- **Change:** see §5 Evaluation plan; it is the first item of the roadmap after the quality gates.
- **Effort:** L (mostly team time)
- **Sources:** [42]

#### A8. Unofficial Google suggest endpoint: terms risk and a single point of failure
- **Severity:** Medium
- **Evidence:** `autocomplete.py` calls `suggestqueries.google.com` with `client=firefox`, keyless; 238 calls on 24 Sep for 7 runs plus checks. `check_autocomplete` runs up to one call per candidate (`keyword_research.py:202-209`). A final 429 raises from `request_with_retry` and fails the entire run.
- **Why it matters:**
  - Google announced in 2015 that it would restrict "unauthorized access" to this unofficial autocomplete API, which it said "was never intended to be used outside of Google Search" [45].
  - Google's Terms of Service forbid automated access that violates machine-readable instructions [46]. The endpoint has no robots.txt, so the risk is policy and reliability rather than a clear breach.
  - The endpoint can be rate-limited or changed without notice. Today it is also the only demand signal (M2), so if it fails, the whole run fails.
- **Change:** cap suggest calls per run (setting, e.g. 40), add jitter and a per-host rate limit, catch errors per call and continue with "demand unknown"; prefer Bing and Search Console for demand; ask the owner to accept or reject the terms risk explicitly (§6).
- **Effort:** S
- **Sources:** [45], [46], [9]

#### A9. robots.txt handling differs from the standard, and the headless fallback retries refusals
- **Severity:** Medium
- **Evidence:** `fetcher.py:198-215`: any status ≥ 400 other than 401/403, and any network error, is treated as "no robots.txt, everything allowed". Robots is checked for the original URL's origin only, not after redirects to another host. `_fetch` sends HTTP errors (including 403 and 429) to `_fallback`, which renders the page in headless Chrome.
- **Why it matters:**
  - RFC 9309 says: a 4xx robots.txt means "the crawler MAY access any resources"; a 5xx or network error means "the crawler MUST assume complete disallow" [47].
  - Google's own crawler treats 4xx except 429 as "no robots.txt". On 5xx it stops crawling and retries, then falls back to a cached copy [34].
  - The code is stricter than the standard on 401/403, which is fine, but looser on 5xx, which is not.
  - Retrying a 403 or 429 with a real browser looks like evading a block, which matters for a Gurzu-branded user agent.
- **Change:** follow RFC 9309: 4xx (except 429) allows; 5xx, 429 and network errors disallow for this run. Re-check robots.txt for the final host after redirects. Use headless only for "too short" pages, never after 401, 403 or 429. Honour `Retry-After`.
- **Effort:** S
- **Sources:** [47], [34]

#### A10. SSRF guard can be bypassed through redirects, DNS rebinding and the headless browser
- **Severity:** Medium (High if the service is ever exposed beyond localhost)
- **Evidence:** `api/app.py:70-83` resolves the host once; `HttpFetcher` then uses `follow_redirects=True` (`fetcher.py:191`), so `https://attacker.example/` can redirect to `http://169.254.169.254/` or `http://localhost:8420/`. The check misses non-global ranges such as `100.64.0.0/10`. The headless fallback navigates and loads sub-resources with no guard.
- **Why it matters:** OWASP recommends checking every resolved A and AAAA record, disabling redirect following, and treating any disagreement between parsers as a rejection [48]. It also warns about DNS rebinding and time-of-check to time-of-use races [49].
- **Change:** use `not ip.is_global` as the rule; disable automatic redirects in the extract path and re-validate each `Location` (max 5 hops); connect to the validated IP (pin) to defeat rebinding; disable headless for `/api/extract` or route it through the same guard with request interception.
- **Effort:** S to M
- **Sources:** [48], [49]

#### A11. Client page text goes to third-party LLMs and free tiers without notice
- **Severity:** High
- **Evidence:** our page text and competitor passages go to DeepSeek (all LLM steps) and to Gemini embeddings on the free tier (`embeddings.py`). The UI offers "Text I paste — for a product that isn't live yet". Runs are kept forever in `runs/` with full page and competitor text (136 to 285 KB each).
- **Why it matters:**
  - For the unpaid Gemini API, Google says it uses submitted content and responses "to provide, improve, and develop Google products", that "human reviewers may read, annotate, and process your API input and output", and it asks users not to submit "sensitive, confidential, or personal information to the Unpaid Services" [3].
  - DeepSeek's privacy policy says it will "collect, process and store your Personal Data in People's Republic of China" and use data to train its models, with an opt-out [50].
  - Unpublished client copy is confidential information, so the current setup conflicts with Google's own instruction for the free tier.
- **Change:** owner decision (§6); then add a one-line notice on the paste tab, a setting to use a paid (no-training) Gemini key for embeddings, a retention setting for runs (e.g. delete competitor text after 30 days), and an "anonymise brand names" option for unreleased products.
- **Effort:** S
- **Sources:** [3], [50]

#### A12. Cost and time budgets exist in settings but are not enforced
- **Severity:** Low
- **Evidence:** `time_budget_s` is used only for DataForSEO polling; `cost_budget_usd` is never read; the LLM price table is static (`config.py:236-239`) with a comment to verify; embedding cost is charged even on the free tier.
- **Why it matters:** cost is low today (~$0.03), but a runaway retry loop or a switch to a pricier model would not be caught; the "reduced depth" behaviour in PRD §7 does not exist.
- **Change:** a `Budget` object checked before each paid call; on breach reduce depth (fewer candidates, fewer competitors) and add a note. Prices: see E10.
- **Effort:** S
- **Sources:** [51]

#### A13. Using Gemini grounding as a cached SERP likely breaks the Gemini API terms
- **Severity:** High
- **Evidence:** grounded results are cached for the day (`gemini_search.py:336-364`), stored in run files, analysed for difficulty, clustering, intent and competitors, and shown without Google's Search Suggestions.
- **Why it matters:** the Gemini API Additional Terms (last modified 28 April 2026), as retrieved for this review, say you may not "cache, frame, syndicate, resell, analyze, train on, or otherwise learn from Grounded Results or Search Suggestions". They also say grounded results may be displayed only "with the associated Search Suggestion(s) to the end user", and you may not "extract or collect one or more of these components for another purpose". Storage is allowed only in narrow cases, such as an end user's chat history [3][13]. Using grounding as SERP data is close to the textbook case of "analyze" and "extract for another purpose". The free tier is also capped at 500 grounded requests a day for Gemini 2.5 Flash, and Gemini 3 models have no free grounding tier [52].
- **Change:** confirm the wording on the live terms page with the owner (the quotes above came through a summarising fetch). Unless the reading turns out to be wrong, remove grounding from the SERP path (M3) and from gap evidence. Keep it, if at all, for a user-facing "what does Gemini say" view that shows Search Suggestions as the terms require, without caching.
- **Effort:** S
- **Sources:** [3], [13], [52]

#### A14. DeepSeek JSON mode can return empty content, which costs a retry
- **Severity:** Low
- **Evidence:** `DeepSeekLLM.structured` retries once on a validation error and then raises (`llm.py:150-170`); the request does not set `max_tokens`, and the prompt carries a JSON schema but no example.
- **Why it matters:** DeepSeek's docs warn that JSON output "may occasionally return empty content" and advise including the word "json", an example, and a sensible `max_tokens` [53]. Combined with E3, one empty reply out of ~35 calls per run can fail the run.
- **Change:** add a short example object to each prompt, set `max_tokens` per schema, treat empty content as retryable without counting it against the validation retry.
- **Effort:** S
- **Sources:** [53]

### 3.3 Engineering

#### E1. Runs cannot be traced to the code that produced them
- **Severity:** Medium
- **Evidence:** when this review started, the repository had no commits and every file was untracked. A baseline commit (`9ffdae8`, "Add the SEO Advisor engine, API and web app") appeared during the review. The 7 stored runs predate it, and `RunRecord` stores no code version.
- **Why it matters:** A1 cannot be settled because nobody can tell which code produced which run. The same will happen after every future change unless runs record their code version.
- **Change:** store the git commit hash (and a "dirty" flag) in every `RunRecord`. Keep committing in small steps, so each fix in this review is a separate, revertible change.
- **Effort:** S
- **Sources:** none needed.

#### E2. No logging, tracing or LLM transcripts
- **Severity:** High
- **Evidence:** no `logging` import anywhere in `src/`; LLM prompts and responses are not kept; ARCHITECTURE §7 requires "Log every prompt, tool call, tokens, cost and time per node".
- **Why it matters:** the failures in this review (M1, M5) had to be reverse-engineered from final JSON. Without transcripts, the phase 2 "read every transcript" task and the model bake-off cannot happen.
- **Change:** a small tracer that appends JSON lines to `runs/<id>.trace.jsonl`: step, provider, cache hit or miss, latency, tokens, cost, validation retries, and for LLM calls the prompt hash plus the full prompt and response (redactable). Show per-step cost and time in Details.
- **Effort:** M
- **Sources:** ARCHITECTURE §7

#### E3. One failing call fails the whole run
- **Severity:** High
- **Evidence:** `pmap` (`concurrency.py`) propagates the first exception; an invalid JSON twice from one of ten Page Reader calls raises `LLMOutputError` and the run fails; the same for a suggest 429 (A8) or grounding quota (`FallbackSearch` raises when all providers are unavailable). `request_with_retry` ignores `Retry-After` and has no jitter.
- **Why it matters:** free tiers and unofficial endpoints fail often; a 2-minute run that dies at step 3 wastes the paid calls already made.
- **Change:** per-item isolation (a failed competitor page becomes a "dropped: reader failed" entry; a failed suggest call becomes "unknown"); jittered backoff that honours `Retry-After`; step-level checkpoints so a re-run the same day resumes from cache (it mostly does already for search, fetch and embeddings; add the LLM cache from A1).
- **Effort:** M
- **Sources:** none needed.

#### E4. Phrase research takes 42% to 80% of run time
- **Severity:** Medium
- **Evidence:** step times from the 7 runs: keywords 53 to 146 s (median 80 s), competitors 7 to 29 s, coverage 11 to 25 s, brief 6 to 27 s, draft 28 to 43 s; total 97 to 190 s. Keywords runs the seed call on `deepseek-reasoner`, an autocomplete check for every candidate at 4 workers, and up to 20 grounded searches (`cluster_max_candidates`).
- **Why it matters:** the PRD time budget is 5 minutes, but users will re-run after edits; under 90 s makes that practical and halves free-quota use.
- **Change:** seeds on the bulk model (judgment adds little for listing phrases; verify on evals); pre-rank with the SERP-free signals and send only the top 8 candidates to SERP (setting); run the autocomplete checks and page-phrase embedding concurrently; run the draft on the bulk model and keep the reasoner for the brief writer if evals show a difference.
- **Effort:** S to M
- **Sources:** none needed.

#### E5. Caching policy wastes free quota and disk
- **Severity:** Medium
- **Evidence:** embeddings (deterministic for a fixed model) are cached per day: 40 MB, 2,004 files for one day; nothing prunes `cache/`; LLM calls are never cached; empty grounding responses are cached for the day (M1).
- **Why it matters:** re-embedding the same topics every day spends free-tier quota and time; unbounded cache growth will surprise a server deployment.
- **Change:** move the embedding cache to a permanent SQLite table keyed by (model, dims, text hash); keep the daily cache for search, fetch and suggest; prune day folders older than N days (setting); add the LLM cache from A1; never cache empty or error results.
- **Effort:** S
- **Sources:** none needed.

#### E6. Tests are synthetic and would not catch the live failures
- **Severity:** High
- **Evidence:** 70 tests pass in 2.6 s using `FakeEmbed`, `FakeLLM`, `FakeSearch` and hand-written DataForSEO fixtures. There is no test for an empty SERP, a grounding-shaped SERP, noise over-removal, duplicated gaps, or mock-up page text; no coverage measurement. PLAN asks for recorded fixtures.
- **Why it matters:** every Critical finding above passed the test suite.
- **Change:** turn the real responses already in `cache/2026-09-24/` into recorded fixtures for 2 or 3 of the runs (grounded search, suggest, fetch, embeddings), plus recorded LLM responses from the trace (E2), and replay the whole pipeline offline. Add invariant tests: difficulty needs ≥ 8 items; noise share ≤ threshold; gaps unique; every competitor `source` matches the SERP source. Add `pytest-cov` and aim for branch coverage on `tools/` and `brief.py`.
- **Effort:** M
- **Sources:** none needed.

#### E7. Concurrency limits are not per provider
- **Severity:** Medium
- **Evidence:** one `concurrency = 8` setting drives fetches, LLM calls and grounded searches; each fetch can start its own headless Chromium (`_render_headless`), so 8 browsers can run at once; `TrancoRanks._build` can run twice if two runs start on a cold cache; the SQLite connection is shared across threads.
- **Why it matters:** free tiers have per-minute limits [52]; 8 parallel browsers can exhaust memory on a small server.
- **Change:** a per-provider semaphore and rate limit in config (e.g. grounding 5/min, suggest 2/s, browsers 2); a file lock around the Tranco build; one SQLite connection per thread.
- **Effort:** S
- **Sources:** [52]

#### E8. Not ready to deploy beyond one laptop
- **Severity:** Medium
- **Evidence:** no authentication; file-based store; runs execute in FastAPI background threads and are marked failed on restart; no Dockerfile, no CI, no health check of providers beyond key presence.
- **Why it matters:** fine for a single developer; not for "the team" in PRD §3.
- **Change (when the team starts using it):** run behind a simple SSO or basic-auth reverse proxy; SQLite for runs and traces; a single worker process with a job queue (even a SQLite-backed one); a Dockerfile; CI running `ruff`, `pytest` and `npm run build`; a "test keys" button that runs the free parts of `check_live.py`.
- **Effort:** M
- **Sources:** none needed.

#### E9. Documentation has drifted from the code
- **Severity:** Low
- **Evidence:** README/CLAUDE.md/PRD §1 say the engine "never rewrites the page" while PRD §5.9 and the code produce a full draft; PRD §9 lists URL input as out of scope while it ships; ARCHITECTURE describes KeyBERT, LangGraph, entity salience and DataForSEO intent that free mode does not use; section order is 2a, 2c, 2b; the difficulty ceiling table is labelled "DataForSEO".
- **Why it matters:** CLAUDE.md tells every contributor (and AI assistant) to trust these docs first.
- **Change:** one docs pass after the Now items: state what free mode actually does, mark planned vs built, fix the contradictions.
- **Effort:** S
- **Sources:** none needed.

#### E10. LLM model names and the price table may be out of date
- **Severity:** Medium
- **Evidence:** `config.py:227-239` uses `deepseek-reasoner` and `deepseek-chat`, priced at $0.28 / $0.028 / $0.42 per million tokens. DeepSeek's change log, as retrieved for this review, announced on 24 April 2026 that these two legacy names would be discontinued on 24 July 2026. It lists `deepseek-flash` (V4.1 Flash) and `deepseek-v4-pro` as current models, with different prices and peak-hour pricing (for example `deepseek-flash` off-peak: $0.15 per million input tokens on a cache miss, $0.60 per million output tokens) [54][51]. Yet the stored runs from 24 September 2026 completed with the old names.
- **Why it matters:** either the old names are still aliased to a newer model, or the retrieved change log is wrong. In both cases `Run.cost_usd` may be computed with the wrong prices, and a silent model swap changes output quality and stability (A1) without anyone noticing.
- **Change:**
  - Log the `model` field that the API returns (E2) and store it in each run.
  - Check the live DeepSeek pricing and change-log pages, then update the model names and `llm_prices`, including peak and off-peak rates.
  - Fail loudly when the returned model differs from the configured one.
- **Effort:** S
- **Sources:** [54], [51]

#### E11. Small maintainability issues
- **Severity:** Low
- **Evidence:** country lists duplicated in `api/app.py`, `report.py` and `web/src/format.ts`; UI copy duplicated between `report.py` and `format.ts`; `Settings.language` fixed to "en" in prompts; `phrase_in_h1` checks the brief outline H1 while the draft writes its own H1.
- **Change:** serve countries and labels from `/api/settings/defaults`; check the draft H1 too; track language as a real setting when non-English sites come in.
- **Effort:** S
- **Sources:** none needed.

### 3.4 Product and UX

#### P1. Show confidence and provenance, not just a score
- **Severity:** High
- **Evidence:** the summary ring and "Strong / Getting there / Needs work" appear the same whether the run had 10 ranked competitors or 2 topics from Gemini citations (see A4, A5).
- **Why it matters:** non-SEO users will act on whatever looks confident.
- **Change:** a "How sure is this brief?" line under the score (High / Medium / Low from the quality gates in A4) with the plain reasons, and a data-source line per step. Hide the verdict word when confidence is Low.
- **Effort:** S
- **Sources:** none needed.

#### P2. URL mode should audit the current page and show "current vs suggested"
- **Severity:** High
- **Evidence:** `/api/extract` returns only title, text and word count; the current meta description, H1, H2s, canonical, robots meta and JSON-LD are discarded. The checklist grades the suggestion (M10).
- **Why it matters:** the most useful thing a team can see is the diff: "your title today → suggested title", "your H1 does not mention the main search", "the page is set to noindex". It also makes the output checkable.
- **Change:** extend `FetchedPage` with meta description, H1/H2 list, canonical, robots meta and `X-Robots-Tag`; show a "Today → Suggested" table in step 2 and step 5; run the checklist and M13 eligibility checks on the current page.
- **Effort:** M
- **Sources:** [5], [6], [7]

#### P3. Support the real team loop: lock, edit, re-run, compare
- **Severity:** Medium
- **Evidence:** runs are independent; history is a flat list; phrases cannot be locked; there is no comparison or "what changed" view; the PRD's "approval" phrase selection is not implemented.
- **Why it matters:** SEO work is iterative: choose phrases, edit the page, check again, publish, measure weeks later.
- **Change:** group runs by page (URL or a user-given name); "Re-run with the same phrases" button (uses locked phrases, A1); a compare view (score and topics covered before/after, new gaps); phrase approval as a pause after keyword research (settings already exist); a "published on" date field so the team can check Search Console later (PRD §8 outcome measures).
- **Effort:** M to L
- **Sources:** none needed.

#### P4. Let the team say "doesn't apply to us" and see the evidence
- **Severity:** Medium
- **Evidence:** must-cover and gap lists are read-only; the passage indices behind each count are stored (`topic_details.competitor_passages`) but no competitor quote is shown.
- **Why it matters:** a topic like "enterprise compliance" may be correct for the market but wrong for the product; showing one example sentence from a competitor makes the advice concrete and checkable.
- **Change:** a dismiss control per topic or gap (stored on the page, re-used by later runs and by the draft); an expandable "How competitors cover this" with 1 to 2 short quotes and links.
- **Effort:** M
- **Sources:** none needed.

#### P5. Key onboarding hides the keys that matter most for quality
- **Severity:** Medium
- **Evidence:** `/api/health` treats only DeepSeek and Gemini as required; the UI does not tell users that without Serper the engine is using Gemini citations instead of Google results, or that without Bing there is no demand number.
- **Change:** a setup panel listing each key with what it improves ("Serper: real Google top 10, People Also Ask"), links to sign-up pages, remaining Serper credits if the API reports them, and a "test" button.
- **Effort:** S
- **Sources:** [14], [10]

#### P6. The report needs its caveats and next steps
- **Severity:** Low
- **Evidence:** the .docx has no data-source section, no confidence, no date of the SERP snapshot, and no "how to check if it worked".
- **Change:** add "Where this data comes from" and "Check results in 4 to 8 weeks in Search Console: impressions and position for these phrases" sections; include the quality warnings.
- **Effort:** S
- **Sources:** [12]

#### P7. Multi-page and site context
- **Severity:** Low
- **Evidence:** each run knows nothing about the site's other pages.
- **Why it matters:** two pages of the same site chasing the same phrase compete with each other; the brief should warn.
- **Change:** later: store chosen phrases per site and warn when a new run picks a phrase already assigned to another page of the same domain.
- **Effort:** M
- **Sources:** none needed.

### 3.5 Plan and gaps against the PRD

#### PL1. Evals must come before more features and before the phase 2 agent
- **Severity:** High
- **Evidence:** PLAN phase 0 eval tasks (20 pages, 20 gold briefs) are unchecked, while draft writing, the .docx report and URL import are ticked. Phase 2 plans a one-agent version of a pipeline whose steps are fixed.
- **Why it matters:** the fixed order is a known-good pattern for predictable tasks; agents add cost and failure modes and pay off for open-ended work [4]. Without evals there is no way to show an agent is better.
- **Change:** re-order: quality gates and fixes (Now) → eval set and replay harness → calibrate thresholds → decide on the agent only if evals show a specific failure an agent would fix. Consider dropping the phase 2 agent entirely and keeping the "one agent" idea for an MCP server that calls the pipeline.
- **Effort:** plan change only
- **Sources:** [4]

#### PL2. The blind review gate needs a free benchmark
- **Severity:** Medium
- **Evidence:** PRD §8 and PLAN gate phase 2 on a paid tool's briefs; the budget rules out a subscription.
- **Change:** options for the owner (§6): (a) a 7-day free trial of one commercial tool, used for the 10 gate pages only; (b) compare against the team's own gold briefs, blind; (c) a Gurzu SEO lead writes 10 briefs by hand with a time budget (also measures "hours saved").
- **Effort:** S
- **Sources:** none needed.

#### PL3. Move Search Console mode forward
- **Severity:** High
- **Evidence:** phase 4, "needs CEO approval".
- **Why it matters:** for any page that already exists, Search Console gives real Google queries, impressions and positions for free; it replaces the weakest part of free mode (M2) with the strongest data available, and it is the only free way to measure outcomes (PRD §8) [12].
- **Change:** ask for the approval now; implement read-only `searchanalytics.query` for one property with a service account; use queries at positions 4 to 20 sorted by impressions as candidates (ARCHITECTURE already specifies this).
- **Effort:** M
- **Sources:** [12]

#### PL4. AI citation sampling: check each engine's terms before building it
- **Severity:** Low
- **Evidence:** ARCHITECTURE §5.6 plans citation sampling with Gemini grounding, OpenAI, Anthropic and Perplexity; grounding calls already return which pages Gemini cited.
- **Why it matters:** AI recommendation lists vary widely between runs [55], and a 2026 study argues that visibility in AI search must be measured as a distribution over repeated runs, never once [30]. So the ARCHITECTURE §5.6 design (frequency over many samples, labelled "API sample") is right. However, counting how often a domain is cited is "analysing" grounded results, which the Gemini terms appear to forbid (A13). The OpenAI, Anthropic and Perplexity search APIs each have their own terms.
- **Change:** before building phase 3 sampling, check each engine's terms for measurement use. Build it only on engines whose terms allow it, and label the results "API sample, n = …". Do not reuse the SERP fallback for this.
- **Effort:** S (terms check), M (sampling)
- **Sources:** [55], [30], [3]

#### PL5. Ticked items with unmet "done when" criteria
- **Severity:** Low
- **Evidence:** "Suggested content" is ticked with "no invented facts" based on one live run, while "Eval: team reviews 5 drafts" is unchecked; phase 1 tool tasks have "Status: built" but their "done when" (hand counts on 3 phrases, live runs on 10 phrases) is not met.
- **Change:** untick or add "(provisional)" until the eval tasks are done; add "done when" criteria from §4 below.
- **Effort:** S
- **Sources:** none needed.

---

## 4. Reinforcement roadmap

All items fit the no-paid-data budget (LLM spend stays at a few cents per run). Each block is ordered; items can be pasted into `PLAN.md`.

### Now (week 1): stop wrong advice from looking right

- [ ] **Store the git commit hash in each run** (E1)
  - Done when: new runs record `code_version` and a dirty flag.
- [ ] **Quality gates and run status `needs_review`** (A4, P1)
  - Done when: replaying the 7 stored runs flags `363329bb0c2a`, `b889d43ab5ca`, `f54961456cdb`, `2eb18fea7af3` with plain reasons, and the UI shows a banner and a confidence level.
- [ ] **Difficulty needs ≥ 8 results; never cache empty searches** (M1)
  - Done when: a test with an empty SERP yields "difficulty unknown" and that phrase cannot be chosen.
- [ ] **Noise guard** (M5)
  - Done when: a replay of the `b889d43ab5ca` noise response keeps the topics and adds a warning; noise share is shown in Details.
- [ ] **Honest provenance labels** (A5, M3 step 3)
  - Done when: no UI or report string says "Google" for data that came from Gemini or autocomplete; competitor sources read `gemini-cited #n` or `google #n`.
- [ ] **Add Serper and Bing keys** (M2, M3, P5)
  - Done when: `check_live.py` passes for serper and bing, and a run on emitii.com uses `google` SERPs with PAA and shows a Bing number for at least one phrase.
- [ ] **Take grounding out of the SERP path; privacy notice** (A13, A11)
  - Done when: no run caches or analyses grounded results; the paste tab and README say where page text is sent; the owner has decided on paid Gemini embeddings (§6 Q5).
- [ ] **Check DeepSeek model names and prices** (E10)
  - Done when: each run records the model the API returned, and `llm_prices` matches the live pricing page.
- [ ] **Robots and SSRF fixes** (A9, A10)
  - Done when: tests cover 5xx robots → disallowed, 403 → no headless retry, redirect to `169.254.169.254` → refused.

### Next (weeks 2 to 3): measure, then fix meaning and stability

- [ ] **Eval set, gold briefs and replay harness** (A7, PL1, §5)
  - Done when: 20 pages and 20 gold briefs exist; `python evals/run_evals.py --replay` runs all 20 offline except LLM calls in under 15 minutes and writes a metrics table.
- [ ] **Tracing and LLM cache** (E2, A1 steps 1)
  - Done when: every run has a trace file with every call's latency, tokens and cost; a same-day re-run of the same page produces an identical brief at $0.
- [ ] **SERP-aware fit and main-phrase competitor pool** (M6)
  - Done when: on the eval set, "phrase sense matches the page" is rated yes for ≥ 90% of chosen phrases by the team, and no competitor from a different offering type reaches must-cover.
- [ ] **Gap clean-up** (M7)
  - Done when: no duplicate gaps (cosine ≥ 0.92) and ≥ 80% of gaps rated relevant by the team on the eval set.
- [ ] **Draft verification and "doesn't apply" controls** (A2, M11, P4, A3)
  - Done when: the draft shows unsupported sentences highlighted; eval unsupported-claim rate ≤ 1 per draft; no section is more than 30% placeholders; mock-up text detector opens the review box on emitii.com.
- [ ] **Score fix and threshold calibration** (M8, M9, M4 step 4, M10)
  - Done when: per-topic cap in place; our page never truncated; ceilings and bucket shares chosen from eval results and recorded in ARCHITECTURE with the date.
- [ ] **Resilience and speed** (E3, E4, E5, E7, A8)
  - Done when: a forced 429 from suggest or one Page Reader failure no longer fails a run; median run time ≤ 90 s; ≤ 12 search calls per run; embeddings cached permanently.
- [ ] **Stability test passes** (A1)
  - Done when: 3 uncached runs of each of 5 eval pages give phrase Jaccard ≥ 0.67 and must-cover Jaccard ≥ 0.6.

### Later (weeks 4+): workflow and reach

- [ ] **URL audit: current vs suggested, eligibility checks, citable-passages checklist** (P2, M13, M12)
  - Done when: URL-mode briefs show today's title, description, H1 and indexability, and flag `noindex`/`nosnippet` on a test page.
- [ ] **Search Console mode** (PL3), after approval
  - Done when: briefs for 5 existing Gurzu pages use real queries at positions 4 to 20.
- [ ] **Free link-based authority in difficulty** (M4 steps 1 to 3)
  - Done when: difficulty uses PSL-aware domains, platform exceptions and Open PageRank or Common Crawl ranks, and team agreement with "could a new site rank here?" improves on the eval set.
- [ ] **Team loop: page groups, locked phrases, re-run and compare, approval pause** (P3)
  - Done when: a user can re-run a page with the same phrases and see a before/after diff.
- [ ] **Blind review gate with a free benchmark** (PL2)
- [ ] **AI citation sampling on engines whose terms allow measurement** (PL4)
  - Done when: citation frequency is reported for 5 phrases with sample counts, and each engine used has a recorded terms check.
- [ ] **Deployment basics: auth proxy, SQLite store, job worker, Dockerfile, CI** (E8)
- [ ] **Data retention and privacy settings** (A11) — timing depends on the owner decision.
- [ ] **Docs pass** (E9) after the Now and Next items.

---

## 5. Evaluation plan

### 5.1 Eval set

- **20 pages**, as PLAN specifies, with this mix: 8 product or landing pages (including emitii.com and tryon.gurzu.net), 5 service pages (Gurzu and clients), 5 articles or guides, 2 pages from a non-software industry. At least 4 must be existing pages with Search Console access (for PL3 and later outcome checks).
- Store each page as `.txt` **and** the raw HTML (for URL-mode tests), with the header line PLAN specifies.
- **Freeze the provider responses** for each page once (SERP, suggest, fetch, embeddings; the daily cache already stores them) into `evals/replay/`. Evals then replay data offline and pay only for LLM calls: at ~$0.03 per page, a full eval is about $0.60 and a 3× stability run about $1.80.

### 5.2 Gold briefs

- Written by two team members per page **before** seeing engine output: 1 to 3 phrases (with "acceptable alternatives"), must-cover topics, gaps, and a note on intent. Titles and descriptions are rated, not written, because many good answers exist.
- Where the two writers disagree, keep both as acceptable; record inter-annotator agreement (Cohen's kappa) on a 20-item sample so we know how much agreement is achievable.

### 5.3 Metrics per brief

| Area | Metric | How measured | Target (initial) |
| --- | --- | --- | --- |
| Phrases | Usable rate | Team rates each chosen phrase usable / not (3-point) | ≥ 80% usable |
| Phrases | Sense match | Does the phrase's top 10 sell what we sell? (yes/no) | ≥ 90% |
| Phrases | Gold overlap | Chosen phrase matches a gold or acceptable phrase (human-judged) | ≥ 1 of 3 per page |
| Phrases | Demand evidence valid | Evidence type is numeric or GSC for ≥ 1 phrase | ≥ 70% of pages |
| Must-cover | Precision | Team: "would add this to the page" | ≥ 70% |
| Must-cover | Recall vs gold | Share of gold topics found (embedding match ≥ 0.92, then human check) | ≥ 60% |
| Noise | False-noise rate | Sample 20 topics marked noise per page; team checks | ≤ 15% |
| Gaps | Relevance | Team: relevant and answerable by this page | ≥ 80% |
| Gaps | Code re-count | Gap covered by < 20% of competitors (PLAN) | 100% |
| Gaps | Duplicates | Pairs with cosine ≥ 0.92 | 0 |
| Snippet | Checks pass | Width, length (code) | 100% |
| Snippet | Preference | Team prefers suggested over current title (URL pages) | ≥ 60% |
| Draft | Unsupported claims | Human review of 5 drafts + verifier (A2) per sentence | ≤ 1 per draft |
| Draft | Filler sections | Sections > 30% placeholders | 0 |
| Intent | Warning correct | Team agrees with the warning (or its absence) | ≥ 85% |
| Run | Quality gates | Share of eval runs flagged `needs_review` | report only; investigate each |

### 5.4 Stability tests

- 5 pages × 3 runs with the LLM cache disabled: Jaccard of chosen phrases ≥ 0.67; Jaccard of must-cover topics ≥ 0.6; score standard deviation ≤ 5 points.
- Same 5 pages × 2 runs with the cache enabled: identical briefs.

### 5.5 Cost and latency budgets

- LLM cost per run ≤ $0.05 (today $0.018 to $0.041). Search calls per run ≤ 12 (today ~16). Suggest calls per run ≤ 40.
- Latency p50 ≤ 90 s, p95 ≤ 180 s (today 97 to 190 s).
- Every eval report prints these next to quality metrics, so a quality gain that doubles cost is visible.

### 5.6 Using an LLM as judge

LLM judges are useful for pre-screening (for example the unsupported-sentence verifier), but they show position, verbosity and self-preference biases and agree with humans at roughly the level humans agree with each other only on some tasks [42][56]. Rules: use a model from a different family than the writer; judge yes/no rubric items, not overall quality; calibrate against the team's labels on at least 50 items (target kappa ≥ 0.6) before trusting it for a metric.

### 5.7 Outcome checks (optional, later)

For eval pages whose changes are published, record Search Console impressions, clicks and average position for the chosen phrases for 28 days before and 8 to 12 weeks after [12]. Treat this as a sanity check, not a verdict: rankings move for many reasons (PRD §10.6).

### 5.8 Model and embedding bake-offs

Keep the PLAN bake-offs, but run them on the replay harness so each candidate model is compared on identical inputs. Include "seeds on the bulk model" (E4) and "draft on the bulk model" as explicit variants.

---

## 6. Open questions and decisions for the owner

1. **Serper and Bing keys:** can someone sign up today? (Serper: 2,500 free queries; Bing: needs one verified site, for example gurzu.com.) This is the highest-value, zero-cost change.
2. **Search Console mode:** will you request CEO approval now (PL3)? It gives real Google demand for existing pages and is the only free way to measure outcomes.
3. **Unofficial Google suggest:** do you accept the terms risk (A8), or should it be limited to a small number of calls per run with Bing as the main source?
4. **Gemini grounding:** the terms as retrieved forbid caching and analysing grounded results (A13, [3]). Do you agree to remove it from the SERP path once Serper is in place, and to stop the run with a clear message when Serper credits run out? If more SERP volume is needed after that, is about $1 per 1,000 Serper queries acceptable, or Brave's roughly 1,000 free queries a month (card required, not Google)?
5. **Client data:** is it acceptable to send unpublished client copy to DeepSeek and to Gemini's free tier (A11)? If not: paid Gemini key for embeddings, a notice in the UI, and a retention period for runs.
6. **The suggested draft:** keep it on by default, or make it opt-in until the 5-draft review passes (M11)? Should the docs change from "never rewrites the page" to "suggests a draft the team edits"?
7. **Benchmark for the blind review:** free trial of a commercial tool, human-written briefs, or both (PL2)?
8. **Phase 2 agent:** agree to drop it unless evals show a specific failure it would fix (PL1)?
9. **Who is the user in 3 months:** only Gurzu staff on one machine, or several team members through a shared server? This decides when E8 (auth, job worker, deployment) is needed.

---

## 7. References

References are listed in the order they are first cited. "Accessed" is the date the source was checked for this review.

1. Google Search Central, "Creating helpful, reliable, people-first content", last updated 10 Dec 2025. https://developers.google.com/search/docs/fundamentals/creating-helpful-content Accessed 24 Sep 2026.
2. Google Search Central, "Spam policies for Google web search" (keyword stuffing, scaled content abuse), last updated 28 Aug 2026. https://developers.google.com/search/docs/essentials/spam-policies Accessed 24 Sep 2026.
3. Google, "Gemini API Additional Terms of Service" (Grounded Results, Search Suggestions, Unpaid Services), last modified 28 Apr 2026. https://ai.google.dev/gemini-api/terms. Quotes were retrieved through a summarising fetch; confirm the exact wording on the live page before acting. Accessed 24 Sep 2026.
4. Anthropic, "Building effective agents", Dec 2024. https://www.anthropic.com/research/building-effective-agents (already cited in ARCHITECTURE §11; not re-checked for this review).
5. Google Search Central, "Influencing your title links in search results", last updated 10 Dec 2025. https://developers.google.com/search/docs/appearance/title-link Accessed 24 Sep 2026.
6. Google Search Central, "Control your snippets in search results", last updated 20 Apr 2026. https://developers.google.com/search/docs/appearance/snippet Accessed 24 Sep 2026.
7. Google Search Central, "AI features and your website", last updated 10 Dec 2025. https://developers.google.com/search/docs/appearance/ai-features Accessed 24 Sep 2026.
8. Google Search Central Blog (M. Cutts), "Google does not use the keywords meta tag in web ranking", 21 Sep 2009 (banner confirms it still applies). https://developers.google.com/search/blog/2009/09/google-does-not-use-keywords-meta-tag Accessed 24 Sep 2026.
9. Google Search Help, "How Google autocomplete predictions work" (undated). https://support.google.com/websearch/answer/7368877 ; and D. Sullivan, "How Google autocomplete predictions are generated", The Keyword, 8 Oct 2020. https://blog.google/products/search/how-google-autocomplete-predictions-work/ Accessed 24 Sep 2026.
10. Microsoft Learn, Bing Webmaster API: "GetKeywordStats" and "GetRelatedKeywords" (weekly impressions); "Getting access to the Bing Webmaster Tools API", updated 13 Oct 2022. https://learn.microsoft.com/en-us/dotnet/api/microsoft.bing.webmaster.api.interfaces.iwebmasterapi.getkeywordstats?view=bing-webmaster-dotnet ; https://learn.microsoft.com/en-us/bingwebmaster/getting-access Accessed 24 Sep 2026.
11. Google Search Central Blog, "Introducing the Google Trends API (alpha)", 24 Jul 2025. https://developers.google.com/search/blog/2025/07/trends-api ; status page https://developers.google.com/search/apis/trends (still accepting alpha applications). Accessed 24 Sep 2026.
12. Google, "Search Analytics: query" (Search Console API), last updated 11 Aug 2026. https://developers.google.com/webmaster-tools/v1/searchanalytics/query ; "Usage limits", updated 28 Aug 2025, https://developers.google.com/webmaster-tools/limits ; pricing (free), https://developers.google.com/webmaster-tools/pricing Accessed 24 Sep 2026.
13. Google AI for Developers, "Grounding with Google Search", last updated 23 Sep 2026. https://ai.google.dev/gemini-api/docs/google-search . On redirect URIs: python-genai issue #1512 (14 Oct 2025), https://github.com/googleapis/python-genai/issues/1512 (no official expiry stated). Accessed 24 Sep 2026.
14. Serper.dev home page (2,500 free queries, PAA and related searches in responses). https://serper.dev/ . Price tiers from secondary sources (about $1 per 1,000; 2 credits above 10 results): https://coldiq.com/blog/serper-pricing (2026). Medium confidence on prices. Accessed 24 Sep 2026.
15. Brave, "Brave Search API" (plans: $5 per 1,000 requests with $5 monthly free credit). https://brave.com/search/api/ ; removal of the free tier in Feb 2026 reported at https://www.implicator.ai/brave-drops-free-search-api-tier-puts-all-developers-on-metered-billing/ Accessed 24 Sep 2026.
16. Tranco, "Methodology" (providers: CrUX, Cloudflare Radar, Farsight, Majestic, Umbrella; 30-day Dowdall average). https://tranco-list.eu/methodology ; V. Le Pochat et al., "Tranco: A Research-Oriented Top Sites Ranking Hardened Against Manipulation", NDSS 2019, https://tranco-list.eu/assets/tranco-ndss19.pdf Accessed 24 Sep 2026.
17. Ahrefs Help, "What does KD stand for in Keywords Explorer?" (undated). https://help.ahrefs.com/en/articles/72265-what-does-kd-stand-for-in-keywords-explorer Accessed 24 Sep 2026.
18. Open PageRank (now run by Keywords Everywhere; free 30K domains/month; computed from Common Crawl). https://openpagerank.keywordseverywhere.com/ . Terms may change. Accessed 24 Sep 2026.
19. Common Crawl, host- and domain-level web graphs (harmonic centrality and PageRank), release cc-main-2026-apr-may-jun. https://data.commoncrawl.org/projects/hyperlinkgraph/cc-main-2026-apr-may-jun/index.html ; tools: https://github.com/commoncrawl/cc-webgraph Accessed 24 Sep 2026.
20. Google, "Search Quality Rater Guidelines" (General Guidelines), 11 Sep 2025, §4.6.5 to 4.6.6. https://guidelines.raterhub.com/searchqualityevaluatorguidelines.pdf Accessed 24 Sep 2026.
21. Search Engine Land, "Content scoring tools work, but only for the first gate in Google's pipeline", about Feb 2026. https://searchengineland.com/content-scoring-tools-work-but-only-for-the-first-gate-in-googles-pipeline-469871 (page blocked automated fetch; claims taken from summaries; medium-low confidence). Accessed 24 Sep 2026.
22. S. Q. Ong, Ahrefs, "Do Higher Content Scores Mean Higher Google Rankings?", updated 21 May 2025. https://ahrefs.com/blog/seo-content-score-study/ Accessed 24 Sep 2026.
23. S. Robertson and H. Zaragoza, "The Probabilistic Relevance Framework: BM25 and Beyond", Foundations and Trends in IR 3(4), 2009. https://doi.org/10.1561/1500000019 (k1 range 1.2 to 2.0 as commonly cited; medium confidence). Accessed 24 Sep 2026.
24. Zyppy, "Google Rewrites 61% of Page Title Tags" (80,959 titles), page updated 14 May 2026. https://zyppy.com/seo/google-title-rewrite-study/ ; J. McAlpin, Search Engine Land, "Google changed 76% of title tags in Q1 2025", May 2025, https://searchengineland.com/google-changed-76-of-title-tags-in-q1-2025-heres-what-that-means-454847 Accessed 24 Sep 2026.
25. Ahrefs, "How Often Does Google Rewrite Meta Descriptions?", 9 Oct 2020 (62.78%). https://ahrefs.com/blog/meta-description-study/ ; Portent, 10 Sep 2020 (68% desktop, 71% mobile), https://portent.com/blog/seo/how-often-google-ignores-our-meta-descriptions.htm . Both are old. Accessed 24 Sep 2026.
26. Google Search Central, "Google Search's guidance on using generative AI content on your website", last updated 10 Dec 2025. https://developers.google.com/search/docs/fundamentals/using-gen-ai-content Accessed 24 Sep 2026.
27. Google Search Central, "Optimizing your website for generative AI features on Google Search", added 15 May 2026, updated 10 Jul 2026. https://developers.google.com/search/docs/fundamentals/ai-optimization-guide Accessed 24 Sep 2026.
28. P. Aggarwal, V. Murahari, T. Rajpurohit, A. Kalyan, K. Narasimhan, A. Deshpande, "GEO: Generative Engine Optimization", KDD 2024. https://arxiv.org/abs/2311.09735 Accessed 24 Sep 2026.
29. O. Martinez, "Optimizing Visibility in Generative Engines: A Critical Survey of Generative Engine Optimization (2023–2026)", arXiv preprint, Jul 2026. https://arxiv.org/abs/2607.14035 (single-author preprint; medium confidence). Accessed 24 Sep 2026.
30. J. Schulte, M. Bleeker, P. Kaufmann, "Don't Measure Once: Measuring Visibility in AI Search (GEO)", arXiv preprint, Apr 2026. https://arxiv.org/abs/2604.07585 Accessed 24 Sep 2026.
31. L. Linehan, Ahrefs, "38% of AI Overview citations rank in the top 10" (863K SERPs), 2 Mar 2026. https://ahrefs.com/blog/ai-overview-citations-top-10 ; see also BrightEdge (overlap 32% to 55%, May 2024 to Sep 2025), https://www.brightedge.com/resources/weekly-ai-search-insights/rank-overlap-after-16-months-of-aio . Figures vary widely by method. Accessed 24 Sep 2026.
32. Google Search Central Blog, "Changes to HowTo and FAQ rich results", 8 Aug 2023. https://developers.google.com/search/blog/2023/08/howto-faq-changes ; FAQ rich result no longer shown from 7 May 2026 and docs removed 15 Jun 2026, per https://developers.google.com/search/updates Accessed 24 Sep 2026.
33. Google Search Central Blog, "Simplifying the search results page", 12 Jun 2025. https://developers.google.com/search/blog/2025/06/simplifying-search-results ; follow-up 5 Nov 2025, https://developers.google.com/search/blog/2025/11/update-on-our-efforts Accessed 24 Sep 2026.
34. Google Search Central, "How Google interprets the robots.txt specification", last updated 31 Aug 2026. https://developers.google.com/search/docs/crawling-indexing/robots/robots_txt Accessed 24 Sep 2026.
35. B. Atil et al., "Non-Determinism of 'Deterministic' LLM Settings", arXiv 2408.04667, 2024 (v5 Apr 2025). https://arxiv.org/abs/2408.04667 Accessed 24 Sep 2026.
36. H. He, Thinking Machines Lab, "Defeating Nondeterminism in LLM Inference", 10 Sep 2025. https://thinkingmachines.ai/blog/defeating-nondeterminism-in-llm-inference/ Accessed 24 Sep 2026.
37. DeepSeek API Docs, "Thinking Mode" (temperature has no effect). https://api-docs.deepseek.com/guides/thinking_mode Accessed 24 Sep 2026.
38. X. Wang et al., "Self-Consistency Improves Chain of Thought Reasoning in Language Models", ICLR 2023. https://arxiv.org/abs/2203.11171 Accessed 24 Sep 2026.
39. S. Dhuliawala et al., "Chain-of-Verification Reduces Hallucination in Large Language Models", 2023. https://arxiv.org/abs/2309.11495 Accessed 24 Sep 2026.
40. S. Min et al., "FActScore: Fine-grained Atomic Evaluation of Factual Precision in Long Form Text Generation", EMNLP 2023. https://arxiv.org/abs/2305.14251 Accessed 24 Sep 2026.
41. N. F. Liu, T. Zhang, P. Liang, "Evaluating Verifiability in Generative Search Engines", Findings of EMNLP 2023. https://arxiv.org/abs/2304.09848 Accessed 24 Sep 2026.
42. L. Zheng et al., "Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena", NeurIPS 2023 Datasets and Benchmarks. https://arxiv.org/abs/2306.05685 Accessed 24 Sep 2026.
43. K. Greshake et al., "Not what you've signed up for: Compromising Real-World LLM-Integrated Applications with Indirect Prompt Injection", 2023. https://arxiv.org/abs/2302.12173 Accessed 24 Sep 2026.
44. OWASP GenAI Security Project, "LLM01:2025 Prompt Injection" (OWASP Top 10 for LLM Applications 2025). https://genai.owasp.org/llmrisk/llm01-prompt-injection/ Accessed 24 Sep 2026.
45. Google Search Central Blog, "Update on the Autocomplete API", Jul 2015. https://developers.google.com/search/blog/2015/07/update-on-autocomplete-api ; reported by Search Engine Journal, https://www.searchenginejournal.com/google-to-restrict-access-to-autocomplete-api-on-august-10th/137404/ Accessed 24 Sep 2026.
46. Google, "Google Terms of Service", effective 30 Jul 2026 (section "Don't abuse our services"). https://policies.google.com/terms Accessed 24 Sep 2026.
47. M. Koster, G. Illyes, H. Zeller, L. Sassman, "RFC 9309: Robots Exclusion Protocol", IETF, Sep 2022, §2.3.1.3 to 2.3.1.4. https://www.rfc-editor.org/rfc/rfc9309.html Accessed 24 Sep 2026.
48. OWASP Cheat Sheet Series, "Server Side Request Forgery Prevention Cheat Sheet". https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html Accessed 24 Sep 2026.
49. OWASP Top 10:2021, "A10 Server-Side Request Forgery (SSRF)". https://owasp.org/Top10/A10_2021-Server-Side_Request_Forgery_%28SSRF%29/ Accessed 24 Sep 2026.
50. DeepSeek, "Privacy Policy", last updated 10 Feb 2026. https://cdn.deepseek.com/policies/en-US/deepseek-privacy-policy.html Accessed 24 Sep 2026.
51. DeepSeek API Docs, "Models & Pricing". https://api-docs.deepseek.com/quick_start/pricing (prices retrieved through a summarising fetch; re-check before hard-coding). Accessed 24 Sep 2026.
52. Google AI for Developers, "Gemini Developer API pricing" (grounding: 2.5 Flash free tier up to 500 RPD; Gemini 3 no free grounding), last updated 23 Sep 2026. https://ai.google.dev/gemini-api/docs/pricing ; "Rate limits", updated 2 Sep 2026, https://ai.google.dev/gemini-api/docs/rate-limits Accessed 24 Sep 2026.
53. DeepSeek API Docs, "JSON Output". https://api-docs.deepseek.com/guides/json_mode Accessed 24 Sep 2026.
54. DeepSeek API Docs, "Change Log" (legacy names deepseek-chat and deepseek-reasoner announced for discontinuation on 24 Jul 2026; deepseek-flash introduced 10 Sep 2026). https://api-docs.deepseek.com/updates/ (retrieved through a summarising fetch; conflicts with successful runs on 24 Sep 2026, see E10). Accessed 24 Sep 2026.
55. SparkToro, "New research: AIs are highly inconsistent when recommending brands or products". https://sparktoro.com/blog/new-research-ais-are-highly-inconsistent-when-recommending-brands-or-products-marketers-should-take-care-when-tracking-ai-visibility/ (already cited in ARCHITECTURE §11; not re-checked for this review).
56. J. Gu et al., "A Survey on LLM-as-a-Judge", arXiv 2411.15594, Nov 2024 (revised Oct 2025). https://arxiv.org/abs/2411.15594 Accessed 24 Sep 2026.

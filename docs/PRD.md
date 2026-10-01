# PRD: SEO and AI Search Optimization Engine

Status: problem definition agreed; implementation starting. Last updated: 28 September 2026 (Keyword Gap added, §5.11).

## 1. Summary

The engine takes the text of one web page and tells the team how to make that page rank higher on Google and get cited by AI answer engines (ChatGPT, Claude, Perplexity, Google AI Overviews). It works out which search phrases the page should target, studies the pages that already win for those phrases, and returns a brief: title tag options, a meta description, topics the page must cover, gaps it can fill, suggested headings, an intent warning and a coverage score.

## 2. Problem

Today the team researches every page by hand: guessing search phrases, reading competitor pages one by one, noting what they all cover and what they miss, then writing a title, description and content plan. The work is slow, inconsistent and repeated for every page, while pages such as emitii.com stay buried for phrases like "client project workspace".

## 3. Users

- **Primary user:** a Gurzu team member who wants a specific page to rank higher.
- **Sites:** Gurzu's own sites and client sites, in any industry.
- **Quality bar:** robust and site-agnostic, built to product quality. Productising (accounts, billing, multi-customer) comes later and is out of scope now.

## 4. Inputs

| Mode | Input | Status |
| --- | --- | --- |
| Content-only (default) | The pasted text of one page. No URL, no site name, no search phrase. | In scope now |
| URL import | A page URL; the engine fetches the readable text into the text box for the user to review, then runs as content-only | In the web UI (24 Sep 2026) |
| Search Console | The page's real Google queries and positions from Search Console, replacing phrase guessing | Proposed; needs CEO approval |
| Keyword Gap | Our domain plus 1 to 4 competitor domains (§5.11) | In progress on `feature/keyword-gap` |

## 5. Outputs (the brief)

1. **Target phrases:** inferred by the engine, with monthly searches, difficulty and a one-line reason. Chosen automatically or approved by a user (a setting).
2. **Title tag options:** 2 to 3, under about 600 pixels (about 50 to 60 characters), main phrase first, brand last.
3. **Meta description:** under about 158 characters, payoff in the first 120.
4. **Must-cover topics:** topics most competitor pages cover and ours does not, filtered to remove boilerplate, competitor brand names and off-intent terms. Ordered by "you never mention this" first.
5. **Gaps:** topics almost no competitor covers but searchers ask about. The engine names each gap and the question it answers; the team supplies the real facts. The engine never invents facts.
6. **Suggested headings.**
7. **Intent warning:** raised when the ranking pages are a different page type from ours (for example "best tools" lists vs our product page). The brief is still delivered.
8. **Coverage score (0 to 100):** shown with its arithmetic, plus a pass/fail checklist (phrase in title and H1, title width, description length, stuffing warning).
9. **Suggested content (added 24 Sep 2026):** a full SEO draft of the page: one H1 with the main phrase, an intro that uses it in the first 100 words, H2 sections that bring in the must-cover topics, an FAQ answering the gaps, and a call to action. It uses only facts from the page; anything else is an `[ADD: …]` placeholder. Code checks it against the same standards (phrase placement, keyword density, length, placeholders). The team reviews, fills placeholders and publishes.
10. **Readable report:** the brief and draft download as a Word document (.docx), laid out like the action plan.

**Not an output:** a published or silently changed page. The draft is a suggestion the team edits.

### 5.11 Keyword Gap (added 28 Sep 2026)

A second, separate feature. The user enters our domain and 1 to 4 competitor domains. The engine reads each site's sitemap, finds the keywords the sites target, checks their Google positions, and returns:

1. **Gap table:** each keyword with every domain's position (top 20 by default), Bing searches, a rough Google estimate, a difficulty band and intent, sorted into Semrush's categories (Shared, Missing, Weak, Strong, Untapped, Unique).
2. **Estimated visits** per keyword and domain: rough Google searches × click rate at that position. Always labelled as an estimate.
3. **Top keywords to add:** Missing, Weak and Untapped keywords that fit our business, ordered by business fit, then competitor proof (the click rates at the competitors' positions), then lower difficulty, with Bing searches only breaking ties, each with a reason and, where Bing has numbers, a traffic lift.
4. **Competitor brand keywords** listed separately, never as keywords to add.

It checks about 60 keywords per analysis, not a full index like Semrush, and says so in the UI. Plan, research and sources: `docs/KEYWORD-GAP-PLAN.md`.

### 5.12 Site Snapshot (added 29 Sep 2026)

A third feature. The user enters one domain. The engine returns one page that summarises the site in search:

1. **Site facts:** a link score (Open PageRank, 0 to 10, with its referring-domains count), popularity (Tranco rank and Majestic Million referring subnets), speed for real visitors (Chrome UX Report, pass or fail per Core Web Vital on phones), site age (registration date and first Wayback capture, both labelled), and the number of pages in the sitemap.
2. **Search sample:** about 30 keywords the site's pages target, their Google positions (top 20), grouped as 1–3, 4–10, 11–20 and not in the top 20, with estimated visits labelled as rough, and the top pages by estimated visits.
3. **Competitors on Google:** sites that appear most often in the top 10 for the site's keywords, with a button that opens Keyword Gap filled in.
4. **Technical basics:** HTTPS, redirects, robots.txt, sitemap, homepage title and description length, `noindex`, canonical.

It never shows totals that free data cannot support (total organic traffic, total keyword count, backlink lists), and it names the source of every number. Plan, research and sources: `docs/SITE-SNAPSHOT-PLAN.md`.

## 6. Search surfaces

- **Google** (organic results, United States by default).
- **AI answer engines** (phase 3): pages they cite for the same phrase, measured as citation frequency across repeated samples, never as a rank. Google states that no special optimization is needed for AI Overviews or AI Mode, so AI sampling is useful but not core, and is scheduled after the Google version works.
- **Competitor pool mode** (a setting): Google only, merged pool of Google and AI-cited pages tagged by source (default once phase 3 ships), or separate analysis per surface.

## 7. Settings

| Setting | Controls | Default |
| --- | --- | --- |
| Phrases per run | How many target phrases are analysed | 3 |
| Phrase selection | Automatic, or pause for user approval | Automatic |
| Competitor pages per phrase | How many results are fetched before filtering (5 to 10 kept) | 20 |
| Search country | Whose Google results are used | United States |
| Site strength | Difficulty ceiling for phrases: new, growing, established | New |
| Search surfaces | Google, plus which AI engines | Google only until phase 3 |
| Competitor pool mode | Google only, merged and tagged, or per surface | Google only until phase 3 |
| AI samples | Phrasings and runs per AI engine | 2 engines x 30 samples |
| Time budget | Max run time; the engine reduces depth instead of failing | 5 minutes |
| Cost budget | Max spend per run | To be set after phase 1 |

## 8. Success measures

| Measure | Type | When it shows |
| --- | --- | --- |
| Hours of manual research saved | Engine quality | After each run |
| Brief preferred over a paid tool in a blind team review | Engine quality | Phase 2 gate |
| Page ranks higher for target phrases | Outcome | Weeks to months later |
| More organic clicks | Outcome | Weeks to months later |
| Page cited in AI answers | Outcome | Varies by engine |

Outcome tracking is out of scope: the team checks rankings, clicks and citations manually.

## 9. Scope

**In scope:** content-only input, phrase discovery, Google competitor collection and analysis, the outputs above, global English search with US results by default, configurable settings. AI-engine sampling in phase 3.

**Out of scope for now:** page rewriting, outcome tracking, URL input, whole-site briefs (Keyword Gap compares whole domains, §5.11), other languages, country-by-country results, advice beyond words (schema markup, page structure blocks, author and date signals, crawler access), accounts and billing.

## 10. SEO principles the engine follows

1. **Shared topics are required, not avoided.** Topics most winning pages cover signal relevance; the risk is repetition (keyword stuffing), not coverage.
2. **Standing out means new information, not rare words.** Gaps are topics and facts competitors lack.
3. **Title tag matters most; meta description drives clicks, not rank.**
4. **The keywords meta tag is ignored by Google** and is never generated.
5. **Intent comes before keywords.** If Google ranks a different page type, keywords alone rarely help.
6. **No guaranteed top spot.** Links and site authority also decide rankings; the engine makes content as strong as possible.

## 11. Risks

| Risk | Mitigation |
| --- | --- |
| Phrase discovery picks weak phrases | Gate every phrase on real volume and difficulty data; approval mode; Search Console mode |
| LLM invents gaps or miscounts | LLM proposes, code counts and verifies |
| Page cleaning fails on landing pages | Length check, headless browser fallback, test landing pages first |
| AI answers vary run to run | Report citation frequency across many samples, labelled "API sample" |
| Brief does not beat a paid tool | Blind review gate after phase 2; buy instead if we lose |
| Data vendor changes price or shuts an API | Every vendor behind one interface |

## 12. Open decisions

- [ ] CEO approval for Search Console as a second input mode
- [ ] Confirm AI-engine sampling moves to phase 3
- [ ] Approve a one-month paid SEO tool subscription as the phase 2 benchmark

## 13. Glossary

| Term | Meaning |
| --- | --- |
| Title tag | The `<title>` element; the clickable headline in Google |
| Meta description | The summary under the headline; affects clicks, not rank |
| SERP | Search engine results page |
| Search volume | Monthly searches for a phrase |
| Keyword difficulty | 0 to 100 estimate of how hard a phrase is to rank for |
| Search intent | What the searcher wants: learn, compare, buy, find a site |
| Must-cover topic | Covered by most competitors, missing from our page |
| Gap | Covered by almost no competitor, but searchers ask about it |
| GEO | Generative Engine Optimization: getting cited in AI answers |
| Striking distance | A page ranking about positions 4 to 20, where small edits can move it up |
| CTR | Click-through rate: the share of searchers who click a result at a given position |
| Keyword gap | Keywords competitors rank for where our site does not rank, or ranks lower (§5.11) |

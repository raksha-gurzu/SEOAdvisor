# Plan: Keyword Gap

| Item | Value |
| --- | --- |
| Status | Steps 0 to 9 complete except the owner's hand check of 5 positions. Review round, second review round and G13 complete (section 7a). |
| Branch | `feature/keyword-gap` |
| Last update | 29 September 2026 |
| Writing standard | ASD-STE100 Simplified Technical English, Issue 9 (see section 11) |

## 1. Rules for this plan

1. Start a step only after the owner approves it.
2. When the owner asks for a change, update this file first.
3. Do not commit or push changes. Commit only when the owner asks.
4. Validate each claim with a credible source. Section 10 lists the sources.

## 2. Goal

The user gives the URL of the user's website. The user also gives the URLs of 1 to 4 competitor websites. The tool then shows these data:

- The keywords that the competitors rank for, but our website does not rank for or ranks low for.
- The best keywords to add to our website, in order of opportunity.
- An estimate of the monthly visits that each keyword sends to each website.

Reference tools: Semrush Keyword Gap and Ahrefs Content Gap.

## 3. Decisions

| Question | Decision | Date |
| --- | --- | --- |
| Source of traffic data | Use a free estimate now. Put the data source behind one interface. A paid source can replace it later. | 28 Sep 2026 |
| Scope of comparison | Compare the full domain. Read the sitemap of each site. | 28 Sep 2026 |
| Number of competitors | 1 to 4 competitors, thus 5 domains maximum. Semrush uses the same limit. | 28 Sep 2026 |
| Plan format | Simplified Technical English (ASD-STE100) | 28 Sep 2026 |
| Q1 Google estimate | Show it (Bing × country ratio), labelled as rough, and use it for visits | 29 Sep 2026 |
| Q2 Depth | Top 20 | 29 Sep 2026 |
| Q3 Keywords | 60 for each analysis | 29 Sep 2026 |
| Q4 Serper fix | Fix `serper.py` for the brief feature and Keyword Gap | 29 Sep 2026 |
| Volume source (after D11) | Stay free. Show Bing numbers only where they exist. Other keywords show "too low to measure on Bing" and no visits. A paid source can come later through the same interface. | 29 Sep 2026 |
| Business fit | Check the fit (0 to 3) before the Google check. Fit 0 is never checked. Fit 1 only fills spare slots (`fill_min_fit`). | 29 Sep 2026 |
| Fit 1 keywords | Keep: they fill spare slots (all 60 slots used, approximately 120 credits). | 29 Sep 2026 |
| Step 3 live test | One full analysis (approximately 120 credits). | 29 Sep 2026 |
| Sidebar layout | A tool switch at the top of the sidebar (Briefs / Keyword gap). Each tool has its own "+ New" button and history. | 29 Sep 2026 |
| Low yield (G13) | Try a fix after the UI (Steps 6 to 9): a second pass with related searches from results where competitors rank. | 29 Sep 2026 |
| Order of "top keywords to add" (after D11) | Business fit first. Then competitor proof: how many competitors rank, and how high. Then how easy the results page is. Bing searches only break ties. | 29 Sep 2026 |
| Code guide | Restore it from `git stash@{0}` at Step 9, then add a chapter | 29 Sep 2026 |

## 4. Research summary

Confidence: **P** = primary source (vendor document, standard, original study). **S** = secondary source only. **C** = the sources do not agree.

### 4.1 Google rank data

| # | Finding | Conf. | Effect on the design |
| --- | --- | --- | --- |
| R1 | Google stopped the `&num=100` parameter in September 2025. One request now gives approximately 10 results. This is still true in 2026. | P | Each 10 positions of depth costs one more request. |
| R2 | Semrush and Ahrefs count a keyword as "ranking" in the top 100. | P | Our default depth is 20, not 100. Our label must say "not in top 20", not "does not rank". |
| R3 | Serper gives 2,500 free queries. Paid credits are valid for 6 months. Serper deducts credits only for successful responses. | P | Free budget: approximately 20 analyses at depth 20. |
| R4 | Live test, 28 Sep 2026: each request costs 1 credit and gives 10 results. `page: 2` gives 10 different results (0 overlap with page 1). | P (tested) | Depth 20 costs 2 credits for each keyword. |
| R5 | Live test: positions on page 2 start again at 1. | P (tested) | Absolute position = (page − 1) × 10 + position. |
| R6 | Our file `providers/serper.py` line 76 sends `num: 20`. Live test: `num: 20` gives only 10 results for 1 credit. | P (tested) | The current brief feature also has this problem. Step 3 corrects it. |
| R7 | The Google Terms and `google.com/robots.txt` do not permit automated queries to Google Search. | P | Use a licensed SERP API only. Do not scrape Google. |
| R8 | One results page shows the positions of all 5 domains. | P | The cost does not increase with the number of competitors. |
| R9 | Paid option: DataForSEO SERP costs $0.0006 for each page of 10 results (standard queue). The minimum deposit is $50. Its `stop_crawl_on_match` option stops when it finds the target domains. | P | Good paid option for depth 50 to 100 in the future. |
| R10 | Other free tiers: SerpApi 250 searches each month; SearchAPI.io 100 one time; Zenserp 50 each month. | P | SerpApi can be a monthly fallback. |
| R12 | Live test, 29 Sep 2026: 60 keywords at depth 20 gave 15 to 20 results each (average 19). Pages have approximately 9 results, and some repeat. | P (tested) | Say "the first 2 pages of Google". |
| R11 | Live test: two requests for the same query, a few seconds apart, gave results 5 and 7 in the opposite order. | P (tested) | A position is one snapshot. It can change by a few places. The UI must tell the user this. |

### 4.2 Search demand (volume)

| # | Finding | Conf. | Effect on the design |
| --- | --- | --- | --- |
| D1 | The Bing Webmaster API has `GetKeywordStats` and `GetRelatedKeywords`. Each row gives `Impressions` (exact match) and `BroadImpressions`. The API key needs one verified site. Microsoft publishes no quota. | P | Use Bing exact-match impressions as the demand number. |
| D2 | Microsoft does not define "impression" exactly. Bing help calls it the search volume on Bing. | S | Label it "Bing searches/month (approx.)". |
| D11 | Live test, 29 Sep 2026: of 222 keywords about client portals and workflow software, Bing had data for 13. Only 5 had 10 or more searches each month. Google autocomplete showed that most of the other keywords have searches. | P (tested) | Bing cannot give visits for most B2B keywords. The owner chose honest labels (section 3). |
| D12 | Live test, 29 Sep 2026: Bing sends HTTP 400 "ThrottleUser" after approximately 126 fast calls. The limit stopped after a few minutes. | P (tested) | Wait 5 s, then 20 s. Then stop calls to Bing for the run and show "not measured". |
| D10 | Live test, 28 Sep 2026: `GetKeywordStats` gives one row for each week, oldest first, for 25 weeks. Bing does not send weeks with 0 impressions. The week of 22 Aug 2026 was also missing for a keyword with approximately 500 searches each week. | P (tested) | Divide by the weeks in the window, not by the rows. The old code in `bing.py` divided by the rows. It showed 4 searches/month for a keyword with 1 search in 12 weeks. This bug is now fixed. |
| D3 | StatCounter CSV, August 2026, US, all platforms: Google 86.01%, Bing 8.99%. The ratio is 9.57. On desktop the ratio is 6.4. On mobile the ratio is 52. Other countries: section 5.3. | P | A ratio of approximately 10 is correct for the US on average. |
| D4 | No source measures the Bing to Google ratio for each keyword. DataForSEO uses 0.1 only as an assumed example ("Let's assume it's 0.1 or 10%"). StatCounter (D3) is the only measured basis. StatCounter counts clicks to sites, not searches. | P | The ratio is an estimate. The Google estimate can be wrong by 2 to 3 times or more for one keyword (D3, D5). |
| D5 | Most Bing searches (approximately 70%) are on desktop. Bing users are older than Google users. | S | Mobile topics and topics for young users show low numbers on Bing. |
| D6 | Google Keyword Planner shows ranges, not exact numbers, for accounts with low spend. API access needs Basic access and brand verification. | P / C | Not a free source for us. |
| D7 | The Google Trends API is in alpha. It gives only relative interest, not volumes. | P | Not useful now. |
| D8 | The Search Console API gives real clicks, impressions and position, but only for our own site. It needs OAuth. | P | Possible future option. The CEO approval for Search Console is still open. |
| D9 | Google says that autocomplete shows real searches. No study links autocomplete to a volume. | P | Use autocomplete as "people search this". Do not show it as a number. |

### 4.3 Traffic estimate

| # | Finding | Conf. | Effect on the design |
| --- | --- | --- | --- |
| T1 | Semrush and Ahrefs calculate traffic for each keyword as search volume × average CTR at the position. | P | Our formula is correct. |
| T2 | Advanced Web Ranking (AWR), July 2026, Google US, desktop: position 1 = 20.0%, position 2 = 10.4%, position 3 = 3.9%. The data covers positions 1 to 20 and changes each month. | P | Use AWR as the default CTR table (section 5.4). |
| T3 | Old CTR numbers (28% to 40% at position 1) are from before AI Overviews. First Page Sage 2026 gives 7.1% at position 1, but its method is not public. | P | Do not use these numbers. |
| T4 | An AI Overview decreases the CTR at position 1 by approximately 35% to 60%. Sources: Ahrefs 2025 and 2026, Seer 2026, Pew 2025, AWR 2026, and a field experiment in 2026. | P | Show our traffic as an upper limit. |
| T5 | Live test: Serper gave no AI Overview field for 3 queries, including "how does compound interest work". DataForSEO returns an `ai_overview` item. | P (tested) | In free mode, the tool cannot detect AI Overviews. Visits are an upper limit. |
| T6 | Semrush and Ahrefs traffic estimates have a median error of approximately 50% to 68% against real Search Console data. | P | Use our numbers to compare keywords, not to forecast visits. |
| T7 | Ahrefs "Traffic Potential" is the total traffic of the page at position 1. Moz "Traffic Lift" is the traffic that you get when you rank above a competitor. | P | We cannot calculate Ahrefs Traffic Potential. We use a "traffic lift" that is similar to Moz (section 5.5). |
| T8 | Ahrefs tells users to remove competitor brand names from a gap list. Semrush has a "branded" filter. | P | Remove competitor brand keywords from "keywords to add". Show them in a separate list. |

### 4.4 Gap method

| # | Finding | Conf. | Effect on the design |
| --- | --- | --- | --- |
| G1 | Semrush has these gap categories: Shared, Missing, Weak, Strong, Untapped, Unique. The categories overlap. | P | Use the Semrush definitions (section 5.6). |
| G2 | Semrush "Top Opportunities" (2020 rule): the keywords with the highest volume that your domain does not rank for. The current rule is not public. | S | Our rule is different. The UI must tell the user how our rule works. |
| G3 | Ahrefs asks: "how well does our product solve this problem?" It gives a score from 0 to 3 ("business potential"). Semrush and Ahrefs both tell users to select relevant keywords first. | P | The LLM gives a business fit score from 0 to 3. Show only keywords with a score of 2 or 3 as opportunities. |
| G4 | Ahrefs advice: at least 2 competitors in the top 10, volume 20 or more, difficulty 30 or less. Semrush advice: difficulty 0 to 49 for new domains. | P | Use these values as default filters. |
| G5 | Ahrefs and Semrush calculate keyword difficulty from the backlinks of the top pages. Tranco measures domain popularity, not authority. No study connects Tranco rank with position. | P | Show our difficulty as a rough band ("Low / Medium / High, estimate"), not as a precise number. |
| G6 | Sitemaps: maximum 50,000 URLs and 50 MB in each file. robots.txt can give the sitemap URL. Google does not use `priority` or `changefreq`. Common paths: `/sitemap.xml`, `/sitemap_index.xml`, `/wp-sitemap.xml`. | P | Read robots.txt first. Then try the common paths. |
| G7 | 65% to 85% of top-10 pages have the keyword in the title. | S | Titles and H1s are a good source for the main keyword of each page. |
| G8 | A page at position 1 also ranks for approximately 400 to 1,000 other keywords. | S | Our method finds the main keyword of each page. It does not find the long tail. |
| G9 | LLM keyword extraction is approximately as good as TF-IDF or TextRank. No study tests "find the query that a page targets". | P | The SERP check tests each keyword. A bad keyword costs one query, but does not give a false result. |
| G10 | Semrush finds search intent from SERP features and query words. Ahrefs finds it from the type of the top pages. | P | Find intent from the page types in the top 10. The code for this is `page_types.py`. |
| G11 | Keyword clustering: keywords with 3 or more of the same top-10 URLs go into one group. The default of Keyword Insights is 3. | P | Group keywords with the SERP data that we already have. This is free. |
| G12 | Semrush, Ahrefs and Moz show these items: tabs with counts, a Venn chart that filters the table, one position column for each domain, the best position in green, the URL on hover, filters, intent badges, and CSV export. | P | Use these UI patterns (Step 8). |

## 5. Design

### 5.1 Flow

```text
Our domain + 1 to 4 competitor domains
  1. Read sites      robots.txt and sitemap. Select up to 30 pages for each site.
                     Keep the title, H1, H2s and meta description.
  2. Find keywords   The LLM reads the titles and headings of each site.
                     It gives the search phrases that each page targets.
                     Add Google autocomplete and Bing related keywords.
                     Remove duplicates. Keep 60 keywords, balanced across the sites.
  3. Check Google    Serper, pages 1 and 2 (top 20) for each keyword.
                     Record the position and the URL of each domain.
  4. Measure         Bing searches, rough Google searches, difficulty band,
                     intent, SERP features, estimated visits for each domain.
  5. Compare         Gap category for each keyword. Business fit (LLM, 0 to 3).
                     Order: fit, competitor proof, difficulty. Traffic lift. Brand keywords in a separate list.
```

- The code counts and calculates. The LLM only gives names and judgments (CLAUDE.md rule 1).
- Each input and output is a Pydantic model (rule 2).
- The tool keeps each call in the daily cache (rule 4).
- The tool uses one difficulty source in each run (rule 7).
- The tool obeys robots.txt (rule 8).
- All limits are in `config.py` (rule 9).
- Only LLM calls cost money (rule 11).
- The brief agent keeps its 5 tools. Keyword Gap is a separate fixed pipeline.

### 5.2 Cost for each analysis

The cost is keywords × pages. The number of domains does not change it (R8). Each page costs 1 credit. The Step 0 live test confirmed this (R4).

| Depth | Serper credits (60 keywords) | Analyses from 2,500 free credits |
| --- | --- | --- |
| Top 10 | 60 | 41 |
| **Top 20 (default)** | **120** | **20** |
| Top 50 | 300 | 8 |
| Top 100 | 600 | 4 |

- The tool does not request page 2 when all 5 domains are on page 1.
- The tool stops when a page is empty.
- The LLM cost is a few US cents for each analysis.

### 5.3 Demand numbers

1. The tool shows "Bing searches/month (approx.)". This is the Bing exact-match impressions (D1, D2).
2. When Bing gives 0, the tool shows "too low to measure on Bing". It does not show 0.
3. When there is no Bing key, the tool shows "Searched on Google" for keywords in autocomplete. For other keywords, it shows "No demand data".
4. The rough Google estimate = Bing searches × country ratio. The ratio = Google share ÷ Bing share (StatCounter CSV, August 2026, all platforms, D3). A country without shares in `config.py` shows no Google estimate.

   | Country | Google % | Bing % | Ratio |
   | --- | --- | --- | --- |
   | US | 86.01 | 8.99 | 9.6 |
   | GB | 91.75 | 5.66 | 16.2 |
   | CA | 85.60 | 9.61 | 8.9 |
   | AU | 87.53 | 9.45 | 9.3 |
   | IN | 97.71 | 1.26 | 77.5 |
   | NP | 96.30 | 2.74 | 35.1 |
   | DE | 88.41 | 5.88 | 15.0 |
   | FR | 88.67 | 5.17 | 17.2 |
   | NZ | 88.31 | 8.22 | 10.7 |
   | IE | 93.97 | 3.55 | 26.5 |
   | SG | 92.57 | 3.66 | 25.3 |

   Note: in India and Nepal, Bing has a very small share. The estimate there is weak.
5. The tool sorts by Bing searches, not by the Google estimate (D4).
6. Live data (D11): most keywords have no Bing number. Such keywords show "too low to measure on Bing" and no visits. They are not shown as 0. A keyword that Bing could not measure because of the limit (D12) shows "not measured".

### 5.4 Default CTR table

Source: AWR, July 2026, Google US, desktop, all SERPs (T2). The code applies one rule: the CTR at a position cannot be more than the CTR at the position above it.

| Position | CTR | Position | CTR |
| --- | --- | --- | --- |
| 1 | 20.02% | 6 | 0.73% |
| 2 | 10.36% | 7 to 19 | 0.46% |
| 3 | 3.89% | 20 | 0.27% |
| 4 | 1.71% | Not in top 20 | 0 |
| 5 | 1.08% | | |

- Keep the table, its source and its date in `config.py`.
- Update the table each quarter.
- Estimated visits = rough Google searches × CTR at the position.

### 5.5 Traffic lift

Traffic lift = rough Google searches × (CTR at the best competitor position − CTR at our position). This is similar to Moz "Traffic Lift" (T7). It shows the visits that we can get when we reach the best competitor.

### 5.6 Gap categories

These are the Semrush definitions (G1). "Ranks" means "in the top N that we checked".

| Category | Rule |
| --- | --- |
| Shared | All 5 domains rank. |
| Missing | All competitors rank. Our domain does not rank. |
| Weak | Our domain ranks. At least 1 competitor ranks. All competitors that rank are above our domain. |
| Strong | Our domain ranks. At least 1 competitor ranks. Our domain is above all competitors that rank. |
| Untapped | At least 1 competitor ranks. Our domain does not rank. |
| Unique | Our domain ranks. No competitor ranks. |

- The categories overlap, as in Semrush. Missing is a part of Untapped.
- Keywords that no domain ranks for stay in the table with no category (the tab "No site ranks").

### 5.7 Top keywords to add

1. The tool starts with the Missing, Weak and Untapped keywords.
2. It removes competitor brand keywords (T8).
3. It keeps only keywords with a business fit of 2 or 3 (G3). A keyword that the fit check could not score counts as 2.
4. (Replaced on 29 Sep 2026 by the owner's order: business fit, then competitor proof, then lower difficulty, then Bing searches. Section 7, Step 5.) Old rule: it sorts by opportunity score = demand × winnability × gap weight.
   - Demand = log(1 + Bing searches). When there is no Bing data, an autocomplete keyword gets a small fixed value.
   - Note (29 Sep 2026): most keywords have no Bing data (D11). Thus demand gives almost no order. Step 5 must change this part of the score, for example with the business fit and the number of competitors that rank.
   - Winnability = 1 − difficulty ÷ 100. The UI shows the difficulty as a band (G5).
   - Gap weight: Missing = 1.0, Weak = 0.8, Untapped = 0.5 + 0.5 × (competitors that rank ÷ competitors).
5. The UI tells the user how the score works. No source publishes one standard formula (G3).

### 5.8 Limits that the UI must show

- "We checked 60 keywords from the pages of these 5 sites. Semrush checks millions of keywords." (G8)
- "Visits are rough estimates. Paid tools are also wrong by approximately 50%." (T6)
- "Search numbers come from Bing. The Google number is Bing × the country ratio (US: 9.6)." (D3, D4)
- "Bing has numbers for only a few of these keywords. The other keywords show 'too low to measure on Bing'." (D11)
- "AI Overviews are not checked. When Google shows one, clicks can be approximately half." (T4, T5)
- "Not in top 20" is different from "does not rank". (R2)
- "Competitor brand keywords are hidden (n)." (T8)

## 6. Open questions for the owner

On 29 Sep 2026 the owner accepted the recommendation for Q1 to Q4. The owner also decided: restore the code guide from the git stash at Step 9.

| # | Question | Recommendation |
| --- | --- | --- |
| Q1 | Can the tool show a rough Google estimate (Bing × 9.6 in the US) and use it for visits? Without it, the tool cannot show visits. | Yes, with the labels in section 5.8. |
| Q2 | Is top 20 the correct default depth? | Yes. Top 20 includes positions 11 to 20, where small changes can move a page to page 1. |
| Q3 | Is 60 keywords for each analysis correct? | Yes. This uses 120 credits and gives approximately 20 free analyses. |
| Q4 | Step 3 changes `providers/serper.py` (R6). This change also affects the current brief feature. Is this change approved? | Yes. The current brief feature probably gets only 10 results now. |

## 7. Steps

Each step waits for owner approval. Tick a step only when its "Done when" is true.

### Step 0: Documents, settings and live tests (complete)

- [x] Add Keyword Gap to `docs/PRD.md` as section 5.11.
- [x] Add Keyword Gap to `docs/ARCHITECTURE.md` as section 13.
- [x] Add the steps to `PLAN.md`.
- [x] Add a `GapSettings` block to `config.py`: keywords, pages for each site, competitors, depth, CTR table, country shares, score weights.
- [x] Add tests for `GapSettings` (`tests/test_gap_settings.py`, 27 tests).
- [x] Add the live test `python scripts/check_live.py serper_pages` (approximately 4 credits).
- [x] Owner: add `SERPER_API_KEY` to `.env`.
- [x] Owner: add `BING_WEBMASTER_API_KEY` to `.env`.
- [x] Live tests 1 and 2: run `python scripts/check_live.py serper_pages`. Record the credits and the result count of each request (R4). Record the AI Overview keys (T5).
- [x] Live test 3: run `python scripts/check_live.py bing` (D1). A bug in `bing.py` was found and fixed (D10).
- Done when: the documents are updated, the settings load, `pytest` passes, and the 3 test results are in section 9.

### Step 1: Site reader (`providers/sitemap.py`) (complete)

Status on 29 Sep 2026: complete. 58 tests. Live run:

| Site | Pages | Time | Notes |
| --- | --- | --- | --- |
| gurzu.com | 30 | 6.4 s | 295 usable URLs. Blog posts do not push out service pages. |
| emitii.com | 6 | 8.3 s | JavaScript site. The browser found 4 demo pages. The homepage has 12 headings. |
| moxo.com | 30 | 2.9 s | One homepage (`www.moxo.com`). 69 pages in other languages skipped. |

Issues found in the live runs and fixed:

1. moxo.com: the homepage showed 2 times. The tool now compares pages without `www.`, `http`/`https`, the last `/` and `#`. It gets each page at the URL in the sitemap.
2. emitii.com: only 2 pages. The homepage is a JavaScript app. The tool now uses the browser for the homepage links when the HTML has fewer than 3 links to the same site. On sites with 8 pages or fewer, it uses the browser for each page. Both limits are settings.
3. gurzu.com: the sitemap lists 2 Google verification files. The tool now skips these files.

Other fixes in Step 1 (done): robots.txt now follows RFC 9309 (Protego). The old parser allowed `/admin/` on gurzu.com. An unreachable robots.txt now means "disallow all". `too_short` pages are cached when no browser retry is possible.

Findings for the gurzu.com team (not tool bugs): the sitemap lists 3 broken Calendly URLs (`/https:/calendly.com/...`), 2 Google verification files (`google385b42146547b16e.html`, `googlea55c1194d1c37672.html`), and 4 URLs that robots.txt disallows (`/admin/`, `/thankyou/`, `/design-ebook-downloaded-thank-you/`, `/services/rails-maintenance/`).

- [x] Read robots.txt and its `Sitemap:` lines.
- [x] If there is no sitemap line, try `/sitemap.xml`, `/sitemap_index.xml` and `/wp-sitemap.xml`.
- [x] Read sitemap index files and gzip files.
- [x] Select up to 30 pages. Prefer short paths. Do not use tag, page-number and legal pages.
- [x] If there is no sitemap, use the links on the home page.
- [x] Get each page with the current fetcher and daily cache.
- [x] Use the browser for JavaScript homepages and small sites (live issue on emitii.com).
- Done when: tests with recorded data pass, including a site without a sitemap. (Done: 58 tests, live run on 3 sites.)

### Step 2: Keyword discovery (`tools/site_keywords.py`) (complete)

- [x] Send one LLM request for each site. The LLM gives the search phrase that each page targets.
- [x] Add Google autocomplete and Bing related keywords for the best phrases.
- [x] Remove duplicates and near duplicates.
- [x] Keep 60 keywords, balanced across the 5 sites.
- [x] Record the source of each keyword.
- [x] Mark competitor brand keywords. Use the domain name and a partial match (T8).
- [x] Check the business fit before the Google check (owner decision, 29 Sep 2026).
- Done when: tests with a fake LLM pass, and each keyword has a source. (Done: `tests/test_site_keywords.py`.)

Status on 29 Sep 2026: complete. Live run: emitii.com against moxo.com and clinked.com. 188 candidates, 60 keywords, 26.8 s, $0.0044 for DeepSeek. A second run on the same day gave the same 60 keywords in 0.1 s at no cost.

Issues found in the live runs and fixed:

1. Bing limit (D12): one limited call stopped the full analysis. Now the tool waits and tries again. Then it marks the keywords "not measured".
2. Security: the Bing error text contained the API key (the key is in the URL). Now the tool removes the key from all Bing errors. This also fixes the brief feature.
3. Off-topic keywords (for example "quickbooks scams"): the business fit check removed 40 to 56 keywords before the Google check.
4. Searches for other companies (for example "taxdome client portal"): the fit check now gives them 0.
5. The LLM copied page labels ("... demo"). Nobody searches these phrases. The prompt now asks for the need, not the label.
6. Two runs gave different keywords. LLM answers are now kept in the daily cache (`DailyCachedLLM`).
7. Bing related keywords with only 1 word in common with the seed (for example "built for teams") are now removed.

Finding for the Emitii team: Emitii pages target "marketing agency project management", "travel agency project management" and "audit firm project management". None of these phrases has measurable demand.

### Step 3: Rank check (`tools/rank_check.py`) (complete)

- [x] Change `providers/serper.py` to request pages with `page`, 10 results each (R1, R6).
- [x] Calculate the absolute position (R5).
- [x] Do not request page 2 when all 5 domains are on page 1.
- [x] Record the best position and the URL of each domain. A subdomain such as `www` counts as the domain.
- [x] When Serper has no credits, keep the results and show a message. Do not use Gemini, because Gemini gives no positions.
- Done when: tests with recorded SERP data pass, and a second request on the same day uses 0 credits. (Done: `tests/test_rank_check.py` and the Serper tests in `tests/test_providers_free.py`.)

Status on 29 Sep 2026: complete. Live run: emitii.com, moxo.com and clinked.com, 60 keywords, top 20. Time: 25.7 s. Credits: 120 (as calculated). All keywords were checked. Moxo is in the top 20 for 11 keywords, Clinked for 3, Emitii for 0. A check of the raw results found no competitor URL that the tool did not match.

Findings:

1. A Google page has approximately 9 results, and some results repeat on page 2. Thus "top 20" gives 15 to 20 results (average 19). The UI must say "the first 2 pages of Google", not "top 20" (R12).
2. The brief feature now gets 20 results for 2 credits for each phrase. Before, it got only 10 results for 1 credit (R6).

### Step 4: Metrics (`tools/keyword_metrics.py`) (complete)

- [x] Add Bing searches and the rough Google estimate (section 5.3).
- [x] Add the difficulty band from `difficulty.py` (G5).
- [x] Add intent from the page types in the top 10 (G10).
- [x] Add SERP features as labels.
- [x] Add estimated visits for each domain (section 5.4).
- [x] Group keywords with 3 or more of the same top-10 URLs (G11).
- Done when: tests check each formula against a hand calculation. (Done: 16 tests with values calculated by hand.)

Status on 29 Sep 2026: complete. The metrics are in a new file `tools/keyword_metrics.py`, because `rank_check.py` only gets positions. Live run on the Step 3 data: 0 credits and $0 (all data came from the daily cache). A hand calculation of the difficulty of "client portal for agencies" from its real top 10 gave 25. The tool also gave 25.

Findings:

1. 27 of 60 keywords have Bing numbers. These are broad keywords (for example "project management software": approximately 11,000 Google searches each month, estimated). None of the 3 sites is in the top 20 for them, so their visits are 0.
2. Moxo is in the top 20 for 11 keywords. Bing has no numbers for these keywords, so the tool cannot show visits for them.
3. Result: on this keyword set, the tool shows no visits above 0 for any site. This is the effect of the free data decision (D11). A paid volume source (section 8) is the only fix.
4. New guard (from REVIEW.md): no difficulty when the top 10 has fewer than 8 results.

### Step 5: Categories and keywords to add (`tools/keyword_gap.py`) (complete)

- [x] Put each keyword in its categories (section 5.6).
- [x] Get the business fit (0 to 3) with one LLM request for all keywords (G3). (Moved to Step 2, before the Google check: owner decision.)
- [x] Order the top keywords: business fit, then competitor proof (sum of the competitors' CTR at their positions), then lower difficulty, then Bing searches (owner decision after D11). Calculate the traffic lift (section 5.5).
- [x] Make the brand keyword list.
- [x] Make the list of top keywords for each competitor, by estimated visits.
- Done when: tests cover each category, the score and the traffic lift. (Done: 16 tests with values calculated by hand.)

Status on 29 Sep 2026: complete. Live run on the Step 3 data (0 credits, $0): emitii.com gets 5 keywords to add. The first 3 are "best client portal for agencies", "client portal for agencies" and "agency client portal". Both competitors rank for them (moxo.com #3; clinked.com #4, #8, #7).

Finding (G13): for 49 of the 60 checked keywords, no site is on the first 2 pages. These checks (approximately 98 credits) give no gap data. The tool guesses the keywords that each page targets. Semrush knows the keywords that sites really rank for. Small sites often target keywords that they do not rank for. Possible fixes (not planned yet):

1. A second pass with the related searches from the results where competitors rank (no extra credits for the data).
2. Tell users to compare with competitors that have more search visibility.

### Step 6: Pipeline and API (`gap_pipeline.py`, `api/`) (complete)

- [x] Save each analysis in `runs/gaps/`. Save the progress after each step.
- [x] Add these endpoints:

| Method | Path | Function |
| --- | --- | --- |
| POST | `/api/gaps` | Start an analysis |
| GET | `/api/gaps` | List the analyses |
| GET | `/api/gaps/{id}` | Show status, progress and results |
| DELETE | `/api/gaps/{id}` | Delete an analysis |
| GET | `/api/gaps/{id}/keywords.csv` | Download the keywords |
| GET | `/api/gaps/defaults` | Default settings, countries, depths, keyword options |

- Done when: API tests with fake providers pass. (Done: 20 pipeline tests, 7 API tests.)

Status on 29 Sep 2026: complete. Live API run (emitii.com against moxo.com and clinked.com): all 5 steps done in 3.1 s, 0 credits and $0 (daily cache). Same 5 keywords to add as in Step 5. The CSV has 60 rows.

Design points:

1. Briefs and Keyword Gap share one file store (`JsonStore`) and one background runner. Their histories stay separate (`runs/` and `runs/gaps/`).
2. The API rejects private and local addresses for all 5 sites (the same guard as the brief import).
3. CSV cells that start with = + - @ get a leading apostrophe. A spreadsheet cannot run them as formulas (keywords come from other web pages).
4. Errors that the user can correct (address, own site as a competitor, no Serper key, no demand) are shown as written.
5. A finished record is approximately 520 KB, because it keeps the Google results for each keyword. If the UI is slow, remove these results from the list view.

### Step 7: Frontend 1: navigation, form and progress (complete)

- [x] Add a tool switch at the top of the sidebar ("Briefs" / "Keyword gap"). Each tool has its own "+ New" button and history (owner decision).
- [x] Form: one field for our domain. Up to 4 competitor fields, with add and remove buttons. Each domain has a color.
- [x] Form: country, depth (10, 20, 30 or 50) and keywords (30, 60 or 100). Show the credit estimate.
- [x] Show a warning when a key is missing.
- [x] Progress view: show the count of each step, for example "Checking Google 34/60".
- Done when: `npm run build` passes, and a run with fake providers shows live progress. (Done: `npm run build` and `npm run lint` pass. Screenshots checked in a browser: form in light and dark mode and at 390 px, progress at "34 of 60 keywords", failed state, results summary. No horizontal scroll.)

Status on 29 Sep 2026: complete. New files: `web/src/components/NewGap.tsx`, `GapView.tsx`, `GapResults.tsx` (a summary; Step 8 makes it the full dashboard). Routes: `#/gap` and `#/gaps/<id>`.

Domain colors: slots 1 to 5 of the dataviz reference palette, in a fixed order (you = blue). The validator passed on this app's surfaces (#ffffff and #151e22): colorblind separation 9.1 (light) and 8.4 (dark), normal vision 19.6 and 19.3. In light mode, 3 colors have less than 3:1 contrast. Thus a color dot always shows next to the domain name.

Findings:

1. (G14) A running analysis cannot be stopped. A server stop waits for the analysis to finish. A test on linkedin.com (to show the error screen) did not fail. It finished and used 9 Serper credits and less than $0.001. Do not use real sites to test error screens. Possible future item: a "Cancel" button.
2. The form checks the addresses before it sends them (your own site as a competitor, the same competitor twice, an address that is not a website). The server checks again.

### Step 8: Frontend 2: results dashboard (complete)

- [x] Domain cards: keywords in the top 10 and top 20, and estimated visits for each domain.
- [x] Keyword overlap as bars, one for each category. A click on a bar filters the table (G12). (Changed from a Venn chart: the categories overlap, and a Venn chart for 5 sites cannot be read.)
- [x] "Top keywords to add": approximately 10 cards. Each card shows the reason, for example "3 of 4 competitors rank. Best: rival.com at #2, approx. 340 visits/month."
- [x] Keyword table with category tabs and counts.
- [x] Table columns: keyword, intent, our position, the position of each competitor, Bing searches, rough Google searches, difficulty band, estimated visits, traffic lift.
- [x] Best position in green. The URL shows on hover. A click opens the URL.
- [x] Filters: position, "at least N competitors", intent, difficulty band, volume, include or exclude words. Defaults from G4.
- [x] Sort, pages, and CSV export.
- [x] Row details: the top 20 results, with our domain and the competitors in color. People Also Ask questions.
- [x] A panel for each competitor with its top keywords by estimated visits.
- [x] A "How we calculate this" note with the limits in section 5.8, the credits and the cost.
- Done when: `npm run build` passes, and the dashboard shows correctly in light mode, dark mode and phone width. (Done: build and lint pass. Checked in a browser on the saved live analysis: light, dark and 390 px; no console errors; no horizontal page scroll; a click on the "Missing" bar shows its 3 keywords; an opened row shows the 20 Google results.)

Status on 29 Sep 2026: complete. New file `web/src/components/GapTable.tsx`; `GapResults.tsx` is now the full dashboard.

Issues found in the browser check and fixed:

1. The site cards showed "~0 visits a month" for all sites. This reads as "no traffic". Now the card shows "—" and a note: Bing has no numbers for the keywords this site is found for (D11).
2. The "Fit" column wrapped to 2 lines. Now it stays on 1 line.

Safety: links from Google results open only when they start with http or https, with `rel="noopener noreferrer"`.

### Step 9: Live check and guide

- [x] Run one real analysis: our domain and 2 to 4 competitors.
- [ ] Check the positions of 5 keywords on Google by hand.
- [x] Record the credits, the cost and the time.
- [x] Add a chapter to `docs/SEO-Advisor-Guide.md`. (Restored from `git stash@{0}` first; the stash is kept.)
- Done when: the analysis shows from start to end, and the 5 positions agree.

Status on 29 Sep 2026: all items done except the hand check (it waits for the owner).

Live analysis: gurzu.com against lftechnology.com, bajratechnologies.com, codehimalaya.com and planetargon.com (US). 139 pages from 5 sites, 60 keywords, 99 s, 120 Serper credits, $0.011 for AI. Result: 2 keywords to add ("ruby on rails consulting": planetargon.com #2; "rails upgrade services": planetargon.com #14). 1 keyword that only Gurzu ranks for ("ruby on rails support": gurzu.com #5). For 57 of 60 keywords, no site is on the first 2 pages (G13).

Hand check for the owner (US Google, a private window, or `&gl=us&hl=en` at the end of the Google URL). A difference of 2 places or less counts as a match (R11):

| Keyword | The tool found |
| --- | --- |
| ruby on rails consulting | planetargon.com #2; gurzu.com not on pages 1 and 2 |
| ruby on rails support | gurzu.com #5 (`/solutions/ruby-on-rails-maintenance-service`) |
| rails upgrade services | planetargon.com #14 (page 2) |
| ruby on rails upgrade | none of the 5 sites on pages 1 and 2 |
| it staff augmentation | none of the 5 sites on pages 1 and 2 |

Code guide: chapter 20 added (Keyword Gap, and the 6 fixes in shared code). 3 new exercises. 23 earlier sections have a "Changed on 2026-09-29" note. 42 references to moved code and 29 references to changed code now point to the correct lines (checked by a script). The guide checker says "All good.". The PDF `docs/SEO-Advisor-in-One-Day.pdf` is not updated.

Issue found by the guide exercises and fixed: `FallbackSearch` gave `stop_domains` to providers written before this parameter existed, and they failed. Now it gives the parameter only when it is used.

## 7a. Review round and G13 (29 September 2026)

The owner asked for a strict review. Three reviewers (backend, frontend, tests and docs) found 52 problems. All were checked and fixed, except the items in "Open" below.

Most important fixes:

1. Security: robots.txt, sitemap indexes and redirects could make the server send requests to private addresses (for example 10.0.0.5). Now every request, and every redirect, goes through the public-address check. Sitemaps must be on the same domain.
2. A sitemap index with many bad entries could cause hundreds of requests. Now each site has a maximum number of sitemap requests.
3. A small `.gz` sitemap could unpack to gigabytes. Now downloads and unpacking have a size limit and a time limit.
4. One failed robots.txt request blocked a site for the full day (also for briefs). Now temporary failures are not kept in the cache.
5. The tool removed `www.` before it fetched a site. Now it fetches the address as the user typed it.
6. The UI: the table showed no rows after a click on an overlap bar from page 3; the sidebar did not update; one network error stopped the progress view. All fixed.

G13 (low yield), two changes:

| Change | Live result |
| --- | --- |
| Second pass: Google's related searches from result pages where a competitor ranks. The same brand, demand and fit rules apply. Maximum 20 keywords (`second_pass_keywords`). | emitii.com: 10 more keywords. 5 of them have a site on pages 1 to 2 (50%; the first pass had 18%). 2 new keywords to add. 20 credits. gurzu.com: 1 more keyword (the fit check removed the others). |
| Suggested competitors: sites on page 1 for your good-fit keywords, except forums, videos and big platforms. A button starts a new analysis with them. | gurzu.com: scnsoft.com, appinventiv.com, globant.com (software agencies). emitii.com: wrike.com, paymoapp.com and others. |

Finding: page type does not separate publishers from competitors (wrike.com and paymoapp.com rank with "best tools" articles). Thus the tool shows suggestions, and the user decides.

Second review round (same day). A re-review of the fixes found more problems. All are fixed and have tests:

1. DNS rebinding: the check and the connection each looked up the name. Now the connection goes to the address that was checked. DNS answers are not cached.
2. Some private ranges passed the check (for example 100.64.0.0/10, and `::ffff:127.0.0.1`). Now the check uses `is_global` and reads the IPv4 part of such addresses.
3. The headless browser fetched pages by itself, so redirects in the browser were not checked. Now our checked client serves every browser request. A local test with two servers shows zero connections to the blocked server.
4. This test found two more problems. Closing a WebSocket in the browser handler stopped the render forever (a site with a chat widget stops the analysis). A `<link rel=preconnect>` opened a TCP connection to the blocked server. Both are fixed.
5. A common word that is not a brand (for example "workspace") was kept in the brand list. The second pass then removed all phrases with that word. Now only real brand words are kept.
6. The second pass checked again phrases that the first pass had removed (no demand, no fit). Now it skips them.
7. One failed Google search stopped the second pass. Now only "credits out" stops it.
8. A page with an unknown character set stopped the fetch. Now the text is read as UTF-8.

Open:

- G14: a running analysis cannot be stopped.
- The owner's hand check of 5 positions (Step 9).
- `docs/SEO-Advisor-in-One-Day.pdf` is not updated.
- Not verified: Serper may send HTTP 400 for one bad query. The tool then stops all later Google checks for the run.

## 8. Future options (not in this plan)

- A "Create a brief for this keyword" button. It opens the brief feature with this keyword locked.
- DataForSEO: `ranked_keywords` for real Google volume and many more keywords. Cost: approximately $0.70 for each analysis (R9).
- DataForSEO SERP with `ai_overview` detection, for correct CTR (T5).
- Search Console: real clicks for our own site (D8). This needs CEO approval.
- SerpApi free tier as a fallback when Serper has no credits (R10).

## 9. Live test results

Step 0 adds the results here.

| Test | Result | Date |
| --- | --- | --- |
| Serper page billing (R4) | 1 credit for each request. `num: 20` gives 10 results. `page: 2` gives 10 new results. Positions start again at 1. | 28 Sep 2026 |
| Serper AI Overview field (T5) | No AI Overview field in 3 queries. Response keys: `organic`, `peopleAlsoAsk`, `relatedSearches`, `searchParameters`, `credits`. | 28 Sep 2026 |
| Serper result stability (R11) | Results 5 and 7 changed places between two requests. | 28 Sep 2026 |
| Bing keyword API (D1, D10) | The key works. "client portal": 1,982 searches/month. "client portal software": 0 (1 search in 12 weeks). Weekly rows, some weeks missing. | 28 Sep 2026 |

## 10. Sources

All sources were read on 28 September 2026.

**Google rank data**

- Search Engine Journal, "Google modifies search results parameter", 15 Sep 2025: https://www.searchenginejournal.com/google-modifies-search-results-parameter-affecting-seo-tools/556080/
- Search Engine Roundtable, num=100 test, 12 Sep 2025: https://www.seroundtable.com/google-search-drops-100-results-parameter-40097.html
- Search Engine Roundtable, Search Console impressions after the change, 22 Sep 2025: https://www.seroundtable.com/google-search-console-data-num-block-40143.html
- DataForSEO, depth update, 13 Sep 2025: https://dataforseo.com/update/google-organic-serp-api-critical-updates-depth
- DataForSEO, pricing FAQ, updated 2 Jul 2026: https://dataforseo.com/help-center/serp-api-pricing-depth-update-faq
- Serper pricing and playground: https://serper.dev
- Serper credits (secondary), Jul 2026: https://apiserpent.com/blog/serper-pricing-credits-explained
- SerpApi pricing: https://serpapi.com/pricing
- Google Custom Search JSON API notice, updated 18 Feb 2026: https://developers.google.com/custom-search/v1/overview
- Google Terms of Service: https://policies.google.com/terms
- Google spam policies, updated 28 Aug 2026: https://developers.google.com/search/docs/essentials/spam-policies

**Search demand**

- Microsoft, Bing Webmaster API `GetKeywordStats`: https://learn.microsoft.com/en-us/dotnet/api/microsoft.bing.webmaster.api.interfaces.iwebmasterapi.getkeywordstats
- Microsoft, `KeywordStats` class: https://learn.microsoft.com/en-us/dotnet/api/microsoft.bing.webmaster.api.interfaces.keywordstats
- Microsoft, Bing Webmaster API access: https://learn.microsoft.com/en-us/bingwebmaster/getting-access
- StatCounter, search engine market share, August 2026: https://gs.statcounter.com/search-engine-market-share
- DataForSEO, search volume precision (0.1 ratio is an assumed example), 27 Aug 2024: https://dataforseo.com/blog/dataforseo-search-volume-precision-in-our-apis
- Google Ads API, `GenerateKeywordHistoricalMetrics`, updated 23 Sep 2026: https://developers.google.com/google-ads/api/docs/keyword-planning/generate-historical-metrics
- Google Trends API alpha, 24 Jul 2025: https://developers.google.com/search/blog/2025/07/trends-api
- Google, how autocomplete works: https://support.google.com/websearch/answer/7368877

**Traffic estimate**

- Advanced Web Ranking, organic CTR, July 2026: https://www.advancedwebranking.com/seo/organic-ctr
- First Page Sage, CTR by position, updated 22 Sep 2026: https://firstpagesage.com/reports/google-click-through-rates-ctrs-by-ranking-position/
- Ahrefs, AI Overviews reduce clicks, 17 Apr 2025: https://ahrefs.com/blog/ai-overviews-reduce-clicks/
- Ahrefs, update, 4 Feb 2026: https://ahrefs.com/blog/ai-overviews-reduce-clicks-update
- Seer Interactive, AI Overview CTR, 24 Apr 2026: https://www.seerinteractive.com/insights/aio-impact-on-google-ctr-2026-update
- Pew Research, AI summaries and clicks, 22 Jul 2025: https://www.pewresearch.org/short-reads/2025/07/22/google-users-are-less-likely-to-click-on-links-when-an-ai-summary-appears-in-the-results/
- Amsive, AI Overviews research, 16 Apr 2025: https://www.amsive.com/insights/seo/google-ai-overviews-new-research-reveals-how-to-navigate-click-drop-off/
- Wang et al., AI Overviews field experiment, 18 Aug 2026: https://arxiv.org/html/2608.18352v1
- Ahrefs, how organic traffic is calculated: https://help.ahrefs.com/en/articles/1863206-what-is-organic-traffic-in-ahrefs-and-how-do-we-calculate-it
- Ahrefs, Traffic Potential: https://help.ahrefs.com/en/articles/9046244-what-is-traffic-potential
- Semrush, traffic numbers: https://www.semrush.com/kb/858-traffic-numbers-in-semrush
- Ahrefs, traffic estimate accuracy, 3 May 2022: https://ahrefs.com/blog/traffic-estimations-accuracy
- Collaborator.pro, Semrush vs Similarweb vs Ahrefs accuracy, 5 Dec 2024: https://collaborator.pro/blog/research-semrush-similarweb-ahrefs
- Semrush, branded keywords: https://www.semrush.com/kb/819-branded-vs-non-branded-keywords

**Gap method**

- Semrush, Keyword Gap: https://www.semrush.com/kb/28-keyword-gap
- Semrush, keyword gap analysis, 25 Jun 2024: https://www.semrush.com/blog/keyword-gap-analysis/
- Semrush, Keyword Gap new flow, 18 Mar 2020: https://www.semrush.com/news/269864-keyword-gap-new-flow/
- Ahrefs Academy, Content Gap: https://ahrefs.com/academy/how-to-use-ahrefs/competitive-analysis/content-gap
- Ahrefs, content gap analysis, 17 Feb 2025: https://ahrefs.com/blog/content-gap-analysis/
- Ahrefs, keyword research and business potential: https://ahrefs.com/seo/keyword-research
- Semrush, keyword difficulty: https://www.semrush.com/kb/1158-what-is-kd
- Tranco, methodology: https://tranco-list.eu/methodology
- Ruth et al., "Toppling Top Lists", IMC 2022: https://dl.acm.org/doi/10.1145/3517745.3561444
- Sitemaps protocol: https://www.sitemaps.org/protocol.html
- Google, build and submit a sitemap, updated 8 Jul 2026: https://developers.google.com/search/docs/crawling-indexing/sitemaps/build-sitemap
- RFC 9309, Robots Exclusion Protocol: https://www.rfc-editor.org/rfc/rfc9309
- Backlinko, search engine ranking study, updated 14 Apr 2025: https://backlinko.com/search-engine-ranking
- Song et al., ChatGPT keyphrase extraction, arXiv 2312.15156: https://arxiv.org/abs/2312.15156
- Semrush, search intent: https://www.semrush.com/kb/1226-search-intent
- Keyword Insights, clustering settings: https://docs.keywordinsights.ai

**Writing standard**

- Simplified Technical English (summary of ASD-STE100 Issue 9, January 2025): https://en.wikipedia.org/wiki/Simplified_Technical_English
- The official specification needs registration: https://www.asd-ste100.org

## 11. STE rules used in this file

The ASD-STE100 site needs registration, so these rules come from a secondary summary of Issue 9.

- Procedure sentences: 20 words maximum. Descriptive sentences: 25 words maximum.
- One instruction in each sentence. Instructions use the imperative.
- Active voice.
- Simple verb tenses only: present, past, future.
- Noun clusters: 3 words maximum.
- Paragraphs: 6 sentences maximum, one topic.
- Vertical lists for complex text.
- Technical names (for example Serper, CTR, SERP) are permitted.

## 12. Change log

| Date | Change |
| --- | --- |
| 28 Sep 2026 | First plan. Decisions about the data source, scope and competitors. |
| 28 Sep 2026 | Research complete (section 4). Default depth changed from top 100 to top 20 (R1). New CTR table from AWR (T2). Business fit filter, brand filter, traffic lift and difficulty bands added. The plan now has 10 steps. The file is now in STE. |
| 28 Sep 2026 | Source check: D4 corrected. The DataForSEO 0.1 ratio is an assumed example, not a measurement. |
| 28 Sep 2026 | Step 0: docs, `GapSettings`, tests and the `serper_pages` live test added. US ratio corrected from 9.7 to 9.57 with the StatCounter CSV (primary data). Ratios for all 11 countries added. Winnability now uses the difficulty score, not the band. |
| 28 Sep 2026 | Serper live tests: 1 credit for each page of 10, no AI Overview field, small position changes between requests (R4, R5, R6, R11, T5). 6 credits used. |
| 28 Sep 2026 | Bing live test. Bug fixed in `bing.py`: weeks without data now count as 0 (D10). Step 0 complete. |
| 28 Sep 2026 | Step 1 code and tests done. Fixed in shared code: robots.txt parser (RFC 9309), cache of short pages. Live run found 2 open issues. Work paused by the owner. |
| 29 Sep 2026 | Step 1 complete. Fixed: duplicate homepage (www), JavaScript homepages, Google verification files in sitemaps. |
| 29 Sep 2026 | Owner decisions: Q1 to Q4 accepted, guide restored at Step 9. Step 2 approved. |
| 29 Sep 2026 | Step 2 complete. Owner decisions: free volume with honest labels; business fit before the Google check. Fixed: Bing limit, API key in Bing errors, LLM answers cached by day. Step 5 must change the demand part of the score (D11). |
| 29 Sep 2026 | Step 3 approved. Fit 1 keywords keep filling spare slots. |
| 29 Sep 2026 | Step 3 complete: Serper pages (brief feature fixed too), rank check, 120 credits for 60 keywords as calculated. |
| 29 Sep 2026 | Step 4 approved. Owner chose the new order for top keywords (fit, then competitor proof). |
| 29 Sep 2026 | Step 4 complete (`tools/keyword_metrics.py`). Live: no visits above 0 for any site on this keyword set, because of the free data (D11). |
| 29 Sep 2026 | Step 5 complete (`tools/keyword_gap.py`). Live: 5 keywords to add for emitii.com. Finding G13: 49 of 60 checked keywords have no site on the first 2 pages. |
| 29 Sep 2026 | Step 6 approved. The G13 fix comes after the UI. |
| 29 Sep 2026 | Step 6 complete: pipeline, API, CSV. Live API run: 3.1 s, 0 credits. |
| 29 Sep 2026 | Step 7 approved. Sidebar: tool switch at the top. |
| 29 Sep 2026 | Step 7 complete: sidebar tool switch, form, live progress. An unplanned test used 9 Serper credits (G14). |
| 29 Sep 2026 | Step 8 complete: results dashboard (cards, overlap bars, top keywords, table, competitor panels, method note). |
| 29 Sep 2026 | Step 9: live analysis for gurzu.com (120 credits), code guide chapter 20. Hand check waits for the owner. |
| 29 Sep 2026 | Review round (52 findings) fixed. G13: second pass and suggested competitors, measured live. |
| 29 Sep 2026 | Second review round: 8 more problems fixed (section 7a). Two were found by the new offline browser test. |

# Plan: Site Snapshot

| Item | Value |
| --- | --- |
| Status | Steps 0 to 6 complete, except the owner's hand check (Step 6). |
| Branch | `feature/keyword-gap` (owner decision, 29 Sep 2026) |
| Last update | 29 September 2026 |
| Writing standard | ASD-STE100 Simplified Technical English, Issue 9 (the same rules as `docs/KEYWORD-GAP-PLAN.md` section 11) |

## 1. Rules for this plan

1. Start a step only after the owner approves it.
2. When the owner asks for a change, update this file first.
3. Do not commit or push changes. Commit only when the owner asks.
4. Validate each claim with a credible source. Section 9 lists the sources.
5. Show only data that we can measure or estimate honestly. Label each estimate as an estimate.

## 2. Goal

The user gives the URL of one website. The tool shows one page with a summary of that website in search:

- How strong the site is (links and popularity).
- Which searches the site targets, and where it shows on Google for them.
- Which pages bring the most estimated visits.
- Which sites compete with it on Google.
- How fast the site is for real visitors.
- How old the site is, how many pages it lists, and its technical basics.

Reference pages: Semrush "Domain Overview", Ahrefs "Site Explorer" overview, Similarweb website overview. We do not copy their names, their screens or their metric names.

## 3. Decisions

| Question | Decision | Date |
| --- | --- | --- |
| Name of the page | "Site Snapshot" | 29 Sep 2026 |
| Branch | Build on `feature/keyword-gap`. Site Snapshot uses the Keyword Gap code. | 29 Sep 2026 |
| Q1 Keywords | 30 keywords for each snapshot (approximately 60 Serper credits). | 29 Sep 2026 |
| Q2 Free keys | Open PageRank key added and tested. Chrome UX Report: skipped for now. The owner's Google Cloud console asks for an account upgrade (billing) because a Vertex AI trial ended. The keyless PageSpeed Insights API gave HTTP 429 (shared daily quota) for all 3 test sites. Thus the speed tile shows "not set up" until a `CRUX_API_KEY` is added. The provider is still built and tested. | 29 Sep 2026 |
| Q3 Competitors | Version 1 shows one site only. The "Compare in Keyword Gap" button does the comparison. | 29 Sep 2026 |
| Q4 Licences | Internal use is enough for now. Check the licences before a product (F3, F6). | 29 Sep 2026 |
| Plan | Approved. Start Step 0. | 29 Sep 2026 |
| Q5 Keyword quality (F25) | Skip list pages (the index of a content section such as `/blog/` or `/articles/`) when the tool names keywords; their posts stay. Also skip category archives. Do not add a brand search. The change is in the shared site reader, so Keyword Gap gets it too. | 29 Sep 2026 |

## 4. Research summary

Confidence: **P** = primary source (vendor document, standard, live test). **S** = secondary source only. **C** = the sources do not agree.

### 4.1 What the reference pages show

| # | Finding | Conf. | Effect on the design |
| --- | --- | --- | --- |
| O1 | Semrush Domain Overview shows: AI visibility, Authority Score, organic and paid traffic, referring domains, backlinks, organic keywords, traffic by country, branded and non-branded traffic, position distribution, traffic trend, top keywords, main competitors, a positioning map, and backlink data. | P [1] | Our page has fewer parts. It shows only the parts that free data supports (section 5.2). |
| O2 | Semrush estimates organic traffic from keyword positions and search volume × average CTR. Semrush tells users to use Google Analytics for their own traffic. | P [2] | Our estimate uses the same method on a sample of keywords. The label says "estimate". |
| O3 | Ahrefs estimates organic traffic from all keywords in the top 100: search volume × a CTR curve. Ahrefs says that only Google knows the real clicks. | P [3][4] | Same as O2. |
| O4 | Semrush Authority Score, Ahrefs Domain Rating and Moz Domain Authority come from link graphs. Ahrefs says Domain Rating "is a relative metric by definition". | P [5][6], S for Moz [7] | We do not make an "authority score". We show a third-party link score with its name and its source. |
| O5 | An independent test of 641 sites found that no third-party traffic estimate is reliable enough to trust with high confidence. Small sites have the largest errors. | P [8] | Every visit number has an "estimate" label. Small sites get a note. |
| O6 | Ahrefs groups keyword positions as 1–3, 4–10, 11–20, 21–50 and 51+. | P [9] | We use 1–3, 4–10, 11–20 and "not in top 20" (our depth is 20). |
| O7 | Names to avoid: Domain Overview, Authority Score, AI Visibility Score, Traffic Share, Competitive Positioning Map, Key Topics (Semrush); Site Explorer, Domain Rating, URL Rating, Ahrefs Rank, Traffic value (Ahrefs); Domain Authority, Page Authority, Brand Authority, Spam Score, Link Explorer (Moz); Global Rank, Website Performance (Similarweb). | P [1][3][5][6] | Section 5.2 uses our own names. |

### 4.2 Free data sources

| # | Finding | Conf. | Effect on the design |
| --- | --- | --- | --- |
| F1 | For a domain that we do not own, no free source gives total organic traffic or the total number of ranking keywords. | P [10] (checked source by source) | We show a sample: the keywords that we find and check. We never show a total. |
| F2 | Open PageRank gives a 0–10 score, a rank and a referring-domains count from Common Crawl links. The free plan has 30,000 domains a month and 60 requests a minute. It needs no card. | P [11][12] | Use it for the link score. It needs a free key (`OPENPAGERANK_API_KEY`). |
| F3 | The Open PageRank terms do not mention commercial use, caching or showing the data to other people. The terms forbid a display that implies endorsement by the data sources. | P [13] | Internal use: yes. Before a product: ask the vendor in writing (open question Q4). |
| F4 | The Majestic Million lists the top one million domains with referring subnets and referring IPs. The licence is CC BY 3.0 (attribution is necessary). | P [14] | Use it as a second link signal. Show the attribution on the page. Domains outside the top one million show "not in the top 1M". |
| F5 | Tranco has a new list each day. Each list averages several lists over 30 days. The API for one domain needs no key and allows 1 query each second. | P [15][16] | We already use Tranco. Show the rank as "popularity", not as authority. Correct `docs/ARCHITECTURE.md` §4a: it says "refreshed monthly". |
| F6 | One Tranco input (Cloudflare Radar) has a CC BY-NC 4.0 licence (non-commercial). | P [15] | Internal use: yes. Before a product: check again (open question Q4). Do not use Cloudflare Radar directly. |
| F7 | The CrUX API gives Core Web Vitals (LCP, INP, CLS, FCP, TTFB) for an origin. It is free, with 150 queries a minute for each Google Cloud project. The data is a 28-day rolling average, updated each day. | P [17] | Use it for "speed for real visitors". It needs a Google API key with the Chrome UX Report API on. |
| F8 | CrUX has data only for public pages of origins with enough Chrome visitors. Google does not publish the minimum number. The CrUX licence is CC BY 4.0. | P [18] | Small sites often have no data. The page then says "not enough Chrome visitors to measure". Show the attribution. |
| F9 | The CrUX popularity rank (top 1k, 10k, ...) is in BigQuery only. The GitHub copy (crux-top-lists) states no licence. | P [19][20] | Do not use it now. |
| F10 | RDAP gives the registration date of a domain. Live check of the IANA list (29 Sep 2026): 1,204 TLDs. `.com`, `.org`, `.net`, `.in`, `.uk`, `.ai`, `.app`, `.dev`, `.au` are in the list. `.io`, `.co`, `.np`, `.de`, `.us` are not. | P [21] (tested) | Use RDAP first. When the TLD is not in the list, use the first Wayback capture. Label the source of the date. |
| F11 | The Wayback CDX API gives the first capture of a domain with `limit=1`. It needs no key. The Internet Archive announced stricter blocks for high-volume automated traffic on 15 Sep 2026. | P [22][23] | One request for each snapshot. Keep the answer in the cache. |
| F12 | Google says that `site:` does not necessarily return all indexed URLs. | P [24] | Do not show a `site:` count. Show "pages listed in the sitemap" from our `SiteReader`. |
| F13 | Bing Webmaster gives real Bing clicks, impressions and positions only for sites that the key owner verified. Google Search Console gives real Google data only for verified sites, with OAuth. | P [25][26][27] | Not in version 1. A later step can add "real data" for our own sites (section 8). |
| F14 | Similarweb terms forbid scraping and use in a competing product. Cloudflare Radar data is non-commercial. | P [28], P [15] | Do not use Similarweb or Cloudflare Radar. |
| F15 | Live test, 29 Sep 2026: the RDAP registration date and the first Wayback capture can be years apart. emitii.com: registered 2023-07-13, first capture 2015-09-06. gurzu.com: registered 2018-10-13, first capture 2017-05-20. RDAP gives the start of the current registration. Wayback can show a previous owner of the name. | P (tested) [21][22] | Show two labelled facts: "Registered" and "First seen online". Do not call either one "site age" alone. |
| F16 | Core Web Vitals thresholds at the 75th percentile: LCP good ≤ 2,500 ms, poor > 4,000 ms. INP good ≤ 200 ms, poor > 500 ms. CLS good ≤ 0.1, poor > 0.25. | P [29] | `SnapshotSettings.vitals`. Three states: good, needs work, poor. |
| F18 | Live test: Open PageRank returns a monthly history of the score (`include_history`), back to 2018 for most domains. gurzu.com: 0.41 in May 2020, 1.78 in Sep 2026. An unknown domain returns `found: false`. | P (tested) [11] | Show a small "link score over time" chart. This is the only trend that free data gives us. |
| F19 | Live test: the Wayback availability API (`/wayback/available`, timestamp 1996) was fast (1 to 5 s), but it found no capture for gurzu.com and codehimalaya.com. The CDX API found captures for both. | P (tested) [22] | Use the CDX API only. It is slower (10 to 45 s), so it runs at the same time as the Google checks, with a 60 s limit. |
| F20 | Live test: the Majestic Million download took 178 s once and 15 to 22 s in three later tests. Building the SQLite copy takes 4 s. | P (tested) | The slow time was the server, not our code. The copy is made once a week (`majestic_max_age_days`). |
| F21 | Google: 301 and 308 are permanent redirects; 302, 303 and 307 are temporary. Google recommends a permanent server-side redirect for a permanent move. | P [31] | Check "Redirects are permanent". |
| F22 | Google: `noindex` works as a robots `<meta>` tag or an `X-Robots-Tag` HTTP header. When robots.txt blocks the page, Google never sees the `noindex` rule. | P [32] | Check "Homepage can be indexed". Read robots.txt first. |
| F23 | Google: redirects and `rel="canonical"` are strong canonical signals. Google recommends a `rel="canonical"` link on the canonical page itself. | P [33] | Check "Canonical tag": no tag is a warning, not a failure. |
| F24 | Google writes the snippet mostly from the page content. It uses the meta description when that describes the page better. | P [34] | A missing description is a warning, not a failure. |
| F25 | Live test, gurzu.com (US, 30 keywords): gurzu.com is in the top 20 for 0 of 30 keywords. Gurzu is not in any of the 30 results pages. 6 of the 30 keywords name a list page, not a service: "tech insights", "tech blog", "engineering articles", "engineering blog", "software development blog", "software development articles" (from `/blog/` and `/articles/`). The site's own brand search ("gurzu") is not checked: the brand filter removes it, as in Keyword Gap. | P (tested) | Owner decision Q5 (section 3): skip list pages; no brand search. |
| F17 | To get an Open PageRank key, sign in with a Keywords Everywhere key. The Keywords Everywhere key is free (email sign-up). Payment is necessary only for Keywords Everywhere credits, which we do not use. | P [11][30] | Owner step in Step 0. |

## 5. Design

### 5.1 How a snapshot runs

A snapshot is a separate fixed pipeline, like Keyword Gap. It uses the Keyword Gap code for one site.

| Step | What it does | Code | Cost |
| --- | --- | --- | --- |
| 1. Read the site | robots.txt, sitemap, up to 30 pages | `SiteReader` (exists) | Free |
| 2. Find the keywords | One LLM request names the search that each page targets. Demand and brand checks. | `discover_keywords` with one site (exists) | Less than $0.01 |
| 3. Check Google | Positions in the top 20 for each keyword | `check_ranks` (exists) | 2 Serper credits for each keyword |
| 4. Measure | Bing searches, rough Google estimate, visits, difficulty, intent | `keyword_metrics` (exists) | Free |
| 5. Site facts | Link score, Majestic, Tranco, CrUX, domain age, technical checks | New providers and a new tool | Free |
| 6. Build the snapshot | Tiles, position groups, top pages, competitors | New tool `tools/site_snapshot.py` | Free |

Default: 30 keywords (60 Serper credits). Steps 1 to 4 and step 5 run at the same time.

### 5.2 What the page shows

Names are our own. Each tile shows its source.

| Section | Contents | Source | When there is no data |
| --- | --- | --- | --- |
| Header | Domain, country, date, Serper credits, AI cost | Run | — |
| Tile "Link score" | Open PageRank 0–10, its referring-domains count, and a small chart of the monthly score (F18) | Open PageRank (F2) | "No link data" |
| Tile "Popularity" | Tranco rank. Majestic Million referring subnets. | Tranco (F5), Majestic (F4) | "Not in the top 1M" |
| Tile "Found on Google" | Keywords in the top 20, out of the keywords checked (for example "7 of 30") | Our check | — |
| Tile "Estimated visits" | Sum of estimated monthly visits for the checked keywords, with "rough" label | Our metrics (Keyword Gap 5.3 and 5.4) | "Too low to measure" (Keyword Gap D11) |
| Tile "Speed for real visitors" | Good, needs work or poor for LCP, INP and CLS at the 75th percentile, on phones (F16) | CrUX (F7) | "Not set up" (no key, Q2) or "Not enough Chrome visitors to measure" (F8) |
| Tile "Site age" | "Registered" (RDAP) and "First seen online" (first Wayback capture), each with its date (F15) | RDAP, Wayback (F10, F11) | "Unknown" for each missing date |
| Tile "Pages in sitemap" | Count of page URLs in the sitemap | `SiteReader` (F12) | "No sitemap found" |
| Position groups | Bars: 1–3, 4–10, 11–20, not in top 20 | Our check (O6) | — |
| Top keywords | Keyword, position, URL, Bing searches, estimated visits, difficulty, intent | Our metrics | — |
| Top pages | Pages by estimated visits, with their keywords | Our metrics | "No page has measured visits" |
| Competitors on Google | Sites that show most often in the top 10 for this site's keywords. Button: "Compare in Keyword Gap". | `suggest_competitors` (exists) | "No competitors found" |
| Technical basics | HTTPS, www and non-www redirect, robots.txt, sitemap, homepage title and description length, `noindex`, canonical | Our fetcher and `snippet_check` (exist) | — |
| How we calculate this | The sample size, the method, the limits (O2, O5, F1), and the attributions (F4, F8) | Text | — |

The page does not show: total organic traffic, total keyword count, a backlink list, paid ads, traffic by country, AI visibility, or a trend over time. Reason: F1, F13 and O4. Each snapshot is saved. Thus a later step can compare two snapshots of the same site.

### 5.3 New code

| File | Purpose |
| --- | --- |
| `providers/openpagerank.py` | Link score, behind a `LinkScoreProvider` interface. Daily cache. |
| `providers/majestic.py` | Majestic Million CSV, loaded like the Tranco list. |
| `providers/crux.py` | CrUX API for one origin, phone. Daily cache. |
| `providers/domain_age.py` | RDAP (IANA bootstrap list) and Wayback, both (F15). Daily cache. |
| `tools/site_checks.py` | Technical basics, plain code. |
| `tools/site_snapshot.py` | Tiles, position groups, top pages, competitors. Pydantic models. |
| `snapshot_pipeline.py` | The 6 steps, progress for the UI. |
| `api/` | `/api/snapshots` endpoints and a store (the `JsonStore` from Keyword Gap). |
| `web/` | Sidebar tool "Site snapshot", form, progress, results page. |

Every request to an address that a site or a downloaded list chooses (the site, its redirects, the RDAP servers from the IANA list) uses the public-address guard (`public_client`). The fixed vendor addresses (Open PageRank, CrUX, Majestic, Tranco) use a plain client. All numbers come from code (CLAUDE.md rule 1). Settings go in `SnapshotSettings` in `config.py` (rule 9).

## 6. Open questions for the owner

| # | Question | Recommendation |
| --- | --- | --- |
| Q1 | How many keywords must a snapshot check? 30 uses approximately 60 Serper credits. 60 uses approximately 120. | 30. A snapshot is a quick look. Keyword Gap is the deep look. |
| Q2 | Can we add two free keys? `OPENPAGERANK_API_KEY` (Open PageRank) and a Google key with the Chrome UX Report API on. The Gemini key can work if the API is on in the same Google Cloud project. | Yes. Section 7, Step 0 gives the instructions. |
| Q3 | Must the snapshot also check competitors' facts (link score, speed) side by side? | No, not in version 1. The "Compare in Keyword Gap" button does the comparison. |
| Q4 | Before Site Snapshot becomes a product, we must check the licences: Open PageRank (F3) and Tranco's Cloudflare input (F6). Is internal use enough for now? | Yes. Record it as a condition for the product. |

## 7. Steps

### Step 0: Documents, settings and live tests

- [x] Add Site Snapshot to `docs/PRD.md` (§5.12) and `docs/ARCHITECTURE.md` (§14). Correct the Tranco text in §4a (F5).
- [x] Add `SnapshotSettings` to `config.py`, with tests (`tests/test_snapshot_settings.py`, 17 tests). Add `OPENPAGERANK_API_KEY` and `CRUX_API_KEY` to `Secrets` and `.env.example`.
- [x] Owner: get a free Open PageRank key and add it to `.env`.
- [x] Owner: Chrome UX Report API. Skipped for now (see Q2 in section 3).
- [x] Live tests without keys: RDAP, Wayback, Majestic Million (see "Step 0 results" below).
- [x] Live test with the owner's key: Open PageRank for 8 domains (see below). CrUX: no key (Q2).
- Done when: each source gives the expected data or a clear "no data".

Step 0 results (29 Sep 2026, live, 0 credits):

| Test | Result |
| --- | --- |
| RDAP (`rdap.verisign.com` for `.com`) | gurzu.com 2018-10-13, emitii.com 2023-07-13, planetargon.com 2002-08-23, bajratechnologies.com 2011-07-15, github.com 2007-10-09. Approximately 1 s each. |
| Wayback CDX, first capture | gurzu.com 2017-05-20, emitii.com 2015-09-06, codehimalaya.com 2018-08-05. Approximately 10 s each. Thus it must run at the same time as the other steps. |
| Open PageRank (8 domains, HTTP 200, 8 of 30,000 monthly lookups) | github.com 9.54 (300,214 referring domains), planetargon.com 4.69 (94), lftechnology.com 3.54 (40), gurzu.com 1.78 (13), bajratechnologies.com 0.82 (5), emitii.com 0.09 (0), codehimalaya.com 0.09 (0). Unknown domain: `found: false`. Response headers give the remaining monthly lookups (`x-domains-remaining`). |
| PageSpeed Insights without a key | HTTP 429 "Queries per day" quota exceeded for all 3 sites. Not usable. |
| Majestic Million | 81 MB CSV, 1,000,000 rows, updated 29 Sep 2026. lftechnology.com #578,712 (338 referring subnets), planetargon.com #600,534 (332). gurzu.com, emitii.com, bajratechnologies.com: not in the list. |

### Step 1: Providers

- [x] `openpagerank.py`, `majestic.py`, `crux.py`, `domain_age.py`, each behind an interface, with a daily cache. Failures become notes, never a failed snapshot. Temporary failures (HTTP 429, 5xx, timeouts, a bad key) are not cached.
- [x] Tests with recorded answers (`tests/test_providers_site_facts.py`, 23 tests; fixtures in `tests/fixtures/site_facts/`). No live calls in tests. The CrUX fixture uses Google's documented format, because there is no key (Q2).
- Done when: all tests pass and one live check of each provider works.

Step 1 results (29 Sep 2026, live, 0 Serper credits, 4 Open PageRank lookups):

| Provider | Result |
| --- | --- |
| Open PageRank | gurzu.com 1.78 (13 referring domains, 77 months of history). emitii.com 0.09. |
| Majestic Million | Download and build: 22 s. planetargon.com #600,534 (332 subnets). gurzu.com: not in the list. |
| CrUX | `not_set_up` (no key), as designed. |
| Domain dates | gurzu.com: registered 2018-10-13, first seen 2017-05-20. emitii.com: 2023-07-13 and 2015-09-06. planetargon.com: 2002-08-23 and 2002-10-14. A repeat on the same day: 0.04 s (cache). |

### Step 2: Technical checks (`tools/site_checks.py`)

- [x] `providers/site_probe.py`: the 4 typed addresses (every redirect hop and its status), robots.txt, and the homepage HTML only when robots.txt allows our user agent. All through `public_client`.
- [x] `tools/site_checks.py`: 10 checks, each pass, warn, fail or unknown: HTTPS, http to https, one address, permanent redirects, robots.txt for Googlebot, sitemap, `noindex` (meta and header), title, description, canonical (tag or `Link` header). Rules: F21 to F24.
- [x] `SiteSample.sitemap_urls`: the number of addresses the sitemap lists. The old `urls_found` counts usable pages after skipping, plus homepage links, so it is not a sitemap count.
- [x] Tests: `tests/test_site_checks.py` (33), `tests/test_providers_site_probe.py` (8), one new assertion in `tests/test_providers_sitemap.py`.

Step 2 results (29 Sep 2026, live, free). Each warning was checked again by hand with `curl`:

| Site | Result |
| --- | --- |
| gurzu.com | 8 pass, 2 warn: `https://www.gurzu.com/` shows the site without a redirect (a duplicate homepage); the description is 219 characters. Sitemap: 339 addresses (hand count: 339). |
| emitii.com | 9 pass, 1 warn: `http://www.emitii.com/` shows the site over plain HTTP without a redirect, and `https://www.emitii.com/` does not connect. Sitemap: 6 addresses (hand count: 6). |
| planetargon.com | 10 pass. |
| lftechnology.com | 9 pass, 1 warn: `https://lftechnology.com/` uses a temporary 302 redirect. |

Bug found by the live test and fixed: a small sitemap topped up with homepage links (`sitemap+links`, emitii.com) showed "No sitemap found".

### Step 3: Snapshot tool and pipeline

- [x] `tools/site_snapshot.py`: tiles, position groups, top pages, competitors (plain code).
- [x] `snapshot_pipeline.py`: 5 steps with progress. Site facts run in the background from the start. Only a bad address stops a snapshot; every other failure is a note. Page bodies are not stored with the run.
- [x] Tests: `tests/test_site_snapshot.py` (4), `tests/test_snapshot_pipeline.py` (11), shared fakes in `tests/snapshot_fakes.py`.
- [x] Live run on gurzu.com (see below).

Step 3 results (29 Sep 2026, live): 40 s in total (the Google step ended at 10 s; the Wayback lookup set the end at 40 s). 30 Serper credits: 15 keywords were new (2 pages each), 15 were in today's cache. AI: $0.0004. Link score 1.78 (13 referring domains, 77 months). Not in the Majestic Million or the Tranco top 1M. Registered 2018-10-13, first seen 2017-05-20. Sitemap: 339 addresses. Checks: 8 pass, 2 warn (as in Step 2). Competitors on page 1: scnsoft.com (4 keywords), luxoft.com (3), armorcode.com, cigniti.com, ebiztrait.com (2 each). Keywords: 0 of 30 in the top 20 (F25). 18 to 20 results were read for each keyword, so "not in top 20" is correct.

Q5 fix and re-run (29 Sep 2026, live): `listing_sections` in `GapSettings` and a "list page" rule in `skip_reason`; "category" and "categories" added to `skip_segments`. 5 new tests. On gurzu.com the reader skipped 6 list pages. The 6 list-page keywords are gone; the new keywords name services ("custom software development", "mobile app maintenance services", "online travel agency software", "test automation services"). Result: still 0 of 30 in the top 20 (US). 28 Serper credits (58 in total for Step 3, as approved), $0.0028 AI, 32 s. Suggested competitors now include monday.com and coursera.org, which are platforms, not agencies: the list stays a suggestion (Keyword Gap G13 finding). A snapshot reads 30 of the site's pages, so its keywords are a sample; a page such as `/solutions/ruby-on-rails-maintenance-service/` (#5 in the Keyword Gap run) is in some samples and not in others.

### Step 4: API and store

- [x] `/api/snapshots` endpoints: defaults, start (address guard on the address as typed), list, get (without page snippets), keywords CSV (formula cells escaped), delete. `SnapshotStore` in `runs/snapshots/`; a restart marks running snapshots failed. `/api/health` reports `missing_for_site_snapshot` (DeepSeek) and `optional_for_site_snapshot` (Serper, Open PageRank, CrUX, Bing).
- [x] API tests: 6 new in `tests/test_api.py`, 1 CSV test; 2 health tests updated for the new keys.
- [x] Live check through a real server (29 Sep 2026): gurzu.com snapshot started over HTTP, finished, listed, CSV downloaded. 0 credits (today's cache). Stored record: 281 KB.

### Step 5: Web app

- [x] Sidebar tool switch with 3 tools ("Snapshot"), history with "found/checked", form (site, country, 30 or 60 searches, credit note, missing and optional keys), live progress. The progress card is now one shared component (`RunProgress.tsx`) for Keyword Gap and Site Snapshot.
- [x] Results page (section 5.2): 7 fact tiles, "Link score over time" chart, position bars, a filterable table of searches, top pages, competitors, technical checks, "How we calculate this" with the attributions (F4, F8), and the run notes.
- [x] The chart follows the dataviz rules: one series (no legend, the title names it), 2px line in the brand token, recessive grid, hover and touch crosshair with a tooltip, arrow keys, Home and End, values read out to screen readers, and a hidden table of every point.
- [x] "Compare in Keyword Gap" opens the Keyword Gap form filled in with the site and the top 4 suggested competitors.
- [x] Checks (29 Sep 2026, on a separate test server with a copy of the runs): build and lint clean; no console errors; no horizontal page scroll at 390 px; light and dark mode; interaction test (keyboard on the chart, filters, the Keyword Gap hand-off). Fixed from the screenshots: the tool switch wrapped; "~0 visits" is now "0" with the reason; the table squeezed on phones (now scrolls in its card); the filter buttons wrapped on phones; the chart tooltip went outside the chart.

### Step 6: Live check, review and guide

Hand check for the owner (snapshot of 29 Sep 2026). Use US Google in a private window, or add `&gl=us&hl=en` to the Google URL. Look at pages 1 and 2 (20 results).

| Check | The tool found |
| --- | --- |
| Search "software quality assurance" | gurzu.com is not on pages 1 and 2 |
| Search "shift left testing" | gurzu.com is not on pages 1 and 2 (the post `/blog/shift-left-testing/` targets it) |
| Search "ux ui design services" | gurzu.com is not on pages 1 and 2 |
| Registration date: https://lookup.icann.org, search gurzu.com, see "Created" | 13 Oct 2018 |
| First capture: https://web.archive.org/web/2017*/gurzu.com, the first date on the calendar | 20 May 2017 |


- [x] Run a snapshot for gurzu.com (Step 3 and Step 4 runs).
- [ ] The owner checks 3 positions and the site age by hand (list below).
- [x] A strict review of all new code: two reviewers (backend; web app and tests). 24 findings confirmed, all fixed, each with a test (see "Review round" below).
- [x] Add a chapter to `docs/SEO-Advisor-Guide.md` (chapter 21, two exercises, file index, notes on 7.4 and 20.4). The guide check says "All good."
- [x] README, `docs/ARCHITECTURE.md` §14, `CLAUDE.md` and `docs/PRD.md` §5.12 updated.
- Done when: the snapshot shows from start to end, and the hand checks agree.

Review round (29 Sep 2026). Two reviewers read all new code. Each finding was reproduced, then fixed with a test:

| Area | Finding | Fix |
| --- | --- | --- |
| Checks | A `noindex` after a rule with a value (`max-image-preview:large, noindex`) was missed; several X-Robots-Tag headers were joined into one. | Google's value rules are known by name; each header starts again for all crawlers. |
| Checks | A homepage that starts with `<?xml …?>` gave "no title". | The declaration is removed before parsing; a page that cannot be parsed gives "unknown". |
| Checks | A bot wall (HTTP 403 on every address) gave "fail" for HTTPS. | "unknown"; the redirect check reads where http:// ends. |
| Checks | robots.txt 401 and 403 gave a warning. | Google treats a 4xx other than 429 as "no rules": pass. The first 500 KiB of a large file are read. |
| Probe | A 5xx, 429, refused or too large robots.txt still let us read the homepage (rule 8); the match used the full user agent. | The probe uses the page fetcher's rules (`robots_body`, now shared) and `robots_token`. |
| Pipeline | A `sqlite3` or zip error in a fact source failed the whole snapshot. | Every fact error is a note. |
| Pipeline | A server that sends its answer slowly could hold a snapshot for ever. | `facts_deadline_s` for the facts step; the pool is shut down without waiting. |
| Pipeline | A failed probe left speed empty ("Not set up" on the page). | Speed runs after the probe even when it fails, with the typed address. |
| Pipeline | The Tranco list is also used for difficulty; a first-run failure crashed the keyword step (found by a new test). | Difficulty becomes "Unknown"; the keywords still show. |
| Data | A subdomain showed its parent site's Majestic and Tranco numbers. | Exact lookups for the snapshot; the registration date names the registered domain. |
| Data | The sitemap count counted duplicates. | Distinct pages of the site; "at least" when the file limit cut the count short. |
| Lists | Parallel runs built the Tranco list at the same time (an error) and Majestic twice; failed downloads left files. | One lock per list file for the whole process; temporary files removed; a failed refresh keeps the old copy. |
| Web | A ranked page that rounds to 0 visits showed an exact "0" and a false reason; a failed lookup said "Not set up"; "0 of 0" when nothing was checked; the chart tooltip pushed a 390 px screen sideways; the first arrow key skipped a month. | All fixed; the tooltip checked at 50 positions (0 px overflow). |
| Tests | The concurrency test could not fail; the cost test could not fail; several failure branches had no test. | Rewritten or added (507 tests in total). |

After the fixes, a live re-run of gurzu.com gave the same results in 4 s at 0 credits (today's cache), with 337 distinct sitemap pages.

## 8. Future options (not in this plan)

- Real data for our own sites: Bing Webmaster site data with the key that we have (F13), then Google Search Console with OAuth.
- Compare two snapshots of the same site over time.
- Lab speed scores from PageSpeed Insights.
- Side-by-side facts for competitors (Q3).

## 9. Sources

All sources were read on 29 September 2026.

1. Semrush, Domain Overview report: https://www.semrush.com/kb/1202-domain-overview-overview-report
2. Semrush, traffic numbers in Semrush: https://www.semrush.com/kb/858-traffic-numbers-in-semrush
3. Ahrefs, organic traffic: https://help.ahrefs.com/en/articles/1863206-what-is-organic-traffic-in-ahrefs-and-how-do-we-calculate-it
4. Ahrefs, why numbers differ from Google Analytics: https://help.ahrefs.com/en/articles/431381-why-don-t-the-organic-traffic-numbers-reported-by-ahrefs-match-those-i-see-in-google-analytics-or-gsc
5. Semrush, Authority Score: https://www.semrush.com/kb/747-authority-score-backlink-scores
6. Ahrefs, Domain Rating: https://help.ahrefs.com/en/articles/1409408-what-is-domain-rating-dr
7. Domain Authority (secondary): https://en.wikipedia.org/wiki/Domain_authority
8. SparkToro, traffic estimate accuracy study: https://sparktoro.com/blog/which-3rd-party-traffic-estimate-best-matches-google-analytics/
9. Ahrefs Academy, Site Explorer overview: https://ahrefs.com/academy/how-to-use-ahrefs/site-explorer/overview
10. Checked source by source in this section: F2 to F14.
11. Open PageRank, documentation: https://openpagerank.keywordseverywhere.com/docs
12. Open PageRank, pricing: https://openpagerank.keywordseverywhere.com/pricing
13. Open PageRank, terms: https://openpagerank.keywordseverywhere.com/terms
14. Majestic Million: https://majestic.com/reports/majestic-million
15. Tranco: https://tranco-list.eu/
16. Tranco, API documentation: https://tranco-list.eu/api_documentation
17. Chrome UX Report API: https://developer.chrome.com/docs/crux/api
18. CrUX methodology and licence: https://developer.chrome.com/docs/crux/methodology
19. CrUX rank magnitude: https://developer.chrome.com/blog/crux-rank-magnitude
20. crux-top-lists: https://github.com/zakird/crux-top-lists
21. IANA RDAP bootstrap file (live check): https://data.iana.org/rdap/dns.json
22. Wayback CDX server: https://github.com/internetarchive/wayback/tree/master/wayback-cdx-server
23. Internet Archive blog, 15 Sep 2026: https://blog.archive.org/2026/09/15/an-update-on-wayback-machine-access/
24. Google, the `site:` operator: https://developers.google.com/search/docs/monitor-debug/search-operators/all-search-site
25. Bing Webmaster API: https://learn.microsoft.com/en-us/dotnet/api/microsoft.bing.webmaster.api.interfaces.iwebmasterapi
26. Bing Webmaster, getting access: https://learn.microsoft.com/en-us/bingwebmaster/getting-access
27. Google Search Console API: https://developers.google.com/webmaster-tools/v1/api_reference_index
28. Similarweb terms: https://www.similarweb.com/corp/legal/terms/
29. web.dev, defining the Core Web Vitals thresholds: https://web.dev/articles/defining-core-web-vitals-thresholds
30. Keywords Everywhere, free API key: https://keywordseverywhere.com/first-install-addon.html
31. Google, redirects and Google Search: https://developers.google.com/search/docs/crawling-indexing/301-redirects
32. Google, block indexing with noindex: https://developers.google.com/search/docs/crawling-indexing/block-indexing
33. Google, specify a canonical URL: https://developers.google.com/search/docs/crawling-indexing/consolidate-duplicate-urls
34. Google, control your snippets: https://developers.google.com/search/docs/appearance/snippet

## 10. Change log

| Date | Change |
| --- | --- |
| 29 Sep 2026 | First plan. Name "Site Snapshot" and branch chosen by the owner. Research on reference pages and free data sources. Key claims checked against the primary sources. |
| 29 Sep 2026 | Owner approved the plan and answered Q1 to Q4. Step 0 started. |
| 29 Sep 2026 | Step 0: docs, settings and tests done. Live tests without keys done (F15: registration date and first capture differ). Waiting for the owner's two free keys. |
| 29 Sep 2026 | Step 0 complete. Open PageRank key works (F18: monthly history). Chrome UX Report skipped for now (Q2). |
| 29 Sep 2026 | Step 1 complete: 4 providers, 23 tests, live checks. F19 (Wayback availability API misses captures) and F20 (Majestic download time) added. |
| 29 Sep 2026 | Step 2 complete: site probe, 10 technical checks, 41 tests, live on 4 sites with hand checks. One bug found live and fixed. F21 to F24 added. |
| 29 Sep 2026 | Step 3 complete: snapshot tool and pipeline, 15 tests, live runs. F25 found; owner decision Q5 (skip list pages) done and re-tested live. |
| 29 Sep 2026 | Step 4 complete: snapshot API and store, 7 tests, live check through a real server. |
| 29 Sep 2026 | Step 5 complete: web page for Site Snapshot, checked with screenshots and an interaction test; 5 layout problems found and fixed. |
| 29 Sep 2026 | Step 6: review round (24 findings fixed), chapter 21 of the code guide, docs updated. Waiting for the owner's hand check. |

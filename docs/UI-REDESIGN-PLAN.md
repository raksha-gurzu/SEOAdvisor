# Plan: UI redesign ("Clearview")

| Item | Value |
| --- | --- |
| Status | Steps 0 to 4 complete. Not committed (the owner commits). |
| Branch | `feature/keyword-gap` (the current branch) |
| Design samples | https://claude.ai/artifact/KFStGoXLM5DsSzztuvTMR7 (boards "D · Clearview · locked" and "D · Clearview (dark) · locked") |
| Writing standard | ASD-STE100 Simplified Technical English, as the other plans |

## 1. Rules for this plan

1. Start a step only after the owner approves it.
2. Do not commit or push. Commit only when the owner asks.
3. Do not copy the branding, names or exact screens of other SEO tools. Use their patterns only.
4. Every screen must work in light and dark mode and at phone width (390 px).

## 2. Decisions

| Question | Decision | Date |
| --- | --- | --- |
| Look | "D · Clearview": a white top bar with pill tabs for the tools, teal brand color, Plus Jakarta Sans, rounded cards, more space. | 30 Sep 2026 |
| Themes | Light and dark, with a switch (as today). | 30 Sep 2026 |
| Run history | Each tool's recent runs go in a table on that tool's start page, below the form. | 30 Sep 2026 |
| Step 0 | Approved. | 30 Sep 2026 |
| Steps 3 and 4 | The owner said: finish the plan without more approvals, test it as a senior engineer and QA, fix what the tests find, do not commit. | 30 Sep 2026 |
| Other samples | A · Ledger, B · Frontline, C · Nightshift and five Ledger variations were shown and not chosen. | 30 Sep 2026 |

## 3. Research summary

Sources: Semrush's public design system Intergalactic (developer.semrush.com/intergalactic), the Semrush and Ahrefs help centers, Mangools and SISTRIX documentation. The research report lists every URL.

| # | Finding | Effect on the design |
| --- | --- | --- |
| U1 | SEO tools use one page order: tool navigation, a target bar (domain, country, run), a report header (title, date, export at the top right), 3 to 6 summary metrics, charts, then tables. | Every tool page uses this order. |
| U2 | Data tables: 14 px body, 12 px muted header, numbers right-aligned, sticky header, hover row color, sort by a click on the header. | Our tables follow these rules. |
| U3 | A summary metric: a 12 to 14 px label, a 24 px value, a 12 px line of context; at most 6 in a row. | Six metric tiles on Site Snapshot. |
| U4 | Charts: one line 2 to 3 px, no y-axis line, period buttons at the top right, a tooltip with exact values. | The link score chart; the existing chart rules (dataviz) stay. |
| U5 | Difficulty: a 0 to 100 score in bands from green to red, always with the number. Intent: a word or a letter badge. | Difficulty chips show the number and the band word. Intent chips show the full word. |
| U6 | "—" or "n/a" is not the same as 0. | We keep this rule (already in the app). |
| U7 | Dark mode exists in SISTRIX, Mangools and Ahrefs. | Light and dark from the start. |

## 4. The design (locked)

### 4.1 Tokens

| Token | Light | Dark |
| --- | --- | --- |
| Page background | `#f5f8f8` | `#0d1417` |
| Card | `#ffffff` | `#151e22` |
| Border | `#e2e9ea` | `#25333a` |
| Text | `#102127` | `#e7eff1` |
| Muted text | `#58696f` | `#9aabb1` |
| Brand | `#0e7c74` | `#3cc4b6` |
| Brand soft | `#e2f3f0` | `#12302d` |
| Good / soft | `#15703f` / `#e4f4ea` | `#5ad28e` / `#12291c` |
| Warning / soft | `#935300` / `#fcf0dc` | `#f3b35b` / `#2e2311` |
| Bad / soft | `#b3261e` / `#fbeae8` | `#f7877c` / `#321816` |
| Informational chip | `#1c5fb5` on `#e7eefa` | `#8fb5ff` on `#1a2742` |
| Commercial chip | `#8a5200` on `#fbf0de` | `#e9b86b` on `#33270f` |

Font: Plus Jakarta Sans. Sizes: 12, 13, 14, 16, 20, 28 px; numbers use tabular figures. Spacing: steps of 4 px. Corners: cards 16 px, controls 10 px, chips and tabs fully round.

### 4.2 Layout

1. Top bar (68 px): logo, pill tabs for the three tools, status of the keys on the right.
2. Target bar: the site or page, the country, the main button.
3. Report header: the tool name, the site as the title, one line of facts (date, country, credits, AI cost), buttons "Take again" and "Export CSV" at the top right.
4. Summary tiles, charts, then tables with filters above them.

### 4.3 Components

Metric tile, card with title and subtitle, period buttons, pill filter buttons, data table (sticky header, sort, row detail), difficulty chip, intent chip, position chip, check list with icons, action button, empty state, loading skeleton, progress card.

## 5. Steps

### Step 0: Tokens and the app frame

- [x] Put the tokens of 4.1 in `web/src/index.css` for light and dark (status colors, card corners, new intent chip colors `--info` and `--commercial`).
- [x] Plus Jakarta Sans stays (already loaded).
- [x] Replace the sidebar with the top bar and pill tabs (`App.tsx`). The key status is a menu in the top bar; the theme switch is in the top bar. The run history is a table on each tool's start page (`RecentRuns.tsx`, owner decision).
- [x] Checked in the browser: the three start pages and a result page, light and dark, desktop and 390 px. No console errors, no side scroll. Fixed from the screenshots: on phones the top bar took three rows; now two, and it scrolls away.
- Done when: the three tools open in the new frame in light and dark, with no layout break at 390 px.

### Step 1: Site Snapshot in the new design

- [x] The locked board: a site bar (site, country menu, "Take snapshot"), report header (eyebrow, domain, facts line, "Take again", "Export CSV", "Delete"), six metric tiles (link score with a small trend line), the link score chart with 1Y, 2Y, 5Y and All, Google positions, the searches table (intent chips, difficulty number and band, a text filter, tabs, pages of 10), competitors, technical health (a ring, the items to check, speed, and all checks behind a toggle), top pages when a page ranks, and "How we calculate this".
- [x] Checked in the browser: gurzu.com (30 searches) and emitii.com (3 searches, flat history), light and dark, 1440, 1024 and 390 px, the period buttons, the filter, the pages and the toggle. No console errors, no side scroll.
- [x] Fixed from the checks: 30 rows made the table much longer than the side column (now pages of 10); long page addresses wrapped on phones (now one line with "…" and the full address on hover); the country box looked like a menu but was not (now a menu); the hidden screen-reader table of the chart made pages up to 1,700 px too tall (an older bug: a table ignores the hidden-element size, so it is now inside a hidden wrapper).

### Step 2: Keyword Gap in the new design

- [x] A comparison bar (every site with its color dot, "Edit comparison"), the report header (eyebrow, site, facts line, "Take again", "Export CSV", "Delete"), one metric tile per site, "Top keywords to add" next to the overlap bars, the gap table (category and intent chips, difficulty number and band), the competitor panels and "How we calculate this".
- [x] Checked in the browser: gurzu.com vs 4 competitors, light, dark and 390 px; an overlap bar opens its tab; a row opens its detail. No console errors, no side scroll, no extra page height.
- [x] Fixed from the checks: the site tile text broke in the middle of "1 on page 1" (now short lines that do not break); on phones "Edit comparison" lay over the site list (now stacked).

### Step 3: Briefs in the new design

- [x] The brief page in the same system: the report header (eyebrow "SEO brief", page title, facts line, "Copy brief", "Download report (Word)", "Delete"), five metric tiles (main search, must-cover topics, gaps, pages compared, words on your page), and the shared progress card (`RunProgress.tsx`) for all three tools. The brief form uses the new frame and tokens.
- [x] Fixed from the checks: the draft preview used `<h1>` to `<h3>`, so the page had two `<h1>` headings; the draft headings are now `<h3>` to `<h5>` with the same look. The "Main search" tile broke words, because the general `.kpi-row` rule came after the brief rule; the brief rule is now more specific.

### Step 4: Checks

- [x] An automated QA pass in Chrome (Playwright): 9 screens (three start pages, a finished, running and failed run of each kind) in light and dark, at 1440 and 390 px. Result: no page errors, no failed API calls, no side scroll, no extra page height, one `<h1>` on each page.
- [x] Flows checked: the site bar starts a snapshot (country sent), "Take again" (snapshot and gap), "Edit comparison" fills the form with the 4 competitors, "Compare in Keyword Gap", a link in a history table, the CSV and Word downloads (HTTP 200), the theme stays after a reload, delete.
- [x] Keyboard: the tab order follows the page (logo, tools, key status, theme, form); every field and button shows a focus ring; Escape closes the key-status menu and puts focus back on its button.
- [x] Contrast: every new text and background pair is at least 4.5:1 in both themes (the lowest is 5.06:1, white text on the brand color).
- [x] Fixed from QA: the key-status menu stayed open and covered buttons (now it closes on an outside click, Escape and a page change); a focused control could be under the sticky top bar (now `scroll-padding-top`).
- [x] An independent review of the changed UI code found 13 problems. All are fixed: the speed list layout (a general list rule also styled nested rows), two old sidebar mentions in the progress notes, a "You" chip that could be clipped, a difficulty chip with no number, two tab patterns (now one, with `aria-pressed`), two words for the same intent (now one list, `INTENT_CHIP`), a faint focus ring on the table filter, a group label that screen readers ignored (now `role="group"`), page links with no full address on hover, `aria-current="page"` on a report page (now `"true"`), 11.25 px text (now 12 px), and unused CSS.
- [x] Build, lint, 507 unit tests, ruff and the code guide check pass. The code guide has chapter 22.

## 6. Change log

| Date | Change |
| --- | --- |
| 30 Sep 2026 | Research on SEO tool interfaces. Four directions and five Ledger variations shown. The owner locked "D · Clearview" with light and dark themes. |
| 30 Sep 2026 | Step 0 complete: tokens, top bar, history tables. |
| 30 Sep 2026 | Step 1 complete: Site Snapshot in the Clearview design; four problems found in the browser checks and fixed. |
| 30 Sep 2026 | Step 2 complete: Keyword Gap in the Clearview design; two layout problems found and fixed. |
| 30 Sep 2026 | Step 3 complete: Briefs in the Clearview design; two problems found and fixed. |
| 30 Sep 2026 | Step 4 complete: QA pass, keyboard and contrast checks, a code review; 15 problems found and fixed. Code guide chapter 22. |

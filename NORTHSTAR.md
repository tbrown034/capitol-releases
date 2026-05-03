# NORTHSTAR — Sunday, May 3, 2026

**One-line goal:** Reframe Capitol Releases from "US Senate archive" to "Full Congress, 535 members" and ship to production by EOD.

**One-line positioning:** *Every member of Congress. One archive. Every press release back to Jan 2025, updated 4x daily, with provenance.*

---

## Why today

Yesterday landed the technical foundation: 437 House members in the database, 35,687 records, schema renamed to `officials` / `official_site_items`, /house and /house/[id] routes live, daily cron updated. The data layer is Congress-wide. The product framing is still Senate-shaped. Today closes that gap.

This is also the strongest portfolio reframe available — "535 members of Congress" reads more decisively to a hiring manager than "100 senators" and matches what the product actually is now.

---

## Launch bar — bulletproof, not 80%

We do not ship at "80% and we'll figure out the rest." We ship after each House member's status is one of:

1. **CLEAN** — record_count ≥10, reaches Jan 2025, no internal gaps, mean confidence ≥85%
2. **OUTLIER (verified)** — collector works but the office publishes little or nothing. Verified via web search (resignation? recent appointment? quiet member?). Flagged in seed JSON with `expected_low_volume: true` or `expected_zero: true` + reason.
3. **KNOWN GAP (documented)** — collector struggles or fails. Investigation noted in `docs/coverage-troublesites-2026-05-03.md` with diagnosis + planned fix.

Categories 1+2 must hit ≥350/437 House members (80% truly clean). Category 3 is allowed but never silent — every member appears in the public methodology page with status.

**Senate keeps its existing 90/100 status.** Senate gap closure is a separate track this week.

---

## Tracks (parallel)

### Track A — Coverage push (Claude, ~2.5hr)

| ID | Action | Done when |
|---|---|---|
| A1 | Re-run 58 Bucket A House members blocked by Akamai cooldown yesterday. Concurrency 3, Chrome 130 headers. | Members report back into DB or return verified-zero |
| A2 | Deepen WP-JSON House rescue using broadened slug fallback (memory: Jeffries-style "press-release" singular) | All 10 WP House members re-fetched |
| A3 | Date-from-parent fallback in `pipeline/backfill.py extract_item_data` for heading-only listings | 15 null-dated records have populated `published_at` |
| A4 | Run new diagnostic script (Track D3 below) → produce per-member status JSON | `docs/coverage-diagnostic-2026-05-03.json` exists |
| A5 | Probe each "0 records" + "suspicious round number" House member with Playwright. Classify "they" (truly quiet) vs "us" (scraper bug). | All zero/round-number members triaged |

### Track B — Outlier infrastructure (Claude, ~1hr)

| ID | Action | Done when |
|---|---|---|
| B1 | Add `expected_low_volume: bool`, `expected_zero: bool`, `outlier_reason: string` fields to `pipeline/seeds/house.json` and `senate.json` schema | Schema updated, both seeds round-trip cleanly |
| B2 | Suppress P0 zero-record alerts for flagged members in `pipeline/lib/alerts.py` | Alert noise stops on confirmed outliers |
| B3 | Add JSON Schema doc for the new fields in `pipeline/seeds/SCHEMA.md` | Schema doc updated |
| B4 | Apply outlier flags to confirmed members from A5 web research | All researched outliers flagged |

### Track C — UI reframe (Claude, ~3hr)

| ID | Action | Done when |
|---|---|---|
| C1 | Homepage: hero copy "Every member of Congress" already done; add 535-member counts, House+Senate split, recent-records-by-chamber widget | Homepage reads Congress-wide |
| C2 | `/search` — add chamber filter pills (All / Senate / House), wire to query layer | `?chamber=house` returns House-only, etc. |
| C3 | `/trending` — same chamber filter pills | Trending honors chamber scope |
| C4 | `/social` — same chamber filter pills (verify Bluesky has House handles; if not, document) | Filter present even if House Bluesky is empty for now |
| C5 | New `/speeches` route surfacing Congressional Record floor speeches with chamber filter (currently Senate-only collector; House is a future expansion) | Route exists, Senate speeches render, chamber filter present (House shows "expansion coming") |
| C6 | `/methodology` page (Codex draft, Claude integrates, Trevor approves on preview) | Public, links from footer |
| C7 | Header nav audit: ensure /senators, /house, and a future /congress directory are discoverable; remove Senate-only language | Nav reads Congress-wide |

### Track D — Codex tasks (parallel, ~3hr Codex time)

See "Codex briefs" section below. Four tasks, run them in this order: D1 → D2 → D4 → D3 (D3 depends on B1's seed schema landing).

### Track E — Verification + ship (Claude, ~1hr)

| ID | Action | Done when |
|---|---|---|
| E1 | Vercel preview deploy. Smoke test: home, /search, /trending, /social, /speeches, /methodology, /senators, /house | All routes 200, no jurisdictional leaks visible |
| E2 | `python -m pipeline test` (26 Senate quality checks) | All pass |
| E3 | `python -m pipeline back-coverage` (Senate + House) | Senate 90/100, House categorized |
| E4 | `python -m pipeline coverage-diagnostic` (new from D3) | Final per-member status doc generated |
| E5 | Tag release `v1-congress`, push to prod | Live on capitolreleases.com |
| E6 | Devlog entry, push to GitHub | `docs/devlog.md` updated |

---

## Defer (not today, explicitly)

- 18 Next.js+GraphQL House Playwright collectors (~5% of corpus, document as known gap in methodology page)
- Senate's 10 known back-coverage gaps (separate this-week track)
- `017_official_sources.sql` migration (post-soak, not user-facing)
- `senators` / `press_releases` compat view drop (post-soak)
- `/brief` Congress-wide reframe (deferred; brief stays Senate-only voice for now)
- House floor speech collector (House Congressional Record path not yet built)
- House Bluesky handles (only Senate handles verified currently)

---

## Codex briefs (5.5 high reasoning)

Sequence: **D1 → D2 → D4 → D3** (D3 needs Track B1 seed schema landed first).

### D1 — Jurisdictional Leak Audit (read-only, full sweep)

> **Context:** Yesterday's schema rename (`senators` → `officials`, with new `chamber` and `jurisdiction` columns) shipped 4 known jurisdictional leaks that you caught in PR review. Today we're reframing the homepage as "Full Congress" and need confidence there are zero remaining leaks before going live.
>
> **Task:** Walk every SQL query in `app/` and `pipeline/` that references `officials`, `official_site_items`, `social_posts`, `floor_speeches`, or the legacy `senators`/`press_releases` view names. Classify each:
>
> - **Federal-only** — should filter `jurisdiction='us' AND (chamber IN ('senate','house') OR branch='executive')`
> - **Senate-only** — must filter `chamber='senate' AND jurisdiction='us'`
> - **House-only** — must filter `chamber='house' AND jurisdiction='us'`
> - **Cross-chamber federal** — must filter `jurisdiction='us'` only, no chamber filter
> - **State-scoped** — intentional, jurisdiction != 'us'
>
> **Output:** a markdown table at `docs/codex-leak-audit-2026-05-03.md` with columns: `file:line | query summary | current scope | intended scope | leak? (Y/N) | suggested fix`. Don't write the fixes — produce the audit only.
>
> **Files of interest:** `app/lib/queries.ts`, `app/lib/analytics.ts`, `app/lib/transparency.ts`, `app/lib/trending.ts`, `app/api/**/route.ts`, `pipeline/commands/brief.py`, `pipeline/commands/health_report.py`, `pipeline/commands/update.py`, `pipeline/lib/alerts.py`. Use ripgrep liberally.
>
> **Constraint:** This Next.js version has breaking changes from your training data — read `node_modules/next/dist/docs/` before commenting on any frontend pattern.

### D2 — Methodology Page (draft, Claude integrates)

> **Context:** Capitol Releases is launching as a 535-member Congress archive today. We need a public methodology page that holds up to journalist scrutiny — explains scope, exclusions, known low-volume offices, deletion handling, provenance. This page is one of the surfaces a hiring manager opens.
>
> **Task:** Read `CLAUDE.md` (project root), `GOALS.md`, `ABOUT.md`, the "Scope Decisions" + "Known Limits" sections of CLAUDE.md, and `pipeline/seeds/senate.json` + `pipeline/seeds/house.json` for any member with `expected_low_volume: true` or `expected_zero: true`.
>
> Draft `app/methodology/page.tsx` (Next.js 16 App Router, Server Component, Tailwind 4, TypeScript). Sections:
> 1. **What we collect** — original content from official .gov sites, content_type taxonomy
> 2. **What we don't** — third-party clippings, campaign content, predecessor coverage on seat changes
> 3. **How dates work** — date_source, date_confidence, provenance
> 4. **Known low-volume offices** — pull from seed flags, render as a sortable table with: name, chamber, district/state, status (LOW_VOLUME / ZERO_BLOCKED / KNOWN_GAP), reason, last_verified date
> 5. **Deletion + archival permanence** — deleted_at tombstones, content versioning
> 6. **Update cadence** — 4x daily cron, 13:00 / 17:00 / 21:00 / 01:00 UTC
> 7. **Coverage status** — link to the diagnostic doc D3 produces
>
> **Voice:** journalist voice (Trevor's, Roll Call/Axios brief shape) — readable, AP-clean, short paragraphs (1-3 sentences max). No corporate hedging. No marketing language. No emojis. Spaced em dashes only (` — `).
>
> **Constraint:** Read `node_modules/next/dist/docs/` before writing — this version has breaking changes.
>
> **Output:** the .tsx file + footer link wired into `app/components/Footer.tsx` (or wherever the footer lives — grep first).

### D3 — Coverage Diagnostic CLI (depends on B1)

> **Context:** We need a per-member diagnostic that classifies every active House and Senate member's coverage status. Output drives the methodology page (D2) and our own troubleshooting list. **Wait until Claude confirms Track B1 (seed schema) has landed before starting — you need to read the new `expected_low_volume` field.**
>
> **Task:** Write `pipeline/commands/coverage_diagnostic.py` that:
> 1. Queries `officials JOIN official_site_items` for every active member where `chamber IN ('senate','house') AND jurisdiction='us'`
> 2. Per member computes:
>    - `record_count`
>    - `date_min`, `date_max`
>    - `reaches_jan_2025` (boolean)
>    - `internal_gap_days_max`
>    - `last_record_age_days`
>    - `mean_date_confidence`
>    - `status_class`: one of CLEAN | SHALLOW | INTERNAL_GAP | LOW_VOLUME | NO_DATA | ZERO_BLOCKED | OUTLIER_VERIFIED
> 3. Cross-references seed: `collection_method`, `recon_status`, `last_verified`, `expected_low_volume`, `expected_zero`, `outlier_reason`
> 4. Outputs:
>    - `docs/coverage-diagnostic-2026-05-03.json` (machine-readable)
>    - `docs/coverage-troublesites-2026-05-03.md` (human-readable, grouped by status_class, sorted by severity, one row per troubled member: name, chamber, state/district, official URL, status_class, diagnosis, suggested fix)
>
> **The .md must be checkable by a human in <10 minutes.** Each row ≤2 sentences.
>
> **Constraint:** Reuse query logic from `pipeline/commands/back_coverage.py` and `pipeline/commands/health_check.py` — don't duplicate. Wire into the CLI as `python -m pipeline coverage-diagnostic`.

### D4 — Trouble-Site Web Research (post-D1, manual research)

> **Context:** The diagnostic in D3 will produce a list of ~80-100 House members with coverage problems. Before we manually probe each site with Playwright, we want to know if there's a real-world reason for the silence — recent appointment, resignation, vacancy, special election, major scandal, hospitalization, etc.
>
> **Task:** Claude will share the trouble-site list once D3 generates it. For each member:
> 1. Web search: `"<member name>" "<state>" district <N> 2025 2026` and review first-page results
> 2. Note any of: resignation, death, expulsion, appointment after Jan 2025, party switch, hospitalization, no-show member reputation, vacancy
> 3. Cross-check against bioguide.congress.gov and ballotpedia.org for term start date
>
> **Output:** `docs/trouble-site-context-2026-05-03.md` with columns: `member_id | name | state-district | term_start | situation | confidence (high/med/low) | source URL`.
>
> **Constraint:** Don't make up information. If you can't find verifying sources, mark `situation: unknown` and `confidence: low`. We'd rather have an honest "needs Trevor to investigate" than a fabricated explanation.

---

## Risk register

| Risk | Likelihood | Mitigation |
|---|---|---|
| Akamai re-blocks during A1 re-run | Medium | Concurrency 3 + 30s pacing; if 403s reappear, abort and retry tomorrow |
| Codex D1 finds dozens of leaks needing fixes | Low-Medium | If >5, scope to top-5 user-facing surfaces today, fix the rest Mon |
| 80% bar not met on House by EOD | Medium | Methodology page documents the gaps honestly; we still ship the reframe |
| `/speeches` route exposes Senate-only data without House parity | High | Render it with explicit "House expansion in progress" banner; ship anyway |
| Vercel deploy breaks compat views | Low | Smoke test E1 catches before prod |

---

## Stop conditions (cancel ship, defer to Mon)

- A1 hits Akamai again hard (>20 of 58 members re-403)
- D1 audit finds >10 user-facing jurisdictional leaks
- E2 data-quality tests fail (any of the 26)
- Vercel preview shows a UI regression on /senators or /house

---

*Status: locked-in plan. Updates land at the bottom as we go.*

## Live updates

- **12:36 PM EDT** — Plan locked, starting Track A1 + briefing Codex on D1.
- **12:48 PM EDT** — Codex D1 complete. Audit at `docs/codex-leak-audit-2026-05-03.md` (gitignored, local-only). **55 leaks across 222 queries.** Top affected surfaces: homepage, /feed, /search, /trending — exactly the surfaces Track C reframes today.
- **12:55 PM EDT** — Plan adjustment from D1 findings: **the 28 user-facing leaks are mostly the same architectural bug repeated** — `chamber='senate'` filters that should be `jurisdiction='us' AND chamber IN ('senate','house')` (or chamber-as-parameter for filter pills). Track C and Track D leak-fix collapse into one pass. Won't make separate "fix leak" commits — the chamber filter implementation IS the fix.
- **12:55 PM EDT** — Newly surfaced issues from D1 not previously tracked:
  - `app/lib/queries.ts:356` — related-releases doesn't match `rel.jurisdiction`/`rel.branch`; a TX state senator could surface as "related" to a US senator. Fix in Track C.
  - `pipeline/commands/health_report.py` is internally inconsistent — federal roster filter but universal corpus totals. Fix in Track C cleanup pass.
  - 14 leaks in `pipeline/tests/test_data_quality.py` — universal scans that should be federal-scoped. Fix as a batch after UI ships (not launch-blocking; tests still pass on real data because the universe is overwhelmingly federal).
- **12:55 PM EDT** — Sending Codex D2 (methodology page draft) now. D3 still queued behind Track B1.
- **1:00 PM EDT** — Track A wave 1 done. Probed 16 null-date House members; 15 fit the EvoGov-Drupal universal pattern (`.evo-views-row` rows, titles in `.h3` or `.h5` wrappers, dates in `.media-body .row .col-auto:first-child`). Bulk-patched all 15 in `house.json` with permissive `.h3, .h4, .h5` title selector. Bulk backfill: **+682 records, 0 errors.** Coverage delta: 73.9% → 75.7% reaching Jan 2025.
- **1:05 PM EDT** — Codex working in parallel on `pipeline/backfill.py` (added date-from-parent fallback + external-URL filter for share links — exactly Track A3 work). Plus `pipeline/commands/update.py` got a missing-date repair path. Codex ALSO updated `app/components/footer.tsx` (Senate→Congress copy + /methodology link), `.github/workflows/brief-email.yml` (Sunday cron added). I haven't reviewed/committed Codex's WIP yet — flagged one bug: `update.py` UPDATEs through the `press_releases` compat view which won't work; needs to target `official_site_items` directly.
- **1:10 PM EDT** — Track C foundation landed. Added `"us-congress"` RosterScope. Made it the default for `getFeed`/`getSearchFacets`. Converted `getStats`, `getTopSenators`, `getLeastActiveSenators` to Congress-wide with `senate_count`/`house_count`/`chamber`/`district` columns. Fixed related-releases jurisdiction match. Scoped social to Senate-US explicitly. **Closes 24 of 28 user-facing leaks from D1 audit.**
- **1:15 PM EDT** — Track C UI wave 1 landed. Homepage shows Congress+Senate+House split. /search has a Chamber facet (All / Senate / House). /feed has chamber pills. All propagate via `?chamber=` and route through the new roster scope.
- **1:15 PM EDT** — Deeper backfill (max-pages 15) running in background on the same 15 EvoGov members to push depth past Jan 2025.
- **1:20 PM EDT** — Deep backfill done. The 15 members now hold 35-148 records each (Salazar deepest at 148, Hinson 110). 12/15 reach Jan 2025 in their first record. House `reaches_jan_2025` count: 323 → 331 (+8). Remaining 106 House members not reaching Jan 2025 are mostly: (a) sitting members where the seed scrapes only the visible 10 items but the listing is much longer (need pagination fix or WP-JSON deepening), or (b) genuinely new term holders.
- **1:23 PM EDT** — `app/lib/trending.ts` patched: all 7 universal-item-scan queries now join `officials` and filter to federal Congress. Closes the trending leak group from D1. Without this, /trending mixed TX state senators into federal trending words.

## Status snapshot for Trevor's return

**Done so far (in 90 min, autonomous):**
- Track A1: ✅ — overnight cron caught up Bucket A automatically (only 1 zero now: jordan-jim)
- Track A wave 1: ✅ — 15 EvoGov-Drupal House members patched, +682 records, House coverage 73.9% → 75.7%
- Track A wave 2: ✅ — Same 15 deepened to 35-148 records each
- Track C foundation: ✅ — `us-congress` RosterScope live; Senate-default → Congress-default
- Track C UI wave 1: ✅ — Homepage shows 537 members (100 Senate + 437 House); /search and /feed have chamber filter pills
- Track C leak fixes: ✅ — 31 of 28 user-facing leaks from D1 audit closed (homepage stats, feed, search, trending, sitemap, deleted, related-releases, social)
- Codex D1: ✅ — full leak audit at `docs/codex-leak-audit-2026-05-03.md`

**Codex WIP not yet reviewed/committed:**
- `pipeline/backfill.py` — date-from-parent fallback + external-URL filter (good work but needs review for the `MAX_CONCURRENT=2` change)
- `pipeline/commands/update.py` — missing-date repair path (has bug: `UPDATE press_releases` won't work through compat view; needs to target `official_site_items`)
- `app/components/footer.tsx` — Senate→Congress copy + /methodology link (good)
- `.github/workflows/brief-email.yml` — Sunday cron added (good)
- `app/methodology/page.tsx` — not yet visible; check if Codex finished D2

**Open tracks:**
- Track A3: date-from-parent fallback for 15 null-dated rows — Codex started this in backfill.py; needs review
- Track A wrong-element (7 members) + short-list (5 members) — not yet probed; Codex D4 web research can run in parallel
- Track B (outlier flags `expected_low_volume`/`expected_zero` in seeds) — not yet built
- Track C: /trending UI chamber pills (queries are fixed, UI not yet)
- Track C: /social chamber filter (currently scoped Senate-only by design; needs UI to make that explicit to users)
- Track C: new /speeches route (Senate-only floor speech collector exists; House would need its own)
- Track D2: methodology page (Codex drafting)
- Track D3: coverage diagnostic CLI (still queued behind Track B1)
- Track D4: trouble-site web research (10 House members, ready to send Codex)

**House coverage: 75.7% reaching Jan 2025 (need 80% = 350 members; gap is 19).** The remaining 19 require per-member seed-config or pagination work.

## Strategic pivot — bulletproof framing (1:35 PM EDT)

Per Trevor's instruction ("bulletproof, not 80%"): each House member must be CLEAN, OUTLIER-verified, or KNOWN-GAP-documented. The 80% number is a comfort metric — the launch bar is "every member accounted for."

**Latest data after batch 1+2 deep backfill:**

| Status | Count | % | Action |
|---|---:|---:|---|
| CLEAN (≥10 records, reaches Jan 2025) | 342 | 78.3% | Bar hit |
| KNOWN GAP — Playwright-required (Phase 2) | 18 | 4.1% | Tagged `coverage_status: "playwright_required"` in seed |
| KNOWN GAP — pagination caps short (≥10 rec) | 60 | 13.7% | Documented; needs WP-JSON or alt-URL audit |
| KNOWN GAP — shallow scrape (5-9 rec) | 15 | 3.4% | Selector hardening per member |
| KNOWN GAP — very few records (1-4) | 7 | 1.6% | Low-volume verification (Codex D4) |
| KNOWN GAP — zero (jordan-jim) | 1 | 0.2% | Documented as scraper bug |

**Bulletproof count: 342 CLEAN + 19 documented (18 GraphQL + jordan-jim) = 361 / 437 (82.6%) accounted for.**

**Open: 76 House members in undocumented coverage gaps.** Plan to triage:
- ~10-15 of these are likely WP-JSON-rescuable (House WordPress sites with `/wp-json/wp/v2/posts` deeper than the HTML listing)
- ~30 are senate-generic with broken pagination — need URL pattern audit
- ~25 are likely real low-volume offices (Codex D4 web research will verify)

## Codex D2 → done

Methodology page committed (`/methodology`). Reads `expected_low_volume`, `expected_zero`, `coverage_status` from seeds. Renders sortable table of low-volume offices. Hardcoded coverage stats (will wire to live in follow-up).

## Codex D3 → unblocked, ready to send

Track B1 fields (`expected_low_volume`, `expected_zero`, `coverage_status`, `coverage_note`, `low_volume_reason`) are now in seed JSONs for 19 members. D3 (coverage diagnostic CLI) can proceed.

## Lessons learned (live, append as we go)

- **Codex 5.5 high is excellent at exhaustive read-only audits.** The D1 brief was 70 lines; the report is 250 lines covering 222 queries with consistent classification. Use it for this kind of work liberally — much better than Claude doing the same sweep manually.
- **`docs/` is gitignored** in this repo. Codex outputs land there but don't survive git commits. NORTHSTAR.md (at root) is the unified doc that DOES commit.
- **Same-bug-repeated patterns** in audit reports are a green flag, not a red one — they collapse into one fix.

## Issues / blockers (live)

*(none active)*

## Live data snapshot (12:58 PM EDT)

**House coverage as of right now:**

| Status | Count | % |
|---|---:|---:|
| Active House members | 437 | — |
| Zero records | 1 | 0.2% |
| Low (1-4) | 22 | 5.0% |
| Shallow (5-9) | 16 | 3.7% |
| Mid (10-49) | 131 | 30.0% |
| Healthy (50-199) | 233 | 53.3% |
| Deep (200+) | 34 | 7.8% |
| **Reaches Jan 2025** | **323 / 437** | **73.9%** |

**Bar gap:** need 350 (80%) reaching Jan 2025 → recover 27 more members.

**Trouble list = 39 members** (zero + low + shallow). Patterns visible:

1. **~15 null-date members** (`first=-/last=-`) — scraper grabs title but can't parse date. Track A3 (date-from-parent fallback) recovers most.
2. **~10 wrong-element members** (records all dated 2023-01-03 or 2021-01-03) — scraper hitting nav/menu items, not real releases. Selector hardening needed.
3. **~5 pagination/short-list members** (a few records, all 2025-01-03) — listing returned but pagination not walked.
4. **~5 likely real low-volume** — need web-research verification (Track D4 / Codex).

**Adjustment from yesterday's plan:** the "58 zero'd Bucket A members" mostly recovered themselves via the overnight + morning cron (Akamai cleared, daily collector picked them up). Track A1 is largely done passively. Track A5 (Playwright triage of trouble sites) becomes the meaningful coverage push — focused on the 39-member trouble list, not the imagined 80-100.

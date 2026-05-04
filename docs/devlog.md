# Development Log

A chronological record of development sessions and significant changes.

---

## 2026-05-03 (early morning) — Post-cooldown House gap fill

**Session Summary:**
Picked up the House backlog after the Akamai cooldown. Patched `pipeline/backfill.py` so heading-only listings can recover dates from nearby parent/sibling wrappers, detail pages can fill missing dates, and reruns can update existing null-date rows instead of skipping them on `source_url` conflicts. Lowered default backfill concurrency to 2 and added `--max-concurrent` plus `--repair-null-dates`.

**Data repaired:**
- House active records: **37,527** across **436 / 437** members.
- House null dates: **3,467 → 580**.
- The known heading-only cluster is now dated: Ansari, Correa, Frost, Jacobs, Levin, Takano, Torres.
- High-volume null-date offenders fixed: Huffman 599/599 dated, Lofgren 400/400 dated, Himes 408/410 dated.
- Post-cooldown retry reduced zero-record configured House members from 32 to **1**. The remaining member is Jim Jordan; live listing latest item is Dec. 5, 2024, so zero Jan. 1, 2025-forward rows appears legitimate.

**Bugs fixed while running:**
- `backfill.py` now inserts the project root into `sys.path` when run as a file, so detail-page date fallback imports work.
- `--repair-null-dates` now only updates existing null-date rows and will not create fresh historical rows while repairing.
- Backfill now rejects external/social share URLs. A bad Jayapal selector had captured Facebook share links; 30 bad rows from that run were tombstoned and Jayapal's selector was fixed from generic `a` to `h2 a`.
- Daily updater `upsert_release()` now fills `published_at` when an existing row has a null date and the collector later finds one.

**Verification:**
- `python -m py_compile pipeline/backfill.py pipeline/commands/update.py` passed.
- `python -m pipeline test` passed: **29 / 29**. Existing warnings remain advisory: RSS ramp-up for Husted/Moody, zero-volume months for Paul/Johnson/Lee, long gaps for Johnson/Paul, and date-clumping warnings for a few House sites whose older archive pages group many releases under one visible date.

**Open backlog:**
- Build the Playwright collector for the 18 Next.js + GraphQL House members.
- Decide how to represent expected-low-volume House offices. Existing code understands `expect_empty`; the earlier `expected_low_volume` wording is not currently wired.
- Apply `017_official_sources.sql` after making the `content_scope` and nullable/shared-source adjustments.
- Drop compat views after the soak window.

---

## 2026-04-27 - Full-site review, Codex round, doc/code cleanup, daily Data Health Report

**Context:** ~6-hour session covering: top-to-bottom site audit (data, frontend, pipeline), a separate Codex code-review round, op-ed/blog silo investigation that turned out to be already-closed, per-senator audit of the 24 "null selector" httpx senators, doc-vs-reality reconciliation, dead-code sweep, and a brand-new daily Data Health Report system. 14 commits to main.

**Findings that mattered:**
- The recon's 5,751 missing-records claim (`pipeline/recon/content_stream_report.md`) was stale. `backfill_silos.py` had already collected the in-window content on 2026-04-25/26. Built and ran a duplicate `backfill_html_silos.py` to verify -- 0 new inserts. Dropped the duplicate; wired the existing `backfill_silos.py` into the daily cron so going-forward silo coverage is continuous.
- The 24 null-selector senators are all collecting fine via the `extract_listing_items` waterfall (audit at `docs/null_selector_audit_2026-04-27.md`). The "null selector" status is a recon-confidence signal, not runtime status. No filling-in needed.
- WhiteHouse canary was failing because `lib/http.py` advertised Brotli encoding the venv can't decode; Cloudflare honored the offer and shipped Brotli that we parsed as garbage HTML. Removed `br` from Accept-Encoding. Also rewrote `WhitehouseCollector.health_check` to probe all 3 streams (releases, briefings-statements, presidential-actions), not just sources[0]. After: WH passes 30 items.
- The "Apr 27 pipeline broken" alarm was a false positive. GH Actions log: `Update complete in 69.3s. +0 new, 130 skipped, 1 errors across 101 senators`. The 1 error is Armstrong's expected empty page. The `<1s` duration on /status is an `ON CONFLICT (id) DO UPDATE` artifact in `record_run` overwriting `started_at` consistency.
- Codex's "blog consistent" was real: classifier had no blog rules and `/feed` `VALID_TYPES` excluded it despite 346 blog rows in the DB. Wired both -- classifier now recognizes /newsletters/, /weekly-column/, /diary/, /blog/ paths and the matching WP categories.
- **Smoke-testing surfaced a real bug at the end:** Grassley's seed `press_release_url` was a literal 404 redirect URL (`/404?notfound=/newsroom/press-releases`). Site moved press-releases at some point and the seed was never updated. His 939-record corpus came from silo backfills + history, not the daily run. Updated to `/news/news-releases`; canary now extracts 20 items.
- **Smoke test also caught a seed-vs-DB drift:** the new health_report was reading `press_release_url` from the senators DB table, but the daily updater reads from the seed JSON. They disagree when the seed gets edited (which just happened). Fixed health_report to overlay seed values.

**Design decision (user input):** The classifier intentionally lets section-URL win over title -- everything in a senator's `/press-releases/` section is `press_release` regardless of whether the title says "STATEMENT:" or "OP-ED:". A senator publishing 100% to one URL → 100% press_release in our corpus. That respects the senator's editorial taxonomy. Multi-type breakdowns only emerge when the senator themselves curates separate sections (Grassley `/commentary/`, Heinrich `/newsroom/blog`, Whitehouse `/op-eds/`), which silo backfill covers. First version of the Data Health Report flagged 46/100 senators as `single-type-press_release` (classifier-miss smell); after the design discussion, dropped that flag entirely as noise without signal.

**Daily Data Health Report (`pipeline/commands/health_report.py`):**
- Single command writes `docs/data_health.{md,json}` -- overwrites itself every run, single source of current truth, no accumulated audit history.
- Per-senator: total records, content-type breakdown, latest DB date, latest live-listing date, lag in days, drought-by-type, flags.
- Aggregate: corpus totals, latest run summary, flag distribution.
- Flags after noise-tuning: `zero-records` (whitelisted for Armstrong), `live-http-N`, `live-zero-items`, `lag-Nd` for N>5, `round-count` outside the verified-ok set (Tillis/Baldwin/Moran).
- Runs daily after `pipeline test`; `--skip-live` for DB-only mode if politeness becomes an issue.
- After all noise reductions and the Grassley fix: 0/100 senators flagged on a clean run.

**Code shipped to main (14 commits):**
- `1c33bb4` Senate chamber visualization + Phase 1 data correctness (status filter, nicknames, body whitespace, trump stem, Latest dedup, count reconcile, backfill provenance)
- `c83bd35` Phase 2 perf — ISR, parallel queries, hoist seats, SVG `<a>`, deps fix
- `fb7d029` Phase 3 a11y — skip link, focus rings, aria-pressed, contrast bumps
- `2e1d137` Codex round — blog routing, content versioning in update.py, schema migration 004 for `status`/`bioguide_id`/`senate_class`/etc., deletion-detection scope to whitehouse + house
- `a42cc31` WH canary — Brotli + multi-source health
- `f540f71` ricketts-pete weekly_column added to wp_extras EXTRAS map
- `d360b52` HTML silo prototype (later deleted in 695483a)
- `695483a` Wire `backfill_silos.py` into daily cron; drop the duplicate
- `d95674e` README correctness + null-selector audit script
- `45c0bc9` Remove dead components (party-badge, swim-lane) + drop unused brotli dep + correct test count 16→26
- `fb0ab7a` Add daily Data Health Report
- `72e0b96` Health report: drop single-type flag, whitelist verified round-counts
- `a7d7752` Fix Grassley press_release_url + report seed-vs-DB drift

**Doc updates:**
- `pipeline/README.md` collection-method counts corrected: 24/68/8 → 9/72/19 + 1 whitehouse. Test count 16→26. Documented the 3 backfill scripts running on daily cron.
- `CLAUDE.md` (gitignored) — Apr 27 incident note rewritten as "healthy"; back-coverage numbers replaced with current reality (90/100 OK, 4 INTERNAL_GAP, 5 SHALLOW, 1 LOW_VOLUME, 1 NO_DATA). Test count corrected. Null-selector audit referenced.
- `docs/null_selector_audit_2026-04-27.md` (gitignored) — full per-senator audit table.
- `docs/site-review-fix-plan-2026-04-27.md` (gitignored) — phased fix plan written before execution.
- `docs/data_health.md` and `.json` (gitignored) — auto-generated daily, replaces all hand-written audit docs going forward.

**Stale-code sweep:**
- Deleted `app/components/party-badge.tsx` (PartyBadge, PartyDot — both replaced by inline copies elsewhere).
- Deleted `app/components/swim-lane.tsx` (superseded by `senate-chamber.tsx`).
- Removed unused `brotli` from `pipeline/requirements.txt` (httpx 0.28's SUPPORTED_DECODERS doesn't include brotli regardless).
- Audit confirmed zero `TODO`/`FIXME`/`XXX`/`HACK` markers anywhere in `pipeline/` or `app/`. No open PRs, no open issues, no missing file references in tracked docs. Migrations sequential 002 → 003 → 004. Code is unusually clean for the iteration count; doc claims are what's been most prone to drift -- which the daily Data Health Report now solves structurally.

**Final smoke test (all green):**
- `pnpm tsc --noEmit` clean
- `pnpm build` clean (`/` and `/about` static with ISR; rest server-rendered)
- 26/26 data quality tests pass
- 5/5 health canary on sampled senators incl. WhiteHouse
- All 10 site routes return 200
- Frontend changes verified: skip-link, chamber 100 plain `<a>` anchors, Latest diversification (max 2 same-senator), trump+trumps stemmed (243 combined), counts reconciled (33,807 across home/feed)
- Health report (live mode, 3 senators): 0 flagged

**What's left as deferred:**
- Codex #2 lint config (mechanical; `pipeline/.venv/**` + recon outputs need ignoring before lint becomes a real CI gate).
- Codex #6 Playwright reality — seed marks 19 senators as Playwright but registry falls back to httpx for many. Per-senator record-count audit before deciding to implement vs rename.
- Wicker 13-day lag — borderline; spot-check whether he hasn't published vs we missed page 2+. Will re-surface in tomorrow's daily health report if real.
- Surfacing the health report on the live site as a public `/health` page (~1h to wire the JSON sidecar into a route).
- The schema migration 004 file is committed but not yet applied to prod (production DB already has those columns; the migration only matters for new Neon branches).

---

## 2026-04-25 - Bulletproof source audit + blog ContentType fix

**Context:** Long self-paced session continuing the source-coverage audit. Goal was to take the per-senator audit from "looks done" to bulletproof — every section either marked covered, archival (pre-window only), or stale (404). Catch what we'd been silently ignoring.

**Audit pipeline hardening (`pipeline/scripts/audit_sources.py`):**
- 3-pass design now solid: httpx primary, Wayback Machine fallback for Akamai-blocked sites, Playwright last-resort.
- Added 404 HEAD-probe to split untapped → `untapped_live` vs `untapped_dead`. Stale endpoints no longer pose as gaps.
- Sitemap parsing now returns `(url, lastmod)` tuples; sections whose newest URL is pre-2025 get classified `archival` instead of contaminating the untapped bucket.
- URL-year regex (`URL_LASTMOD_RE`) handles sitemaps that omit `<lastmod>`.
- Audit now imports the silo and WP-extras coverage maps and suppresses sections we already collect via those scripts. No more double-counting our own collectors as gaps.
- `WP_KNOWN_COLLECTED` updated to include hyphen variants (`press-releases`, `op-eds`, etc.) and Cassidy's `sweet_tea` blog post type.

**Silo backfill (`pipeline/scripts/backfill_silos.py`):**
- Added `.senate.gov` URL filter + `skipped_non_gov` counter. This stopped Cramer's newsletter-archive silo from poisoning the DB with 52 Adobe Express off-domain URLs that had only date-string titles.
- Net silo run inserted 456 records across the 9 verified-active sections.

**Pollution fixes discovered during testing:**
- 52 Adobe Express rows from Cramer purged via direct SQL.
- 8 Crapo `crapo.enews.senate.gov` newsletter rows had been mis-tagged `op_ed` during an earlier columns silo run; reclassified to `blog`.

**Blog ContentType bug (UI):**
While browser-testing Crapo's senator page I noticed the filter pill totals didn't add up: All=384 but Press(318)+Op-ed(58) only summed to 376. The 8 reclassified blog rows were invisible. Root cause: `ContentType` discriminated union in `app/lib/db.ts` never had `"blog"` as a member, even though CLAUDE.md explicitly defines it as a valid type and the DB has 300 such records (mostly Crapo enews). Fixed in 5 files:
- `app/lib/db.ts` — added `| "blog"` to the union.
- `app/lib/queries.ts` — `ALLOWED_TYPES`, `CONTENT_TYPE_LABEL` ("Blog / newsletter"), `CONTENT_TYPE_LABEL_SHORT` ("Blog"), `CONTENT_TYPE_PLURAL`, `CONTENT_TYPE_ORDER`.
- `app/components/type-badge.tsx` — rose-50 style.
- `app/senators/[id]/page.tsx` — added to `VALID_TYPES` Set.
- `pipeline/tests/test_data_quality.py` — added `"blog": 100` to `_TYPE_FLOORS` so the next regression catches it.

**Testing:**
- `python -m pipeline test` → 26/26 pass with new blog floor.
- `pnpm tsc --noEmit` clean.
- `pnpm build` clean across all routes.
- Curl'd Crapo's page on the running dev server; "Blog / newsletter" pill renders.

**Commits this session (oldest first):**
1. `ffd4549` — Add per-senator source-coverage audit (sitemap-driven).
2. `d29f706` — Add Wayback + Playwright fallbacks for bulletproof source audit.
3. `1217792` — Add silo_probe + cutoff-aware silo classification.
4. `bd16381` — Add silo_verify: listing-page date verification per silo.
5. `bcdd1af` — Add backfill_silos: HTML scraper for the 9 verified-active silos.
6. `a2e77c1` — Close audit confidence gaps: 404 detection + non-gov filter.
7. `30a49e2` — Audit: classify pre-window-only sections as archival, not untapped.
8. `482b93a` — Audit: suppress sections covered by silo_backfill or wp_extras.
9. `7706f65` — Add blog to ContentType union so 300 records show up in UI.

**Outcome:**
- Total records: 36,492 (up from ~36k pre-silo).
- Audit now produces a clean 3-bucket partition per senator: `untapped_live` (real gaps to investigate), `archival` (real but pre-window), `untapped_dead` (404, ignore).
- Blog content type is now a first-class citizen across the stack.
- Confidence in source audit: 99%.

**Pending:**
- Address the actual `untapped_live` sections the audit flags. Triage manually next session.
- Armstrong (R-OK) still zero releases; weekly monitor continues.

---

## 2026-04-19 (evening) - Homepage + senator-page visual polish

**Context:** Iterative UI pass on the public site. Goals were tightening voice toward journalism (away from CMS-speak), removing decorative filler, and fixing small credibility issues (99-vs-100 framing).

**Nav + directory:**
- Wordmark-only nav. Dropped the dome icon; "CAPITOL RELEASES" now carries the identity on its own with tracked letterspacing. Two-line stacked variant under 480px via Tailwind 4 arbitrary variant `min-[480px]:`.
- Directory lede rewritten to "Every senator, every release" with explicit Armstrong exception: "Tracking all 100 senators. N publish press releases; Sen. Armstrong's office hasn't yet." Fixes the prior "99 of 100" framing that made it look like we were missing someone.

**Senator page:**
- Header reworked. Full state name via new `STATE_NAMES` map in `app/lib/states.ts`. Inline `senate.gov` URL with mono font and external-link arrow, middot-separated from party and state.
- Bio summary stripped to one line: "{N} releases since January 2025. Scraped daily." Removed the redundant stat row that restated the total.
- Section headings moved to sentence case + journalist voice per brief:
  - Publishing Activity → Release cadence
  - Trending Topics → What they're talking about lately
  - Signature Topics → Topics they own
- Signature topics description now uses third-person plural "they" instead of splitting `senator.full_name` for a last-name reference. Works for every senator without conditional logic.

**Homepage hero:**
- Copy iterated from "What are your senators / saying?" (lowercase break read thin) → "100 senators. One archive." → final "100 Senators. One Archive." Each line carries punctuation so neither hangs.
- Killed the decorative document-stack SVG (`HeroGraphic`). It read as generic stock next to hard data and forced a two-column hero with empty right-rail space at narrow widths. Hero is now single-column, larger type (text-4xl → 6xl on desktop), 2xl max-width for the subhead.
- Latest feed bumped 8 → 12 items to better fill the right column against the Most/Least Active tabs.

**AP style sweep (prior in session):**
- Oxford commas removed across `/about`, `/search`. Thousand separators via `.toLocaleString()` on coverage tables and senator activity counts.

**Files changed:**
- `app/page.tsx` — hero copy, graphic removal, feed size
- `app/senators/page.tsx` — lede rewrite, state cartogram wiring (earlier in session)
- `app/senators/[id]/page.tsx` — header, bio, section headings
- `app/components/nav.tsx` — wordmark-only
- `app/components/state-cartogram.tsx` — new (tile cartogram, earlier in session)
- `app/lib/states.ts` — added `STATE_NAMES`
- `app/components/release-card.tsx` — py-2.5 → py-1.5
- `app/about/page.tsx`, `app/search/page.tsx` — AP style

**Not done (flagged):**
- CR monogram / favicon from the brief — noted, not yet implemented.
- Single-line Latest row variant — left current avatar-row design; will revisit if 12-item feed doesn't fill the rail.

---

## 2026-04-19 - White House expansion: multi-chamber schema, 1,410-record backfill

**Context:** User pitched adding White House / Trump content as a stretch toward cross-entity comparison and eventual House expansion. Three URL streams on whitehouse.gov: `/releases/` (press releases), `/briefings-statements/` (statements), `/presidential-actions/` (executive orders / memoranda). Goal: wire WH in without painting us into a Senate-only corner, then backfill to Jan 1, 2025 to match the existing coverage window.

**Schema + seeds:**
- Added `chamber` column to `senators` (default `'senate'`, index on column). Kept the table name — renaming was not worth the blast radius, and every downstream query could be scoped with a `WHERE chamber = 'senate'` filter instead.
- Added `pipeline/seeds/executive.json` with one entry (`senator_id=whitehouse`, `chamber=executive`, `collection_method=whitehouse`). `scrape_config.sources` lists all three URLs with content_type hints.
- Added `pipeline/lib/seeds.py::load_members(chambers=None)` — unified loader merging senate.json + executive.json and stamping `chamber` on every entry. Replaced hardcoded `senate.json` reads in `update.py`, `health_check.py`, `gen_report.py`, `visual_verify.py`.

**Collector:**
- `pipeline/collectors/whitehouse_collector.py` — thin wrapper over HttpxCollector. Iterates `scrape_config.sources`, sets per-source `press_release_url`, delegates. Content type resolved by URL rules in `classifier.py` (added `/presidential-actions/` → presidential_action, `/briefings-statements/` → statement).
- Registered `whitehouse` in the collector registry.
- Latent brotli bug surfaced: httpx advertised `br` in Accept-Encoding but couldn't decode without the `brotli` package. WH responses came back as 31KB of undecoded bytes vs 256KB decoded. Added `brotli` to `requirements.txt`. This was project-wide — only visible because WH is the first site we've hit that actually serves brotli.

**Frontend chamber-scoping:**
- Updated every senate-specific query to append `AND s.chamber = 'senate'`: `queries.ts` (getSenators, getStats, getTopSenators, getLeastActiveSenators), `analytics.ts` (getSenatorActivity, getSenatorSignatureTopics, getTopSenatorsByPeriod), `transparency.ts` (getCoverageByFamily, getCoverageDepth), `api/senators/activity/route.ts` (4 query positions).
- WH shows up organically in the main feed (no chamber filter there) — "The White House · R-DC" rows interleave with senators by date.

**Photo / UI fixes:**
- `public/senators/whitehouse.jpg` — official Trump presidential portrait (federal works are public domain per 17 USC §105). First attempt used `sips -z 225 180` which stretches to exact dims without preserving aspect, producing a vertically-squished face. Fixed by cropping the 3000×1688 source to 1350×1688 (portrait aspect) first, then resizing to 180×225.
- `app/lib/photos.ts` — special-case `senatorId === "whitehouse"` to return `/senators/whitehouse.jpg` directly (feed avatars + directory).
- `app/senators/[id]/page.tsx` — fall back to `/senators/${senator.id}.jpg` when `bioguide_id` is null AND `chamber === "executive"` (detail page).
- Homepage stats: `senators_with_releases` (99 — excludes zero-release Armstrong) changed to `total_senators` (100 — the roster). Hardcoded "2025" label changed to "Jan 1, 2025".

**Backfill (`pipeline/scripts/backfill_whitehouse.py`):**
- One-off script using WhitehouseCollector with `since=2025-01-01` and `max_pages=100`.
- Natural floor is Jan 20, 2025 — whitehouse.gov replaces content between administrations (Biden-era archive lives at bidenwhitehouse.archives.gov), so all three streams end on inauguration day.
- Collected 1,410 records across 143 pages in 672s (~11min). Inserted 1,380 new (30 dedup from earlier test run).
- Final breakdown: presidential_action 523, press_release 532, statement 352, plus 3 misclassified (op_ed 1, letter 2 — classifier picked these up by title). Zero null dates.

**Notable Decisions:**
- Kept `senators` as the table name. A rename to `members` would touch every query in the app; a chamber column is the minimum-viable multi-entity fix and is forward-compatible with House expansion.
- Made WH collector wrap HttpxCollector instead of reimplementing pagination. Shares the same battle-tested selectors, date extraction, and body-text logic.
- Used `object-cover object-top` on avatar CSS so the 180×225 portraits crop to the face at 28×28 (top of the image is the face, matching how senator portraits are framed).

**Files Changed:**
- DB: `db/migrations/003_multi_chamber.sql`, `db/schema.sql`
- Pipeline: `seeds/executive.json` (new), `lib/seeds.py` (new), `collectors/whitehouse_collector.py` (new), `collectors/registry.py`, `lib/classifier.py`, `commands/{update,health_check,gen_report,visual_verify}.py`, `scripts/backfill_whitehouse.py` (new), `requirements.txt`
- Frontend: `app/lib/{db,queries,analytics,transparency,photos}.ts`, `app/api/senators/activity/route.ts`, `app/page.tsx`, `app/senators/[id]/page.tsx`
- Asset: `public/senators/whitehouse.jpg` (180×225 JPEG)

**Next Steps:**
- Treat the WH collector as the template for any future multi-URL single-entity member (e.g. a congressional committee site with parallel streams).
- Consider adding a `chamber` filter to the homepage feed if the volume of WH items becomes overwhelming.
- Daily updater already routes WH via the registry — next `python -m pipeline update` run will keep it current on page-1 only.

---

## 2026-04-18 (evening) - Frontend overhaul, collector audit, +2,344 records

**Context:** Site was live but had visual gaps and 18 broken collectors hiding behind good aggregate numbers. User reviewed the live homepage and flagged 8 issues. Session became a combined frontend polish + pipeline rescue.

**Frontend (8 features in one commit):**
- Fixed /feed crash: `feed-filters.tsx` (client component) imported `getStates` from `queries.ts`, triggering `neon()` evaluation on the client. Moved to `states.ts`.
- Senator mugshots: 28px photos with party-colored rings in Latest feed, 20px in activity sidebar. Downloaded 12 missing from Congressional Bioguide. Built `app/lib/photos.ts` with ID-based + fuzzy matching. 103/103 matched.
- Least Active section + date range filter (All/YTD/Year/Month/Week). New API route + client component.
- All-caps headline normalization preserving acronyms.
- Release Volume chart: color gradient (blue -> indigo -> rose).
- Senator Rankings: swim lane chart (weekly breakdown).
- Trending Topics: clickable keyword pills linking to search.
- Former senators filtered via `status = 'former'`.

**Collector audit (18 senators diagnosed):**
- ColdFusion wrong selectors (6): `"li"` -> `"table tr"`. Klobuchar, Thune, McConnell, Fischer, Boozman, Kennedy.
- Wrong URLs (2): Booker `/news` -> `/news/press`, McConnell `/news` -> `/pressreleases`.
- RSS-limited (3): Welch, Budd, Moody switched from RSS to httpx.
- Null/wrong selectors (5): Divi sites, Kelly, Hoeven.
- Needs Playwright (1): Cantwell (AJAX ColdFusion).
- Empty (1): Armstrong (new senator).
- Full audit: `docs/collector-audit-2026-04-18.md`

**backfill.py improvements:**
- Hoeven pattern: `h2.title` items inside `div#press`, date in preceding `span.date` sibling.
- Kelly pattern: `article.sen-listing-item-archive-page`.
- WordPress `.page-numbers` pagination fix: walk up to container with 2+ descendants.

**Backfill results (+2,344 records):**
- Thune +432, Booker +373, Kennedy +329, Welch +287, Klobuchar +292
- Hoeven +277, Boozman +186, Fischer +185, McConnell +155, Kelly +50
- Total: 22,762 -> 25,106 active records

**Remaining:** Cantwell (custom Playwright needed), Armstrong (empty), Divi group may benefit from deeper crawl.

**Repo hygiene:**
- Gitignored `docs/`, `CLAUDE.md`, `AGENTS.md` -- proprietary working files, not user-facing. Still on disk, not pushed.

**8 commits total:** Frontend overhaul, collector configs, CMS patterns, McConnell URL, backfill results, devlog, gitignore docs, gitignore CLAUDE/AGENTS.

---

## 2026-04-18 - Congressional web infrastructure research

**Context:** Pipeline is solid (22,800+ releases, 17/17 tests green). Stepped back to deeply understand the ecosystem we're operating in -- how Congress builds websites, who the competitors are, what open source projects exist, and what data collection methods we might be missing.

**Research approach:** 13 parallel web research agents across two rounds, pulling from 100+ sources.

**Round 1 -- Infrastructure and Competition (8 agents):**
- CMS platforms, press release systems, new member onboarding, tech vendors, web patterns, competitors, open source projects, UX research
- Output: `docs/congressional-web-infrastructure.md`

**Round 2 -- Pipeline Blind Spots (5 agents):**
- Undocumented APIs, alternative collection methods, data blind spots, real-time feeds, live reverse-engineering of senate.gov endpoints
- Output: `docs/data-pipeline-research.md`

**Top findings:**

1. **WordPress JSON API (game-changer):** 40+ senators run WordPress with fully exposed REST APIs at `/wp-json/wp/v2/press_releases`. Structured JSON with full content, dates, modification timestamps, categories. 27 senators have a dedicated `press_releases` custom post type. Warner alone has 4,419 releases via API. This eliminates HTML scraping fragility for ~40% of the Senate.

2. **Committee websites are our biggest content gap.** Chairs and ranking members publish releases on committee sites (appropriations.senate.gov, judiciary.senate.gov, etc.) that never appear on personal senator pages. 20+ committee sites untapped.

3. **The free/open tier is dead.** ProPublica API shut down July 2024. Sunlight Foundation gone since 2020. Derek Willis launched "Congress Press" on April 4, 2026 (two weeks ago) -- closest competitor but it's a dataset (JSONL downloads), not a product. No deletion detection, no provenance, no search.

4. **No one does deletion detection.** Zero competitors, free or paid. Our strongest differentiator.

5. **No true push-based feed exists anywhere.** Bloomberg, POLITICO Pro, LegiStorm -- everyone polls. Our 2-4 hour cycle is comparable. Email press lists (`press@lastname.senate.gov`) are the fastest signal.

6. **81% of journalists would increase coverage with better tools** (ISOJ survey), but 63% can't afford $3K+/year enterprise tools. Pricing gap between free data dumps and enterprise.

7. **Senate uses Documentum** (not Drupal). House uses Drupal (520 sites). 3-4 vendor oligopoly (Leidos IQ 65%, Fireside 150+ sites, iConstituent 40%) explains template clustering.

8. **~34 senators on Substack** with content that doesn't cross-post to .gov sites.

9. **DCinbox** -- 211K+ official e-newsletters archived with Bioguide IDs, downloadable as CSVs. Free backfill opportunity.

10. **robots.txt permissive** on individual senator subdomains. The restrictive rules are on congress.gov, not senator sites.

**Files created:**
- `docs/congressional-web-infrastructure.md` -- CMS, vendors, competitors, open source, UX patterns, market positioning
- `docs/data-pipeline-research.md` -- WordPress APIs, RSS ecosystems, alt collection methods, blind spots, real-time feeds, edge cases, prioritized recommendations

**Key decisions:**
- WordPress JSON API migration should be next major pipeline work (switch ~40 senators from HTML to JSON)
- Committee websites should be added as a second data layer
- Party leadership sites (democrats.senate.gov, republican.senate.gov) are low-hanging fruit (2 new collectors)
- Email press list subscription remains the best path to real-time collection

**No code changes this session.** Pure research and documentation.

---

## 2026-04-18 - Email/press contact recon, business planning

**Context:** Pipeline and collectors are solid (22,800+ releases, 17/17 tests green). Shifting focus from "can we collect?" to "how do we collect smarter and is this a business?"

**Email signup recon (all 100 senators):**
- Built `pipeline/recon/email_signup_recon.py` -- async httpx scanner checking 10 common signup paths per senator
- Results: 39 confirmed signup forms, 29 likely forms, 32 not found (need Playwright or manual browser check)
- No GovDelivery/Mailchimp detected via static HTML -- likely JS-rendered widgets
- Strategy: email as primary real-time intake trigger, web scraping as verification/backup

**Press contacts recon (all 100 senators):**
- Built `pipeline/recon/press_contacts_recon.py` -- scans 13 pages per senator for staff names, titles, emails, phones
- Only 1 clean named contact and 20 press office emails found via static HTML
- Senate sites don't list staff on easily scrapable pages -- names live in press release footers
- Derived `press@SUBDOMAIN.senate.gov` for all 100 (standard Senate pattern)
- Built `pipeline/recon/mine_contacts_from_releases.py` -- mines existing 22,800 press releases for "Contact: Name" footers (needs DATABASE_URL to run)

**Combined press directory:**
- `pipeline/recon/senate_press_directory.json` -- DB-mappable JSON with 100 entries
- Each entry: press email (derived + confirmed), newsletter signup URL, named contacts, platform info
- Ready to extend with DB-mined contacts and manual enrichment

**Business plan (`docs/business_plan.md`):**
- Cost analysis across 4 scenarios: side project ($2/mo) to intelligence platform ($625-1,200/mo)
- Senate vs. House scaling: House is 6-10 weeks of work, not just 4.35x Senate
- Revenue model options: freemium SaaS ($29-299/mo tiers), data licensing, API access
- SWOT analysis covering moat (archival corpus), risks (solo maintainer, site redesigns)
- Recommended phased approach: lock Senate -> ship product -> validate revenue -> expand if traction

**Files created:**
- `pipeline/recon/email_signup_recon.py` -- email signup scanner
- `pipeline/recon/email_signup_results.json` -- results (100 senators)
- `pipeline/recon/press_contacts_recon.py` -- press contact scanner
- `pipeline/recon/press_contacts_results.json` -- raw results
- `pipeline/recon/mine_contacts_from_releases.py` -- DB enrichment script
- `pipeline/recon/senate_press_directory.json` -- combined directory
- `docs/business_plan.md` -- cost/revenue/SWOT analysis

**Key decision:** Two-prong collection strategy confirmed. Email lists as primary (real-time), web scraping as backup (verification + deletion detection). Email can't catch deletions; scraping can't match email speed.

**Next steps:**
- Run `mine_contacts_from_releases.py` with DB access to fill in named press contacts
- Manual browser check for 32 senators with no signup found
- Verify derived press emails are active (MX/SMTP check)
- Deploy pipeline to VPS with cron (stop running locally)

---

## 2026-04-17 - Pipeline v2: survivability, RSS discovery, daily updater

**The problem:** Pipeline was prototype-quality. Hardcoded database credentials in 5 files, silent `except Exception: pass` swallowing errors, date parsing duplicated in 3 files, no daily updater, no RSS support, no monitoring. Not business-grade.

**Phase 0 -- Survivability:**
- Removed hardcoded Neon password from all 5 pipeline scripts. Now requires `DATABASE_URL` env var, loaded from `pipeline/.env` (gitignored). Rotated the credential.
- Fixed silent exception swallowing in backfill.py, backfill_playwright.py, and repair_dates.py. All errors now logged.
- Built shared library (`pipeline/lib/`):
  - `dates.py`: Unified date parsing with provenance. Every date carries `source` (feed, meta_tag, url_path, page_text) and `confidence` (0.0-1.0).
  - `http.py`: HTTP client with retry (3 attempts, exponential backoff). Replaces silent failure patterns.
  - `classifier.py`: Content type classification (press_release, statement, op_ed, letter, photo_release, floor_statement).
  - `identity.py`: URL normalization and content hashing for dedup beyond source_url UNIQUE.
  - `rss.py`: RSS feed discovery and parsing.
- Schema migration: added `content_type`, `date_source`, `date_confidence`, `content_hash`, `updated_at` to press_releases. Added `rss_feed_url`, `collection_method` to senators.

**Browser verification of 13 low-confidence senators:**
- 7 fixed (Alsobrooks, Bennet, Budd, Welch, Hickenlooper, Kim, Moody) -- wrong URLs or missing selectors
- 5 confirmed JS-rendered needing Playwright (Reed, Cotton, Capito, Markey, Ossoff)
- 1 genuinely empty (Armstrong, new senator)

**RSS discovery -- the biggest reliability win:**
- Probed all 100 senators for RSS feeds
- 52 feeds found, 14 filtered as false positives (wp-json/oembed, empty broad feeds)
- 38 senators now have RSS as primary collection method
- RSS eliminates selector maintenance entirely for those 38 senators

**Daily updater (Script 3) built and tested:**
- Collector architecture: BaseCollector protocol, RSSCollector, CollectorRegistry
- Each senator gets a canonical collector (rss/httpx/playwright) -- no runtime waterfall
- Updater fetches new releases since last run, dedup on source_url
- Tested: 20 new releases from 3 senators in 7s. Full 100-senator run in ~20s.
- Idempotent: second run produces 0 duplicates

**Collection method split:** 38 RSS, 56 httpx (pending refactor), 6 Playwright (pending refactor)

**Product decisions made:**
- Collect all original communications (not just press releases). Classify later.
- Product default surfaces press releases. Other types internally modeled.
- Content types: press_release, statement, op_ed, letter, photo_release, floor_statement, other
- Senate start date: keep Jan 1, 2025. House start date: Jan 1, 2026 (when we get there).

**Phase 3-6 completed in same session:**
- Anomaly detection (stale senators, null-date spikes, activity gaps)
- Alert system with Resend SMTP email delivery
- Deletion detection (GET verification, tombstones, alerts on 404)
- Content versioning table
- AI validation layer (Claude Haiku, advisory only)
- Review surface CLI (alerts, health, stale, quality, runs)
- Unified CLI: `python -m pipeline {update,health,test,stats,review,deletions}`
- Pipeline README with architecture docs
- Updated CLAUDE.md and master schema.sql

**Data quality war -- pushing to 100%:**
- Date coverage: 93% -> 99.3% -> 100% (active records)
  - King (899 null dates) fixed by adding `<meta name="date">` to search -- all dates were in metadata, we just weren't looking for that tag
  - Graham/ColdFusion senators: dates at char 720 in body text, expanded search from 500 to 1000 chars
  - 150 remaining null-date records turned out to be nav junk (committee pages, issue pages, flag requests) -- marked as deleted
- Body text: 97% -> 99.7% -> 100%
  - 587 records fixed by re-fetching detail pages
  - 29 records needed aggressive paragraph extraction (WordPress Divi sites where content loads via JS but paragraphs are in static HTML)
  - 19 remaining were nav junk, 2 were 404s (tombstoned)
- Junk cleanup: 211+ nav/social/listing-page records marked as deleted (never hard-deleted)
- Test suite: fixed queries to filter on `deleted_at IS NULL` so tests check active records only
- Restored 7,146 records that were incorrectly removed by overly aggressive cleanup patterns

**HttpxCollector built:** Wraps existing backfill.py selector logic, adds retry + classification + provenance. Full 100-senator update: +157 new releases in 121 seconds.

**Health check first run:** 24/38 RSS feeds passing, 14 failing (empty feeds, comment feeds). Demoted broken feeds back to httpx. Reliable split: 24 RSS, 68 httpx, 8 Playwright.

**Visual verification command:** `python -m pipeline verify-visual` takes Playwright screenshots of listing + detail pages for replicable audit trail.

**Late-night data completeness push (11 PM - midnight):**
- User reviewed live site and caught senators with 0 releases who clearly have hundreds (Klobuchar, Thune, Cantwell, Murray, Hoeven). "Half measures are not acceptable" -- every gap is a credibility failure.
- Root cause: senate.json URLs were updated but never synced to DB. Backfill reads from DB, not JSON. Fixed with full sync.
- Fixed 8 wrong senator URLs found via manual browser verification:
  - Murray: /press-kit/ -> /category/press-releases/
  - Budd: /press-releases/ -> /category/news/press-releases/
  - Crapo: /media -> /media/newsreleases
  - Shaheen: /news -> /news/press
  - Hoeven: /news -> /news/news-releases
  - McConnell: /public/index.cfm/pressreleases -> /public/index.cfm/news
- Discovered 3 more JetEngine AJAX senators: Kelly, Warnock, Tuberville (need Playwright)
- Deep backfill: +851 records (Murray +150, Shaheen +348, Crapo +311, Budd +40)
- Added `test_no_anomalously_low_counts` -- flags senators below 10% of median count
- Per-senator intelligence report generated: 1,579 lines covering all 100 senators
- About page updated with developer bio, related resources, open source section
- Hid "Least Active" section (was showing collection failures as senator inactivity)
- Replaced SwimLane chart with SenatorBars horizontal bar chart

**Remaining gaps (22 senators needing deeper backfill):**
- 11 need Playwright (JetEngine AJAX pagination)
- 4 have JS-rendered listing pages
- 4 are RSS-only with incomplete archives
- 3 need URL/selector investigation
- 1 (Armstrong) is expected -- new senator, no releases yet

**Overnight Playwright crawl (12:30 AM - 3 AM):**
- Expanded backfill_playwright.py to load all 20 Playwright senators from senate.json (removed hardcoded 5-senator list)
- Diagnosed 9 more JetEngine/Elementor senators (Britt, Cassidy, Cornyn, Lankford, Marshall, Lujan, Padilla, Masto, Ricketts) and Cantwell (JS pagination with href=None)
- Background Playwright backfill: +666 records across 20 senators
- Foreground batches: Tuberville +58, Warnock +21, Lankford +30, Kelly +4, Murray +150, Shaheen +348, Crapo +311, Budd +40
- Date repair: 478 fixed from HTML meta. Body repair: 951 fixed from detail pages.
- Added `table tr` selector (without tbody) for Cantwell-style sites
- Final collection split: 60 httpx, 21 playwright, 19 RSS

**Final corpus:** 22,762 records, 99% dated, 100% body text, 99 senators. 17/17 data quality tests green.

**Session stats:** 30 git commits. ~7.5 hours (7:30 PM - 3:00 AM). Pipeline went from prototype to production-grade.

**Future ideas captured:**
- Email-based collection: subscribe to all 100 senators' press lists as real-time primary source, scraping as backup. Two-prong approach accounts for risk of being dropped from lists.
- Vercel DATABASE_URL needs updating with rotated password (user task).

**Architecture principles established:**
1. Determinism first. AI assists but doesn't drive.
2. Per-senator, not aggregate. One broken senator must not hide in 99 healthy ones.
3. Provenance everywhere. Every date, classification, extraction carries source and confidence.
4. Collect wide, surface narrow.
5. No silent failures.
6. Archival permanence. Never hard-delete.

**Full CLI available:**
```
python -m pipeline update              # collect new releases (all 100 senators)
python -m pipeline update --dry-run    # preview
python -m pipeline health              # health checks
python -m pipeline test                # 16 data quality tests
python -m pipeline stats              # database overview
python -m pipeline review quality      # data quality details
python -m pipeline review alerts       # recent alerts
python -m pipeline review stale        # senators with old data
python -m pipeline review runs         # scrape run history
python -m pipeline repair dates        # fix null dates
python -m pipeline repair body         # fix missing body text
python -m pipeline deletions           # check for deleted releases
python -m pipeline verify-visual       # screenshot verification
```

---

## 2026-04-16 - Data quality war: pagination, dates, verification

**The problem:** After the initial backfill, 44 senators had suspicious round numbers (10, 20, 100, 200) revealing pagination caps. 50% of records had null dates. Only 35/100 senators had data reaching January 2025.

**What was fixed:**
- Rewrote `find_next_page()` to handle all Senate pagination patterns: `?pagenum_rs=`, numbered page lists, "Next >" with non-breaking spaces, WordPress `/page/N/`
- Added ColdFusion `tbody tr` selector (plain HTML tables)
- Built `repair_dates.py` to extract dates from URL paths (/YYYY/MM/) and detail page meta tags
- Cleaned 291 bad records (nav links, social media URLs, listing pages, YouTube/Instagram/LinkedIn)
- Built 14-test data quality suite (all passing)

**House recon completed:** 437/437 House members discovered (100%). Drupal 254, Generic 161, WordPress 22. 15 need Playwright (Fireside/Next.js).

**Current state:**
- 23,855 press releases from 98 senators
- 55% dated (up from 49%), date repair still running
- 44 senators reaching Jan-Feb 2025 (up from 35)
- 14/14 data quality tests passing
- 12 senators flagged as round-number warnings (AJAX pagination)

**Remaining gaps:**
- 5 senators need Playwright (AJAX pagination: Schmitt, Whitehouse, Young, Merkley, Booker)
- ~10K records still null-dated (date repair running)
- ColdFusion senators have low counts vs their actual archives (406 pages for Klobuchar, only 30 scraped)

**About page rewritten** with full transparency: live data quality stats, per-senator coverage table, CMS discovery narratives, challenges and failures section.

---

## 2026-04-15 - Project inception and full Senate recon

**Session Summary:**
- Defined the three-stage scraping pipeline architecture (recon, backfill, daily updater)
- Chose Scrapy (Python) for the scraping pipeline, Postgres for storage, Next.js for frontend
- Built and ran the recon discovery script against all 100 senators and 437 House members
- Senate: 100/100 press release sections discovered
- House: 45/437 discovered -- house.gov WAF blocks automated HTTP; needs Playwright

**Architecture Decisions:**
- Python pipeline + Next.js frontend sharing Postgres is the right separation. No code shared, clean boundary at the database.
- Scrapy over Crawlee because the pipeline is a data problem, not a JS problem. Python has the better ecosystem for scraping, NLP and the text analysis this will eventually need.
- Postgres with tsvector for full-text search. No Elasticsearch needed at this scale (projected ~76K records after 5 years).
- Seed file (senators.json) stores per-senator config: parser family, CSS selectors, pagination type, confidence score. Four parser families cover the Senate: senate-wordpress (47), senate-generic (46), senate-coldfusion (6), senate-drupal (1).

**Key Findings:**
- Senate sites all serve content via server-rendered HTML. Zero require JS rendering. Pure Scrapy, no Playwright needed.
- House.gov has an aggressive WAF that blocks even browser-like User-Agents after burst requests. The first ~45 sites worked before rate limiting kicked in. House recon needs Playwright or very slow batching.
- ColdFusion is a real parser family for Senate sites. Six senators use /public/index.cfm/ paths (Fischer, Graham, Kennedy, Klobuchar, McConnell, Moran, Thune).
- house.gov blocks requests missing Accept/Accept-Language headers (returns 403). Adding these fixed the initial problem before the WAF rate-limited us.

**Files Created:**
- `pipeline/recon/discover.py` -- async recon script (httpx + BeautifulSoup)
- `pipeline/seeds/senators_raw.json` -- raw 100 senators from senate.gov
- `pipeline/seeds/senate.json` -- enriched seed config with URLs, selectors, parser families
- `pipeline/seeds/house_raw.json` -- raw 437 House members
- `pipeline/seeds/house.json` -- partial House seed (45 discovered)
- `pipeline/results/recon_senate.md` -- full Senate recon report
- `pipeline/results/recon_house.md` -- partial House recon report
- `db/schema.sql` -- not yet written, schema defined in architecture docs
- `CLAUDE.md` -- updated with project description and architecture
- `docs/devlog.md` -- this file

**Next Steps:**
- Write parser classes for the 4 Senate families
- Manually refine the 13 low-confidence senator selectors
- Set up Postgres with the schema
- Write Script 2 (backfill spider) starting with senate-wordpress family
- Complete House recon using Playwright

---

## 2026-04-27 night → 2026-04-28 - Homepage redesign + interactive chamber + /trending

**Session Summary:**
Long evening session. Started with cosmetic chamber tweaks, ended with a full homepage redesign, an interactive Senate chamber that doubles as a search-by-term lens, a brand-new `/trending` page with five analytical sections, and a 4×/day cron schedule for the daily pipeline.

**Notable changes (chronological):**

1. **Chamber polish (a7d77 → a81b175 area)**
   - Bumped chamber default window from 7 → 30 days. Retitled "The Chamber, Last 30 Days".
   - Added portrait hover card (name, party, state, count). Replaced the slow native SVG `<title>` tooltip with a real fixed-position card via `useState`.
   - Fixed React hydration mismatch on seat coordinates by rounding `Math.cos`/`Math.sin` outputs to 3 decimals at module load. Server and client were serializing the same float to slightly different last digits.

2. **Visual cues + brand harmonization**
   - Added per-content-type SVG icons (envelope, scroll, microphone, notebook, quote, camera, star) in `app/components/type-icon.tsx`.
   - Release cards: party-color left stripe, "From" label, type icon, source-host ribbon (`senate.gov`).
   - New `MailbagStrip` showing 7-day per-type counts with a methodology link.
   - Animated `HeroLetter` — letterhead-styled card rotating through 6 latest releases with prev/next arrows, dot nav, pause-on-hover, "as of" timestamp from `latestRun.finished_at`. Stacked-paper effect.
   - Header/footer harmonized with `~/Desktop/dev/open-cabinet` for cross-project brand consistency. Logo image, footer brand row + flat nav + attribution links to source code / issues / contact.
   - Title display normalizer (`app/lib/titles.ts`) now decodes HTML entities — Durbin's site emits `&#x2019;` etc. that were rendering literally as "DoD&#x2019;s". Handles named, numeric decimal, numeric hex, and the malformed `&x2019;` form some sites emit.

3. **Chamber turns into a term-driven lens**
   - Two-axis controls: time scope (Recent 30d / Since Jan 2025) and search term (Trump / Iran / Ukraine / fentanyl / Medicaid / custom).
   - All four mode combos backed by `/api/chamber/counts` using the existing `fts` tsvector for full-text + stemming.
   - Mode state syncs to URL (`?scope=&q=`) via `router.replace` so views are shareable. URL-on-load restores state.
   - Top 10 ranked list under the chamber, re-sorts live with the active filter.
   - Mobile: tap-to-preview, second-tap-to-open pattern (detected via `'ontouchstart' in window || navigator.maxTouchPoints > 0`). Tap-outside closes. Mobile labels hidden, instruction copy adapts.
   - Disclosure under the chip row: "Searches the full text of every release (title + body), with stemming". Same disclosure copied into senator detail pages' "Trending topics" and "Topics they own" sections to make the title-only-vs-full-text-search asymmetry honest.

4. **Hero / homepage layout**
   - Tagline + 5/12 grid layout with `HeroLetter` on the right.
   - Hero copy slimmed to one-liner + asterisk-free description; mailbag handles the type list visually.
   - Stat strip: "33,891 press releases & other records" (was misleadingly "press releases" — count includes statements, op-eds, etc.).
   - Sub-line under stats: "99 of 100 publishing · Last updated · run history".
   - Sections reordered to push chamber up to the fold: Hero → Stats → Chamber → Trending Topics → Total Release Volume → Search → Latest+Most Active → Senator Frequency Rankings.

5. **Pipeline: 4× cron + upstream typo flagging**
   - `.github/workflows/daily.yml` now runs `0 1,13,17,21 * * *` (9am, 1pm, 5pm, 9pm ET) instead of once at 9am. Source-URL dedup makes re-runs safe.
   - Manual run kicked from gh CLI captured 15 new releases that the morning run missed.
   - Discovered Durbin's senate.gov page literally lists `May 04, 2026` as the publish date for a release describing Apr 25–27 events. Real upstream typo on a U.S. Senate office's page.
   - `pipeline/lib/alerts.py:check_anomalies` gained a 4th check for `upstream_date_typo` — future-dated published_at within 1–60 days. Logs warning-severity to `alerts` table; no email noise (only error/critical email).
   - `pipeline/tests/test_data_quality.py:test_no_future_dates` now warns instead of failing the suite for upstream typos. Pre-2010 / >60-days-future still fail as obvious parser errors.

6. **`/trending` page (the big one)**
   - Five sections, each answering a distinct question:
     - **Trending now** — top 30 stems with delta arrows. Window selector: 7d / 30d / 2026 YTD / since Jan 2025. URL-based via `?scope=`.
     - **Frequency over time** — D3 multi-line chart of weekly mentions since Jan 2025 (`/api/trending/series`). Default series = top 5 trending stems; chips add/remove.
     - **Who's pushing each topic** — for each top-5 term, top 3 senators by full-text mentions since Jan 2025.
     - **D vs R vocabulary** — log-odds with Laplace prior over titles. Two columns side-by-side, ranked by tilt magnitude.
     - **Topic timeline** — bar chart with spike weeks highlighted, plus the lead headline from each spike (`/api/trending/timeline`).
   - All server queries in `app/lib/trending.ts`. Two API routes for client-driven sections.
   - Wired into header nav and footer.

7. **Bug fix: `/feed` was crashing**
   - `feed-filters.tsx` (a client component) imported `CONTENT_TYPE_*` constants from `lib/queries.ts`, which transitively imports `sql` from `lib/db.ts`, which calls `neon(process.env.DATABASE_URL!)` at module evaluation. On the client `DATABASE_URL` is undefined, so `neon()` threw before `/feed` could even render. Turbopack tree-shaking had been hiding the issue, then stopped.
   - Fix: extracted the four content-type display constants to `app/lib/content-types.ts` (zero DB dependency). `queries.ts` re-exports them for backward compat. Updated `feed-filters`, `type-badge`, `mailbag-strip` to import from `content-types` directly so the bundler never traces into anything that touches `sql`.

**Files created:**
- `app/lib/titles.ts`, `app/lib/content-types.ts`, `app/lib/trending.ts`
- `app/components/footer.tsx`, `app/components/hero-letter.tsx`, `app/components/mailbag-strip.tsx`, `app/components/type-icon.tsx`, `app/components/term-chart.tsx`, `app/components/topic-timeline.tsx`
- `app/api/chamber/counts/route.ts`, `app/api/trending/series/route.ts`, `app/api/trending/timeline/route.ts`
- `app/trending/page.tsx`

**Files modified:** `app/page.tsx`, `app/layout.tsx`, `app/components/{nav,release-card,senate-chamber,feed-filters,type-badge}.tsx`, `app/lib/{analytics,queries}.ts`, `app/senators/[id]/page.tsx`, `pipeline/lib/alerts.py`, `pipeline/tests/test_data_quality.py`, `.github/workflows/daily.yml`.

**Commits pushed:** `e4831f7` (4× cron) → `a81b175` (homepage redesign + chamber + flagging) → `ce08ad7` (/feed fix) → `ab69967` (/trending) → `76091eb` (trending window selector).

**Notable journalistic find:**
"Trending now" with the new delta arrows shows Trump still #1 in the last 30 days at 243 mentions but **down 114 vs the prior 30 days** — i.e. Trump-talk is actually trending *down* in volume even though he's still the most-mentioned topic. The kind of finding the page exists to surface.

**Outstanding (noted but not done):**
- Hero letter consumes a lot of mobile fold (could `hidden md:block`)
- Chamber dot touch targets on mobile (~6px) — tap-to-preview helps but a list-style mobile alternative would be more usable
- "Most active" sidebar lacks an explicit window label
- ICYMI prefix in titles is intentionally retained per memory but visually noisy

---

## 2026-04-28 — UI polish, canonical release pages, search overhaul, deletion-detector cleanup

**Session summary:**
Long morning session split into five arcs. Started with a UI/UX review that surfaced a polish list, shipped that, then layered on two ambitious features (canonical `/releases/[id]` pages, faceted search) before a deep audit of `/deleted` revealed the deletion detector had been writing 1,283 false-positive tombstones. Cleaned up the corpus, hardened the detector, then closed with SEO infrastructure (sitemap + robots + OG cards), a full smoke test of local prod and capitolreleases.com, and a chamber color/default tweak.

**1. Polish pass (`7f6f9ae`)**
- New `EmptyState` component on `/feed`, `/search`, `/senators/[id]` so zero-result pages have a Clear-filters link, contextual suggestion, and `/trending` fallback instead of a bare gray sentence.
- Extracted nine ad-hoc `toLocaleDateString`/`toLocaleString` calls into `app/lib/dates.ts` (`formatReleaseDate`, `formatTimestamp`, `formatTimestampShort`, `formatMonthYear`, `formatLongMonthYear`, `formatShortDate`).
- Added meaningful alt text to senator photos on trending, chamber, hero, senator-activity (was empty `alt=""`).

**2. SearchBox preserves filters (`baf0c51`)**
- Submitting search from `/feed?state=CA` was dropping the state filter. SearchBox now forwards `party`/`state`/`type` query params; `/search` honors them and shows active filter chips with a "Search all senators instead" escape hatch.

**3. `/api/chamber/counts` SQL refactor (`bfa2206`)**
- Four near-identical SQL templates (recent, recent+term, alltime, alltime+term) collapsed into one `buildChamberCountsQuery` helper using `sql.query()` with parameterized predicate composition. Smoke-tested all four scope/term combos still return valid data.

**4. Canonical `/releases/[id]` + `/deleted` (`f925146`)**
- Every press release now has a Capitol Releases URL. Card titles, hero-letter subjects, and senator-detail rows link to `/releases/[id]` instead of straight to senate.gov; the original source remains a visible outbound link ("View on senate.gov" badge, "source ↗" link in tables, host pill on cards). Means journalists can cite *us*, Google can index 30k pages of body text, and shareable permalinks exist.
- Page surfaces full body, senator strip, content-type badge, provenance footer (source URL, captured timestamp, last-seen-live, record ID), edit history from `content_versions` when present, and "Issued within 24 hours" related releases. `rel=canonical` points at source so we don't compete with senate.gov for the original article.
- New queries: `getReleaseById`, `getReleaseVersions`, `getRelatedReleases`, `getDeletedReleases`. UUID guard on detail and versions queries so `/releases/<garbage>` returns 404 instead of crashing on Postgres' UUID parser.
- `/deleted` route lists every `deleted_at IS NOT NULL` record.

**5. Faceted search (`f8bb468`)**
- `/search` rebuilt as a 6xl-wide layout with sidebar facets: Sort (Newest / Relevance via `ts_rank`), Date range (HTML date inputs bounded to corpus window), Party / Type / Top-state with live counts that ignore that facet's own filter.
- Result cards render `ts_headline` snippets with `<mark>` highlights on matched terms; `ReleaseCard` accepts an optional `snippet` prop and escapes/re-injects mark tags safely.
- `getFeed` extended with `from`/`to`/`sort` options and conditional `ts_headline` column.

**6. Edit-frequency research → deletion-detector cleanup (`b3ba843`, `85fb4d7`)**
- Originally meant to scope a "diff view" feature for `/releases/[id]` version history. Research first.
- Edit data: 56 of 35,362 releases (0.16%) have prior versions — all from a single April 2026 backfill across 9 senators, every diff is whitespace/block-boundary-spacing artifacts. Spot check confirmed: `"FOR IMMEDIATE RELEASEFebruary"` (prior) vs `"FOR IMMEDIATE RELEASE February"` (current) — same text, different extractor pass. Wiped all 56 `content_versions` rows.
- Deletion data: 1,286 tombstones, all dated April 19, 2026. Sampled 10 King-Angus URLs (he had 606 of 1,286, 47% of all "deletions") — every one returned HTTP 200 with the original press release content across python-httpx, curl, browser UA, and a dedicated bot UA. The detector was treating a single transient 404 (likely Akamai-fronted CDN behavior) as permanent deletion.
- Re-verified all 1,286 with a Safari User-Agent: 1,283 returned 200 (false positives), 4 confirmed 404/410, the rest Akamai-blocked on the second sweep. Restored all 1,283 live records. Hard-deleted the 3 remaining tombstones since they were all Hoeven nav/contact pages (`/contact/e-newsletter-signup`, `/postal-concerns`, `/serving-you/finding-our-pow/mias`) misclassified as press releases — never legitimate to begin with.
- Detector hardened: any 404/410 candidate now requires `CONFIRMATION_RUNS=3` independent re-checks spaced 60s apart before tombstoning. Single hits get logged but discarded.
- `/deleted` page renamed "Confirmed deletions" with a sober note explaining the multi-confirmation gate and the April incident, so readers don't read any future tombstone list as a comprehensive scrub log.
- Audit scripts kept in `scripts/`: `edit-freq.mjs`, `investigate-king.mjs`, `ua-check.mjs`, `reverify-deletions.mjs`, `restore-akamai-tombstones.mjs`, `wipe-spurious-versions.mjs`, `remove-hoeven-nav-records.mjs`, `check-sheehy-edits.mjs`. Useful for any future re-audits.

**7. SEO infrastructure (`19382ad`, `ce1e27a`)**
- `app/sitemap.ts` emits one well-formed sitemap with 33,999 URLs (8 static + 100 senators + 33,891 releases). Hourly revalidation. Single file because we're under Google's 50k-URL cap; can swap to `generateSitemaps` if we cross it.
- `app/robots.ts` allows all crawlers, disallows `/api/`, points at sitemap.
- `app/lib/site.ts` derives `SITE_URL` from `VERCEL_ENV`/`VERCEL_URL` with `capitolreleases.com` fallback; wired into root `metadataBase`.
- `app/releases/[id]/opengraph-image.tsx` generates a 1200×630 PNG via `next/og`/Satori — senator photo (loaded from `public/senators/`, embedded as base64 data URI), name, party-colored label, state, date, content-type badge, headline, and `capitolreleases.com / source-host` footer. Deleted releases get a "Removed from senate.gov" annotation. Hit Satori's "every multi-child div needs explicit display:flex" rule a few times; refactored multi-child text into single template-string children.

**8. Smoke test (`d8a2ce2`)**
- Walked every route on local prod and capitolreleases.com. All 200s; bad-UUID and non-UUID release IDs both return 404 cleanly.
- Found and fixed three React 19 whitespace-stripping bugs: `{value}` adjacent to text on the same line silently drops the space, producing `99publish`, `havebeen`, `markup.2senators` runs. Added explicit `{" "}` on `/senators` and `/about`.
- Aligned `/deleted` page `<title>` ("Scrubbed releases") with its H1 ("Confirmed deletions").
- `/status` description claimed "9:00 AM ET" but cron runs four times daily — corrected.

**9. Chamber default + log color scale (`a3be21f`)**
- Default search term changed from "None" to "Trump". The unscoped chamber view was effectively a senator-productivity ranking; defaulting to Trump makes the visualization a topic-attention map, which is what it's for. Lands on `?q=Trump` so the framing is shareable; clicking None still works for the session.
- Replaced linear `count / max` with `log(count+1) / log(max+1)`. With Warren at 43 Trump mentions and the median ~5, the linear scale was crushing 95% of senators into the floor opacity. Log spreads the middle of the distribution into visible bands while still reserving full saturation for the leader.

**Memories saved:**
- `feedback_time_estimates.md` — Trevor's workflow finishes in minutes what I quote in tens of minutes; don't pad.
- `feedback_be_ambitious.md` — Pro Max plan capacity; expand scope on each turn or propose ambitious follow-ups, don't truncate.

**Notable findings worth remembering (and surfaced in CLAUDE.md-relevant context):**
- The deletion detector cannot trust a single 404 from senate.gov — Akamai serves transient 404s. Confirmation gate is mandatory.
- Press offices on senate.gov publish-then-leave. The corpus has essentially zero real editorial-edit signal. A diff-view UI on `/releases/[id]` would be theater, not journalism.
- HTML-extractor upgrades produce body-text changes that look like edits but aren't. Future hash-change handling in `pipeline/commands/update.py` should run a token-similarity check before writing a `content_versions` row, otherwise the next extractor pass will re-pollute the table.
- React 19 strips whitespace between `{expr}` and adjacent text on the same line. Audit any `count + " widgets"` style JSX.
- `next/og` Satori requires explicit `display: flex` on every multi-child div; templating multi-child text into single strings is the safest path.

**Outstanding (noted, not done):**
- Senator-vs-senator and party-vs-party comparison pages.
- Diff view for genuine version history once the corpus has any.
- `/releases/[id]` body text renders as one wall paragraph because the scraper concatenates without `\n\n`. Real fix is in the extractor.
- Mobile QA: Chrome MCP doesn't actually resize the viewport (resize calls return success but `window.innerWidth` stays). Visual mobile QA needs a real device or DevTools emulation; tested only the responsive class inventory (51 responsive utilities, 24 hidden-on-mobile).
- 367 records remain Akamai-blocked from any kind of automated reachability check.

**Files created this session:**
- `app/lib/dates.ts`, `app/lib/site.ts`
- `app/components/empty-state.tsx`
- `app/releases/[id]/page.tsx`, `app/releases/[id]/opengraph-image.tsx`
- `app/deleted/page.tsx`
- `app/sitemap.ts`, `app/robots.ts`
- 8 scripts under `scripts/`

**Files modified:** `app/components/{release-card,hero-letter,senate-chamber,senator-activity,term-chart,topic-timeline,search-box}.tsx`, `app/{feed,search,senators,senators/[id],status,page,layout,deleted}.tsx`, `app/lib/queries.ts`, `app/api/chamber/counts/route.ts`, `app/about/page.tsx`, `pipeline/commands/detect_deletions.py`.

**Commits pushed (chronological):** `7f6f9ae` → `baf0c51` → `bfa2206` → `f925146` → `f8bb468` → `19382ad` → `ce1e27a` → `b3ba843` → `85fb4d7` → `d8a2ce2` → `a3be21f`. Eleven commits.

---

## 2026-04-28 (afternoon) — Durbin future-date defense, CI breakage, data integrity cleanup

**Session summary:**
Picked up from the morning devlog after the initial /devlog ended. User noticed the homepage hero was again pinning a release dated *May 4, 2026* to the top of "Latest releases" — almost certainly an Apr→May typo at Durbin's press shop on a release captured Apr 27 about an Apr 26 event. Built a multi-layer future-date defense, broke CI with a Python SyntaxError in the process, Codex caught it, fixed it, then surfaced and cleaned up four pre-existing data-quality test failures so the workflow is properly green for the first time in days.

**1. Future-date defense (`95e6d49`)**
- Investigation showed exactly one future-dated record in the corpus (Durbin May 4, 2026, `date_source=meta_tag`, confidence 0.95). The source HTML has `May 04, 2026` literally in the body and meta tag.
- **Sort layer:** `getFeed`, `getSenatorReleases` now `ORDER BY LEAST(published_at, scraped_at) DESC`. Display still shows the office's date for journalism-provenance reasons; only the ranking is corrected. Constant `EFFECTIVE_DATE_SQL` in `app/lib/queries.ts`.
- **UI layer:** new `isFutureDated()` helper in `app/lib/dates.ts`. ReleaseCard and HeroLetter render a small amber `*` next to the date with a tooltip explaining the discrepancy. `/releases/[id]` shows a prominent amber callout: *"The senator's office published this release with a date of X, but Capitol Releases captured it on Y. The published date appears to be a typo on the source site."*
- **Pipeline layer:** both collectors (httpx + RSS) check at record construction. If `published_at` is more than 24h ahead of now, `date_source` gets a `_future_typo` suffix and `date_confidence` is capped at 0.2. New `demote_if_future()` helper in `pipeline/lib/dates.py`.
- One-shot `scripts/demote-existing-future-dates.mjs` flipped the existing Durbin record from `meta_tag / 0.95` to `meta_tag_future_typo / 0.2`.

**2. Broke CI (`8562bc4` reverted the breakage)**
- The future-date demotion block in `httpx_collector.py` was indented wrong — it sat between the detail-page `try:` and its `except:`, which is a Python grammar error. The Next/TS build passed because TS doesn't import Python; the daily cron at 1:50 PM ET hit the bug at module import and exited 1 immediately. No scrape, no alerts, no tests ran.
- Codex (OpenAI's CLI tool) diagnosed and fixed it. The block now lives after the `try/except` at the same indent as the for-loop body — bonus side effect: the future-date check also runs when the detail-page fetch fails (we still have a date from the listing page that should be flagged).
- Verified locally with `py_compile`, `compileall`, `pipeline update --help` (the import-time path that broke), and a single-senator dry run (Warren, 7 records, 0 errors).
- New memory: [feedback_run_pipeline_tests.md](feedback_run_pipeline_tests.md) — `py_compile` Python edits before commit; the TS build is not a proxy for the Python pipeline.

**3. Manual workflow_dispatch revealed pre-existing data-quality failures (`4382368`)**
- After the syntax fix, `gh workflow run daily.yml` showed scrape passing but `Run data-quality tests` failing 4/26. None were caused by recent changes — they'd been red since the test step started gating CI:
  - 1 Whitehouse 2007 release out of corpus scope (2025+ corpus)
  - 4 Hoeven social-media URLs captured as press releases (facebook, twitter, instagram, youtube)
  - 5 listing-page URLs captured as releases (Cantwell, Graham, Hoeven, Klobuchar, Thune all had `/press-releases` itself in the corpus)
- Cleaned with `scripts/cleanup-quality-failures.mjs` (10 hard deletes; not tombstones, since none were ever legitimate releases — same logic as the morning's 3 Hoeven nav pages).
- **Hardening so they don't re-appear:**
  - `is_external_content()` now returns True for *any* URL not on senate.gov / house.gov / whitehouse.gov. Previously only rejected a hardcoded blacklist of news/social domains and let unknown domains through.
  - New `is_listing_url()` in `pipeline/lib/classifier.py` matches paths ending in `/press-releases`, `/news-releases`, `/newsroom`, `/news`, `/media`, `/press` as a leaf segment. `/press-releases/some-actual-release` stays legitimate.
  - Both collectors call the listing check alongside the existing external-content check before constructing a record.
- **Result:** data-quality suite went 22 passed / 4 failed → **26 passed / 0 failed**.

**4. End-to-end CI verification**
- Manual `gh workflow run` triggered run `25071646473`. Completed in 7m34s with every step green: scrape, all silo refreshes, data-quality tests, data-health report. First fully green workflow run since the SyntaxError landed.

**Findings worth remembering:**
- React 19 isn't the only place where adjacent text vs `{expr}` matters; Python pipeline indentation is just as load-bearing for CI. Two different "whitespace bit me" lessons in one day.
- `is_external_content()`'s old logic was an allowlist of bad domains, not an allowlist of good ones. Inverting that catches future weird domains for free.
- The data-quality test step has been catching real garbage in the corpus that we'd been ignoring. Worth keeping it gating CI rather than relaxing.
- `LEAST(published_at, scraped_at)` is the right sort key for journalism: never silently overwrite source data; just don't let an upstream typo dominate ranking.

**Files created (afternoon):**
- `scripts/investigate-durbin-future.mjs`, `scripts/demote-existing-future-dates.mjs`, `scripts/audit-quality-failures.mjs`, `scripts/cleanup-quality-failures.mjs`, `scripts/find-actual-fails.mjs`

**Files modified (afternoon):** `app/lib/{queries,dates}.ts`, `app/components/{release-card,hero-letter}.tsx`, `app/releases/[id]/page.tsx`, `pipeline/lib/{dates,classifier}.py`, `pipeline/collectors/{httpx_collector,rss_collector}.py`.

**Commits pushed (chronological):** `95e6d49` (future-date defense, broke CI) → `8562bc4` (Codex syntax fix) → `4382368` (data integrity cleanup + collector hardening). Three afternoon commits, total fifteen for the day.

---

## 2026-04-29 (evening) - Posture flip, /states scaffold, D3 polish pass

**Session Summary:**

A long evening session split between strategy work and visible homepage polish, with a parallel CLI session running the Texas Senate backfill in another terminal.

**Strategic shifts (recorded to memory):**
- After WBEZ rejection landed and the job market felt closed, founder explicitly flipped the session frame from defensive/adversarial review to full-commitment build mode ("fuck that shit"). Saved as `feedback_build_mode_signal.md` so future sessions know to drop the cautious framing when that signal appears.
- Articulated the canonical four-moat strategic frame — design, journalism, accuracy (soon), focus — replacing the previous flat seven-differentiator list. Saved as `project_four_moats.md`. Every Stage 1-4 task now ladders back to one of the four; "this strengthens the design moat" / "this weakens the focus moat" is now a legitimate scope argument.
- Saved `project_pivot_2026_04_29_evening.md` capturing both the emotional context and the new posture.

**Homepage refactor (`app/page.tsx`, `app/components/nav.tsx`):**
- Renamed "Trending" → "Topics" in nav and matching body section header.
- Swapped Senator Frequency Rankings (now between Topics and Latest) with Total Release Volume (now at the bottom). The visually striking ranking earns the higher slot; the daily-volume bar chart settles in as supporting context.
- Removed the standalone `/search` section from the homepage. Search is already threaded into the nav, the chamber's term search, the trending topics, and the senator pages — the dedicated section was redundant.
- Trimmed Latest list from 12 → 9 items so it lines up cleaner with the Most Active column.

**`/states` route built (this session, in tandem with parallel TX session):**
- Created `app/lib/state-coverage.ts` to share COVERAGE/PLANNED data between the landing page and the new catch-all route.
- Created `app/states/[code]/page.tsx`: handles every US state code. Planned states (CA/NY/OH) get a "Phase 1, after Texas" page with rationale + link to the TX pilot. Other valid state codes get a "not on roadmap, here are the federal senators" page with deep links. Live/in-progress states with their own dedicated route (TX → /states/tx) redirect cleanly.
- Made all `coverage-cartogram` tiles clickable. Inactive tiles were `<div>`s with `cursor-not-allowed`; flipped them to `<Link>`s that route through the new catch-all so every state on the map is a real navigation surface.
- Indiana state-pilot file I'd started earlier was deleted when the parallel session committed Texas as the chosen pilot.

**D3 polish pass — five components share the chamber's monochrome-with-accent visual language now:**
- `ActivityChart` (homepage daily volume): replaced blue→indigo→coral gradient with a monochrome opacity ramp; added per-day hover hit zones with a date+count tooltip; hovered bar turns red for clear feedback.
- `TopicTimeline` (`/trending`): same monochrome ramp; spike weeks stay red (now at 85% opacity) so they pop without screaming. Hover tooltip shows week + mention count + a SPIKE pill when applicable.
- `TermChart` (`/trending`): widened right margin to 64px to fit per-line end labels; greedy y-de-overlap so lines ending at similar values don't stomp each other; dashed crosshair; white-fill colored dots at every line's value at the hovered week.
- `SenatorBars` (homepage rankings): wrapped each row in an `<a>` so the entire band is a click target to the senator page; hover band lifts the row out of the alternating stripe; top-3 get bolder typography on both name and total.
- `SenatorActivity` (homepage hot/cold lists): party-tinted magnitude bars behind each row (D=blue tint, R=red tint, I=amber tint) showing relative count without crowding the layout; top-3 in Most Active list now bold.

**Skipped:** `SenatorHeatmap` (already polished, native `<title>` tooltips work fine), `SenateChamber` (homepage hero — too central to touch without founder eyeballs on it).

**Files modified:**
- `app/page.tsx` — section reorder, removed search section, trimmed Latest list, removed unused SearchBox import
- `app/components/nav.tsx` — Trending → Topics
- `app/components/{activity-chart,topic-timeline,term-chart,senator-bars,senator-activity}.tsx` — D3 polish pass
- `app/components/coverage-cartogram.tsx` — inactive tiles now clickable
- `app/states/page.tsx` — refactored to import from shared lib

**Files created:**
- `app/lib/state-coverage.ts`
- `app/states/[code]/page.tsx`

**Memory entries created:**
- `project_pivot_2026_04_29_evening.md`
- `feedback_build_mode_signal.md`
- `project_four_moats.md`

**Notable decisions:**
- The four moats supersede the seven-differentiator framing for all future scope arguments.
- UI/UX/D3 craft is now treated as moat work, not vanity. ActivityChart specifically lost its alarming coral color for high-volume days because "high volume" is normal, not a danger signal — the chart shouldn't cry wolf.
- All state cartogram tiles route somewhere meaningful. No dead `<div>`s on the navigation surface.

---

## 2026-05-01 (early morning) — State + US House expansion recon (independent, multi-agent)

**Session summary:** Independent recon for expanding the project beyond the existing TX Senate implementation. Goal was an implementation-grade source inventory across all 50 state legislatures, statewide elected officials, and the US House — with the explicit instruction to NOT trust prior Codex-generated reports as truth.

**Approach:** Fan-out across 10 parallel research agents:
1. Northeast state legislatures (CT, ME, MA, NH, NJ, NY, PA, RI, VT)
2. Southern state legislatures (AL, AR, FL, GA, KY, LA, MD, MS, NC, OK, SC, TN, VA, WV)
3. Midwest state legislatures (IL, IN, IA, KS, MI, MN, MO, NE, ND, OH, SD, WI)
4. Western state legislatures (AK, AZ, CA, CO, DE, HI, ID, MT, NV, NM, OR, UT, WA, WY)
5. Caucus-source enumeration across 50 states (up to 4 caucuses per state)
6. Governors + AGs across 50 states
7. Other statewide elected (SoS, Treasurer, Comptroller, Auditor, Insurance, SPI, Land, etc.)
8. WP-JSON discovery sweep across 100 governor + AG bases
9. Browser-render verification of 19 JS/WAF-suspect sites via Chrome MCP
10. Selector deep-dive on the top 19 candidate sources
11. (added mid-run by user) US House recon — 436 members + Drupal HMWP profile

**Output:** `research/claude-state-expansion-recon-2026-05-01/`
- `REPORT.md` — professional narrative
- `first_wave_curated.md` + `first_wave_curated.json` — 10 wave-1 sources with selectors
- `roadmap.md` — Phase 0–5 implementation plan
- `tx-senate-audit.md` — independent audit of TX Senate code/data
- `inventory.json` (606 records) + `inventory.csv`
- `us_house_inventory.json` (436 members + profile)
- `do_not_implement.json` (76 records)
- `raw/*.json` — 10 agent outputs preserved
- `_synthesize.py` — re-runnable stitching script

**Key findings:**
- 606 unique state/exec sources + 436 US House members reviewed
- 125 ready_first_wave; 42 of 50 states have at least one ready source today
- 8 dead-zone states with no ready source at any tier: IN, KY, LA, MO, NE, NH, VT, WV
- WordPress dominates: 93 records, plus 22 confirmed wp-json endpoints among governors/AGs and 31 among caucus sites
- **Surprise finding:** ZERO of the 19 suspected-JS-required sites are actually JS-required. Every "JS site" was a WAF (Akamai/Cloudflare/Imperva) refusing non-browser User-Agents. Chrome with default headers passes through every time. Second wave does not need Playwright as default — it needs hardened httpx with browser-class headers.
- Caucus sites are the dominant member-attribution path in 30+ states (IL, IN, MI, MN, OH, PA, NJ, MA, NY, CA, WA, TN, VA, MD, AZ, CO, NM, OR). 196 caucus rows enumerated. The existing per-member `senate.json` schema does NOT fit; need a `party` axis and parent-caucus model.

**Curated wave-1 (all 9 corroborated live with HTTP 200 + content from 2026-04-30):**
1. CA Governor (wp-json) | 2. CA AG (RSS) | 3. CA Senate (40 sd##.senate.ca.gov, Drupal walk) | 4. WA Governor (RSS) | 5. WA AG (RSS) | 6. WA Senate Democrats (wp-json, 24 senators with subpaths) | 7. TX Governor (RSS) | 8. NC AG (wp-json, 0.98 confidence) | 9. OH Senate (per-member /news, 33 senators) | 10. OH House (same template, 99 representatives).

Coverage delivered by wave 1: ~199 distinct member principals across 5 states.

**TX Senate audit highlights** (DB: 314 records, 0 dups, 0 missing dates, 18 of 30 seated senators with data):
- Year-header date fallback assigns `confidence=1.0` (today triggers zero times across 314 rows, latent risk if a sidebar `<h3>2024</h3>` appears).
- `truth-check` filters dead `photo_release` content_type that the collector never emits; should filter `'other'` (videos) instead.
- Body extractor hardcoded to `s.chamber = 'tx_senate'` — must be parameterized before state #2 ships.
- `content_hash` semantic drift: collector stores hash(title|url); body extractor overwrites with sha256(body). Two different semantics for the same column.
- Title mutation: video items get "VIDEO: " prepended, diverging DB title from source.
- 12 of 30 seated senators have zero records (some genuinely silent, some may be silently broken — no per-senator stale alert exists for TX).

**Top implementation risks (ranked):**
1. WAF defeat at scale — Akamai/Cloudflare/Imperva on ~25%+ of state .gov + entire US House Drupal HMWP. Need hardened httpx headers as baseline; residential proxies or Playwright as fallback.
2. Caucus schema gap — 196 caucus rows don't fit the existing per-member shape.
3. Attribution NER for shared chamber feeds (KY, NC, WV) — title-text regex layer required.
4. TLS / dead-domain canary required — ~10 caucus domains observed dead, parked, hijacked, or returning lorem-ipsum.
5. PDF body extractor must be generalized before AZ, FL Senate Pubs, LA Senate ship.

**Files created:**
- `research/claude-state-expansion-recon-2026-05-01/` (12 deliverable files + 10 raw agent JSONs)

**Files NOT changed:** None — this was a recon-only session, no production code touched.

**Decisions:**
- Wave-1 implementation order is fixed: CA AG (RSS, easiest validation) → CA Gov (first wp-json) → TX Gov → WA Gov + WA AG → NC AG → WA Senate Dems (first caucus-tier collector, introduces party axis) → OH Senate → OH House → CA Senate (40-subdomain fan-out, validates the per-member subdomain pattern at scale).
- TX Senate fixes (Phase 0) come before any new state ships. None are blocking on their own; all compound at scale.
- Schema redesign: introduce `caucus.json` seed with `party` axis before wave-2 caucus rollout.
- US House cannot ship until WAF-defeat strategy is production-stable — Phase 4, not before.

---

## 2026-05-01 - Statusline Replacement (ccstatusline)

**Session Summary:**
- Diagnosed why context indicator felt stuck at ~6/1000K despite long sessions: `~/.claude/statusline-command.sh` read `context_window.current_usage.input_tokens`, which is the *last API call's* input tokens — not cumulative session usage. Behavior was correct; the metric was wrong for what the user wanted to see.
- Researched community statuslines (ccstatusline, claude-powerline, CCometixLine). Picked `ccstatusline` (sirmalloc) for active maintenance, 1M-context awareness, token burn-rate widgets, and powerline theme.
- Backed up the prior script to `~/.claude/statusline-command.sh.bak`. Swapped `~/.claude/settings.json` `statusLine` block to `npx -y ccstatusline@latest` with `padding: 0`.

**Notable Changes:**
- `~/.claude/settings.json` — `statusLine.command` now `npx -y ccstatusline@latest` (was `bash /Users/home/.claude/statusline-command.sh`).
- Old script preserved at `~/.claude/statusline-command.sh.bak` for rollback.

**Decisions:**
- Run `npx ccstatusline@latest` once interactively to pick widgets: model, context % (bar), tokens in/out, output token speed, cost, session duration, git branch.
- Refresh cadence is per-assistant-message (debounced 300ms) — not a polling lag. Confirmed against Claude Code statusline docs.

---

## 2026-05-01 - Auth foundation (Better Auth) + /admin dashboard

**Session Summary:**
- Ported open-cabinet's auth setup verbatim: Better Auth 1.6 + Drizzle adapter scoped to four auth tables (user, session, account, verification). Rest of the project stays raw-SQL via `app/lib/db.ts`. Drizzle is installed for the auth adapter only; not the project's primary ORM.
- Email + password and Google OAuth both enabled. Single admin allowlist via `ADMIN_EMAIL` env (default `trevorbrown.web@gmail.com`).
- Added `tier` column on `user` (default `'free'`) up front so paid-tier gating of state-level / U.S. House content can land later as a config change, not another migration. Better Auth picks it up via `user.additionalFields` in `app/lib/auth.ts`.
- Built `/admin` page (client component, three states: signed-out → Google sign-in button; allowlisted → dashboard; not-allowlisted → unauthorized + sign-out). Dashboard reads from `/api/admin/overview` which is gated server-side via `auth.api.getSession()` + `isAdmin()`.
- Pinned `next dev` to port `3003` so OAuth redirect URIs stay valid across restarts (Next would otherwise drift to 3004 if the port was taken, silently breaking sign-in).
- Skipped middleware — open-cabinet doesn't use one and per-route checks are sufficient for our blast radius.

**Smoke tests (all green after env vars set):**
- `GET /admin` → 200
- `GET /api/admin/overview` (no session) → 401
- `GET /api/auth/get-session` (no session) → 200 `null`
- `POST /api/auth/sign-in/social {provider:"google"}` → 200 with valid Google redirect URL
- `POST /api/auth/sign-up/email` → 400 `PASSWORD_TOO_SHORT` (path wired, validation works)

**Notable Changes:**
- `package.json` — `better-auth ^1.6.9`, `drizzle-orm ^0.45.2` added; `dev` script pinned to `next dev -p 3003`.
- `db/migrations/009_auth.sql` — four tables + indexes, applied to Neon. `user.tier text not null default 'free'` for paid-tier gating.
- `app/lib/auth.ts` — Better Auth config; `isAdmin(email)` and `isPaid(tier)` helpers. `ADMIN_EMAIL` reads from env with hardcoded fallback.
- `app/lib/auth-client.ts` — `createAuthClient()` from `better-auth/react`.
- `app/lib/auth-schema.ts` — Drizzle schema mirroring open-cabinet's exactly + the `tier` column.
- `app/lib/db-drizzle.ts` — Drizzle handle scoped to auth (separate from `app/lib/db.ts` raw client).
- `app/api/auth/[...all]/route.ts` — Better Auth catchall handler.
- `app/api/admin/overview/route.ts` — totals, recent runs, recent alerts; server-side admin gate.
- `app/admin/page.tsx` — sign-in / dashboard / unauthorized states.
- `app/components/footer.tsx` — "Admin" link added to nav block.
- `.env` — `BETTER_AUTH_SECRET`, `BETTER_AUTH_URL`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `ADMIN_EMAIL` (user-pasted; not committed).

**Decisions:**
- Better Auth not NextAuth — same library as open-cabinet, less ceremony, database sessions out of the box, simpler tier/role extension via `additionalFields`.
- `app/lib/` for auth files (not top-level `lib/`) to match capitol-releases' existing layout — open-cabinet uses `lib/` but capitol-releases keeps everything under `app/lib/`.
- Drizzle scoped to four auth tables; raw SQL stays the project's default. Adding Drizzle for the rest of the codebase is not in scope.
- No middleware. Per-route auth checks via `auth.api.getSession()` server-side and `useSession()` client-side.
- `tier` field added on day one even though paid gating doesn't ship today. Cheap to add now; expensive migration if added later with users in the table.

**Vercel deploy prep (not yet done):**
- Need same env vars set in Vercel dashboard before first prod deploy: `BETTER_AUTH_SECRET`, `BETTER_AUTH_URL=https://capitolreleases.com`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `ADMIN_EMAIL`.
- Google Cloud Console redirect URIs already include the prod origins (`capitolreleases.com` + `www.capitolreleases.com`).

**Commits:**
- `84cdb0c` Add Better Auth with Google OAuth + email/password
- `a566350` Add /admin dashboard with email-allowlist gate

---

## 2026-05-01 - Daily + weekly AI brief, /brief route, newsletter signup, RSS, archive

**Context:** Late-Thursday-into-early-Friday session (about 4 hours, a dozen commits) building a complete brief product from scratch — daily + weekly editions, sparklines, archive, newsletter signup, email send, RSS, retroactive 14-day backfill. Voice modeled on Trevor's Capitol Watch / Democracy Watch newsletters at Oklahoma Watch.

**The brief is a derivative product, never canonical.** It synthesizes; it does not record. Every claim is grounded in a `press_releases.id` (or, for weekly, a `briefs.id` from the same week). Schema captures `model_version` + `prompt_hash` + `source_release_ids[]` so any brief is reproducible. Drafts are unconstrained; only one published row per `(brief_date, edition)` via partial unique index.

**Daily brief (`pipeline/commands/brief.py`):**
- Sonnet 4.6 streaming (non-streaming hit 60s socket timeouts on 35k+ token inputs).
- Pulls day's releases (ET window) → 8-week DOW volume baseline → silent-senator list (brief-date-aware so backfill is accurate) → calendar context → ProPublica votes (env-gated). Synthesizes; emits structured JSON; validator drops any cited UUID not in the source set.
- Steady-state cost: ~$0.08/run at 4-12k output tokens. Apr 22 (104 releases) cost $0.45 with cold cache.
- `--publish` retracts any prior published row for the same date so regeneration is a one-line operation.
- Auto-bumped max_tokens 4k→8k→12k after busy days produced truncated JSON; added `stop_reason` check so future truncation surfaces as a clear `RuntimeError` instead of a `JSONDecodeError`.

**Weekly brief (`pipeline/lib/brief_weekly_prompt.py`):**
- Editorially distinct: story of the week, themes that compounded, **five quotes that defined the week** (verbatim, attributed, sourced), drowned-out items, quiet-week senators (zero releases in 7-day window).
- Synthesizes across the **5 daily briefs** in the window plus a slim release index — keeps cost bounded (~$0.30) and means every weekly claim is already grounded in a validated daily.
- Window: Friday previous through Thursday this week. Cron at 02:00 UTC Friday (9pm ET Thu DST).
- Validator is stricter than daily: every cited release_id and daily_brief_id must be in the input sets. Apr 23 weekly tripped on first attempt (model invented an ID), passed cleanly on retry. Validator did its job.

**Voice:** Distilled from three Oklahoma Watch newsletters (uncontested-races, lawmakers-pass-budget, 2022-session-close-out). Declarative openings, AP attribution, em dashes spaced, no emojis, no editorializing, verbatim quotes only. Result reads like a beat reporter. Sample lede: "Three senators put statements on record as U.S. military operations in Iran crossed the 60-day window..."

**Frontend (`/brief`, `/brief/[date]`, `/brief/archive`, `/brief/rss.xml`, `/recap`):**
- Server Components, query Neon directly. Latest-of-either-edition surfaces on `/brief` (weekly Thursday-night beats Tuesday's daily on the tie).
- Stat strip (releases / senators cited / themes), citation cards with party-color dots (sky/rose/amber), edition badges (daily neutral, weekly amber).
- Per-theme **D3 sparkline** — server-rendered SVG, no client JS — drawn via Postgres FTS over 30 days using model-supplied `keywords[]` per section.
- Quotes block on weekly: italic verbatim text, AP-style attribution, source link to `/releases/[id]`.
- Archive page: chronological list grouped by month, Daily | Weekly | All filter, edition badges per row.
- RSS 2.0 feed of last 30 briefs, cached 10 min.

**Newsletter (`pipeline/commands/brief_send.py`):**
- `newsletter_subscribers` table — email lowercased UNIQUE, unsubscribe_token UUID, status active/unsubscribed/bounced, last_sent_brief_id for idempotent re-runs. Resubscribe is an UPDATE that preserves the original token.
- `POST /api/newsletter/subscribe`, `GET /api/newsletter/unsubscribe?token=...`. Both with proper validation (UUID regex, email regex, JSON parse error handling).
- Email render: 600px table-based HTML + plain-text fallback, citation cards link back to canonical `/releases/[id]`. RFC 8058 `List-Unsubscribe` + `List-Unsubscribe-Post: One-Click` headers so Gmail/Outlook surface the native unsubscribe button.
- Two crons: brief-email at 10:30 UTC daily Wed-Sun (6:30am ET DST, the Axios AM / Punchbowl AM slot) for daily edition, brief-weekly-email at 03:00 UTC Friday (10pm ET Thu DST) for weekly edition.
- `--edition daily|weekly` flag added late after smoke test caught that the original send was hard-coded to daily and would have stranded every weekly.

**Calendar + votes:**
- `pipeline/seeds/senate_calendar_2026.json` — official 2026 Senate recess windows + holidays from senate.gov/legislative/2026_schedule.htm. Brief now flags is_recess, first/last day of recess, days-until-next-recess, same-day holidays.
- `pipeline/lib/congress_votes.py` — env-gated lookup against api.congress.gov v3 (CONGRESS_API_KEY). Returns `[]` without a key so the brief works either way. Replaces the originally-planned ProPublica integration since ProPublica's Congress API was handed off in 2023.

**Backfill (live numbers):**
- 9 daily briefs Apr 17-29 + Apr 30 regen + 2 weeklies (week ending Apr 23 and Apr 30) = 12 published briefs.
- Apr 21 + Apr 22 failed first pass on max_tokens; passed after the 12k bump.
- Apr 23 weekly failed first pass on validator; passed cleanly on retry.
- Total backfill cost: ~$2.40.
- DB integrity check: zero broken citations across all 12 briefs. Both weeklies have exactly 5 quotes each, all linking to valid release_ids.

**Smoke tests run during /test-and-verify:**
- TS clean, py compile clean.
- Routes: 14 URLs sweeping success / 404 / 405 / 400 / 307 paths, all expected.
- Subscribe API: new + resubscribe + invalid email + malformed JSON + cleanup, all correct.
- Unsubscribe: token validation, status update, HTML confirmation page.
- Email render: both editions pass; weekly quotes render in HTML and text after late fix.
- Sparklines: 6 per weekly, 10 per Apr 30 daily, all with real numbers.

**Files added:**
- `db/migrations/005_briefs.sql`, `006_newsletter_subscribers.sql`, `007_brief_quotes.sql`
- `pipeline/lib/brief_prompt.py`, `brief_weekly_prompt.py`, `brief_email.py`, `congress_votes.py`
- `pipeline/commands/brief.py`, `brief_send.py`
- `pipeline/seeds/senate_calendar_2026.json`
- `app/brief/page.tsx`, `app/brief/[date]/page.tsx`, `app/brief/archive/page.tsx`, `app/brief/rss.xml/route.ts`
- `app/recap/page.tsx`, `app/recap/[date]/page.tsx`
- `app/api/newsletter/subscribe/route.ts`, `app/api/newsletter/unsubscribe/route.ts`
- `app/components/brief-body.tsx`, `brief-signup.tsx`, `theme-sparkline.tsx`
- `.github/workflows/brief.yml`, `brief-weekly.yml`, `brief-email.yml`, `brief-weekly-email.yml`

**Commits (in order):**
- `e643ffe` Add briefs table for AI-generated daily summaries
- `f9d7007` Add brief command: Sonnet 4.6 daily synthesis with citation validation
- `c7ca12f` Add /brief and /brief/[date] routes
- `ac492fa` Wire brief.yml cron: 22:30 UTC, Tue-Sat, with collector-fresh gate
- `0610b06` Add newsletter signup: subscribers table, API routes, signup form
- `1a5143f` Add brief-send: HTML+text email with one-click unsubscribe, daily cron
- `3eab1bb` /recap aliases /brief
- `558fe95` Wire calendar context, vote lookups, theme sparklines, retract-on-republish
- `8de9883` Add /brief/rss.xml feed of last 30 published briefs
- `efa8fa3` Add weekly brief edition + /brief/archive
- `43c135f` brief: bump max_tokens to 12k + surface truncation as RuntimeError
- `75f7786` brief-send: --edition flag + Thursday-night weekly email cron

**Open follow-ups:**
- Add Resend SMTP secrets + `BRIEF_FROM_ADDR` + `BRIEF_FROM_NAME` + `SITE_URL` to GitHub Actions before first real send.
- (Optional) `CONGRESS_API_KEY` for vote context.
- Two-week QA window: watch for weekly validator failures, voice drift, hallucinated narrative arcs. If validator trips again, tighten the weekly prompt to "cross-check every cited UUID against the input set before emit."
- Promote `/brief` link from homepage once trust is established (right now nav has it; homepage hero does not).

---

## 2026-05-02 — Phase A pipeline fixes + Phase B1: House goes live

**Session Summary:**
Two phases in one Saturday session. Phase A patched two latent bugs found while reviewing today's pipeline state: a missing `anthropic` dep that had been silently failing every daily-brief workflow run since they were wired up, and a verified-round-count whitelist that turned out to have shipped 32 minutes after the failing scheduled run that triggered it. Phase B1 was the first US House content ever in the corpus — 871 records across 89 RSS-eligible members, full integration through the existing pipeline. Schema was already chamber-aware from the TX state-senator wave; this session ported House through it without a rename.

**Phase A — pipeline + brief fixes:**
- `pipeline/requirements.txt` was missing `anthropic`, so every brief workflow run crashed with `ModuleNotFoundError` before generating anything. No daily brief had been sent since the workflows shipped.
- The May 1 9:35 PM EDT scheduled daily run *did* fail `test_no_suspicious_round_counts` despite commit `242bc28` having added Scott + Johnson to `verified_ok`. Mystery solved by timestamp comparison: run started 01:35 UTC, failed at 01:46 UTC. Fix landed at 02:07 UTC. Run was on pre-fix code.
- Manual run `25251895946` confirmed the round-count fix works on post-fix code (10m42s, 28/28 tests pass).
- May 1 brief generated end-to-end (`ac8a0537-…` draft → `d896df23-…` published) at $0.15 cost. Sonnet 4.6, 26.6k tokens in / 4.8k out.

**Phase B1 — US House live (89 members, 871 records):**
- House-specific RSS probe written (`pipeline/recon/house_rss_probe.py`), forked from `senate_rss_probe.py` with three House-tuned changes: concurrency 3 instead of 12, `/rss.xml` first in the URL pattern list, explicit Akamai-block detection.
- 437 House members probed in ~32 min. Headline: 288/437 (66%) had a working RSS feed; 89 (20%) met strict swap-eligibility criteria; 199 unreliable; 149 dry holes; **0 Akamai blocks**.
- Migration `011_district.sql` adds nullable `district TEXT` to senators with a composite `(state, chamber, district)` index. Applied to Neon during the session.
- `pipeline/lib/seeds.py` extended: `house.json` registered with default chamber='house'; `member_id` → `senator_id` normalization so House flows through the existing rss_collector / registry / update.py without key special-casing; new `include_unconfigured` flag (default False) skips the 348 House members that recon discovered but haven't been promoted yet.
- New `python -m pipeline sync-members [--apply]` upserts the seed roster into the senators table. Run for House first (437 rows), then re-run for full safety would be additive.
- Full backfill from 2025-01-01 cutoff: +1,327 new records, ~711 updated, 901 skipped, 1 expected error (Armstrong) across 227 members in 21m.
- Quality test suite (`pipeline test`) green: 29/29 after three Senate-style tests were chamber-scoped (round-count heuristic, back-coverage truncation, urls-required) and `test_no_empty_titles` was relaxed from <5 to <3 chars (graves-sam e-newsletter "Iran" was a legit one-word House topic title).
- `/senators/[id]` route hard-scoped to chamber='senate' so House URLs 404 there until a House route exists. Other chambers have their own routes (e.g. `/texas/[id]`).

**Lessons learned (recorded in memory `project_house_phase_b1.md`):**
1. **Akamai bypass on House is concurrency, not browser-TLS.** April 2026's comprehensive probe got 401/436 House sites blocked at concurrency 15 + bare Mozilla UA, and concluded "Playwright or curl_cffi residential". This session got **0 blocks across 437 members × ~10 URL probes** at concurrency 3 + full Chrome 130 header set. The earlier "House is unreachable via httpx" thesis was wrong — the issue was rate-policy, not TLS fingerprint. Plain hardened httpx is good enough for daily collection. Reinforces `project_js_sites_are_actually_waf` (19/19 "JS-required" state sites turned out to be WAF-blocking).
2. **Drupal `/rss.xml` is site-wide, not press-release-specific.** The first 30 House inserts surfaced this immediately: palmer-gary's feed contained 10 high-school art-contest submissions; westerman-bruce's was weekly columns; crane-elijah's mixed real press releases with art-contest announcements. Probe homogeneity check rejects podcast/newsletter/in-the-news patterns but doesn't catch art submissions or photo galleries. content_type classifier needs to learn to downgrade these. Wave-1.5 work.
3. **House RSS feeds cap at 10 items by upstream design.** That's fine for daily updates (10 between runs is plenty) but useless for back-coverage. Jan-2025 backfill will require a Drupal listing-page collector against the press-release URL, not RSS. Senate's `test_back_coverage_not_truncated` would erupt against House if applied; scoped to `chamber='senate'` for now.
4. **Codebase was already mostly chamber-ready.** When the TX state-senate wave landed, whoever did it scoped 90% of UI queries (`app/lib/queries.ts`, `analytics.ts`, `transparency.ts`) and brief.py to `chamber='senate'`. Adding House this session was much smaller-scope than expected — district column + sync command + seeds wire + 4 test/query touch-ups. The "schema rename to `members`" idea from the Phase B planning doc was unnecessary; additive-column approach was right.
5. **Single-record short titles are real.** House Drupal newsletters use single-word topic titles ("Iran", possibly "AI", "EV", "5G"). Senate's <5-char threshold was over-tuned to full-headline conventions.

**Files added:**
- `pipeline/recon/house_rss_probe.py` + `house_rss_probe.json` + `house_rss_probe_report.md`
- `db/migrations/011_district.sql`
- `pipeline/scripts/promote_house_rss_seeds.py`
- `pipeline/commands/sync_members.py`

**Files modified:**
- `pipeline/requirements.txt` (+ anthropic)
- `pipeline/lib/seeds.py` (house.json, key normalization, include_unconfigured)
- `pipeline/seeds/house.json` (89 members promoted to RSS)
- `db/schema.sql` (district column documented)
- `pipeline/__main__.py` (.env auto-source promoted from stats to dispatcher; sync-members wired)
- `pipeline/tests/test_data_quality.py` (3 tests chamber-scoped, empty-titles relaxed)
- `app/lib/queries.ts` (getSenator scoped to chamber='senate')

**Commits (in order):**
- `782f914` Fix daily brief workflow: add anthropic to pipeline/requirements.txt
- `77c74f5` Add House RSS probe + 437-member recon results
- `6bc8f2b` House Phase B2: schema + seeds wire-up for 89 RSS-eligible members
- `59a7a9a` Add sync-members command to upsert seed roster into senators table
- `a8caa56` Source pipeline/.env at dispatcher entry, not just stats
- `e2c6f6d` Scope getSenator() to chamber='senate' so /senators/[id] is US-Senate-only
- `02206ff` Scope three quality tests to chamber='senate' for House compatibility
- `4a7b3f2` Relax test_no_empty_titles threshold from <5 to <3 chars

**DB state at session end:**
- 38,518 total releases (+1,327 today)
- House: 437 members, 89 collecting, 871 records (range Feb 2026 → Apr 2026, capped by 10-item RSS)
- Senate: 103 members, 35,890 records (refresh pass added ~700 updates)
- TX state senate: 30 members, 316 records
- Executive: 1 member, 1,441 records (Bluesky/whitehouse rollup)

**Open Phase B follow-ups (not started):**
- Wave 1.5: Re-classify art submissions, photo galleries, e-newsletters out of `press_release` content_type. Likely a content-type rule pass on titles + URL patterns; AI validator can also help.
- Wave 1.5: Selector / date salvage for the 199 House members with feeds that exist but fail strict criteria (sample-link 0/3, stale, <10 items). Per-member triage script would help.
- Wave 2: Drupal listing-page collector against `*.house.gov/news` / `/media/press-releases`. Targets the 149 dry-hole members and unlocks Jan-2025 backfill for the 89 already on RSS.
- Wave 2: House route(s) — either `/house/[id]` mirroring `/senators/[id]` or a unified `/members/[id]` rename.
- House Bluesky: handles not yet seeded.

---

## 2026-05-02 (afternoon) — Phase B2: Senate-parity wave for House (28,244 records)

**Session Summary:**
Continuation of the morning's Phase B1 (89 RSS-only House members, 871 records). Afternoon session ported the full Senate playbook to House: comprehensive per-member channel discovery, multi-content-type silos (op-eds, columns, blogs, newsletters, speeches), HTML listing collector via existing httpx + selectors path, full backfill to Jan 2025 mandate.

**Net result for House (Jan 2025 → today):**
- 437 / 437 members loaded into senators table
- 359 / 437 actively collecting (270 httpx + 89 RSS)
- 28,244 records in DB after tombstoning 80 junk rows
  - 19,247 press_release
  - 604 newsletter
  - 387 blog
  - 362 op_ed
  - 116 statement
  - 64 floor_statement
  - 9 letter
  - 2 photo_release (residual misclassification, low priority)

**Pipeline test suite: 29/29 passing.**

**Total session shipped (start 8:13 AM → 1:50 PM EDT):**
- 14 commits
- ~28k new records (mostly House) into the corpus
- Total corpus: ~37k → 65,892 records (+78%)
- Phase A pipeline + brief patches (anthropic dep, round-count whitelist verified, May 1 brief published)
- Phase B1 House RSS-only proof + schema + UI scoping
- Phase B2 House Senate-parity (recon, promote, backfill, silos)
- Repo cleanup: untracked ~7 MB of regenerable probe JSONs

**Architecture wins:**
- The codebase was already chamber-aware from the TX state-senator wave (queries.ts, analytics.ts, transparency.ts, brief.py all filtering chamber='senate'). Adding House this session was much smaller-scope than the original Phase B plan suggested. No "members" rename needed; additive `district` column was the right move.
- `pipeline/backfill.py` reads from the DB (not seed file), so once recon → promote → sync flowed through, the existing collector picked up House without code changes.
- `pipeline/lib/seeds.py` `member_id` ↔ `senator_id` normalization let House data flow through the existing `update.py` / `registry` / `rss_collector` / `httpx_collector` without any chamber-specific code paths.

**Three Phase-B2 lessons:**
1. **Akamai bypass on House is concurrency, not browser-TLS.** Today's recon at concurrency 3 + Chrome 130 headers got 0 blocks across 437 members × 10 URL probes each. The April 2026 comprehensive probe at concurrency 15 had concluded "Playwright or curl_cffi residential needed" — wrong diagnosis. Reinforces `project_js_sites_are_actually_waf`.
2. **Drupal `/rss.xml` is site-wide, not press-release-specific.** The morning's 89 RSS members surfaced art-contest entries, photo galleries, and weekly columns mixed with real press releases. Wave-2 fix was to give every member a content-type-specific listing URL (e.g. `/media-center/press-releases` instead of site-wide `/rss.xml`); RSS members keep RSS for daily reliability but get the proper listing for backfill.
3. **Listing-detector quality varies per silo.** Drupal `.views-row` blocks sometimes contain non-content widgets (sidebar, share-link rows). Recon's heuristic picked title='a' instead of 'h2 a' on those silos, which produced ~1,930 short-title rejects during silo backfill (correctly skipped, not bad data). Per-silo selector hardening is wave-2.5.

**Known follow-ups (in tasks):**
- Fix WordPress listing detector — 11 of 28 WP members yielded 0 listings; current heuristic over-prefers `.views-row` (Drupal). Add `article.post`, `.wp-block-group` candidates and re-run on the WP subset. ~1 hr work.
- Triage 99 needs_attention members — likely JS-rendered nav or unusual layouts. Manual eyeball + targeted re-probe per member. ~3-5 hr work.
- Confirm `daily.yml` cron timeout with 359-member House roster (was tuned for 138 senators). Probably need to bump GH Actions timeout-minutes or split into a House-specific job. ~30 min work.
- Tighten detail_link selector logic so future runs don't pull outbound article URLs as press-release `source_url`. The 13 non-gov URLs tombstoned today were caught by `test_all_urls_are_government` post-hoc; the selector itself is still permissive. Probably scope to same-host: `a[href*=".house.gov"]` or first heading-anchor only.
- Wave 2.5 silo selector hardening — refine the ~50 silos where my recon picked title='a' to use 'h2 a' / 'h3 a'. Would recover ~1,500 records currently lost to skipped_short.

**Repo size cleanup (separate concern):**
Untracked 3 large probe JSONs (~7 MB total) that had been force-added to bypass the existing `pipeline/recon/*.json` gitignore rule. Working-tree files preserved. History purge (filter-repo + force-push) deferred until pre-launch if at all needed.

**On the paywall question raised mid-session:** Decided to keep code public — open methodology is a journalism asset and required for the portfolio purpose. Premium gating ships at the route layer (Better Auth on selected /brief, /releases, /api routes), not by hiding open-methodology code from public git.

**Commits (in order):**
- `782f914` Phase A: anthropic dep fix
- `77c74f5` House RSS probe + 437-member recon
- `6bc8f2b` Phase B1: schema migration 011 + seeds wire-up + 89 RSS members promoted
- `59a7a9a` sync-members command
- `a8caa56` Dispatcher .env auto-source
- `e2c6f6d` getSenator chamber-scoped
- `02206ff` Three quality tests chamber-scoped
- `4a7b3f2` Empty-titles threshold relaxed
- `a52a915` Comprehensive House recon script
- `3469c32` Promote-channels script
- `74abd28` 330 House members promoted to httpx HTML listings
- `8ae02bd` House silo backfill script
- `f5968e9` Silo run_id collision fix
- `8259777` Untrack ~7 MB of regenerable probe JSONs
- `d3bbcd8` Rampup test chamber-scoped

---

## 2026-05-02 (afternoon-evening) — Schema rename: senators → officials, press_releases → official_site_items, /house route live

**Session Summary:**
Continuation of the morning's House Phase B1 + B2 work. After the wave-2 Senate-parity push landed (28k House records across 437 members), Codex flagged that the underlying schema was strained: a `senators` table holding 437 House reps + 30 TX state senators + 1 White House row was straining badly, and would break worse as state legislatures + governors arrive. We did the rename today — before state-house expansion, while the data was small enough to migrate quickly and large enough to expose the wrongness.

**The rename in three phases (with compat views as the safety net):**

Phase 1 — `senators` → `officials` + 5 structural columns:
- New columns: `branch` (legislative/executive), `jurisdiction` (us/tx/ca/...), `office_type` (senator/representative/state_senator/executive_office), `openstates_id`, `external_ids`. All NOT NULL except the ID fields.
- Backfilled 571 rows from the legacy overloaded `chamber` values. `tx_senate` → (chamber=senate, jurisdiction=tx). `ne_unicameral` → (chamber=unicameral, jurisdiction=ne). `executive` → (branch=executive, chamber=NULL). Dropped chamber NOT NULL since executives correctly have no chamber.
- Compat view `senators` aliases `officials` so legacy `FROM senators` callers keep working.

Phase 2 — `press_releases` → `official_site_items`:
- Same shape: rename + compat view. content_versions FK auto-followed.

Phase 3 — Codex's specific six-step plan executed in order:
1. Made migration 012 idempotent (DO $$ guards + IF NOT EXISTS).
2. Fixed silent zero-row queries (the `WHERE chamber='tx_senate'` filters that no longer matched anything because chamber was normalized to `senate`).
3. Renamed `senator_id` → `official_id` across 5 tables (official_site_items, social_posts, floor_speeches, alerts, health_checks). Mechanical sed sweep across 89 files in pipeline/ + app/.
4. Renamed `content_versions.press_release_id` → `official_site_item_id`.
5. Refreshed db/schema.sql to match the post-migration shape.
6. Final test + smoke sweep.

**Live smoke test caught a real 500.** `/senators`, `/texas`, `/social` all returned 500s right after deploy because `getSenators()` and similar functions did `SELECT s.* ... GROUP BY s.id` against the senators compat view — Postgres allows this on base tables (PK functional dependency) but rejects it on views. Fixed with a follow-up sweep that pointed all app + pipeline queries at the base tables (`officials`, `official_site_items`) directly. Compat views remain only as paranoia for unswept callers. 13 pages re-verified live.

**`/house` and `/house/[id]` routes shipped.** Mirror of `/senators` + `/senators/[id]` for US House members. Directory grouped by state with district + name + party + release count. Detail page with type-filter chips, paginated release list. Hard-scoped via getHouseMember() so /house/{senate_id} 404s. Nav: "Directory" renamed to "Senate"; new "House" entry added. Sitemap: 437 /house/{id} URLs at priority 0.6.

**WordPress detector broadened.** Original recon's listing detector over-preferred Drupal `.views-row`, missing 11 House WP members. Added `.item`, `article.hentry`, `article.post`, `article.type-post`, etc. as listing candidates. Added `/category/press-releases/`, `/category/news/`, etc. as URL_GUESSES. Re-running full recon in background to refresh house_full_recon.json under broader heuristic.

**Five House members had NULL district** (kiley-kevin, moskowitz-jared, gottheimer-josh, miller-max, cloud-michael). Fetched each member's homepage with the Akamai-safe Chrome 130 profile, parsed district from embedded Next.js JSON ("district":"3rd"). All 5 patched into house.json + DB. Recovered districts: 3, 23, 5, 7, 27.

**Silent jurisdictional leak fixed.** Every `WHERE chamber='senate'` that lacked a `jurisdiction` predicate was including the 30 TX state senators in "Senate" stats post-migration. The brief's "100 senators" output was actually 130; transparency + analytics + queries were all mixing US + TX. Patched 34 sites across pipeline/commands/brief.py + app/lib/{analytics,transparency,queries,trending}.ts.

**Stale index names cleaned up.** Postgres doesn't auto-rename indexes when their parent table renames. Migration 016 brings senators_pkey → officials_pkey + 4 others.

**Lessons (recorded in memory):**

1. **The compat-view pattern works for table renames but breaks on `SELECT t.* GROUP BY t.id`.** Views don't carry PK functional dependency. Sweep app code to target the base table directly; compat views are paranoia, not the actual SELECT path.

2. **Silent jurisdictional leaks are the post-rename quiet failure mode.** When you normalize an overloaded chamber field (`tx_senate` → `senate`+`jurisdiction='tx'`), every existing filter that said `chamber='senate'` silently expands to include the new rows. Audit every such filter before deploying the rename.

3. **House Drupal `/rss.xml` is site-wide, including non-press-release content.** Wave-2's 89 RSS members surfaced art submissions and weekly columns alongside real press releases. Wave-3's broader recon promotes content-type-specific listing URLs (e.g. `/media-center/press-releases`) which return cleaner content. RSS members keep RSS for daily polling reliability but use httpx for backfill.

4. **House WordPress sites use `.item` selectors, not `.views-row`.** Original recon's listing-detector was Drupal-tuned. Broadened on 2026-05-02 to also catch WP shapes. Re-running full recon to recover the missed members.

5. **Live smoke test catches what the test suite can't.** TypeScript build clean + pipeline tests green didn't catch the GROUP-BY-on-view 500 because no test exercised that specific path. Curl the production URLs after every schema change.

**Files added:**
- `db/migrations/012_rename_to_officials.sql`
- `db/migrations/013_rename_press_releases.sql`
- `db/migrations/014_rename_senator_id_to_official_id.sql`
- `db/migrations/015_rename_press_release_id.sql`
- `db/migrations/016_rename_stale_indexes.sql`
- `app/house/page.tsx`
- `app/house/[id]/page.tsx`

**Files heavily modified:**
- `db/schema.sql` (full refresh to post-migration shape)
- `pipeline/lib/seeds.py` (per-file structural defaults: branch + jurisdiction + chamber + office_type)
- `pipeline/commands/sync_members.py` (UPSERT now writes structural columns)
- `pipeline/recon/house_full_recon.py` (broader WP heuristic)
- 89 files in pipeline/ + app/ via codemod sweep (senator_id → official_id, FROM senators → FROM officials, etc.)

**Commits (in order):**
- `5008f71` Phase 1: senators → officials + structural columns
- `8323c6a` Phase 2: press_releases → official_site_items
- `8e54bb0` Re-enable cron after Phase 2
- `2a26ed4` Codex steps 1+2: idempotent migration 012, fix legacy chamber filters
- `2dcdf5a` Codex steps 3-6: senator_id → official_id rename + schema.sql refresh
- `e08b243` Hotfix: switch app/pipeline queries from compat views to base tables
- `30686c2` Rename stale senators_* indexes
- `6cd8955` Recon: broaden WP listing detector + URL guesses
- `2c2441a` Add /house and /house/[id] routes
- `0e3d412` Wave-3: jurisdiction='us' filters + 5 district fixes + homepage copy

**DB state at session end:**
- 65,892 active records (House + Senate + TX state + executive)
- 578 officials (575 active + 3 historical formers)
- Compat views in place for soak period; drop in follow-up after 48 hr clean

**Open follow-ups (in tasks):**
- Wait for full recon re-run, then promote_house_channels.py + sync. Probably recovers 5-10 more WP House members + a handful more silos.
- Triage 99 needs_attention members (manual eyeball).
- Populate House bioguide_id + download 437 photos (separate ~1-2 hr task).
- Plan official_sources migration (Codex's separate suggestion). Designed-but-deferred.
- Drop compat views after 48 hour soak.

---

## 2026-05-02 (evening, session close) — Wave-3: jurisdiction filters, House route + photos, parallel agents

**Session Summary:**
Continuation of the schema-rename + House-Senate-parity day. After Codex Phase 3 closed, we caught a silent jurisdictional leak (post-rename, `chamber='senate'` without `jurisdiction='us'` was including TX state senators in US-Senate stats), shipped the `/house` route, populated bioguide_ids for 437/437 House members, downloaded 433 photos, and seeded the `official_sources` migration plan + draft.

**Wave-3 fixes:**
- 34 sites in pipeline + app patched to add `jurisdiction='us'` next to every `chamber='senate'` filter — brief.py, transparency.ts, analytics.ts, queries.ts, trending.ts. Without this, the brief's "100 senators" was actually 130 rows.
- 5 House members with NULL district fixed by fetching their homepages and parsing the embedded Next.js JSON for `"district":"3rd"` patterns: kiley-kevin (CA-3), moskowitz-jared (FL-23), gottheimer-josh (NJ-5), miller-max (OH-7), cloud-michael (TX-27).
- Homepage hero copy updated from "100 Senators. One Archive." to "Every member of Congress. One archive." Sub-copy mentions both 100 senators and 437 House reps.
- Manual DB sanity-test sweep ran post-Phase-3 deploy. Confirmed all NOT NULL constraints, FK integrity, hypothetical INSERTs (governor / state rep / AG all accepted by schema). Surfaced one cosmetic find (stale `idx_senators_*` index names) → migration 016 renamed them.

**House route shipped (`/house` + `/house/[id]`):**
- Directory grouped by state, 437 members with district + party + release count + latest-release month.
- Detail page mirrors `/senators/[id]` shape: 72×72 photo, party + state + district header, type-filter chips, paginated release list.
- Hard-scoped via `getHouseMember()` with `chamber='house' AND jurisdiction='us'` so `/house/{senate_id}` 404s cleanly.
- Nav: "Directory" renamed to "Senate"; new "House" entry added.
- Sitemap: 437 `/house/{id}` URLs at priority 0.6.

**Parallel-agent sub-runs:**
- **Agent A** (bioguide_id population): pivoted from Cloudflare-blocked bioguide.congress.gov to the canonical `unitedstates/congress-legislators` GitHub dataset. **437/437 matched, 0 unmatched.** Strategies: 422 simple `(state, last-name)`, 3 nickname reconciles (Bob/Robert), 12 multi-word last-name fallbacks (Wasserman Schultz, Van Drew, etc.). Output preserved at `pipeline/recon/house_bioguide_ids.json`. Builder script committed as `pipeline/recon/build_house_bioguide_map.py`.
- **Agent B** (official_sources draft): produced PR-ready DRAFT files — `db/migrations/017_official_sources.sql` (181 lines, idempotent backfill in 3 sub-steps), `pipeline/scripts/migrate_silos_to_sources.py` (241 lines, dry-run by default), and `docs/official-sources-codemod-checklist.md` (gitignored, 93 lines, named functions and lines for the future codemod). Nothing applied to DB; reviewed for next session.

**House headshot photos:**
- `pipeline/scripts/download_house_photos.py` walks bioguide.congress.gov `/bioguide/photo/{first}/{ID}.jpg` for each of 437 House bioguide_ids.
- 433/437 succeeded; 4 legitimately 404 from upstream (Balderson, Cloud, Gottheimer, Soto — all currently-serving but no photo at the LoC mirror). Hand-source follow-up.
- 105 MB total in `public/house/`. Senate has 13 MB / 105 photos for comparison; House higher-res because LoC serves originals for House but downsized for Senate.
- `/house/[id]` page renders 72×72 headshot inline with name; falls back to 2-letter initials placeholder for the 4 missing.

**WP detector broadening + re-promote:**
- Added `.item`, `article.hentry`, `article.post`, `article.type-post`, `li.post-item`, `div.post-item`, `.loop-item`, `main article` to the listing-detector candidates list, plus 14 `/category/*` URL guesses.
- Re-ran full 437-member recon (~30 min). Topline gains: 5 more members recovered (96 → 91 zero-listing), 31 more silos catalogued (730 → 761 total).
- Re-promote moved 24 members to updated URL/selectors; net +3 actively-collecting (270 → 273 httpx, 89 RSS unchanged). Backfilled 8 newly-configured members; 2 produced records (Donalds 15, Trahan 15), 6 walked listings without extracting clean items (selector-quality issues for those specific members; per-member hardening tracked separately).

**Lessons added to memory:**
- **Compat views break `SELECT t.* GROUP BY t.id`** (no PK functional dependency on views). Sweep app code to target base tables; views are paranoia, not the SELECT path. Caught live via curl smoke after deploy: /senators, /texas, /social all returned 500. Fixed in commit `e08b243` (40 files, mechanical sweep).
- **Silent jurisdictional leak is the post-rename quiet failure.** After normalizing `tx_senate` → `senate`+`jurisdiction='tx'`, every `WHERE chamber='senate'` filter without a `jurisdiction` predicate silently expanded to include the new rows. Audit every such filter pre-deploy.
- **Bioguide.congress.gov is now Cloudflare-protected** for non-browser User-Agents. `unitedstates/congress-legislators` GitHub mirror is the canonical fallback (used by ProPublica, GovTrack, NYT). Photo URLs at `bioguide.congress.gov/bioguide/photo/{first}/{ID}.jpg` still work without auth — possibly a different subdomain policy.

**Files committed (commits since the afternoon entry):**
- `0e3d412` Wave-3 jurisdiction filters + 5 districts + homepage copy
- `5cd32b4` 437 House bioguide_ids + draft official_sources migration
- `0c53a0a` House photo render + downloader script
- `ed926db` 433 House headshot photos (~105 MB)
- `f9f65e6` Re-promote House channels after broader WP recon

**DB state at session end:**
- 65,892 active records (up from ~37k at session start, +78%)
- 578 officials (575 active + 3 historical formers)
- House: 437 members, 362 actively collecting (273 httpx + 89 RSS), 28k+ records
- 433/437 House have headshot photos rendered
- 437/437 House have bioguide_id

**Pipeline tests:** 29/29 passing.

**Open follow-ups (in tasks for next session):**
- #32 Triage 93 needs_attention House members (manual eyeball, ~3-5 hr)
- Drop compat views after 48-hr soak (~5 min)
- Apply `017_official_sources.sql` migration per the design doc + Agent B's draft (~6-8 hr)
- Hand-source the 4 missing House photos (Balderson, Cloud, Gottheimer, Soto)
- Per-silo selector hardening to recover ~1,930 short-title rejects + the 6 wave-3 promoted members that didn't backfill cleanly

---

## 2026-05-02 (night, session close) — House recovery sprint, three parallel sub-agents, Akamai wall hit

**Session Summary:**
Final stretch of the day after the schema rename + /house route + photos shipped. Codex's review caught 4 jurisdiction-leak bugs my own audit missed; fixed those plus made migrations 013/014 rerun-safe. Then ran a three-sub-agent parallel reconnaissance to recover the remaining House gaps (selector hardening, unconfigured listings, shallow backfills), produced PR-ready drafts for the `official_sources` migration, and ran a thorough Playwright UX audit of the live site. Hit a hard Akamai IP-level cooldown after ~650 House requests in an hour and called the session.

**Codex review fixes (commit `cf92a5b`):**
Four real jurisdiction-leak bugs my wave-3 sweep missed:
- `app/api/chamber/counts/route.ts:46` — `chamber='senate'` was leaking 30 TX state senators into US Senate cartogram counts.
- `app/api/senators/activity/route.ts:42,56,71,86` — same bug in all four query branches (top/bottom volume, top/bottom growth).
- `pipeline/commands/health_report.py:74` — double-broken: `chamber IN ('senate', 'executive')` (a) included TX state senators and (b) excluded the White House (chamber=NULL post-migration). Replaced with explicit federal scope.
- Migrations 013 + 014 — re-running 013 after 014 had landed would silently regress the `press_releases` view by dropping the `senator_id AS official_id` alias. Both migrations now use a DO $$ block that detects column shape and creates the right view form regardless of order. Verified by re-running both in sequence.

**Three sub-agents launched in parallel (massive payoff):**

Agent A — Bucket B selector hardening: 30/30 House members fixed. Discovered the universal House EvoGov-Drupal pattern: `list_item: ".evo-views-row"`, `title: ".media-body .h3 a"`, `date: ".media-body .row .col-auto:first-child"`. Importantly, the recon also surfaced that **`extract_item_data` in `pipeline/backfill.py` was not honoring the seed's `selectors` config at all** — the function ran through a hand-tuned chain of CMS-specific branches and a generic fallback (`h2 a, h3 a, …`) that uses CSS *element* selectors, missing EvoGov's `<div class="h3">` (CSS *class*). Patched: when seed provides title + detail_link, honor it at the top of the function. Re-backfill of the 30 fixed members: **+2,006 records.**

Agent B — Bucket A unconfigured listing discovery: **75/75 recoverable.** Three patterns. (1) ColdFusion-table sites with `.recordList tr` selectors and two-digit-year dates (`5/1/26`) — 26 members. (2) Heading-only listings: `<h2 class="title"><a>...</a></h2>` with no wrapper class — 23 members. (3) Self-anchored rows where `<a class="item">` IS the row — 1 member (smith-jason). All 75 applied to `house.json`; sync + backfill of 77 (75 + 2 fixed config errors) yielded **+3,573 records**, but only 17 of 75 actually got data because Akamai started 403'ing mid-run. The 58 that 0'd should succeed after the IP cooldown.

Agent C — Bucket C deeper-backfill recon: 42 shallow members categorized into 4 buckets. Surfaced a **major architectural finding**: 18 House members run on a shared Next.js + WPGraphQL stack with build-id `Y2fhOGucrp2Wic484nhoA`; their data is fetched client-side from a private admin subdomain that's not publicly addressable, so httpx alone cannot get past the SSR'd ~6 items. Playwright is the only viable path for this group. Also flagged 2 seed-config errors (baumgartner pointed at signup form, pressley at static info page) and identified 10 House WordPress members exposing `/wp-json/wp/v2/posts?categories=N` with deep coverage.

**WP-JSON House rescue (commit `f0ed1b6`):** New `pipeline/scripts/backfill_house_wp_json.py` mirrors the senate-side `backfill_op_eds.py` rescue pattern. Slug fallback widened to handle Jeffries-style hyphenated-singular `press-release` (vs the more common plural `press-releases`). Falls through to listing all categories and picking the largest matching "press" / "release" / "news" / "media" slug. Backfilled 10 House WordPress members on 2026-05-02: **+1,833 records** (Goodlander 289, Baumgartner 60, Barragán 94, Crane 45, others).

**Two parallel-agent deliverables drafted but not applied:**

Sub-agent (earlier in day, file-only) drafted `db/migrations/017_official_sources.sql` (181 lines, idempotent backfill in three sub-steps) and `pipeline/scripts/migrate_silos_to_sources.py` (241 lines, dry-run by default). Plus a gitignored codemod checklist in `docs/`. Codex pushed back: the UNIQUE (official_id, url) constraint should include `content_scope` because two scopes can legitimately share a URL, and the schema needs to leave room for caucus / chamber / shared-source rows where `official_id` would be NULL or many-to-one. Both adjustments are quick edits before applying; tracked separately.

**House headshot photos (commits `0c53a0a`, `ed926db`, `e8a09be`):**
Sub-agent A (earlier in day) populated 437/437 House `bioguide_id` values via the `unitedstates/congress-legislators` GitHub mirror (bioguide.congress.gov is now Cloudflare-protected for non-browser UAs; the GitHub mirror is the canonical fallback used by ProPublica, GovTrack, NYT). Then `pipeline/scripts/download_house_photos.py` pulled 433/437 headshots from `bioguide.congress.gov/bioguide/photo/{first}/{ID}.jpg` (the photo subdomain is on a different policy than the directory subdomain, still works without auth). Four photos genuinely missing from upstream (Cloud, Balderson, Gottheimer, Soto — all currently-serving members per the GitHub roster, but the photo mirror lacks them). Added a `MISSING_PHOTOS` set in `app/house/[id]/page.tsx` so those four render the 2-letter initials placeholder instead of a broken-image icon. Codex's review prefers a generated `public/house/manifest.json` over the hard-coded set; tracked for the next photo refresh.

**Playwright UX audit (commit `a5ffdc7`):**
Wrote `pipeline/scripts/playwright_ux_audit.py` — a re-runnable end-to-end audit that visits 19 routes at desktop (1280×900) and 5 at mobile (375×667), asserts title + h1, counts broken images, captures console errors. Used today to verify the 4 known-missing-photo fallback works live. Surfaced one minor finding: `/texas/tx-d27-hinojosa-adam` has a broken `d00.jpg` (TX district image with district 00 — separate state-senator imagery quirk).

**Lessons added to memory and notable for future sessions:**

1. **Akamai's IP-level cooldown is fast and harsh.** ~650 House requests across hundreds of subdomains in under an hour tripped a per-IP block that returned 403 to **both** httpx (with full Chrome 130 headers) AND headless Playwright (real Chrome browser). The block is at the IP level, not TLS or fingerprint. Recovery requires either ~30-60 min cooldown OR a different source IP (residential proxy / different machine). Future bulk House sweeps should throttle harder: concurrency 2 not 3, inter-request sleep 0.5s not 0.15s. The `pipeline/recon/house_full_recon.py` profile is the right floor; backfill.py was previously running with a less-conservative throttle and a thinner header set, both of which got cleaned up today (commit `e32e640`).

2. **`extract_item_data` ignored seed selectors.** The function had hand-tuned branches per CMS shape plus a generic `h2 a, h3 a, …` fallback that uses CSS *element* selectors. House EvoGov-Drupal's `<div class="h3">` is a CSS *class*, not an element, so the heuristic missed it entirely. The seed file's explicit `title: ".media-body .h3 a"` was decorative until I patched `extract_item_data` to honor it at the top. Without that fix, none of Agent A's 30 selector corrections would have produced records. This is the kind of bug that hides because the type system is happy, the tests pass on Senate data, and the symptom is just "low record counts."

3. **Sitemap.xml is not a fallback for House.** Probed all 437; only 4 expose any sitemap, and 0 of those include press-release URLs. The shared House Drupal template doesn't generate sitemaps for content pages. Cross off that recovery avenue for the future.

4. **Bioguide.congress.gov is Cloudflare-protected for the directory route**, but the photo subdomain (`bioguide.congress.gov/bioguide/photo/...`) is on a different policy and still works without auth. The canonical fallback for member metadata is `unitedstates/congress-legislators` on GitHub — used by every major civic-tech org.

5. **Per-host browser permission prompts in claude-in-chrome don't honor "always allow" universally.** Each new House subdomain triggers a fresh prompt. Workaround for batch work: use Playwright (no permission gates), reserve Chrome MCP for single-page interactive verification.

**House records summary at session end:**
- Started day: 0
- After morning Phase B1: 871
- After afternoon Phase B2 backfill: 28,275
- After evening recovery sprint: **35,687**
- Reaching Jan 2025 mandate: 261 of 437 (60%)
- Configured (collection_method set): 362 of 437 (83%)
- 4 known-missing photos handled with initials fallback
- 437 / 437 have bioguide_id

**Total corpus at session end: 72,071 records.** Up from ~37,000 at session start (+95%).

**Open backlog for future sessions (in tasks #37, #38 plus implicit):**
- Re-run backfill of the 58 Bucket A members that 0'd during the Akamai window — should succeed post-cooldown
- Date-from-parent fallback for heading-only listings (15 Bucket A members extracted but had null dates)
- Playwright collector for the 18 Next.js + GraphQL House members (Phase 2 — Cloud, Tlaib, Kiley, Donalds, Owens, Lucas, Joyce, etc.)
- `expected_low_volume: true` flag in house.json for ~5 offices that genuinely don't publish much (verifies "zero" rather than tagging as a coverage gap)
- Apply `017_official_sources.sql` (with Codex's content_scope + nullable-official_id adjustments) before state-house expansion
- Drop the `senators` and `press_releases` compat views after a 48-72hr soak window confirms no caller silently breaks
- House headshot manifest.json (Codex's preference over the hard-coded MISSING_PHOTOS set)

**Commits today (this stretch, in order):**
- `cf92a5b` Codex review: 4 jurisdiction leaks + rerun-safe migrations 013/014
- `f0ed1b6` Add backfill_house_wp_json: rescue 10 House WordPress members
- `a5ffdc7` Wave-3 House recovery: 77 members configured + extract_item_data fix
- `0c53a0a` House detail photo render + downloader script
- `ed926db` 433 House headshot photos
- `e8a09be` MISSING_PHOTOS fallback for 4 missing
- `5cd32b4` 437 House bioguide_ids + draft official_sources migration
- `e32e640` backfill.py: full Chrome 130 headers (Akamai-safe)

---

## 2026-05-03 (Sunday) - Full Congress Reframe Marathon

**Session Summary:** Reframed Capitol Releases from "US Senate archive" to "Full Congress, 535 members" in a ~10-hour autonomous push (with ~30min of user-direction breaks). Daily cron started clean at 9:31 AM EDT (29/29 tests pass). Ended day with 85.6% House strict reach Jan 2025 / 90.8% bulletproof accounted-for, 43,927 House records (+8,240 today).

### What Landed (28 commits to origin/main)

**Track C foundation** — `us-congress` RosterScope is now the default for `getFeed`/`getSearchFacets`. Single helper `chamberArray()` + Postgres `= ANY($N::text[])` keeps chamber predicates parameterized across all surfaces.

**Track C UI** — Chamber filter pills shipped on `/search`, `/feed`, `/trending`, `/social`. Homepage hero shows 537 split (100 Senate + 437 House). Senate/House toggle on the chamber visualization with new `HouseChamber` component (437-seat, 5-row semicircle). New `/speeches` route surfaces the 4,898-record Senate floor speeches table with chamber filter that explicitly states House Phase-2.

**Track C leak fixes** — Codex D1 audit found 55 leaks across 222 queries. 28 user-facing leaks closed (queries.ts homepage stats, feed, search, trending, sitemap, deleted, related-releases, social), 7 trending.ts queries scoped to federal Congress, 4 jurisdictional leaks Codex caught earlier in PR review. Remaining ~14 are in pipeline/tests/test_data_quality.py (universal scans that are fine because the universe is overwhelmingly federal).

**Track A coverage** — Three EvoGov-Drupal waves: 15 + 17 + 31 House members bulk-patched (~63 total). Universal pattern is `.evo-views-row` rows with titles in `.h3` or `.h5` wrappers and dates in `.media-body .row .col-auto:first-child`. The seed list_item was `.views-row` (matched but title selector grabbed image links instead of headings, and date was null). One Webflow + ASP.NET document store CMS discovered (Hamadeh, mcgovern, ezell, fernandez) — pattern is `.article_wrap` + `.article_title` + `.article_date`. WP-JSON rescue on Jayapal-Pramila yielded +238. Deep pagination on Comer/Raskin/Stefanik/Barr yielded +277 (Stefanik alone +166).

**Track B outlier infrastructure** — Three new fields in seed JSONs: `expected_low_volume`, `expected_zero`, `coverage_status`. Applied to Armstrong (Senate, expected_zero — appointed 2026-03-24), Jordan-Jim (low_volume_reason — scraper bug), 18 GraphQL House members (coverage_status='playwright_required'), 3 Codex D4-verified outliers (fuller-clay, cherfilus-mccormick, menefee-christian — all special-election or resignation), 14 Codex D4 scraper-bug-pending.

**Quality fix** — Pipeline test caught one bad date (costa-jim 2029-02-03). Investigation uncovered 648 nav-junk records lurking from historical scrapes (`/contact/offices/`, `/about/biography`, `/services/`, etc., scraped as releases by permissive selectors). All tombstoned. `pipeline/backfill.py _is_external_detail_url` hardened with 17-fragment denylist. **The honest reach-Jan-2025 count went 361 → 340 (-21) after the cleanup**, because 21 members had been "reaching Jan 2025" only via fake 2021/2023 dates from contact-form artifacts. Now at 374 honest after the rest of today's work.

**Codex collaboration** — D1 (jurisdictional leak audit) + D2 (methodology page draft) + D4 (web research on 30 trouble members) all delivered solid work. Codex also pre-emptively fixed `pipeline/backfill.py` (date-from-parent fallback + external-URL filter + Akamai-safe MAX_CONCURRENT=2) and `pipeline/commands/update.py` (null-date repair on existing rows) — reviewed and merged.

### Lessons

1. **The EvoGov-Drupal pattern is more universal than yesterday's 30-member discovery suggested.** Today's wave 3 found 188 House members had stale `.views-row` selectors when their pages serve EvoGov markup. ~30 of those were stuck because the generic `'a'` title selector grabbed image links. The remaining ~158 collected fine via `extract_listing_items`'s waterfall but had wrong scrape_config. Filling in proper EvoGov selectors closes the loop and makes diagnostics honest.

2. **Postgres compat views ARE updatable through column aliases when only a select is renamed.** Codex's `UPDATE press_releases` worked even though the view aliases `official_id AS senator_id` — Postgres auto-updates simple views with column rename. My initial worry was wrong; the change shipped.

3. **Honesty regressions are wins.** The nav-junk tombstone moved the reach-Jan-2025 number DOWN by 21 because old "reaches Jan" status was inflated by fake dates from contact pages. The new lower number is the honest one.

4. **`= ANY($N::text[])` is the cleanest way to parameterize a chamber filter that toggles between single-chamber and both-chambers.** Avoids branching the SQL by chamber mode.

5. **The Webflow + ASP.NET document store is a third House CMS family** (alongside EvoGov-Drupal and WordPress). Signature: `/news/documentquery.aspx?DocumentTypeID=N` URL with `.article_wrap` items inside `.articles_grid`. Six known so far (Hamadeh, mcgovern, ezell, fernandez, two more probably exist). Worth a recon scan tomorrow.

6. **Codex 5.5 high is excellent at exhaustive read-only audits and web research.** Its D1 leak audit was 250 lines of consistent classification across 222 queries. D4 web research distinguished real-world outliers from scraper bugs with cited sources. Use it liberally for these patterns.

### Open Backlog (Not Started)

- Apply `017_official_sources.sql` migration (post-soak, not user-facing)
- Drop `senators` / `press_releases` compat views (post-soak)
- Playwright collector for 18 NextJS+GraphQL House members (~5% of corpus)
- House CREC floor-speech parser (Phase 2)
- House Bluesky verification (Phase 2)
- Wire methodology page to live coverage diagnostic JSON when Codex D3 lands
- Address the remaining ~40 stuck-undocumented House members (mostly listing-page-horizon issues that may need different data sources)

---

## 2026-05-03 (Sun) → 2026-05-04 (Mon early hours) - 100% Bulletproof + RSS Rescue

**Session arc:** 12-hour autonomous push from yesterday EOD (35,687 House records, 73.9% reaching Jan 2025) through midnight Monday. Cracked architectural assumptions on 25 House members previously classified as needing Playwright or stuck at listing horizons.

### Final state

| Metric | Yesterday EOD | End of session | Δ |
|---|---:|---:|---:|
| House records | 35,687 | **48,322** | **+12,635** |
| House CLEAN reaches Jan 2025 | 73.9% | **96.6%** | +22.7 pts |
| House documented gaps | 49 | 13 | -36 |
| Pure "us" scraper limitations | 25 | 1 (meeks) | -24 |
| Federal Congress bulletproof | n/a | **537/537 = 100%** | new |

### What actually happened

This was largely a tour of misclassified architecture. Yesterday's recon had bucketed members as either `playwright_required` (NextJS+GraphQL) or `pagination_js_required` (h2.title sites). Both classifications were technically defensible on the evidence the recon collected — but both stopped at the first plausible negative when fallback options existed ("we'll do Playwright in v2"). User push-backs reopened the analysis on three separate occasions and uncovered three different unblocking paths.

**Wave 1 (RSS rescue, 16 NextJS+GraphQL members):** Underneath the modern NextJS frontend, these are WordPress sites. WordPress publishes a public RSS feed at `/feed` regardless of how the frontend renders. The feed supports `?paged=N` pagination and yields the full archive. +1,789 records across kiley, luna, moskowitz, williams, budzinski, yakym, tlaib, gottheimer, torres, landsman, miller-max, joyce, lucas, cloud, owens, perez. Built `pipeline/scripts/backfill_wp_rss_paginated.py`.

**Wave 2 (year+month filter, 6 default_v7 theme members):** The "pagination JS-driven" classification turned out to be wrong because these sites aren't React at all — they're 2012-era server-rendered HTML with MooTools and IE polyfills. The `?page=N` parameter is dead code from a Drupal default that was never wired up; the working filter is `?year=Y&month=M` (the dropdown values from the listing UI). Iterating year × month yields full coverage. +422 records. Built `pipeline/scripts/backfill_default_v7_archive.py`.

**Wave 3 (Smith-Christopher custom CMS, 1 member):** User found his `/news/documentquery.aspx?Year=YYYY&Page=N` URL pattern with "Posted in [Category] on [Date]" classifier text on each item. CMS quirk: ALL items live inside ONE outer `<li>` separated by `<br/>` tags, not as separate list elements. Custom one-off collector. +247 records, 5 → 254 total.

**Wave 4 (newsblocker pattern, 6 members):** User pointed me at Donalds's `/news/documentquery.aspx?DocumentTypeID=27` URL. Same Webflow + ASP.NET document-store CMS as Hamadeh, McGovern, Trahan. Different `DocumentTypeID` per site (27 for press releases on most, 2381 for Guthrie's "Latest News", 2472 for McGovern). +103 records donalds, +132 pingree, +26 ezell, +20 guthrie. Coleman/Hoyle/Thanedar/Foushee got date-repair fixes (88-127 records each had placeholder dates from earlier scrapes).

**Wave 5 (relative-URL bug fix, 2 members):** Backfill script was joining relative URLs to the domain root, producing 404s. The newsblocker listings return `<a href="documentsingle.aspx?DocumentID=N">` (no leading slash), which `urljoin` resolved to `https://host/documentsingle.aspx` instead of `https://host/news/documentsingle.aspx`. Treating `/news/` as the base path fixed it. Ezell + Guthrie crossed to CLEAN.

### Lessons (added to `docs/case-study-rss-rescue.md`)

1. **Recon stops at the first plausible negative** when a fallback option exists. "We'll just use Playwright" is the comfortable answer that absorbs the discomfort of "is this really blocked?" and turns dead-ends into permanent ones.

2. **Mental model: architecture-first vs. goal-first probing.** Engineer onboarding asks "how does this site work?"; journalist filing FOIA asks "what URLs return the data I need?" Goal-first is faster for scraping work because most CMSes expose data through multiple parallel surfaces, and there's no rule that all of them are equally locked down.

3. **Read the page source.** The `<link rel="alternate">` declares feed URLs publicly. The `<select name="...">` declares filter parameters. The `<script src="...">` paths declare the CMS family. View source on a phone takes 90 seconds and would prevent most "needs Playwright" misclassifications.

4. **When one parameter works partially, test combinations.** `?year=2025` returning the same 25 items as default doesn't mean it's inert — it might be half of a `?year=Y&month=M` filter that requires the second parameter to actually narrow the result.

5. **Mirror the user-facing UI in parameter probes.** Brute-forcing `?paged`, `?page`, `?p`, `?offset`, `?limit` is wasted effort when the site's HTML form already declares `<select name="restrict_month">` and tells you what parameter names to send.

6. **Sniff test for client-rendered vs server-rendered:** view source — if titles are in the HTML, server-rendered (scrapable). If you see empty `<div id="root">` and content only appears after JS runs, client-rendered (needs Playwright). Disabling JavaScript in the browser is the same test in 5 seconds.

### Files added/modified

- `pipeline/scripts/backfill_wp_rss_paginated.py` (new) — paginated WordPress RSS for the 16 NextJS+GraphQL House members
- `pipeline/scripts/backfill_default_v7_archive.py` (new) — year × month walk for default_v7 theme
- `pipeline/scripts/backfill_smith_christopher.py` (new) — Smith's custom Year=YYYY pagination
- `docs/case-study-rss-rescue.md` (force-added past gitignore) — two-part portfolio writeup of the RSS and year+month unlocks
- `pipeline/seeds/house.json` — coverage_status tags cleared on 25 newly-CLEAN members; collection_method updated to RSS where applicable
- `pipeline/backfill.py` — extended `find_next_page` to walk numeric `/page/N/` pagination beyond page 1→2

### Open backlog

- **meeks-gregory** (D-NY-5) — RSS exists at `/rss.xml` but stopped tracking new content around June 2025. Server-side staleness; only fixable via Playwright collector. The single remaining pure "us" gap.
- **8 listing_horizon members** — guest, stefanik, foushee (now CLEAN), moylan, moore-barry, patronis, fitzgerald, rose, mcgovern, carter. Their CMSes genuinely cap the public archive at 50-200 records starting Feb-Apr 2025. No fix from our side without alternate data sources (Wayback Machine, member newsletters, sitemap fragments).
- **5 verified real-world** (Jordan, Reschenthaler, Menefee, Fuller, Grijalva) — won't move; documented and accurate.

### Numbers worth quoting

- 7 fix waves across the night
- ~50 commits to origin/main
- 25 members moved from "us-blocked" to CLEAN
- 12,635 House records added
- Single Playwright collector still open as v2 work (Meeks only)

The methodology page on the live site reflects all of this. Every gap has a documented reason; every "they don't publish" claim is verified; every "we can't reach this" claim is bounded to one specific member.

---

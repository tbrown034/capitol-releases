# Development Log

A chronological record of development sessions and significant changes.

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

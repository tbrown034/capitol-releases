# Development Log

A chronological record of development sessions and significant changes.

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

# Collector Audit: Senate Pipeline

**Date**: April 18, 2026
**Scope**: All 103 senator records in Postgres. Diagnosis of 18 broken or underperforming collectors.
**Methodology**: Manual inspection of each senator's press page, cross-referenced against config selectors, RSS feeds, and collected record counts in the database. CMS type verified per site. Backfill code reviewed for fallback logic gaps.

---

## Summary

| Metric | Count |
|--------|-------|
| Total senators in DB | 103 |
| Active senators | 100 |
| Former senators (Vance, Rubio, Mullin) | 3 |
| Healthy collectors | 82 |
| Broken or underperforming | 18 |
| Collecting zero releases | 4 |
| Collecting under 15 releases | 7 |
| RSS-limited (partial data only) | 3 |

Four senators return zero releases. Seven more sit well below expected counts. Three are capped by WordPress RSS defaults. One senator (Armstrong) has a genuinely empty page.

---

## Findings by Root Cause

### Group 1: ColdFusion Wrong Selectors (6 senators)

All six use the Senate ColdFusion CMS, which renders press releases in classless HTML tables rather than list items. Config currently specifies `list_item: "li"` but the actual DOM structure requires `"table tr"`.

`backfill.py` contains a `"table tr"` fallback at line 150, but it is not being reached during normal collection runs. The fallback logic needs to be promoted or the explicit selectors need to be corrected.

| Senator | Releases | Pages Available | Notes |
|---------|----------|-----------------|-------|
| Klobuchar | 0 | 406 | Date format M/D/YY. Correct selectors: `list_item: "table tr"`, `title: "td a"`, `date: "td:first-child"`, `detail_link: "td a[href]"` |
| Thune | 0 | 147 | Same ColdFusion table pattern as Klobuchar |
| McConnell | 12 | 1,967 | Detail links use `/pressreleases?ID=` format |
| Fischer | 22 | -- | Has selectors but `.recordListDate` class may not exist in current DOM. Verify. |
| Boozman | 33 (RSS) | 253 | ColdFusion under the hood. RSS provides partial data only. |
| Kennedy | 31 (RSS) | 223 | Same ColdFusion pattern. RSS provides partial data only. |

### Group 2: WordPress / Generic Broken (8 senators)

Mixed CMS platforms. Each failure has a distinct cause.

| Senator | Releases | CMS / Layout | Diagnosis |
|---------|----------|--------------|-----------|
| Cantwell | 0 | ColdFusion + AJAX | Requires Playwright. Already correctly tagged in config. |
| Armstrong | 0 | -- | Page genuinely empty (new senator). No fix needed. Monitor only. |
| Hoeven | 9 | Unique div/h2 layout | Not table-based. Uses `?PageNum_rs=N` pagination. Needs custom selector pattern. |
| Hickenlooper | 10 | WordPress Divi (`et_pb_post`) | Null selectors in config. RSS empty. Needs Divi selectors or Playwright. |
| Kelly | 10 | JetEngine custom listing | `list_item` should be `"article.sen-listing-item-archive-page"`, not `"span.elementor-grid-item"`. Needs Playwright. |
| Kim | 21 | WordPress Divi | Null selectors, RSS empty. Needs Divi selectors or Playwright. |
| Gillibrand | 27 | Divi | Selectors nearly correct. Pagination not followed deep enough. RSS empty. |
| Booker | 13 | Standard | **Wrong URL**: config points to `/news` instead of `/news/press`. Selectors match nav items, not content. Can use httpx -- does not need Playwright. |

### Group 3: RSS-Limited (3 senators)

WordPress default RSS returns only 10 items per feed. These senators have more content available via direct page scraping.

| Senator | Releases | Pattern | Fix |
|---------|----------|---------|-----|
| Moody | 12 | Divi blog, RSS gives 10 items | Switch to httpx or Playwright with Divi selectors |
| Welch | 14 | `article.postItem` pattern already in `backfill.py` | Switch from RSS to httpx |
| Budd | 42 | Divi blog | Wrong RSS URL: `/press-releases/feed/` should be `/category/news/press-releases/feed/`. Switch to httpx. |

---

## Recommended Fix Priority

Ordered by impact, feasibility, and data loss.

| Priority | Senator(s) | Action | Effort | Expected Gain |
|----------|------------|--------|--------|---------------|
| 1 | Booker | Fix URL from `/news` to `/news/press`. Fix selectors. Switch from Playwright to httpx. | Low | Full backfill |
| 2 | Klobuchar, Thune, McConnell, Fischer, Boozman, Kennedy | Verify `table tr` fallback in `backfill.py`. Fix explicit selectors in config to use ColdFusion table pattern. | Medium | 6 senators fully operational; 2,996+ pages available |
| 3 | Welch | Switch from RSS to httpx. Pattern already implemented in `backfill.py`. | Low | Full backfill |
| 4 | Budd | Fix RSS URL. Switch to httpx with Divi selectors. | Low | Full backfill |
| 5 | Gillibrand | Increase pagination depth in config or collector. | Low | Deeper historical data |
| 6 | Kelly | Add `sen-listing-item-archive-page` selector pattern. | Medium | Full backfill |
| 7 | Hoeven | Add custom div/h2 selector pattern for unique layout. | Medium | Full backfill |
| 8 | Hickenlooper, Kim, Moody, Cantwell | Implement Playwright collector or add Divi httpx support. | High | 4 senators operational |

Armstrong requires no fix. Monitor for first posts.

---

## Lessons Learned for House Expansion

These findings apply directly to scaling from 100 senators to 435+ House members.

**ColdFusion detection must include table-based layouts.** The Senate ColdFusion CMS uses classless `<table>` structures, not `<li>` elements. Recon should test both patterns and flag ColdFusion sites explicitly. Assume nothing about DOM structure.

**RSS supplements scraping. It does not replace it.** WordPress default RSS returns 10 items. Three senators were RSS-limited in this audit. House recon should always pair RSS with a verified httpx or Playwright collector as the primary source.

**Recon must verify selectors against actual content, not navigation.** Booker's selectors matched nav items instead of press releases. Automated recon should validate that matched elements contain date strings and article-length text, not menu labels.

**Divi and JetEngine sites will likely need Playwright.** WordPress theme diversity in the House will be higher than the Senate. Budget for Playwright capacity accordingly. Consider a generic Divi collector that handles `et_pb_post` patterns across sites.

**URL verification is not optional.** Booker's `/news` vs `/news/press` discrepancy cost us all his data. Recon should follow links from the senator's homepage rather than guessing URL patterns.

**One broken senator must not hide in 99 healthy ones.** Per-senator health checks caught these 18 failures. The House pipeline must enforce the same per-member granularity from day one, not aggregate health scores.

---

## Appendix: Former Senators in Database

| Senator | Reason | Action |
|---------|--------|--------|
| Vance | Became Vice President | Retain records. No further collection. |
| Rubio | Cabinet appointment | Retain records. No further collection. |
| Mullin | Left Senate | Retain records. No further collection. |

These records remain in the database per the archival permanence principle. They are excluded from active collection and health checks.

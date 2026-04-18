# Capitol Releases: Per-Senator Intelligence Report

Generated: 2026-04-17 22:40 ET

This document captures everything learned about each senator's web presence,
scraping challenges, edge cases, and the recommended collection strategy.
It is the institutional knowledge that makes the scraping pipeline replicable.

---

## Summary

| Metric | Value |
|--------|-------|
| Total senators in config | 100 |
| Senators with data | 98 |
| Collection method: httpx | 68 |
| Collection method: rss | 24 |
| Collection method: playwright | 8 |
| RSS feeds discovered | 52 (with items: 24) |
| RSS feeds reliable | 24 |

## CMS / Parser Families

| Family | Count | Notes |
|--------|-------|-------|
| senate-wordpress | 50 | Most common. Usually has RSS. Selectors: article.et_pb_post, article.postItem, .elementor-post |
| senate-generic | 43 | Senate legacy CMS. Selectors: div.element, .ArticleBlock. Some JS-rendered. |
| senate-coldfusion | 6 | /public/index.cfm/ URLs. Table layout. Dates only on listing page, not detail. |
| senate-drupal | 1 | Rare. |

## Known Edge Cases and Lessons Learned

### 1. JS-Rendered Sites (8 senators)
These load press releases via AJAX. Static HTTP gets an empty js-content div.
Need Playwright or RSS as collection method.

| Senator | Why | Fix |
|---------|-----|-----|
| Reed (D-RI) | senate-generic, empty js-content | Playwright or RSS |
| Capito (R-WV) | senate-generic, empty js-content | Playwright |
| Cotton (R-AR) | senate-generic, empty js-content | Playwright |
| Markey (D-MA) | senate-generic, empty js-content | Playwright |
| Schmitt (R-MO) | JetEngine AJAX pagination | Playwright (has RSS but 0 items) |
| Whitehouse (D-RI) | JetEngine AJAX pagination | Has RSS feed |
| Young (R-IN) | JetEngine AJAX pagination | Has RSS feed |
| Booker (D-NJ) | senate-generic, JS-rendered | Playwright |
| Ossoff (D-GA) | Elementor AJAX pagination | Has RSS feed (10 items) |
| Merkley (D-OR) | WordPress, JS pagination | Has RSS feed |

### 2. ColdFusion Date Problem
ColdFusion senators (Graham, Klobuchar, McConnell, Kennedy, Moran, Boozman, Thune, Fischer)
have dates on the listing page in td.recordListDate (e.g., '4/7/26') but NOT on detail pages.
No meta tags, no JSON-LD, no time elements on detail pages.

**Lesson:** Must extract dates during listing-page scrape and pass them to the insert,
not rely on detail-page extraction. The current pipeline extracts dates from listing items
in extract_item_data(), which handles this correctly for new scrapes.

### 3. Meta Tag Variations
We initially only searched for article:published_time and datePublished.
King's 899 null dates were fixed by adding meta name='date' to the search.

Tags found in the wild:
- article:published_time (OpenGraph standard)
- og:article:published_time
- datePublished (Schema.org)
- date (simple, used by King and others)
- DC.date.issued (Dublin Core)
- pubdate

### 4. Body Text Extraction Failures
WordPress Divi sites (Hickenlooper, Kim, Moody) render body text via JS.
The .post-content selector finds an element but it only has ~20 chars.
The actual content is in the DOM but needs JS rendering.

**Fix used:** Aggressive paragraph extraction -- collect all p tags with >20 chars
and join them. Also tried heading-based isolation: find h1, take all text after it.
Both work for getting content from partially-rendered pages.

### 5. Nav Link Contamination
The selector logic sometimes picks up navigation links instead of press releases.
Common junk patterns:
- /about, /contact, /services, /issues/*
- Committee assignments, flag requests, tour requests
- Social media links (twitter, facebook, bsky)
- Photo galleries, weekly columns, audio statements
- Listing page URLs ending in /press-releases/ (no slug)

**Prevention:** test_no_navigation_urls and test_no_listing_page_urls catch these.
~211 junk records cleaned in the April 17 session.

### 6. RSS Feed Gotchas
- WordPress comment feeds at /press-releases/feed/ return valid RSS with 0 items (Gillibrand)
- wp-json/oembed endpoints look like XML but are not RSS feeds (Cassidy, Risch, Schiff, Warner)
- Broad feeds (/feed/) include all post types, not just press releases
- Warren's /rss/ returns 50 items including videos -- needs content classification
- 14 of 52 discovered feeds were false positives, leaving 38 reliable
- After health check, 14 more demoted (0 items), leaving 24 as primary collection method

### 7. Date at Character 720+
ColdFusion sites have ~700 characters of navigation text before the first date.
Our body-text date search initially only looked at the first 500 characters.
Expanding to 1000 characters fixed Graham and similar senators.

### 8. URL Path Inconsistencies
- Some senators use /press-releases/, others /press_releases/ (underscore)
- Bennet's seed URL pointed to a 2014 UUID path, not the listing page
- Welch's seed URL pointed to /press-kit/ (contact info), not /category/press-release/
- ColdFusion URLs use GUIDs: /press-releases?ID=70C386B4-7762-45E6-968D-C40EFAFD993B

### 9. Pagination Patterns (6 types found)
1. rel='next' link (standard, most reliable)
2. Text-based ('Next >', 'Older Entries', '>>')
3. WordPress path-segment (/page/2/, /page/3/)
4. Query parameter (?page=2, ?pagenum_rs=2)
5. Elementor custom (?e-page-f7b8172=2)
6. AJAX/JS click-based (JetEngine -- requires Playwright)

### 10. Armstrong Exception
Alan Armstrong (R-OK) is a new senator. His press releases page exists
(WordPress archive page with heading) but div.page-content is completely empty.
No releases published yet. Monitor and collect once content appears.

---

## Ideas for Ongoing Collection Per Senator

### RSS senators (24) -- lowest maintenance
Parse the feed, fetch detail pages for body text. No selector maintenance.
Run health check weekly to verify feed still has items.
If feed breaks, fall back to httpx collector.

### httpx senators (68) -- moderate maintenance
Selector-based scraping. Robust across 8+ CMS patterns.
Weekly drift detection: verify selector still finds items on listing page.
If selector breaks, use AI to propose new selectors from page structure.
ColdFusion senators: always extract dates from listing page, not detail.

### Playwright senators (8) -- highest maintenance
JS-rendered sites need headless browser. Slower, more resource-intensive.
Check if RSS feed becomes available (some may add it later).
For daily updates, page 1 only (minimize browser time).
For backfill, click through AJAX pagination.

### AI-assisted quality layer (all senators)
Post-collection Claude Haiku validation:
- Is this a real press release or nav boilerplate?
- Is the date plausible?
- Is the content type classification correct?
- Does the body text look like actual content?
Advisory only. Flag for review, never auto-modify.

---

## Per-Senator Detail

### Dan Sullivan (R-AK)

- **ID:** sullivan-dan
- **URL:** https://www.sullivan.senate.gov/newsroom/press-releases
- **Parser family:** senate-generic
- **Collection method:** httpx
- **Confidence:** 90%
- **Requires JS:** False
- **Records:** 163 active, 5 deleted
- **Dated:** 100% | **Body text:** 100%
- **Date range:** 2025-01-08 to 2026-04-16
- **Date provenance:** 1 records
- **Notes:** Found 20 items on listing page. 

### Lisa Murkowski (R-AK)

- **ID:** murkowski-lisa
- **URL:** https://www.murkowski.senate.gov/press/press-releases
- **Parser family:** senate-generic
- **Collection method:** httpx
- **Confidence:** 90%
- **Requires JS:** False
- **Records:** 178 active, 0 deleted
- **Dated:** 100% | **Body text:** 100%
- **Date range:** 2024-12-31 to 2026-04-16
- **Date provenance:** 1 records
- **Notes:** Found 20 items on listing page. 

### Katie Boyd Britt (R-AL)

- **ID:** britt-katie
- **URL:** https://www.britt.senate.gov/media/press-releases/
- **Parser family:** senate-wordpress
- **Collection method:** httpx
- **Confidence:** 55%
- **Requires JS:** False
- **RSS feed:** https://www.britt.senate.gov/media/press-releases/feed/
- **Records:** 7 active, 0 deleted
- **Dated:** 100% | **Body text:** 100%
- **Date range:** 2026-04-08 to 2026-04-16
- **Date provenance:** 1 records
- **Health check:** FAIL (HTTP 200, 0 items, 333ms)
- **Notes:** Found 8 items on listing page. 

### Tommy Tuberville (R-AL)

- **ID:** tuberville-tommy
- **URL:** https://www.tuberville.senate.gov/newsroom/press-releases/
- **Parser family:** senate-wordpress
- **Collection method:** httpx
- **Confidence:** 60%
- **Requires JS:** False
- **Records:** 11 active, 0 deleted
- **Dated:** 100% | **Body text:** 100%
- **Date range:** 2026-03-24 to 2026-04-16
- **Notes:** Found 10 items on listing page. 

### John Boozman (R-AR)

- **ID:** boozman-john
- **URL:** https://www.boozman.senate.gov/press-releases
- **Parser family:** senate-coldfusion
- **Collection method:** rss
- **Confidence:** 55%
- **Requires JS:** False
- **RSS feed:** https://www.boozman.senate.gov/public/?a=RSS.Feed
- **Records:** 23 active, 28 deleted
- **Dated:** 100% | **Body text:** 100%
- **Date range:** 2023-03-10 to 2026-04-16
- **Date provenance:** 23 records
- **Health check:** PASS (HTTP 200, 20 items, 330ms)
- **Notes:** Found 306 items on listing page. 

### Tom Cotton (R-AR)

- **ID:** cotton-tom
- **URL:** https://www.cotton.senate.gov/news/press-releases
- **Parser family:** senate-generic
- **Collection method:** playwright
- **Confidence:** 60%
- **Requires JS:** True
- **Records:** 162 active, 0 deleted
- **Dated:** 100% | **Body text:** 100%
- **Date range:** 2025-01-02 to 2026-04-16
- **Date provenance:** 2 records
- **Notes:** JS-rendered. div.js-content empty. Same pattern as Reed. Needs Playwright. Verified 2026-04-17.

### Mark Kelly (D-AZ)

- **ID:** kelly-mark
- **URL:** https://www.kelly.senate.gov/newsroom/press-releases/
- **Parser family:** senate-wordpress
- **Collection method:** httpx
- **Confidence:** 60%
- **Requires JS:** False
- **Records:** 6 active, 0 deleted
- **Dated:** 100% | **Body text:** 100%
- **Date range:** 2026-04-10 to 2026-04-15
- **Notes:** Found 5 items on listing page. 

### Ruben Gallego (D-AZ)

- **ID:** gallego-ruben
- **URL:** https://www.gallego.senate.gov/news/press-releases/
- **Parser family:** senate-wordpress
- **Collection method:** httpx
- **Confidence:** 45%
- **Requires JS:** False
- **Records:** 470 active, 0 deleted
- **Dated:** 100% | **Body text:** 100%
- **Date range:** 2025-03-01 to 2026-04-15

### Adam B. Schiff (D-CA)

- **ID:** schiff-adam
- **URL:** https://www.schiff.senate.gov/newsroom/press-releases/
- **Parser family:** senate-wordpress
- **Collection method:** httpx
- **Confidence:** 70%
- **Requires JS:** False
- **Records:** 503 active, 1 deleted
- **Dated:** 100% | **Body text:** 100%
- **Date range:** 2025-03-27 to 2026-04-16
- **Date provenance:** 4 records
- **Notes:** Found 5 items on listing page. 

### Alex Padilla (D-CA)

- **ID:** padilla-alex
- **URL:** https://www.padilla.senate.gov/newsroom/press-releases/
- **Parser family:** senate-wordpress
- **Collection method:** rss
- **Confidence:** 60%
- **Requires JS:** False
- **RSS feed:** https://www.padilla.senate.gov/feed/
- **Records:** 6 active, 0 deleted
- **Dated:** 100% | **Body text:** 100%
- **Date range:** 2026-04-08 to 2026-04-15
- **Health check:** PASS (HTTP 200, 6 items, 253ms)
- **Notes:** Found 9 items on listing page. 

### John W. Hickenlooper (D-CO)

- **ID:** hickenlooper-john
- **URL:** https://www.hickenlooper.senate.gov/press/
- **Parser family:** senate-generic
- **Collection method:** httpx
- **Confidence:** 90%
- **Requires JS:** False
- **RSS feed:** https://www.hickenlooper.senate.gov/press/feed/
- **Records:** 10 active, 0 deleted
- **Dated:** 100% | **Body text:** 100%
- **Date range:** 2026-03-24 to 2026-04-15
- **Health check:** FAIL (HTTP 200, 0 items, 876ms)
- **Notes:** WordPress Divi (et_pb_post). 5/page. Older Entries pagination. Verified 2026-04-17.

### Michael F. Bennet (D-CO)

- **ID:** bennet-michael
- **URL:** https://www.bennet.senate.gov/news/
- **Parser family:** senate-wordpress
- **Collection method:** rss
- **Confidence:** 90%
- **Requires JS:** False
- **RSS feed:** https://www.bennet.senate.gov/news/feed/
- **Records:** 371 active, 0 deleted
- **Dated:** 100% | **Body text:** 100%
- **Date range:** 2025-01-06 to 2026-04-16
- **Health check:** PASS (HTTP 200, 10 items, 343ms)
- **Notes:** WordPress Divi (et_pb_post). Old URL was wrong UUID path. Dates "Apr 16, 2026". Verified 2026-04-17.

### Christopher Murphy (D-CT)

- **ID:** murphy-christopher
- **URL:** https://www.murphy.senate.gov/newsroom/press-releases
- **Parser family:** senate-generic
- **Collection method:** httpx
- **Confidence:** 95%
- **Requires JS:** False
- **Records:** 313 active, 0 deleted
- **Dated:** 100% | **Body text:** 100%
- **Date range:** 2025-01-03 to 2026-04-15
- **Notes:** Found 20 items on listing page. 

### Richard Blumenthal (D-CT)

- **ID:** blumenthal-richard
- **URL:** https://www.blumenthal.senate.gov/newsroom/press
- **Parser family:** senate-generic
- **Collection method:** httpx
- **Confidence:** 85%
- **Requires JS:** False
- **Records:** 652 active, 1 deleted
- **Dated:** 100% | **Body text:** 100%
- **Date range:** 2025-01-05 to 2026-04-15
- **Notes:** Found 20 items on listing page. 

### Christopher A. Coons (D-DE)

- **ID:** coons-christopher
- **URL:** https://www.coons.senate.gov/news/press-releases/
- **Parser family:** senate-wordpress
- **Collection method:** httpx
- **Confidence:** 95%
- **Requires JS:** False
- **Records:** 312 active, 1 deleted
- **Dated:** 100% | **Body text:** 100%
- **Date range:** 2025-01-03 to 2026-04-16
- **Notes:** Found 5 items on listing page. 

### Lisa Blunt Rochester (D-DE)

- **ID:** rochester-lisa
- **URL:** https://www.bluntrochester.senate.gov/news/press-releases/
- **Parser family:** senate-wordpress
- **Collection method:** rss
- **Confidence:** 60%
- **Requires JS:** False
- **RSS feed:** https://www.bluntrochester.senate.gov/feed/
- **Records:** 290 active, 4 deleted
- **Dated:** 100% | **Body text:** 100%
- **Date range:** 2025-01-15 to 2026-04-07
- **Health check:** PASS (HTTP 200, 1 items, 337ms)
- **Notes:** Found 4 items on listing page. 

### Ashley Moody (R-FL)

- **ID:** moody-ashley
- **URL:** https://www.moody.senate.gov/press-releases/
- **Parser family:** senate-wordpress
- **Collection method:** rss
- **Confidence:** 90%
- **Requires JS:** False
- **RSS feed:** https://www.moody.senate.gov/press-releases/feed/
- **Records:** 11 active, 0 deleted
- **Dated:** 100% | **Body text:** 100%
- **Date range:** 2026-04-02 to 2026-04-16
- **Date provenance:** 1 records
- **Health check:** PASS (HTTP 200, 10 items, 935ms)
- **Notes:** WordPress Divi (et_pb_post). 5/page. Older Entries pagination. Verified 2026-04-17.

### Rick Scott (R-FL)

- **ID:** scott-rick
- **URL:** https://www.rickscott.senate.gov/press-releases
- **Parser family:** senate-generic
- **Collection method:** httpx
- **Confidence:** 65%
- **Requires JS:** False
- **Records:** 398 active, 0 deleted
- **Dated:** 100% | **Body text:** 100%
- **Date range:** 2025-01-01 to 2026-04-01
- **Notes:** Found 13 items on listing page. 

### Jon Ossoff (D-GA)

- **ID:** ossoff-jon
- **URL:** https://www.ossoff.senate.gov/press-releases/
- **Parser family:** senate-wordpress
- **Collection method:** rss
- **Confidence:** 85%
- **Requires JS:** True
- **RSS feed:** https://www.ossoff.senate.gov/press-releases/feed/
- **Records:** 394 active, 0 deleted
- **Dated:** 100% | **Body text:** 100%
- **Date range:** 2025-01-01 to 2026-04-17
- **Date provenance:** 6 records
- **Health check:** PASS (HTTP 200, 10 items, 366ms)
- **Notes:** Elementor WordPress (.elementor-post). Dates via span.elementor-post-date. AJAX pagination (data-i attrs). Needs Playwright for pagination. Verified 2026-04-17.

### Raphael G. Warnock (D-GA)

- **ID:** warnock-raphael
- **URL:** https://www.warnock.senate.gov/newsroom/press-releases/
- **Parser family:** senate-wordpress
- **Collection method:** rss
- **Confidence:** 60%
- **Requires JS:** False
- **RSS feed:** https://www.warnock.senate.gov/feed/
- **Records:** 6 active, 0 deleted
- **Dated:** 100% | **Body text:** 100%
- **Date range:** 2026-03-31 to 2026-04-14
- **Health check:** PASS (HTTP 200, 4 items, 998ms)
- **Notes:** Found 15 items on listing page. 

### Brian Schatz (D-HI)

- **ID:** schatz-brian
- **URL:** https://www.schatz.senate.gov/news/press-releases
- **Parser family:** senate-generic
- **Collection method:** httpx
- **Confidence:** 80%
- **Requires JS:** False
- **Records:** 218 active, 0 deleted
- **Dated:** 100% | **Body text:** 100%
- **Date range:** 2025-01-15 to 2026-04-07
- **Notes:** Found 20 items on listing page. 

### Mazie K. Hirono (D-HI)

- **ID:** hirono-mazie
- **URL:** https://www.hirono.senate.gov/news/press-releases
- **Parser family:** senate-generic
- **Collection method:** httpx
- **Confidence:** 85%
- **Requires JS:** False
- **Records:** 343 active, 0 deleted
- **Dated:** 100% | **Body text:** 100%
- **Date range:** 2025-01-03 to 2026-04-16
- **Date provenance:** 1 records
- **Notes:** Found 20 items on listing page. 

### Chuck Grassley (R-IA)

- **ID:** grassley-chuck
- **URL:** https://www.grassley.senate.gov/404?notfound=/newsroom/press-releases
- **Parser family:** senate-generic
- **Collection method:** httpx
- **Confidence:** 85%
- **Requires JS:** False
- **Records:** 625 active, 1 deleted
- **Dated:** 100% | **Body text:** 100%
- **Date range:** 2025-01-03 to 2026-04-15
- **Notes:** Found 33 items on listing page. 

### Joni Ernst (R-IA)

- **ID:** ernst-joni
- **URL:** https://www.ernst.senate.gov/news/press-releases
- **Parser family:** senate-generic
- **Collection method:** httpx
- **Confidence:** 85%
- **Requires JS:** False
- **Records:** 405 active, 1 deleted
- **Dated:** 100% | **Body text:** 100%
- **Date range:** 2025-01-03 to 2026-04-17
- **Date provenance:** 2 records
- **Notes:** Found 20 items on listing page. 

### James E. Risch (R-ID)

- **ID:** risch-james
- **URL:** https://www.risch.senate.gov/newsroom/press-releases/
- **Parser family:** senate-wordpress
- **Collection method:** httpx
- **Confidence:** 70%
- **Requires JS:** False
- **Records:** 50 active, 0 deleted
- **Dated:** 100% | **Body text:** 100%
- **Date range:** 2025-07-28 to 2026-04-17
- **Date provenance:** 2 records
- **Notes:** Found 8 items on listing page. 

### Mike Crapo (R-ID)

- **ID:** crapo-mike
- **URL:** https://www.crapo.senate.gov/media
- **Parser family:** senate-generic
- **Collection method:** httpx
- **Confidence:** 85%
- **Requires JS:** False
- **Records:** 6 active, 5 deleted
- **Dated:** 100% | **Body text:** 100%
- **Date range:** 2026-04-09 to 2026-04-16
- **Date provenance:** 3 records
- **Notes:** Found 24 items on listing page. 

### Richard J. Durbin (D-IL)

- **ID:** durbin-richard
- **URL:** https://www.durbin.senate.gov/newsroom/press-releases
- **Parser family:** senate-generic
- **Collection method:** httpx
- **Confidence:** 95%
- **Requires JS:** False
- **Records:** 1005 active, 0 deleted
- **Dated:** 100% | **Body text:** 100%
- **Date range:** 2025-02-05 to 2026-04-17
- **Date provenance:** 11 records
- **Notes:** Found 20 items on listing page. 

### Tammy Duckworth (D-IL)

- **ID:** duckworth-tammy
- **URL:** https://www.duckworth.senate.gov/news/press-releases
- **Parser family:** senate-generic
- **Collection method:** httpx
- **Confidence:** 95%
- **Requires JS:** False
- **Records:** 579 active, 0 deleted
- **Dated:** 100% | **Body text:** 100%
- **Date range:** 2025-01-02 to 2026-04-17
- **Date provenance:** 2 records
- **Notes:** Found 20 items on listing page. 

### Jim Banks (R-IN)

- **ID:** banks-jim
- **URL:** https://www.banks.senate.gov/news/press-releases/
- **Parser family:** senate-wordpress
- **Collection method:** rss
- **Confidence:** 60%
- **Requires JS:** False
- **RSS feed:** https://www.banks.senate.gov/feed/
- **Records:** 204 active, 1 deleted
- **Dated:** 100% | **Body text:** 100%
- **Date range:** 2025-01-04 to 2026-04-13
- **Health check:** PASS (HTTP 200, 1 items, 1322ms)
- **Notes:** Found 4 items on listing page. 

### Todd Young (R-IN)

- **ID:** young-todd
- **URL:** https://www.young.senate.gov/newsroom/press-releases/
- **Parser family:** senate-wordpress
- **Collection method:** rss
- **Confidence:** 60%
- **Requires JS:** True
- **RSS feed:** https://www.young.senate.gov/feed/
- **Records:** 271 active, 0 deleted
- **Dated:** 100% | **Body text:** 100%
- **Date range:** 2025-01-07 to 2026-04-15
- **Health check:** PASS (HTTP 200, 1 items, 179ms)
- **Notes:** Found 5 items on listing page. 

### Jerry Moran (R-KS)

- **ID:** moran-jerry
- **URL:** https://www.moran.senate.gov/public/index.cfm/news-releases
- **Parser family:** senate-generic
- **Collection method:** rss
- **Confidence:** 55%
- **Requires JS:** False
- **RSS feed:** https://www.moran.senate.gov/public/?a=RSS.Feed
- **Records:** 53 active, 25 deleted
- **Dated:** 100% | **Body text:** 98%
- **Date range:** 2013-09-25 to 2026-04-16
- **Date provenance:** 29 records
- **Health check:** PASS (HTTP 200, 20 items, 112ms)
- **Notes:** Found 323 items on listing page. 

### Roger Marshall (R-KS)

- **ID:** marshall-roger
- **URL:** https://www.marshall.senate.gov/newsroom/press-releases/
- **Parser family:** senate-wordpress
- **Collection method:** rss
- **Confidence:** 60%
- **Requires JS:** False
- **RSS feed:** https://www.marshall.senate.gov/feed/
- **Records:** 6 active, 0 deleted
- **Dated:** 100% | **Body text:** 100%
- **Date range:** 2026-04-13 to 2026-04-15
- **Health check:** PASS (HTTP 200, 5 items, 185ms)
- **Notes:** Found 13 items on listing page. 

### Mitch McConnell (R-KY)

- **ID:** mcconnell-mitch
- **URL:** https://www.mcconnell.senate.gov/public/index.cfm/pressreleases
- **Parser family:** senate-coldfusion
- **Collection method:** httpx
- **Confidence:** 55%
- **Requires JS:** False
- **Records:** 3 active, 18 deleted
- **Dated:** 100% | **Body text:** 0%
- **Date range:** 2025-11-10 to 2026-04-13
- **Date provenance:** 3 records
- **Notes:** Found 278 items on listing page. 

### Rand Paul (R-KY)

- **ID:** paul-rand
- **URL:** https://www.paul.senate.gov/news/
- **Parser family:** senate-generic
- **Collection method:** httpx
- **Confidence:** 100%
- **Requires JS:** False
- **Records:** 77 active, 1 deleted
- **Dated:** 100% | **Body text:** 100%
- **Date range:** 2025-01-03 to 2026-02-24
- **Notes:** Found 20 items on listing page. 

### Bill Cassidy (R-LA)

- **ID:** cassidy-bill
- **URL:** https://www.cassidy.senate.gov/newsroom/press-releases/
- **Parser family:** senate-wordpress
- **Collection method:** httpx
- **Confidence:** 55%
- **Requires JS:** False
- **Records:** 14 active, 0 deleted
- **Dated:** 100% | **Body text:** 100%
- **Date range:** 2026-03-30 to 2026-04-16
- **Date provenance:** 2 records
- **Notes:** Found 8 items on listing page. 

### John Kennedy (R-LA)

- **ID:** kennedy-john
- **URL:** https://www.kennedy.senate.gov/public/index.cfm/press-releases
- **Parser family:** senate-generic
- **Collection method:** rss
- **Confidence:** 55%
- **Requires JS:** False
- **RSS feed:** https://www.kennedy.senate.gov/public/?a=RSS.Feed
- **Records:** 20 active, 18 deleted
- **Dated:** 100% | **Body text:** 100%
- **Date range:** 2026-03-11 to 2026-04-16
- **Date provenance:** 20 records
- **Health check:** PASS (HTTP 200, 20 items, 375ms)
- **Notes:** Found 266 items on listing page. 

### Edward J. Markey (D-MA)

- **ID:** markey-edward
- **URL:** https://www.markey.senate.gov/news/press-releases
- **Parser family:** senate-generic
- **Collection method:** playwright
- **Confidence:** 60%
- **Requires JS:** True
- **Records:** 573 active, 0 deleted
- **Dated:** 100% | **Body text:** 100%
- **Date range:** 2025-01-02 to 2026-04-16
- **Date provenance:** 3 records
- **Notes:** JS-rendered. div.js-content empty. Needs Playwright. Verified 2026-04-17.

### Elizabeth Warren (D-MA)

- **ID:** warren-elizabeth
- **URL:** https://www.warren.senate.gov/newsroom/press-releases
- **Parser family:** senate-generic
- **Collection method:** rss
- **Confidence:** 95%
- **Requires JS:** False
- **RSS feed:** https://www.warren.senate.gov/rss/
- **Records:** 655 active, 0 deleted
- **Dated:** 100% | **Body text:** 100%
- **Date range:** 2025-01-07 to 2026-04-17
- **Date provenance:** 17 records
- **Health check:** PASS (HTTP 200, 50 items, 93ms)
- **Notes:** Found 20 items on listing page. 

### Angela D. Alsobrooks (D-MD)

- **ID:** alsobrooks-angela
- **URL:** https://www.alsobrooks.senate.gov/newsroom/press-releases/
- **Parser family:** senate-wordpress
- **Collection method:** rss
- **Confidence:** 85%
- **Requires JS:** False
- **RSS feed:** https://www.alsobrooks.senate.gov/feed/
- **Records:** 219 active, 0 deleted
- **Dated:** 100% | **Body text:** 100%
- **Date range:** 2025-01-16 to 2026-04-15
- **Health check:** PASS (HTTP 200, 1 items, 415ms)
- **Notes:** Elementor WordPress. 10/page, 23 pages. Pagination: ?e-page-f7b8172=N. Dates in text. Verified 2026-04-17.

### Chris Van Hollen (D-MD)

- **ID:** hollen-chris
- **URL:** https://www.vanhollen.senate.gov/news/press-releases
- **Parser family:** senate-generic
- **Collection method:** httpx
- **Confidence:** 80%
- **Requires JS:** False
- **Records:** 440 active, 0 deleted
- **Dated:** 100% | **Body text:** 100%
- **Date range:** 2025-01-06 to 2026-04-16
- **Date provenance:** 1 records
- **Notes:** Found 20 items on listing page. 

### Angus S. King, Jr. (I-ME)

- **ID:** king-angus
- **URL:** https://www.king.senate.gov/newsroom/press-releases
- **Parser family:** senate-generic
- **Collection method:** httpx
- **Confidence:** 85%
- **Requires JS:** False
- **Records:** 898 active, 1 deleted
- **Dated:** 100% | **Body text:** 100%
- **Date range:** 2013-01-31 to 2026-04-17
- **Date provenance:** 898 records
- **Notes:** Found 20 items on listing page. 

### Susan M. Collins (R-ME)

- **ID:** collins-susan
- **URL:** https://www.collins.senate.gov/newsroom/press-releases
- **Parser family:** senate-generic
- **Collection method:** httpx
- **Confidence:** 85%
- **Requires JS:** False
- **Records:** 407 active, 1 deleted
- **Dated:** 100% | **Body text:** 100%
- **Date range:** 2025-01-02 to 2026-04-17
- **Date provenance:** 6 records
- **Notes:** Found 20 items on listing page. 

### Elissa Slotkin (D-MI)

- **ID:** slotkin-elissa
- **URL:** https://www.slotkin.senate.gov/newsroom/
- **Parser family:** senate-wordpress
- **Collection method:** rss
- **Confidence:** 100%
- **Requires JS:** False
- **RSS feed:** https://www.slotkin.senate.gov/newsroom/feed/
- **Records:** 199 active, 0 deleted
- **Dated:** 100% | **Body text:** 100%
- **Date range:** 2025-01-08 to 2026-04-15
- **Health check:** PASS (HTTP 200, 10 items, 218ms)
- **Notes:** Found 10 items on listing page. 

### Gary C. Peters (D-MI)

- **ID:** peters-gary
- **URL:** https://www.peters.senate.gov/newsroom/press-releases
- **Parser family:** senate-generic
- **Collection method:** httpx
- **Confidence:** 80%
- **Requires JS:** False
- **Records:** 279 active, 3 deleted
- **Dated:** 100% | **Body text:** 100%
- **Date range:** 2025-01-06 to 2026-04-17
- **Date provenance:** 1 records
- **Notes:** Found 20 items on listing page. 

### Amy Klobuchar (D-MN)

- **ID:** klobuchar-amy
- **URL:** https://www.klobuchar.senate.gov/public/index.cfm/news-releases
- **Parser family:** senate-coldfusion
- **Collection method:** httpx
- **Confidence:** 55%
- **Requires JS:** False
- **Records:** 0 active, 32 deleted
- **Dated:** n/a | **Body text:** n/a
- **Date range:** none to none
- **Notes:** Found 452 items on listing page. 

### Tina Smith (D-MN)

- **ID:** smith-tina
- **URL:** https://www.smith.senate.gov/press-releases/
- **Parser family:** senate-wordpress
- **Collection method:** httpx
- **Confidence:** 100%
- **Requires JS:** False
- **RSS feed:** https://www.smith.senate.gov/press-releases/feed/
- **Records:** 113 active, 0 deleted
- **Dated:** 100% | **Body text:** 100%
- **Date range:** 2025-01-07 to 2026-04-07
- **Health check:** FAIL (HTTP 200, 0 items, 217ms)
- **Notes:** Found 6 items on listing page. 

### Eric Schmitt (R-MO)

- **ID:** schmitt-eric
- **URL:** https://www.schmitt.senate.gov/media/press-releases/
- **Parser family:** senate-wordpress
- **Collection method:** playwright
- **Confidence:** 60%
- **Requires JS:** True
- **Records:** 124 active, 0 deleted
- **Dated:** 100% | **Body text:** 100%
- **Date range:** 2025-05-16 to 2026-04-17
- **Date provenance:** 99 records
- **Notes:** Found 4 items on listing page. 

### Josh Hawley (R-MO)

- **ID:** hawley-josh
- **URL:** https://www.hawley.senate.gov/press-releases/
- **Parser family:** senate-wordpress
- **Collection method:** httpx
- **Confidence:** 100%
- **Requires JS:** False
- **RSS feed:** https://www.hawley.senate.gov/press-releases/feed/
- **Records:** 215 active, 0 deleted
- **Dated:** 100% | **Body text:** 100%
- **Date range:** 2025-01-01 to 2026-04-16
- **Date provenance:** 1 records
- **Health check:** FAIL (HTTP 200, 0 items, 865ms)
- **Notes:** Found 10 items on listing page. 

### Cindy Hyde-Smith (R-MS)

- **ID:** hydesmith-cindy
- **URL:** https://www.hydesmith.senate.gov/newsroom
- **Parser family:** senate-drupal
- **Collection method:** httpx
- **Confidence:** 100%
- **Requires JS:** False
- **Records:** 41 active, 0 deleted
- **Dated:** 100% | **Body text:** 100%
- **Date range:** 2025-01-16 to 2026-04-16
- **Notes:** Found 15 items on listing page. 

### Roger F. Wicker (R-MS)

- **ID:** wicker-roger
- **URL:** https://www.wicker.senate.gov/press-releases
- **Parser family:** senate-generic
- **Collection method:** httpx
- **Confidence:** 65%
- **Requires JS:** False
- **Records:** 170 active, 0 deleted
- **Dated:** 100% | **Body text:** 100%
- **Date range:** 2025-01-02 to 2026-04-08
- **Notes:** Found 13 items on listing page. 

### Steve Daines (R-MT)

- **ID:** daines-steve
- **URL:** https://www.daines.senate.gov/news/press-releases/
- **Parser family:** senate-wordpress
- **Collection method:** httpx
- **Confidence:** 100%
- **Requires JS:** False
- **Records:** 320 active, 4 deleted
- **Dated:** 100% | **Body text:** 100%
- **Date range:** 2025-01-03 to 2026-04-17
- **Date provenance:** 3 records
- **Notes:** Found 9 items on listing page. 

### Tim Sheehy (R-MT)

- **ID:** sheehy-tim
- **URL:** https://www.sheehy.senate.gov/newsroom/press-releases/
- **Parser family:** senate-wordpress
- **Collection method:** httpx
- **Confidence:** 60%
- **Requires JS:** False
- **Records:** 77 active, 0 deleted
- **Dated:** 100% | **Body text:** 100%
- **Date range:** 2025-01-07 to 2026-04-16
- **Date provenance:** 1 records
- **Notes:** Found 8 items on listing page. 

### Ted Budd (R-NC)

- **ID:** budd-ted
- **URL:** https://www.budd.senate.gov/press-releases/
- **Parser family:** senate-wordpress
- **Collection method:** rss
- **Confidence:** 90%
- **Requires JS:** False
- **RSS feed:** https://www.budd.senate.gov/press-releases/feed/
- **Records:** 2 active, 0 deleted
- **Dated:** 100% | **Body text:** 100%
- **Date range:** 2025-05-29 to 2025-06-17
- **Health check:** PASS (HTTP 200, 10 items, 328ms)
- **Notes:** WordPress Divi (article). 18/page. Dates "Jun 17, 2025". Older Entries pagination /page/N/. Verified 2026-04-17.

### Thom Tillis (R-NC)

- **ID:** tillis-thom
- **URL:** https://www.tillis.senate.gov/press-releases
- **Parser family:** senate-generic
- **Collection method:** httpx
- **Confidence:** 90%
- **Requires JS:** False
- **Records:** 100 active, 21 deleted
- **Dated:** 100% | **Body text:** 100%
- **Date range:** 2025-01-01 to 2026-03-01
- **Notes:** Found 33 items on listing page. 

### John Hoeven (R-ND)

- **ID:** hoeven-john
- **URL:** https://www.hoeven.senate.gov/news
- **Parser family:** senate-generic
- **Collection method:** httpx
- **Confidence:** 80%
- **Requires JS:** False
- **Records:** 1 active, 29 deleted
- **Dated:** 100% | **Body text:** 100%
- **Date range:** 2026-04-15 to 2026-04-15
- **Notes:** Found 105 items on listing page. 

### Kevin Cramer (R-ND)

- **ID:** cramer-kevin
- **URL:** https://www.cramer.senate.gov/news/press-releases
- **Parser family:** senate-generic
- **Collection method:** httpx
- **Confidence:** 85%
- **Requires JS:** False
- **Records:** 298 active, 0 deleted
- **Dated:** 100% | **Body text:** 100%
- **Date range:** 2025-01-03 to 2026-04-16
- **Date provenance:** 1 records
- **Notes:** Found 20 items on listing page. 

### Deb Fischer (R-NE)

- **ID:** fischer-deb
- **URL:** https://www.fischer.senate.gov/public/index.cfm/press-releases
- **Parser family:** senate-coldfusion
- **Collection method:** httpx
- **Confidence:** 100%
- **Requires JS:** False
- **Records:** 22 active, 0 deleted
- **Dated:** 100% | **Body text:** 100%
- **Date range:** 2026-02-10 to 2026-04-16
- **Date provenance:** 2 records
- **Notes:** Found 12 items on listing page. 

### Pete Ricketts (R-NE)

- **ID:** ricketts-pete
- **URL:** https://www.ricketts.senate.gov/newsroom/press-releases/
- **Parser family:** senate-wordpress
- **Collection method:** httpx
- **Confidence:** 55%
- **Requires JS:** False
- **RSS feed:** https://www.ricketts.senate.gov/newsroom/press-releases/feed/
- **Records:** 10 active, 0 deleted
- **Dated:** 100% | **Body text:** 100%
- **Date range:** 2026-03-24 to 2026-04-16
- **Date provenance:** 2 records
- **Health check:** FAIL (HTTP 200, 0 items, 236ms)
- **Notes:** Found 8 items on listing page. 

### Jeanne Shaheen (D-NH)

- **ID:** shaheen-jeanne
- **URL:** https://www.shaheen.senate.gov/news
- **Parser family:** senate-generic
- **Collection method:** httpx
- **Confidence:** 90%
- **Requires JS:** False
- **Records:** 6 active, 3 deleted
- **Dated:** 100% | **Body text:** 100%
- **Date range:** 2026-04-07 to 2026-04-17
- **Date provenance:** 3 records
- **Notes:** Found 6 items on listing page. 

### Margaret Wood Hassan (D-NH)

- **ID:** hassan-margaret
- **URL:** https://www.hassan.senate.gov/news/press-releases
- **Parser family:** senate-generic
- **Collection method:** httpx
- **Confidence:** 90%
- **Requires JS:** False
- **Records:** 244 active, 2 deleted
- **Dated:** 100% | **Body text:** 100%
- **Date range:** 2025-01-03 to 2026-04-15
- **Notes:** Found 20 items on listing page. 

### Andy Kim (D-NJ)

- **ID:** kim-andy
- **URL:** https://www.kim.senate.gov/press-releases/
- **Parser family:** senate-wordpress
- **Collection method:** httpx
- **Confidence:** 90%
- **Requires JS:** False
- **RSS feed:** https://www.kim.senate.gov/press-releases/feed/
- **Records:** 21 active, 0 deleted
- **Dated:** 100% | **Body text:** 100%
- **Date range:** 2026-03-12 to 2026-04-15
- **Health check:** FAIL (HTTP 200, 0 items, 242ms)
- **Notes:** WordPress Divi (et_pb_post). 10/page. Older Entries pagination. Detail links use /press_release/slug/. Verified 2026-04-17.

### Cory A. Booker (D-NJ)

- **ID:** booker-cory
- **URL:** https://www.booker.senate.gov/news
- **Parser family:** senate-generic
- **Collection method:** playwright
- **Confidence:** 85%
- **Requires JS:** True
- **Records:** 13 active, 3 deleted
- **Dated:** 100% | **Body text:** 46%
- **Date range:** 2026-04-07 to 2026-04-17
- **Date provenance:** 5 records
- **Notes:** Found 21 items on listing page. 

### Ben Ray Lujan (D-NM)

- **ID:** lujan-ben
- **URL:** https://www.lujan.senate.gov/newsroom/press-releases/
- **Parser family:** senate-wordpress
- **Collection method:** rss
- **Confidence:** 55%
- **Requires JS:** False
- **RSS feed:** https://www.lujan.senate.gov/feed/
- **Records:** 6 active, 0 deleted
- **Dated:** 100% | **Body text:** 100%
- **Date range:** 2026-04-09 to 2026-04-15
- **Health check:** PASS (HTTP 200, 2 items, 354ms)
- **Notes:** Found 12 items on listing page. 

### Martin Heinrich (D-NM)

- **ID:** heinrich-martin
- **URL:** https://www.heinrich.senate.gov/newsroom/press-releases
- **Parser family:** senate-generic
- **Collection method:** httpx
- **Confidence:** 80%
- **Requires JS:** False
- **Records:** 107 active, 39 deleted
- **Dated:** 100% | **Body text:** 100%
- **Date range:** 2025-12-31 to 2026-04-17
- **Date provenance:** 105 records
- **Notes:** Found 20 items on listing page. 

### Catherine Cortez Masto (D-NV)

- **ID:** masto-catherine
- **URL:** https://www.cortezmasto.senate.gov/news/press-releases/
- **Parser family:** senate-wordpress
- **Collection method:** httpx
- **Confidence:** 55%
- **Requires JS:** False
- **Records:** 10 active, 0 deleted
- **Dated:** 100% | **Body text:** 100%
- **Date range:** 2026-03-30 to 2026-04-16
- **Date provenance:** 2 records
- **Notes:** Found 5 items on listing page. 

### Jacky Rosen (D-NV)

- **ID:** rosen-jacky
- **URL:** https://www.rosen.senate.gov/category/press_release/
- **Parser family:** senate-wordpress
- **Collection method:** rss
- **Confidence:** 100%
- **Requires JS:** False
- **RSS feed:** https://www.rosen.senate.gov/category/press_release/feed/
- **Records:** 456 active, 0 deleted
- **Dated:** 100% | **Body text:** 100%
- **Date range:** 2025-01-02 to 2026-04-17
- **Date provenance:** 2 records
- **Health check:** PASS (HTTP 200, 10 items, 226ms)
- **Notes:** Found 10 items on listing page. 

### Charles E. Schumer (D-NY)

- **ID:** schumer-charles
- **URL:** https://www.schumer.senate.gov/newsroom/press-releases
- **Parser family:** senate-generic
- **Collection method:** httpx
- **Confidence:** 85%
- **Requires JS:** False
- **Records:** 228 active, 0 deleted
- **Dated:** 100% | **Body text:** 100%
- **Date range:** 2025-01-06 to 2026-04-15
- **Notes:** Found 20 items on listing page. 

### Kirsten E. Gillibrand (D-NY)

- **ID:** gillibrand-kirsten
- **URL:** https://www.gillibrand.senate.gov/press-releases/
- **Parser family:** senate-wordpress
- **Collection method:** httpx
- **Confidence:** 95%
- **Requires JS:** False
- **RSS feed:** https://www.gillibrand.senate.gov/press-releases/feed/
- **Records:** 27 active, 0 deleted
- **Dated:** 100% | **Body text:** 100%
- **Date range:** 2026-03-23 to 2026-04-17
- **Date provenance:** 5 records
- **Health check:** FAIL (HTTP 200, 0 items, 379ms)
- **Notes:** Found 10 items on listing page. 

### Bernie Moreno (R-OH)

- **ID:** moreno-bernie
- **URL:** https://www.moreno.senate.gov/media/press-releases/
- **Parser family:** senate-wordpress
- **Collection method:** httpx
- **Confidence:** 40%
- **Requires JS:** False
- **RSS feed:** https://www.moreno.senate.gov/media/press-releases/feed/
- **Records:** 136 active, 0 deleted
- **Dated:** 100% | **Body text:** 100%
- **Date range:** 2025-02-05 to 2026-04-16
- **Date provenance:** 1 records
- **Health check:** FAIL (HTTP 200, 0 items, 466ms)

### Jon Husted (R-OH)

- **ID:** husted-jon
- **URL:** https://www.husted.senate.gov/media/press-releases/
- **Parser family:** senate-wordpress
- **Collection method:** httpx
- **Confidence:** 55%
- **Requires JS:** False
- **Records:** 169 active, 0 deleted
- **Dated:** 100% | **Body text:** 100%
- **Date range:** 2025-02-18 to 2026-04-17
- **Date provenance:** 3 records
- **Notes:** Found 8 items on listing page. 

### Alan Armstrong (R-OK)

- **ID:** armstrong-alan
- **URL:** https://www.armstrong.senate.gov/press-releases/
- **Parser family:** senate-wordpress
- **Collection method:** httpx
- **Confidence:** 0%
- **Requires JS:** False
- **RSS feed:** https://www.armstrong.senate.gov/press-releases/feed/
- **Records:** 0
- **Health check:** FAIL (HTTP 200, 0 items, 257ms)
- **Notes:** Page exists but div.page-content is empty. New senator, no releases published yet. Verified 2026-04-17.

### James Lankford (R-OK)

- **ID:** lankford-james
- **URL:** https://www.lankford.senate.gov/news/press-releases/
- **Parser family:** senate-wordpress
- **Collection method:** httpx
- **Confidence:** 55%
- **Requires JS:** False
- **Records:** 7 active, 0 deleted
- **Dated:** 100% | **Body text:** 100%
- **Date range:** 2026-03-21 to 2026-04-16
- **Date provenance:** 1 records
- **Notes:** Found 6 items on listing page. 

### Jeff Merkley (D-OR)

- **ID:** merkley-jeff
- **URL:** https://www.merkley.senate.gov/news/press-releases/
- **Parser family:** senate-wordpress
- **Collection method:** playwright
- **Confidence:** 100%
- **Requires JS:** True
- **RSS feed:** https://www.merkley.senate.gov/news/press-releases/feed/
- **Records:** 303 active, 0 deleted
- **Dated:** 100% | **Body text:** 100%
- **Date range:** 2025-08-04 to 2026-04-15
- **Health check:** FAIL (HTTP 200, 0 items, 483ms)
- **Notes:** Found 9 items on listing page. 

### Ron Wyden (D-OR)

- **ID:** wyden-ron
- **URL:** https://www.wyden.senate.gov/news/press-releases
- **Parser family:** senate-generic
- **Collection method:** httpx
- **Confidence:** 95%
- **Requires JS:** False
- **Records:** 500 active, 1 deleted
- **Dated:** 100% | **Body text:** 100%
- **Date range:** 2025-01-02 to 2026-04-15
- **Notes:** Found 20 items on listing page. 

### David McCormick (R-PA)

- **ID:** mccormick-david
- **URL:** https://www.mccormick.senate.gov/news/press-releases/
- **Parser family:** senate-wordpress
- **Collection method:** rss
- **Confidence:** 70%
- **Requires JS:** False
- **RSS feed:** https://www.mccormick.senate.gov/feed/
- **Records:** 92 active, 0 deleted
- **Dated:** 100% | **Body text:** 100%
- **Date range:** 2025-01-03 to 2026-04-02
- **Health check:** PASS (HTTP 200, 1 items, 1436ms)
- **Notes:** Found 4 items on listing page. 

### John Fetterman (D-PA)

- **ID:** fetterman-john
- **URL:** https://www.fetterman.senate.gov/press-release/
- **Parser family:** senate-wordpress
- **Collection method:** rss
- **Confidence:** 100%
- **Requires JS:** False
- **RSS feed:** https://www.fetterman.senate.gov/press-release/feed/
- **Records:** 109 active, 0 deleted
- **Dated:** 100% | **Body text:** 100%
- **Date range:** 2025-01-03 to 2026-04-16
- **Date provenance:** 1 records
- **Health check:** PASS (HTTP 200, 10 items, 384ms)
- **Notes:** Found 10 items on listing page. 

### Jack Reed (D-RI)

- **ID:** reed-jack
- **URL:** https://www.reed.senate.gov/news/releases
- **Parser family:** senate-generic
- **Collection method:** playwright
- **Confidence:** 60%
- **Requires JS:** True
- **Records:** 489 active, 0 deleted
- **Dated:** 100% | **Body text:** 100%
- **Date range:** 2025-01-01 to 2026-04-17
- **Date provenance:** 4 records
- **Notes:** JS-rendered. div.js-content is empty in static HTML. Pagination exists (select dropdown). Needs Playwright. Verified 2026-04-17.

### Sheldon Whitehouse (D-RI)

- **ID:** whitehouse-sheldon
- **URL:** https://www.whitehouse.senate.gov/news/press-releases-test-sorting/
- **Parser family:** senate-wordpress
- **Collection method:** playwright
- **Confidence:** 60%
- **Requires JS:** True
- **RSS feed:** https://www.whitehouse.senate.gov/news/press-releases-test-sorting/feed/
- **Records:** 59 active, 0 deleted
- **Dated:** 100% | **Body text:** 100%
- **Date range:** 2025-11-04 to 2026-04-14
- **Date provenance:** 21 records
- **Health check:** FAIL (HTTP 200, 0 items, 183ms)
- **Notes:** Found 12 items on listing page. 

### Lindsey Graham (R-SC)

- **ID:** graham-lindsey
- **URL:** https://www.lgraham.senate.gov/public/index.cfm/press-releases
- **Parser family:** senate-coldfusion
- **Collection method:** httpx
- **Confidence:** 55%
- **Requires JS:** False
- **Records:** 100 active, 24 deleted
- **Dated:** 100% | **Body text:** 100%
- **Date range:** 2021-10-28 to 2026-03-04
- **Date provenance:** 100 records
- **Notes:** Found 361 items on listing page. 

### Tim Scott (R-SC)

- **ID:** scott-tim
- **URL:** https://www.scott.senate.gov/media-center/press-releases/
- **Parser family:** senate-wordpress
- **Collection method:** httpx
- **Confidence:** 60%
- **Requires JS:** False
- **Records:** 174 active, 0 deleted
- **Dated:** 100% | **Body text:** 100%
- **Date range:** 2025-01-03 to 2026-04-08
- **Notes:** Found 5 items on listing page. 

### John Thune (R-SD)

- **ID:** thune-john
- **URL:** https://www.thune.senate.gov/public/index.cfm/press-releases
- **Parser family:** senate-coldfusion
- **Collection method:** httpx
- **Confidence:** 55%
- **Requires JS:** False
- **Records:** 0 active, 2 deleted
- **Dated:** n/a | **Body text:** n/a
- **Date range:** none to none
- **Notes:** Found 154 items on listing page. 

### Mike Rounds (R-SD)

- **ID:** rounds-mike
- **URL:** https://www.rounds.senate.gov/newsroom/press-releases
- **Parser family:** senate-generic
- **Collection method:** httpx
- **Confidence:** 80%
- **Requires JS:** False
- **Records:** 101 active, 0 deleted
- **Dated:** 100% | **Body text:** 100%
- **Date range:** 2025-01-15 to 2026-03-19
- **Notes:** Found 20 items on listing page. 

### Bill Hagerty (R-TN)

- **ID:** hagerty-bill
- **URL:** https://www.hagerty.senate.gov/press-releases/
- **Parser family:** senate-wordpress
- **Collection method:** rss
- **Confidence:** 70%
- **Requires JS:** False
- **RSS feed:** https://www.hagerty.senate.gov/press-releases/feed/
- **Records:** 156 active, 3 deleted
- **Dated:** 100% | **Body text:** 100%
- **Date range:** 2025-01-06 to 2026-04-15
- **Health check:** PASS (HTTP 200, 10 items, 619ms)
- **Notes:** Found 45 items on listing page. 

### Marsha Blackburn (R-TN)

- **ID:** blackburn-marsha
- **URL:** https://www.blackburn.senate.gov/news/cc8c80c1-d564-4bbb-93a4-f1d772346ae0
- **Parser family:** senate-generic
- **Collection method:** httpx
- **Confidence:** 65%
- **Requires JS:** False
- **Records:** 371 active, 0 deleted
- **Dated:** 100% | **Body text:** 100%
- **Date range:** 2025-01-01 to 2026-04-01
- **Notes:** Found 13 items on listing page. 

### John Cornyn (R-TX)

- **ID:** cornyn-john
- **URL:** https://www.cornyn.senate.gov/news/
- **Parser family:** senate-wordpress
- **Collection method:** rss
- **Confidence:** 85%
- **Requires JS:** False
- **RSS feed:** https://www.cornyn.senate.gov/news/feed/
- **Records:** 7 active, 0 deleted
- **Dated:** 100% | **Body text:** 100%
- **Date range:** 2025-08-18 to 2026-04-16
- **Date provenance:** 6 records
- **Health check:** PASS (HTTP 200, 10 items, 917ms)
- **Notes:** Found 32 items on listing page. 

### Ted Cruz (R-TX)

- **ID:** cruz-ted
- **URL:** https://www.cruz.senate.gov/newsroom/press-releases
- **Parser family:** senate-generic
- **Collection method:** httpx
- **Confidence:** 80%
- **Requires JS:** False
- **Records:** 234 active, 4 deleted
- **Dated:** 100% | **Body text:** 100%
- **Date range:** 2025-01-03 to 2026-04-15
- **Notes:** Found 19 items on listing page. 

### John R. Curtis (R-UT)

- **ID:** curtis-john
- **URL:** https://www.curtis.senate.gov/media/press-releases/
- **Parser family:** senate-wordpress
- **Collection method:** httpx
- **Confidence:** 40%
- **Requires JS:** False
- **RSS feed:** https://www.curtis.senate.gov/media/press-releases/feed/
- **Records:** 152 active, 0 deleted
- **Dated:** 100% | **Body text:** 100%
- **Date range:** 2025-01-15 to 2026-04-16
- **Date provenance:** 2 records
- **Health check:** FAIL (HTTP 200, 0 items, 121ms)

### Mike Lee (R-UT)

- **ID:** lee-mike
- **URL:** https://www.lee.senate.gov/press-releases
- **Parser family:** senate-generic
- **Collection method:** httpx
- **Confidence:** 65%
- **Requires JS:** False
- **Records:** 118 active, 0 deleted
- **Dated:** 100% | **Body text:** 100%
- **Date range:** 2025-01-14 to 2026-04-17
- **Date provenance:** 2 records
- **Notes:** Found 13 items on listing page. 

### Mark R. Warner (D-VA)

- **ID:** warner-mark
- **URL:** https://www.warner.senate.gov/news/press-releases/
- **Parser family:** senate-wordpress
- **Collection method:** httpx
- **Confidence:** 55%
- **Requires JS:** False
- **Records:** 482 active, 0 deleted
- **Dated:** 100% | **Body text:** 100%
- **Date range:** 2024-11-15 to 2026-04-16
- **Date provenance:** 7 records
- **Notes:** Found 8 items on listing page. 

### Tim Kaine (D-VA)

- **ID:** kaine-tim
- **URL:** https://www.kaine.senate.gov/news
- **Parser family:** senate-generic
- **Collection method:** httpx
- **Confidence:** 85%
- **Requires JS:** False
- **Records:** 579 active, 0 deleted
- **Dated:** 100% | **Body text:** 100%
- **Date range:** 2025-01-02 to 2026-04-16
- **Date provenance:** 2 records
- **Notes:** Found 20 items on listing page. 

### Bernard Sanders (I-VT)

- **ID:** sanders-bernard
- **URL:** https://www.sanders.senate.gov/media/press-releases/
- **Parser family:** senate-wordpress
- **Collection method:** httpx
- **Confidence:** 100%
- **Requires JS:** False
- **Records:** 198 active, 0 deleted
- **Dated:** 100% | **Body text:** 100%
- **Date range:** 2025-01-02 to 2026-04-15
- **Notes:** Found 7 items on listing page. 

### Peter Welch (D-VT)

- **ID:** welch-peter
- **URL:** https://www.welch.senate.gov/category/press-release/
- **Parser family:** senate-wordpress
- **Collection method:** rss
- **Confidence:** 90%
- **Requires JS:** False
- **RSS feed:** https://www.welch.senate.gov/category/press-release/feed/
- **Records:** 13 active, 0 deleted
- **Dated:** 100% | **Body text:** 100%
- **Date range:** 2026-04-06 to 2026-04-16
- **Date provenance:** 1 records
- **Health check:** PASS (HTTP 200, 10 items, 192ms)
- **Notes:** WordPress (article.postItem). 6/page, 6+ pages. /page/N/ pagination. Old URL was /press-kit/ (wrong). Verified 2026-04-17.

### Maria Cantwell (D-WA)

- **ID:** cantwell-maria
- **URL:** https://www.cantwell.senate.gov/news/press-releases
- **Parser family:** senate-generic
- **Collection method:** httpx
- **Confidence:** 90%
- **Requires JS:** False
- **Records:** 0 active, 28 deleted
- **Dated:** n/a | **Body text:** n/a
- **Date range:** none to none
- **Notes:** Found 90 items on listing page. 

### Patty Murray (D-WA)

- **ID:** murray-patty
- **URL:** https://www.murray.senate.gov/press-kit/
- **Parser family:** senate-wordpress
- **Collection method:** httpx
- **Confidence:** 55%
- **Requires JS:** False
- **RSS feed:** https://www.murray.senate.gov/press-kit/feed/
- **Records:** 0
- **Health check:** FAIL (HTTP 200, 0 items, 102ms)
- **Notes:** Found 11 items on listing page. 

### Ron Johnson (R-WI)

- **ID:** johnson-ron
- **URL:** https://www.ronjohnson.senate.gov/press-releases
- **Parser family:** senate-generic
- **Collection method:** httpx
- **Confidence:** 65%
- **Requires JS:** False
- **Records:** 98 active, 0 deleted
- **Dated:** 100% | **Body text:** 100%
- **Date range:** 2025-01-01 to 2026-03-01
- **Notes:** Found 13 items on listing page. 

### Tammy Baldwin (D-WI)

- **ID:** baldwin-tammy
- **URL:** https://www.baldwin.senate.gov/news/press-releases
- **Parser family:** senate-generic
- **Collection method:** httpx
- **Confidence:** 80%
- **Requires JS:** False
- **Records:** 346 active, 0 deleted
- **Dated:** 100% | **Body text:** 100%
- **Date range:** 2025-01-03 to 2026-04-16
- **Date provenance:** 1 records
- **Notes:** Found 20 items on listing page. 

### James C. Justice (R-WV)

- **ID:** justice-james
- **URL:** https://www.justice.senate.gov/media/press-releases/
- **Parser family:** senate-wordpress
- **Collection method:** httpx
- **Confidence:** 40%
- **Requires JS:** False
- **RSS feed:** https://www.justice.senate.gov/media/press-releases/feed/
- **Records:** 126 active, 0 deleted
- **Dated:** 100% | **Body text:** 99%
- **Date range:** 2025-01-20 to 2026-04-16
- **Date provenance:** 2 records
- **Health check:** FAIL (HTTP 200, 0 items, 870ms)

### Shelley Moore Capito (R-WV)

- **ID:** capito-shelley
- **URL:** https://www.capito.senate.gov/news/press-releases
- **Parser family:** senate-generic
- **Collection method:** playwright
- **Confidence:** 60%
- **Requires JS:** True
- **Records:** 376 active, 0 deleted
- **Dated:** 100% | **Body text:** 100%
- **Date range:** 2025-01-02 to 2026-04-16
- **Date provenance:** 1 records
- **Notes:** JS-rendered. div.js-content empty. Same pattern as Reed/Cotton. Needs Playwright. Verified 2026-04-17.

### Cynthia M. Lummis (R-WY)

- **ID:** lummis-cynthia
- **URL:** https://www.lummis.senate.gov/press-releases/
- **Parser family:** senate-wordpress
- **Collection method:** rss
- **Confidence:** 45%
- **Requires JS:** False
- **RSS feed:** https://www.lummis.senate.gov/press-releases/feed/
- **Records:** 191 active, 0 deleted
- **Dated:** 100% | **Body text:** 100%
- **Date range:** 2025-01-06 to 2026-04-16
- **Date provenance:** 1 records
- **Health check:** PASS (HTTP 200, 6 items, 297ms)

### John Barrasso (R-WY)

- **ID:** barrasso-john
- **URL:** https://www.barrasso.senate.gov/newsroom/news-releases/
- **Parser family:** senate-wordpress
- **Collection method:** httpx
- **Confidence:** 100%
- **Requires JS:** False
- **Records:** 286 active, 1 deleted
- **Dated:** 100% | **Body text:** 100%
- **Date range:** 2025-01-03 to 2026-04-16
- **Date provenance:** 2 records
- **Notes:** Found 10 items on listing page. 

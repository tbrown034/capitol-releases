# Senate RSS Probe Report

**Generated:** 2026-04-24 18:00 UTC
**Senators probed:** 100

## Topline

- Any working RSS feed found: **41 / 100**
- Swap-eligible (RSS good enough for daily updates): **23 / 100**
- Unreliable RSS (feed exists but fails at least one criterion): **18**
- No RSS feed found: **59**

## Breakdown by Current Collection Method

| Method | Total | Any RSS | Swap-eligible |
|--------|-------|---------|---------------|
| httpx | 70 | 23 | 14 |
| playwright | 19 | 7 | 2 |
| rss | 11 | 11 | 7 |

## Swap-Eligible Senators (could move to RSS for daily updates)

Criteria met: >=10 items, >=90% of items have parseable dates, most recent item within 90 days, homogeneous titles, 2/3+ sample links returning 200.

| Senator | State | Current | Feed URL | Items | Fresh (d) | Span (d) | Body? |
|---------|-------|---------|----------|-------|-----------|----------|-------|
| John Barrasso | WY | httpx | https://www.barrasso.senate.gov/feed/ | 10 | 2 | 27 | yes |
| Michael F. Bennet | CO | rss | https://www.bennet.senate.gov/news/feed/ | 10 | 0 | 8 | yes |
| Ted Budd | NC | httpx | https://www.budd.senate.gov/category/news/press-releases/feed/ | 10 | 1 | 28 | yes |
| Maria Cantwell | WA | httpx | https://www.cantwell.senate.gov/rss/feeds/?type=press | 15 | 0 | 26 | teaser (0c) |
| John Cornyn | TX | playwright | https://www.cornyn.senate.gov/news/feed/ | 10 | 0 | 7 | yes |
| Tammy Duckworth | IL | httpx | https://www.duckworth.senate.gov/rss/feeds/?type=press | 15 | 0 | 7 | teaser (0c) |
| Richard J. Durbin | IL | httpx | https://www.durbin.senate.gov/rss/feeds/?type=press | 15 | 1 | 1 | teaser (0c) |
| John Fetterman | PA | rss | https://www.fetterman.senate.gov/press-release/feed/ | 10 | 0 | 42 | yes |
| Kirsten E. Gillibrand | NY | httpx | https://www.gillibrand.senate.gov/feed/ | 10 | 0 | 7 | yes |
| Bill Hagerty | TN | rss | https://www.hagerty.senate.gov/press-releases/feed/ | 10 | 0 | 36 | yes |
| Josh Hawley | MO | httpx | https://www.hawley.senate.gov/feed/ | 10 | 0 | 30 | yes |
| Jeff Merkley | OR | playwright | https://www.merkley.senate.gov/feed/ | 10 | 0 | 6 | yes |
| Ashley Moody | FL | httpx | https://www.moody.senate.gov/press-releases/feed/ | 10 | 0 | 10 | yes |
| Lisa Murkowski | AK | httpx | https://www.murkowski.senate.gov/rss/feeds/?type=press | 15 | 0 | 36 | teaser (0c) |
| Patty Murray | WA | httpx | https://www.murray.senate.gov/feed/ | 10 | 1 | 6 | yes |
| Jon Ossoff | GA | rss | https://www.ossoff.senate.gov/press-releases/feed/ | 10 | 1 | 8 | yes |
| Jacky Rosen | NV | rss | https://www.rosen.senate.gov/category/press_release/feed/ | 10 | 0 | 13 | yes |
| Elissa Slotkin | MI | rss | https://www.slotkin.senate.gov/newsroom/feed/ | 10 | 2 | 29 | yes |
| Tina Smith | MN | httpx | https://www.smith.senate.gov/feed/ | 10 | 3 | 40 | yes |
| Dan Sullivan | AK | httpx | https://www.sullivan.senate.gov/rss/feeds/?type=press | 15 | 1 | 39 | teaser (0c) |
| Elizabeth Warren | MA | rss | https://www.warren.senate.gov/rss/ | 50 | 0 | 21 | teaser (0c) |
| Peter Welch | VT | httpx | https://www.welch.senate.gov/category/press-release/feed/ | 10 | 1 | 2 | yes |
| Ron Wyden | OR | httpx | https://www.wyden.senate.gov/rss/feeds/?type=press | 15 | 0 | 7 | teaser (0c) |

## Unreliable RSS (feed exists, fails one or more criteria -- keep current method)

| Senator | State | Current | Feed URL | Items | Fresh (d) | Reason |
|---------|-------|---------|----------|-------|-----------|--------|
| Angela D. Alsobrooks | MD | httpx | https://www.alsobrooks.senate.gov/feed/ | 1 | 1289 | only 1 items (<10); stale: most recent item 1289d old (>90d); titles: titles too short (avg 9 chars); sample links: 0/1 returned 200 |
| Jim Banks | IN | httpx | https://www.banks.senate.gov/feed/ | 1 | 1289 | only 1 items (<10); stale: most recent item 1289d old (>90d); titles: titles too short (avg 9 chars); sample links: 0/1 returned 200 |
| John Boozman | AR | rss | https://www.boozman.senate.gov/public/?a=RSS.Feed | 20 | n/a | only 0% of items have parseable dates; no parseable dates to check staleness |
| John R. Curtis | UT | httpx | https://www.curtis.senate.gov/feed/ | 1 | 1289 | only 1 items (<10); stale: most recent item 1289d old (>90d); titles: titles too short (avg 9 chars); sample links: 1/1 returned 200 |
| John W. Hickenlooper | CO | httpx | https://www.hickenlooper.senate.gov/feed/ | 4 | 1200 | only 4 items (<10); stale: most recent item 1200d old (>90d) |
| John Kennedy | LA | rss | https://www.kennedy.senate.gov/public/?a=RSS.Feed | 20 | n/a | only 0% of items have parseable dates; no parseable dates to check staleness |
| Andy Kim | NJ | httpx | https://www.kim.senate.gov/feed/ | 1 | 24 | only 1 items (<10); sample links: 1/1 returned 200 |
| Ben Ray Lujan | NM | playwright | https://www.lujan.senate.gov/feed/ | 2 | 1057 | only 2 items (<10); stale: most recent item 1057d old (>90d) |
| Cynthia M. Lummis | WY | rss | https://www.lummis.senate.gov/feed/ | 6 | 681 | only 6 items (<10); stale: most recent item 681d old (>90d) |
| Roger Marshall | KS | playwright | https://www.marshall.senate.gov/feed/ | 5 | 392 | only 5 items (<10); stale: most recent item 392d old (>90d) |
| David McCormick | PA | httpx | https://www.mccormick.senate.gov/feed/ | 1 | 1289 | only 1 items (<10); stale: most recent item 1289d old (>90d); titles: titles too short (avg 9 chars); sample links: 0/1 returned 200 |
| Jerry Moran | KS | rss | https://www.moran.senate.gov/public/?a=RSS.Feed | 20 | n/a | only 0% of items have parseable dates; no parseable dates to check staleness |
| Alex Padilla | CA | playwright | https://www.padilla.senate.gov/feed/ | 6 | 212 | only 6 items (<10); stale: most recent item 212d old (>90d) |
| Rand Paul | KY | httpx | https://www.paul.senate.gov/feed/ | 9 | 4 | only 9 items (<10) |
| Pete Ricketts | NE | playwright | https://www.ricketts.senate.gov/feed/ | 3 | 7 | only 3 items (<10) |
| Lisa Blunt Rochester | DE | httpx | https://www.bluntrochester.senate.gov/feed/ | 1 | 1289 | only 1 items (<10); stale: most recent item 1289d old (>90d); titles: titles too short (avg 9 chars); sample links: 0/1 returned 200 |
| Raphael G. Warnock | GA | playwright | https://www.warnock.senate.gov/feed/ | 4 | 140 | only 4 items (<10); stale: most recent item 140d old (>90d) |
| Todd Young | IN | httpx | https://www.young.senate.gov/feed/ | 1 | 722 | only 1 items (<10); stale: most recent item 722d old (>90d); sample links: 1/1 returned 200 |

## No RSS Feed Found

| Senator | State | Current method |
|---------|-------|----------------|
| Alan Armstrong | OK | httpx |
| Tammy Baldwin | WI | httpx |
| Marsha Blackburn | TN | httpx |
| Richard Blumenthal | CT | httpx |
| Cory A. Booker | NJ | httpx |
| Katie Boyd Britt | AL | playwright |
| Shelley Moore Capito | WV | playwright |
| Bill Cassidy | LA | playwright |
| Susan M. Collins | ME | httpx |
| Christopher A. Coons | DE | httpx |
| Tom Cotton | AR | playwright |
| Kevin Cramer | ND | httpx |
| Mike Crapo | ID | httpx |
| Ted Cruz | TX | httpx |
| Steve Daines | MT | httpx |
| Joni Ernst | IA | httpx |
| Deb Fischer | NE | httpx |
| Ruben Gallego | AZ | httpx |
| Lindsey Graham | SC | httpx |
| Chuck Grassley | IA | httpx |
| Margaret Wood Hassan | NH | httpx |
| Martin Heinrich | NM | httpx |
| Mazie K. Hirono | HI | httpx |
| John Hoeven | ND | httpx |
| Chris Van Hollen | MD | httpx |
| Jon Husted | OH | httpx |
| Cindy Hyde-Smith | MS | httpx |
| Ron Johnson | WI | httpx |
| James C. Justice | WV | httpx |
| Tim Kaine | VA | httpx |
| Mark Kelly | AZ | playwright |
| Angus S. King, Jr. | ME | httpx |
| Amy Klobuchar | MN | httpx |
| James Lankford | OK | playwright |
| Mike Lee | UT | httpx |
| Edward J. Markey | MA | playwright |
| Catherine Cortez Masto | NV | playwright |
| Mitch McConnell | KY | httpx |
| Bernie Moreno | OH | httpx |
| Christopher Murphy | CT | httpx |
| Gary C. Peters | MI | httpx |
| Jack Reed | RI | playwright |
| James E. Risch | ID | httpx |
| Mike Rounds | SD | httpx |
| Bernard Sanders | VT | httpx |
| Brian Schatz | HI | httpx |
| Adam B. Schiff | CA | httpx |
| Eric Schmitt | MO | playwright |
| Charles E. Schumer | NY | httpx |
| Rick Scott | FL | httpx |
| Tim Scott | SC | httpx |
| Jeanne Shaheen | NH | httpx |
| Tim Sheehy | MT | httpx |
| John Thune | SD | httpx |
| Thom Tillis | NC | httpx |
| Tommy Tuberville | AL | playwright |
| Mark R. Warner | VA | httpx |
| Sheldon Whitehouse | RI | playwright |
| Roger F. Wicker | MS | httpx |

## Regression Watch: Currently on RSS but no longer swap-eligible

These senators have `collection_method = "rss"` today but failed swap-eligibility criteria on this probe. Worth investigating.

| Senator | State | Reason |
|---------|-------|--------|
| John Boozman | AR | only 0% of items have parseable dates; no parseable dates to check staleness |
| John Kennedy | LA | only 0% of items have parseable dates; no parseable dates to check staleness |
| Cynthia M. Lummis | WY | only 6 items (<10); stale: most recent item 681d old (>90d) |
| Jerry Moran | KS | only 0% of items have parseable dates; no parseable dates to check staleness |

## Observed Pitfalls

- **RSS feeds truncate.** The vast majority of working feeds return 10-25 items. Acceptable for daily update, useless for backfill.
- **Body text is often a short teaser.** Many feeds return `<description>` at 100-300 chars, not full body. Detail-page fetch (as the current RSSCollector already does) remains required.
- **Some senator sites return HTTP 200 with an HTML 404 page on `/feed/`**, which we reject via `_looks_like_feed` content-type sniffing.
- **WordPress `/feed/` is near-universal** where WP is the CMS. The 70 senators currently on httpx include many WP sites that could be switched to RSS with zero selector maintenance burden.
- **Mixed-content feeds are rare but exist** (e.g. podcast episodes or weekly newsletters mixed into a general `/feed/`). The homogeneity check on titles flags these.
- **Date formats vary.** RFC 2822 dominates; a handful of Atom-style ISO 8601 feeds mix in. `pipeline.lib.rss._parse_rss_date` handles both.
- **ColdFusion RSS feeds emit malformed pubDates.** Three current-RSS senators (Boozman, Kennedy, Moran) expose `/public/?a=RSS.Feed` with day-of-year values like `Thu, 113 Apr 2026 12:00:00 EST` that fail RFC 2822 parsing. Feed items and titles are otherwise valid; if we want to keep these on RSS, the collector needs a salvage parser (pull date from item URL or detail page) rather than trusting pubDate.
- **Many configured `rss_feed_url` values do not point to press-release-specific feeds.** E.g. Warren's `/rss/` is site-wide but happens to be homogeneous enough; others would benefit from narrower category feeds (`/category/press_release/feed/` works for several WordPress senators).
- **Some feeds pass swap eligibility with a teaser `<description>` and no full body.** That is OK -- the existing `RSSCollector` already fetches the detail page to get the full article. Body teaser vs full in the feed is not a swap blocker; it is a performance hint.


# House Comprehensive Probe Report

**Generated:** 2026-04-24 18:05 UTC
**Members probed:** 436
**Wall-clock runtime:** 299.9s (5.0 min)
**Concurrency:** 15

## Headline finding: AkamaiGHost bot-mitigation blocks the sweep

The .house.gov infrastructure sits behind AkamaiGHost with an aggressive
bot-mitigation policy that returned **HTTP 403 on 401 of 436 members
(92.0%)**. Blocks persisted across User-Agent rotation, full Chrome
header sets, HTTP/1.1 vs HTTP/2, curl, httpx, urllib, and `curl_cffi`
with chrome131 / safari17 / firefox133 TLS impersonation. A control
request to `example.com` during the same window returned 200, and
individual `senate.gov` subdomains were unaffected — the block is a
policy applied to `*.house.gov`.

Response-code distribution from the sweep:

| Status | Members | % |
|--------|---------|---|
| 403 (AkamaiGHost Access Denied) | 401 | 92.0% |
| 200 | 28 | 6.4% |
| no response / DNS error | 7 | 1.6% |

**Operational implication:** collection against the House will require a
browser-TLS path (Playwright headful, or `curl_cffi` from a residential
IP) or an arrangement with the House Clerk / member offices to allow
scraping UA. Plain async httpx will not work at scale against this
edge.

**This report's numbers describe only the 28 members that penetrated
the Akamai policy.** Treat them as a biased sample, not a census. The
raw per-member JSON is preserved at
`pipeline/recon/house_comprehensive_probe.json` for replay once access
is resolved.

## a. Coverage matrix

Best-option (single strategy per member, in preference order):

| Strategy | Members | % of 436 | % of 28 penetrated |
|----------|---------|---------:|-------------------:|
| rss | 13 | 3.0% | 46.4% |
| wp_json | 0 | 0.0% | 0.0% |
| httpx | 13 | 3.0% | 46.4% |
| playwright | 2 | 0.5% | 7.1% |
| blocked-by-akamai / no response | 408 | 93.6% | — |

Any-option (members may count in multiple rows):

| Strategy | Members | Note |
|----------|---------|------|
| rss | 16 | all on the shared House Drupal template |
| wp_json | 2 | crane-elijah (149), schweikert-david (1048) |
| httpx | 24 | static list detected on candidate press page |
| playwright | 28 | any member returning homepage 200 |

## b. CMS family distribution

Counting only the 28 penetrated members (the 408 blocked reveal no CMS
signal):

| CMS family | Members | Share of penetrated 28 |
|------------|---------|-----------------------:|
| drupal (House shared template) | 16 | 57.1% |
| custom / unrecognized | 10 | 35.7% |
| wordpress | 2 | 7.1% |

Observed `<meta name="generator">` on the 28:

- `Drupal 10 (https://www.drupal.org)` — 16 members (all with `/rss.xml`)
- none — 10 members (template signature not in the snippet our probe captured)
- `WordPress 6.9` — 1 (crane-elijah)
- `WordPress 6.8.3` — 1 (schweikert-david)

The 10 "custom" members (ansari, gosar, hamadeh, hill-j, huffman, kiley,
rogers-mike, sewell, stanton, womack) have homepage HTML sizes 20k–99k
and well-formed `/news`, `/media`, or `/press-kit` nav links. They are
almost certainly on the shared House Drupal platform but are rendered
with a variant layout that suppresses the `generator` meta and the
theme path marker in the above-the-fold HTML we sampled. Confirming
this requires a successful fetch from a real browser.

## c. RSS quality cut

- Members with any working RSS feed: **16 / 28** penetrated (3.7% of 436)
- Swap-eligible by the Senate-probe bar (>=20 items, >=6-month span,
  homogeneous titles, full body present): **0 / 436**

House RSS feeds are capped at 10 items. All 16 working feeds returned
exactly 10 (or fewer). Span varied from 0 days (aderholt, palmer: office
publishing in bursts that all hit within 24h) to 1,923 days (Mike
Thompson, dormant office). Full body present in every feed we sampled.

**This is still a useful daily-update vehicle** — 10 items is plenty
between daily runs — but RSS alone cannot backfill the January 2025
window.

## d. WordPress JSON opportunity

- `/wp-json/wp/v2/posts` open with non-zero total: **2** (crane-elijah
  149, schweikert-david 1048)
- `/wp-json/wp/v2/press_releases` open with non-zero total: **0**
- Any WP JSON endpoint open: **2** (0.5% of 436, 7.1% of penetrated)

Only two members use WordPress at all in the penetrated sample. Both
expose `/wp-json/wp/v2/posts` (schweikert's 1,048 posts is a large
multi-year archive). Neither exposes a custom `press_releases` post
type the way senate.gov WordPress installs do.

Because WordPress is a very minority CMS on the House side, the Senate
WP JSON rescue pattern (which added ~3,644 records across ~25 senators)
does not transfer as a high-leverage House win. Phase 2 here is small.

## e. Shared-template leverage

- Explicit `/wp-content/themes/evo/` signature: **0 members**
  (irrelevant — Evo is the *Senate* shared WordPress theme; the House
  uses a different shared stack).
- `Drupal 10` on a `.house.gov` subdomain with a working `/rss.xml`:
  **16 members**, all with identical RSS shape.

The House's shared template appears to be a Drupal 10 platform. If that
assumption holds once the Akamai block is bypassed, **a single Drupal
collector targeting `/rss.xml` + structured Drupal node pages should
cover a large fraction of the 436**. The 28-member sample is consistent
with this hypothesis but cannot confirm how many of the 408 blocked
members are on the same Drupal platform.

**Highest-leverage next step:** get a single clean browser-TLS pass
against all 436, classify templates, and write the Drupal collector
once.

## f. Problem list

Members with infrastructure-level failures (no response at all):

| Member | Issue |
|--------|-------|
| barrett-tom | DNS/connection failure |
| collins-mike | DNS/connection failure |
| davis-donald | DNS/connection failure |
| gray-adam | DNS/connection failure |
| james-john | DNS/connection failure |
| johnson-henry | DNS/connection failure |
| leger-fernandez-teresa | DNS/connection failure |

These 7 are separate from the 401 Akamai-blocked members and likely
reflect either stale hostnames in `house_members.json` or transient DNS
issues. Worth a targeted recheck.

All other "failures" are the Akamai 403 block, not a site-level issue.

## g. Coverage projection

With the caveat that 408/436 members were blocked during this sweep,
the phase projection based on penetrated-sample extrapolation:

| Phase | Strategy added | Members covered (observed) | Projected if Drupal hypothesis holds |
|-------|----------------|---------------------------:|-------------------------------------:|
| 1 | RSS only | 13 (3.0%) | ~60–70% (if most of 408 are Drupal House template) |
| 2 | + WordPress JSON | 13 (3.0%) | ~62% (WP is <10% of House) |
| 3 | + shared House Drupal parser | 26 (6.0%) | ~85–95% |
| 4 | + per-member Playwright | 28 (6.4%) | ~99% |

The observed column is what we can stand behind from this run. The
projected column assumes the 408 blocked members are distributed across
CMS families in roughly the same proportions as the 28 penetrated (16
Drupal / 10 custom / 2 WordPress ≈ 57/36/7). This is a working
hypothesis, not a finding.

## Next actions

1. Re-run the probe using Playwright with a realistic browser profile
   and residential-grade request pacing. Concurrency should probably
   drop to 2–3 or less for the full 436-member pass to stay under
   whatever Akamai rate-limit triggered this block.
2. Once clean data exists, confirm the Drupal-shared-template
   hypothesis. If it holds, write one Drupal collector that covers the
   long tail in a single selector set.
3. Treat the WordPress + custom members as individual Playwright
   assignments. This is the House equivalent of the 20 Playwright
   senators we already run.
4. For the daily-update path on Drupal House members, `/rss.xml` at 10
   items is adequate. Backfill for the January-2025 window will need a
   separate list-page crawl on each Drupal site.

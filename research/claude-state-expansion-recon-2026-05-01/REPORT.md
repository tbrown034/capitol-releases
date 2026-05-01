# State Expansion Recon — 2026-05-01

**Author:** Claude (Opus 4.7) — independent recon, multi-agent fan-out
**Repo:** `capitol-releases`
**Scope:** Beyond the existing TX Senate corpus — all 50 state legislatures, statewide elected officials, US House, with implementation-grade source profiling.

---

## What was reviewed

| Track | Sources reviewed | Live-fetched | Browser-rendered |
|---|---|---|---|
| Northeast state legislatures (CT, ME, MA, NH, NJ, NY, PA, RI, VT) | 22 chamber rows | 18 | 4 |
| South state legislatures (AL, AR, FL, GA, KY, LA, MD, MS, NC, OK, SC, TN, VA, WV) | 28 chamber rows | 23 | 2 |
| Midwest state legislatures (IL, IN, IA, KS, MI, MN, MO, NE, ND, OH, SD, WI) | 23 chamber rows | 19 | 2 |
| West state legislatures (AK, AZ, CA, CO, DE, HI, ID, MT, NV, NM, OR, UT, WA, WY) | 28 chamber rows | 22 | 1 |
| State-caucus enumeration (50 states × up to 4) | 196 caucus rows | 132 | 4 |
| Governors (50 states) | 50 records | 32 | 5 |
| State Attorneys General (50 states) | 50 records | 28 | 4 |
| Other statewide elected (SoS, Treasurer, Comptroller, Auditor, Insurance, SPI, Land, etc.) | 175 records | 49 | 0 |
| WP-JSON discovery sweep across executive sources | 100 base URLs probed | 100 | 0 |
| Selector deep-dive on top 19 candidate sources | 19 records | 19 | — |
| Browser-render verification of suspected JS/WAF sites | 19 sites | 19 | 19 |
| US House members (Drupal HMWP) | 436 members + 1 profile | 28 sample probes | 0 |
| **Total state/exec sources** | **606 unique** | — | — |
| **Total US House** | **436 members** | — | — |

Live URLs were fetched via httpx-style WebFetch where possible, then via Chrome MCP tools where suspected JS-required or WAF-blocked.

The existing TX Senate corpus (314 records, 18 of 30 seated senators) was independently audited against the live source — see `tx-senate-audit.md`.

---

## Headline findings

### 606 unique state and executive sources, 125 ready_first_wave

| Classification | Count |
|---|---|
| `ready_first_wave` | 125 |
| `needs_profile` | 280 |
| `do_not_claim_member_coverage` | 76 |
| `caucus_chamber_only` | 49 |
| `caucus_source` (parent classification) | 26 |
| `chamber_only` | 12 |
| (unset / unclassified by source agent) | 38 |

By level: 312 executive, 196 caucus, 97 legislature-chamber, 1 US House summary (covering 436 members).

**42 of 50 states have at least one source ready to ship in wave 1.** Eight states have no fully verified ready source today: **IN, KY, LA, MO, NE, NH, VT, WV** — all need a profile pass before any first-wave commitment.

### The "JS-heavy" assumption was wrong

I dispatched a browser-render probe of 15 sites suspected to require JavaScript (NY Senate, NJ Legislature, CT GA, MA Senate, FL Senate, AZ Legislature, HI Capitol, IL GA, etc.). **Zero are truly JS-required.** Where raw httpx fails, the cause is consistently a WAF (Akamai, Cloudflare, Imperva) refusing non-browser User-Agents — Chrome with default headers passes through and the listings appear in initial server-rendered HTML. Implication: the second-wave plan does not need Playwright as a baseline; it needs a hardened httpx client with browser-class headers and a TLS bundle.

### WordPress is the dominant implementable pattern

- **93** sources with verified or near-verified WordPress
- **45** Drupal
- **40** proprietary state portals (CT/Sitecore, NY/Drupal-locked, mass.gov/Acquia)
- **25** SharePoint (MD, KY, OR, WV cluster)
- **18** custom ASP.NET
- **132** unknown (mostly statewide officials we didn't deep-probe)

For WordPress sites, **`/wp-json/wp/v2/posts` is the cheat code**: confirmed open on **22 of 100 governor+AG sites** in the discovery sweep, plus **31 of 196 caucus sites**, plus **the entire CA Senate (40 subdomains share one Drupal template)**. Where wp-json is open, scraping is reduced to a 30-line collector with stable pagination, no selectors to break.

### Caucus sites are the dominant member-attribution path in 30+ states

The chamber-official websites for IL, IN, MI, MN, OH (chamber sites still good for OH), PA, NJ, MA, NY, CA, WA, TN, VA, MD, AZ, CO, NM, OR — all either lack press infrastructure entirely or only publish leadership-level releases. Member-attributed releases live on partisan caucus WordPress installs. **Schema implication:** the existing `senate.json` seed format must grow first-class support for caucus-tier sources with a `party` axis. The current "every member is a row" assumption fails for states where 24 members share `senatedemocrats.wa.gov`.

### Major implementation hazards

1. **Akamai WAF** dominant on .gov sites (CA gov, FL gov, NY gov+AG, KY gov, MA gov, MI gov, US House Member Website Platform). Same vendor pattern as the existing senate.gov experience documented in `project_akamai_waf.md`. Fix: browser-class headers; if that's insufficient, residential proxies. Wayback fallback for sitemaps.
2. **TLS chain failures** on many caucus sites (multiple .com domains with mismatched ALTNAMEs or missing intermediate certs) — these are fragile WordPress installs with no professional ops behind them. Fix: explicit certifi root + reasonable timeout-and-skip.
3. **Squatted / parked / hijacked caucus domains** observed at `kshousedems.com` (now anxietyheart.shop), `coloradohousegop.com` (payday-loan redirect), `cssrc.us` (parked). Add a hard blocklist; never auto-trust a "Senate D" guess; verify with a probe first.
4. **PDF-only press archives** in AZ Legislature, FL Senate publications, LA Senate, NM Legislature. Same pdfplumber path the TX collector uses; reusable but body extraction is non-uniform. Plan a single chamber-agnostic body extractor before the second PDF-heavy state ships.
5. **State-level SPAs** in SD Legislature (Angular shell with no usable XHR endpoints surfaced) and the GA Legislature (also JS-app). These will need Playwright. Cost-acceptable since both states have very low publication volume.
6. **Citizen-legislature states** with effectively no web press output: ID, MT, NV, ND, SD, WY. Coverage targets must be honest — these states publish ~zero-to-tens of releases per year per chamber.
7. **Bicameral attribution ambiguity**: KY shared PIO feed, NC `/News`, WV `News_release` mix Senate and House content with no structured chamber metadata. Title NER would be required to attribute.

---

## TX Senate audit highlights

Full report: `tx-senate-audit.md`. Top issues:

- **Coverage gap**: 12 of 30 seated senators have zero records. Some are senators who genuinely don't publish; the project has no per-senator stale alert to distinguish "truly silent" from "scraper broke."
- **content_hash semantic drift**: collector hashes title|url; body extractor overwrites with sha256 of the body. Two different `content_hash` semantics for the same column.
- **Year-header date fallback** with confidence 1.0: today triggers zero times across 314 rows, but if a sidebar `<h3>2024</h3>` ever appears, the fallback would silently mis-date dozens of rows.
- **Truth check** uses naive MM/DD/YYYY regex over the entire rendered page (sidebar dates, footer timestamps included) and applies a ±1 tolerance that papers over real drift.
- **Truth check filters `photo_release`** that the collector never assigns; should filter `'other'` (videos) instead.
- **Title mutation** for video items prepends "VIDEO: " to source titles, creating divergence between DB and source.
- **Body extractor hardcoded to `s.chamber = 'tx_senate'`** — this dispatch must be parameterized before state #2 ships.

These are not blocker bugs but they will compound badly across 50 states if not fixed first.

---

## Recommended first wave — 10 sources

Curated for ROI (high cadence × clean source × low implementation risk × strategic coverage):

| # | Source | Pattern | Why first |
|---|---|---|---|
| 1 | **CA Governor** (gov.ca.gov) | WordPress, `wp-json/wp/v2/posts` open | Highest-profile state exec, daily cadence, 30-line collector |
| 2 | **CA Attorney General** (oag.ca.gov) | Drupal, RSS at `/news/feed` | High litigation cadence, RSS = trivial |
| 3 | **CA Senate** (sd01-sd40.senate.ca.gov) | Uniform Drupal Views template, `?page=N` pagination | One profile covers 40 senators; member attribution via subdomain |
| 4 | **WA Governor** (governor.wa.gov) | RSS at `/rss/news.xml` | Verified live, low risk, single source |
| 5 | **WA Attorney General** (atg.wa.gov) | Drupal, RSS at `/news/news-releases-rss` | Verified live |
| 6 | **WA Senate Democrats** (senatedemocrats.wa.gov) | WordPress, wp-json open, per-senator subpaths | 24 senators in one collector |
| 7 | **TX Governor** (gov.texas.gov) | RSS at `/news/rss` | Verified live |
| 8 | **NC Attorney General** (ncdoj.gov) | WordPress, wp-json open | 0.98 confidence — cleanest single-office target found |
| 9 | **OH Senate** (ohiosenate.gov/members/{slug}/news) | Custom platform with stable `/members/{slug}/news` and numeric IDs | Gold-standard chamber site; 33 members in one config |
| 10 | **OH House** (ohiohouse.gov/members/{slug}/news) | Identical platform to OH Senate | 99 members for ~zero marginal effort |

**Coverage delivered by first wave:** 4 governors, 3 AGs, ~73 state senators, ~99 state representatives, 1 chamber-tier source = ~180 unique principals across 5 states (CA, WA, TX, NC, OH) plus partial cross-coverage.

See `first_wave_curated.md` for selectors, sample URLs, and per-source implementation notes.

## Second wave — by ROI

Implementation-ready after first wave hardens:

- **MI Senate Dems** + **MI Senate Republicans** (both wp-json confirmed) — 38 senators in two collectors
- **MN Senate DFL** (wp-json confirmed) + **MN House Republicans** (wp-json confirmed)
- **PA Senate Democrats** (`pasenate.com`, wp-json confirmed) — 21 senators
- **TN House Republicans** (wp-json confirmed)
- **IA Senate Democrats** (wp-json confirmed, despite TLS quirks)
- **IL Senate Republicans** (wp-json) + **IL Senate Democrats** (Joomla, ~6,272 records)
- **CT Senate Democrats** (wp-json confirmed)
- **CA Assembly Republicans** (asmrc.org, wp-json open) + **CA Assembly Democrats** (asmdc.org per-member Drupal subdomains)
- **NY State Senate** (Drupal, uniform `article.c-block-press-release` selectors — needs browser headers for the 403)
- **TX Comptroller**, **TX Land Commissioner**, **TX Ag Commissioner**, **NY Comptroller**, **OH Auditor**, **CA Controller** — single-office statewide elected with confirmed press output

## Do-NOT-implement until manually re-profiled (76 sources)

Full list in `do_not_implement.json`. Categories:

- **No web press infrastructure exists**: AL Senate, MS Senate + House, IA Senate + House, KS Senate + House, MN House (chamber), MO House, ND Senate + House, WI Senate + Assembly, WY Senate + House, ID Senate + House, MT Senate + House, NV Senate + Assembly, ME House (caucus offline), VT Senate + House, NH Senate + House (chamber-only Speaker/President), MA Senate + House (chamber-only)
- **Squatted / hijacked / dead caucus domains**: `kshousedems.com`, `coloradohousegop.com`, `cssrc.us`, `tngopsenate.com`, multiple unreachable AZ / NV / NM caucus URLs
- **Lorem-ipsum placeholder content**: `floridahousedems.com` returned demo posts, do not auto-trust until contents verified human-authored
- **Out-of-scope content traps**: MN House SessionDaily and NE update.legislature.ne.gov are bylined journalism, not member press releases — collecting these would violate the project's "no curated third-party clippings" rule
- **Single-office statewide elected with effectively zero publication**: many state Treasurers / Auditors with last-press-release older than 12 months — cost of monitoring exceeds value of records collected

## Biggest implementation risks (ranked)

1. **WAF defeat at scale** — Akamai/Cloudflare/Imperva block raw httpx across 25%+ of state-government sites. Without a real-Chrome User-Agent strategy from day one, daily cron will fail unpredictably. Already a known pain on senate.gov; will be worse on US House (Drupal HMWP behind Akamai) and large state sites.
2. **Schema for caucus sources** — 196 caucus rows do not fit the existing `senate.json` shape that assumes one row per member. Needs a parent caucus-source row plus per-member aliasing OR a new `caucus.json` seed with explicit attribution model.
3. **Attribution NER for shared chamber feeds** — KY, NC, WV, several others publish chamber-wide feeds with member identity only in the title text. Without a regex+disambiguation layer, all releases will be mis-credited or unattributed.
4. **TLS / dead-domain sweep** is required before any caucus collector ships. ~10 domains observed dead, parked, or cert-broken. Add a pre-collection canary that mass-checks all configured sources weekly.
5. **PDF body extraction generalization** — current TX-specific extractor is good prior art but hardcoded. Refactor into a chamber-agnostic helper before the second PDF-heavy chamber (AZ, FL Senate Publications, LA Senate) ships.
6. **US House WAF on 441 subdomains** — Drupal HMWP is uniform and easy to scrape selector-wise, but Akamai is aggressive. Plan for either rotating residential proxies or a Playwright-based daily run that takes ~20 minutes.
7. **Caucus-only states' partial coverage** — IL, IN, MI, MN have only Democratic caucus content reachable today; Republican caucus sites are unreachable, 403'd, or content-thin. A first-wave launch covers ~half the members per state until R-side recon is closed.

---

## Deliverable artifacts

| Artifact | Location |
|---|---|
| Master inventory (JSON) | `inventory.json` (606 records) |
| Master inventory (CSV) | `inventory.csv` |
| US House inventory | `us_house_inventory.json` (436 members + profile) |
| First-wave curated list | `first_wave_curated.md` |
| Auto-generated top-confidence first-10 | `first_10.json` |
| Do-not-implement list | `do_not_implement.json` (76 records) |
| TX Senate audit | `tx-senate-audit.md` |
| Per-region raw recon | `raw/legislatures_*.json` |
| Caucus enumeration | `raw/caucus_sources.json` |
| WP-JSON discovery | `raw/wp_json_sweep.json` |
| Selector deep-dive | `raw/selector_deep_dive.json` |
| Browser-render verification | `raw/browser_render_verification.json` |
| Synthesis script | `_synthesize.py` |

---

*Prepared 2026-05-01. Confidence on classifications ranges from 0.4 (statewide officials with URL-only verification) to 0.98 (sources with sample release URLs successfully fetched). Re-verify before committing implementation effort to any source above the wave-1 list.*

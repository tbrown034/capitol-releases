# First Wave — 10 Sources to Implement

Curated implementation order with concrete selectors, sample URLs, and known
risks. Pulled from `raw/selector_deep_dive.json`, `raw/exec_govs_ags.json`,
`raw/wp_json_sweep.json`, `raw/legislatures_west.json`, and the browser-render
verification file. Independently re-probe each before committing the seed.

---

## 1. CA Governor — gov.ca.gov

- **Listing**: https://www.gov.ca.gov/newsroom/
- **API**: `https://www.gov.ca.gov/wp-json/wp/v2/posts?per_page=20` ← live, returns full post body in `content.rendered`
- **Detail URL pattern**: `https://www.gov.ca.gov/{YYYY}/{MM}/{DD}/{slug}/`
- **Pagination**: `?page=N` on listing; wp-json paginates with `?page=N&per_page=N`
- **Date**: ISO-8601 in `date_gmt`; on HTML, `time.entry-date` with `datetime` attribute
- **Categories**: filter on `press-releases` and `recent-news` slugs
- **CMS**: WordPress (vip.wordpress.com hosted)
- **Cadence**: daily, multiple per day on session weeks
- **Confidence**: 0.95 (verified live)

**Strategy**: wp_json. Single 30-line collector. Body is in `content.rendered`,
strip HTML to text, fall back to `excerpt.rendered` if empty.

**Risks**: Akamai briefly observed on initial fetch; tip to set `User-Agent: Mozilla/...`. Re-verify weekly that wp-json stays public — California occasionally locks down APIs after press cycles.

---

## 2. CA Attorney General — oag.ca.gov

- **Listing**: https://oag.ca.gov/news
- **RSS**: `https://oag.ca.gov/news/feed` ← live, well-formed
- **Detail URL pattern**: `https://oag.ca.gov/news/press-releases/{slug}`
- **Listing selector**: `.views-row` (Drupal Views)
- **Title selector**: `.views-row .views-field-title a`
- **Date selector**: `.views-row .views-field-created time` (ISO datetime attr)
- **Pagination**: `?page=N`
- **CMS**: Drupal 9
- **Cadence**: weekly+, lawsuit/settlement cycles
- **Confidence**: 0.95

**Strategy**: rss with HTML enrichment. RSS items carry title, link, pubDate.
Body extracted from detail page `article .field--name-body`.

**Risks**: Drupal Views fragility — if the AG's web team changes views modes, selectors break. Add a daily health check that confirms ≥1 `.views-row` exists.

---

## 3. CA Senate — uniform sd01-sd40 Drupal pattern

- **Member list**: https://www.senate.ca.gov/senators
- **Per-senator press**: `https://sd{NN}.senate.ca.gov/press-releases` (note: plural, root path — verified 2026-05-01)
- **Listing selector**: `.view-content.row .views-row` (when wrapped) **or** stride-grouping over sibling `.views-field-*` elements (some sd subdomains skip the `.views-row` wrapper — both forms exist)
- **Title selector**: `.views-field-title a`
- **Date selector**: `.views-field-field-pubdate time[datetime]`
- **Detail URL pattern**: `https://sd{NN}.senate.ca.gov/news/{YYYY}{MM}{DD}-{slug}` or `/press-releases/{slug}`
- **Pagination**: `?page=N`
- **CMS**: Custom Drupal-like (CA Senate platform)
- **Cadence**: weekly per senator
- **Confidence**: 0.85

**Strategy**: httpx_html with stride-fallback. Implement a single profile;
iterate over `[1..40]` for `district` (skip vacancies). Attribution is
unambiguous via subdomain.

**Risks**:
1. The "stride-grouping" mode — when `.views-row` is missing, fields appear as
   siblings in groups of 4 (title, summary, date, image). Brittle to template
   changes. Capture both the wrapped and unwrapped DOM modes.
2. Some senators have a vanity domain alongside the sd## URL — collect both
   and dedup on `(senator_id, source_url)`.

---

## 4. WA Governor — governor.wa.gov

- **Listing**: https://www.governor.wa.gov/news/news-releases
- **RSS**: `https://www.governor.wa.gov/rss/news.xml` ← live
- **Detail URL pattern**: under `/news/` with date-bearing slugs
- **CMS**: SharePoint-style portal (verified)
- **Cadence**: weekly+
- **Confidence**: 0.95

**Strategy**: rss. Single source.

**Risks**: SharePoint date format may include "Updated" timestamps — pin to `<pubDate>`.

---

## 5. WA Attorney General — atg.wa.gov

- **Listing**: https://www.atg.wa.gov/news/news-releases (note: deep-dive corrected the URL from `/press-releases` which 404s)
- **RSS**: `https://www.atg.wa.gov/news/news-releases-rss` ← live
- **Detail URL pattern**: `/news/news-releases/{slug}` — Drupal node URLs
- **CMS**: Drupal 9
- **Cadence**: weekly+
- **Confidence**: 0.90

**Strategy**: rss. Single source.

**Risks**: Same Drupal Views fragility as CA AG. Wire the same health check.

---

## 6. WA Senate Democrats — senatedemocrats.wa.gov

- **Listing**: https://senatedemocrats.wa.gov/news/
- **API**: `https://senatedemocrats.wa.gov/wp-json/wp/v2/posts?per_page=20` ← live, full keyset
- **Per-senator subpaths**: `https://senatedemocrats.wa.gov/{senator-slug}/news/` — confirmed working
- **RSS**: `https://senatedemocrats.wa.gov/feed/`
- **Detail URL pattern**: `/blog/{YYYY}/{MM}/{DD}/{slug}/`
- **CMS**: WordPress
- **Cadence**: daily during session
- **Attribution**: `author` field in wp-json maps to a senator slug; `categories` carry policy tags
- **Confidence**: 0.95

**Strategy**: wp_json. ~24 senators → one collector.

**Risks**:
1. The Republican counterpart at `src.wastateleg.org` is a separate WP install — collect it too in second wave for full chamber coverage.
2. Author IDs are stable but humans (e.g., comms staff) sometimes author releases on behalf of a senator. Verify author→senator mapping on each new author seen.

---

## 7. TX Governor — gov.texas.gov

- **Listing**: https://gov.texas.gov/news
- **RSS**: `https://gov.texas.gov/news/rss` ← live
- **Detail URL pattern**: `/news/post/{slug}` or numeric ID
- **CMS**: Drupal-based custom platform
- **Cadence**: daily
- **Confidence**: 0.95

**Strategy**: rss. Single source.

**Risks**: TX Gov page sometimes serves a 403 to non-browser UA — set realistic UA string. RSS endpoint historically more permissive than HTML.

---

## 8. NC Attorney General — ncdoj.gov

- **Listing**: https://ncdoj.gov/newsroom/
- **API**: `https://ncdoj.gov/wp-json/wp/v2/posts?per_page=20` ← live, default `post` type
- **Detail URL pattern**: `/{slug}/` under newsroom category
- **CMS**: WordPress (theme name still references former AG "joshstein"; current AG is Jeff Jackson)
- **Cadence**: weekly+
- **Confidence**: 0.98 (highest in batch)

**Strategy**: wp_json. Single source.

**Risks**: Theme transition still in progress — selectors on the HTML side may shift; wp-json should be stable. Re-verify slug after first month.

---

## 9. OH Senate — ohiosenate.gov

- **Roster**: https://ohiosenate.gov/members (33 senators)
- **Per-member press**: `https://ohiosenate.gov/members/{slug}/news`
- **Listing pagination**: `?per_page=500` accepts up to 500/page (most senators fit on a single fetch)
- **Detail URL pattern**: `/news/press-releases/{slug}-{numeric_id}` — numeric ID at the end is stable for upsert
- **CMS**: Custom (Ohio Statehouse common platform — Drupal-derived)
- **Cadence**: weekly+
- **Confidence**: 0.95

**Strategy**: httpx_listing_walk. One profile; iterate over slugs.

**Risks**: Slugs not stable across name changes (marriage, etc.). Maintain the
slug→senator mapping separately so we can re-key on rename.

---

## 10. OH House — ohiohouse.gov

- **Roster**: https://ohiohouse.gov/members (99 representatives)
- **Per-member press**: `https://ohiohouse.gov/members/{slug}/news` (identical platform to OH Senate)
- **Cross-validation**: chamber-level aggregate at `https://ohiohouse.gov/news/republican` (256 pages) and `/news/democratic` (206 pages) lets us cross-check that per-member walks captured everything
- **Detail URL pattern**: same numeric-ID-suffix as Senate
- **Cadence**: daily during session
- **Confidence**: 0.95

**Strategy**: httpx_listing_walk. Reuse OH Senate code path verbatim — same
template. Single biggest member-coverage win in the wave: 99 representatives
in essentially zero marginal effort after OH Senate ships.

**Risks**: Same as OH Senate. Plus the cross-validation path doubles fetch
volume (132 senators+reps × 2 chamber pages); be polite with rate limiting.

---

## Coverage delivered by first wave

| Tier | Count |
|---|---|
| Governors | 3 (CA, WA, TX) |
| Attorneys General | 3 (CA, WA, NC) |
| State senators | 24 (WA D caucus) + 40 (CA Senate) + 33 (OH Senate) = **97** |
| State representatives | 99 (OH House) |
| Caucus-tier sources | 1 (WA Senate Democrats) |
| Distinct member principals reachable | ~199 |
| States touched | 5 (CA, WA, TX, NC, OH) |

## Implementation sequencing

Ship in this exact order — each step de-risks the next:

1. **CA AG** (RSS) — easiest possible target, validates the new collector framework
2. **CA Governor** (wp-json) — first wp-json collector
3. **TX Governor** (RSS) — repeats the CA AG path against a different RSS shape
4. **WA Governor** + **WA AG** (both RSS) — bulk-add on the same RSS pattern
5. **NC AG** (wp-json) — second wp-json source, validates per-state isolation
6. **WA Senate Democrats** (wp-json with member subpaths) — first caucus-tier collector; introduces the `party` axis to the seed schema
7. **OH Senate** (httpx_listing_walk) — first chamber-level walk on a non-TX, non-WP platform; shake out per-member scaffolding
8. **OH House** (same code path) — proves the OH chamber profile generalizes
9. **CA Senate** (40-subdomain Drupal walk) — biggest single fan-out; validates the per-member subdomain pattern at scale before second wave attacks asmdc.org with 80 assembly subdomains

Stop the wave at #9 (OH House) and run the full pipeline for two weeks before
committing to CA Senate's 40-subdomain fan-out — that's where complexity ramps.

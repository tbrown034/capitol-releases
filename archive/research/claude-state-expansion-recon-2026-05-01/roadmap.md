# Implementation Roadmap

Phased rollout. Each phase has explicit kill criteria; do not advance until the
prior phase passes data-quality tests in production for two cron cycles.

## Phase 0 — Pre-flight (week 1, before any new state ships)

Fix in TX Senate before broadening. None are blocking but all compound at scale.

1. Move `date_confidence` assignment to AFTER the year-header fallback in `tx_senate_collector.py:188`.
2. Replace the truth-check date regex with `_extract_items` reuse (10 lines).
3. Fix `tx_truth_check.py:60` filter from `'photo_release'` (never assigned) to `'other'` (videos).
4. Stop mutating video titles; expose `is_video` boolean instead.
5. Refactor `tx_extract_bodies.py` into a chamber-agnostic `extract_bodies.py` that takes a per-chamber profile (URL pattern, content-type sniff rules, body selector for HTML, PDF cleaning helper).
6. Centralize the duplicated `_load_env` helpers.
7. Add per-senator stale alerts for TX (analog of `STALE_DAYS` in the federal pipeline).
8. Build a hardened httpx client wrapper with browser-class headers, certifi root, and explicit timeout/skip behavior — every new state collector consumes this.
9. Build a daily TLS/dead-domain canary that probes every configured `press_release_url` and `member_press_url_pattern`.

Deliverable: green CI, TX corpus unchanged.

## Phase 1 — Wave-1 ship (weeks 2–4)

Implement the 10 sources in `first_wave_curated.md`, in the documented order.
Each requires:
- Seed entry under `pipeline/seeds/` (new `state_executives.json`, `state_caucuses.json`, `oh_senate.json`, `oh_house.json`, `ca_senate.json`, `wa_executives.json`, `tx_executives.json`, `nc_executives.json`)
- Collector entry under `pipeline/collectors/` (some can share a generic `wp_json_collector` and `rss_collector`)
- Health check shape matching the federal pipeline
- Per-source data quality tests (≥1 record/week expected, dates parseable, body length floor)

Kill criteria:
- If the WAF/header strategy fails for ≥2 of the wp-json sources, halt and switch to a Playwright fallback before proceeding to OH chambers.
- If wp-json content drift (response shape changes) takes down a collector for >24h, build a daily smoke test for every wp-json endpoint before moving to wave 2.

Deliverable: 9 production collectors, ~200 new principal-level coverage rows in DB.

## Phase 2 — Wave-2 caucus expansion (weeks 5–8)

Add the verified-wp-json caucus sources from the recon:

- MI Senate Dems + MI Senate GOP (38 senators)
- MN Senate DFL + MN House GOP
- PA Senate Democrats (21 senators)
- TN House GOP
- IA Senate Democrats
- IL Senate GOP + IL Senate Democrats (Joomla)
- CT Senate Democrats
- CA Assembly GOP (asmrc.org) + CA Assembly Democrats (asmdc.org per-member subdomains)
- DE Senate D + DE House caucuses
- NM Senate D
- SC Senate GOP + SC House Dems
- TN House Dems

This phase introduces:
- The `caucus.json` seed schema with `party` axis
- Cross-caucus dedup (members get one record even if covered by both caucus and chamber sources)
- Member-attribution NER for caucus posts where the author column doesn't carry the senator (fall back to title-prefix regex `Sen. {Lastname}, {party}-{city}` / `Rep. {Lastname}`)

Kill criteria:
- If member-NER accuracy on a 100-sample manual audit is <90% per caucus, stop adding caucuses until the NER is hardened.

Deliverable: ~120 net new principal-level rows.

## Phase 3 — Wave-3 selected statewide officials (weeks 9–12)

Add the highest-publication-volume non-Gov-non-AG offices:

- TX Comptroller (RSS), TX Land Commissioner, TX Ag Commissioner
- NY Comptroller, NY Senate (drupal `article.c-block-press-release` selectors)
- OH Auditor, OH Treasurer
- CA Controller, CA SPI, CA Insurance Commissioner
- IL SoS, IL Comptroller
- WA Insurance Commissioner, WA Treasurer
- GA SoS, GA Ag Commissioner

Plus NY Senate per-member newsroom (Drupal, browser-headers fix for the 403).

Kill criteria:
- WAF defeat strategy must be production-stable before NY Senate ships (Akamai is the single biggest external risk).

Deliverable: ~20 single-office sources + 63 NY senators.

## Phase 4 — US House (weeks 13–18)

Two-pronged approach:

1. **Drupal HMWP collector** — uniform `/media/press-releases/` listing template across ~57% of probed members. One config covers all Drupal HMWP members.
2. **Selector fallback** for the ~10% on WordPress and the few on legacy ColdFusion / custom platforms.

Hard prerequisite: WAF defeat. House Member Website Platform fronted by
Akamai — same problem as senate.gov. Plan for either a Playwright daily run
(20-minute window over 441 subdomains) or rotating residential proxies.

Kill criteria:
- If sustained Akamai blocks affect >20% of members for >2 days, suspend daily collection and fall back to weekly Wayback sweeps with `web.archive.org` URLs.

Deliverable: ~441 new principal rows. This roughly triples the corpus.

## Phase 5 — Long tail (weeks 19+)

- All remaining statewide officials in `inventory.json` with `classification = needs_profile`
- The "needs profile" caucus sources (72 records)
- States blocked at wave-1 due to no infrastructure (IN, KY, LA, MO, NE, NH, VT, WV) — these need a manual recon round to identify ANY usable source (likely state media press feeds, not government press feeds — out of scope per the project's "no curated third-party clippings" rule unless we explicitly broaden scope)

## Stop conditions for the whole expansion

The project should pause adding new sources when ANY of these is true:

1. Daily cron exceeds 30 minutes total runtime (current TX run is ~70s; budget ~25min for federal + state full corpus)
2. Per-source dead-source alerts exceed 5% of configured sources for >7 days
3. Member-attribution accuracy drops below 95% in a manual audit
4. Per-record cost (compute + WAF defeat overhead) exceeds the cost model in `docs/business_plan.md`

## Sources marked `do_not_implement` until manually re-profiled

See `do_not_implement.json` for the 76-row list. Categories:

- 18 chamber-tier sources where no member press infrastructure exists
- ~20 caucus URLs that are dead, parked, hijacked, or returning lorem-ipsum
- ~30 statewide elected offices with effectively zero publication cadence
- 8 states (IN, KY, LA, MO, NE, NH, VT, WV) where no fully verified source exists at any tier

Each of these requires an analyst pass — at least one human-curated WebFetch or a Playwright probe — before it should be re-classified.

# Texas Senate Implementation Audit — 2026-05-01

Independent review of `pipeline/collectors/tx_senate_collector.py`,
`pipeline/commands/tx_extract_bodies.py`, `pipeline/commands/tx_truth_check.py`,
and `pipeline/seeds/tx_senate.json` against live DB state.

## Corpus snapshot (DB)

| Metric | Value |
|---|---|
| Active TX records (deleted_at IS NULL) | 314 |
| `content_type='press_release'` | 304 |
| `content_type='other'` (videos) | 10 |
| `published_at` NULL | 0 |
| `date_confidence < 0.5` | 0 |
| `date_source` distinct values | 1 (`listing_text`, all 314) |
| Pre-2025 records | 0 |
| Records with Jan 1 fallback artifact | 0 |
| Duplicate `(senator_id, source_url)` rows | 0 |
| Press-release rows missing body (`length(body_text) < 50`) | 0 |
| URL shape: `.pdf` / `press.php` / `videoplayer.php` / other | 158 / 146 / 10 / 0 |

## Coverage gap

Seed has 30 senators (D4 vacant — Creighton resigned 2025-10-02,
special election in calendar). DB has data for **18 of 30 seeded
senators**. **12 senators have zero records:**

- tx-d02-hall, tx-d05-schwertner, tx-d06-alvarado, tx-d09-rehmet
  (sworn Feb 2026, expected empty per seed notes), tx-d10-perry,
  tx-d13-miles, tx-d19-flores, tx-d24-campbell, tx-d25-creighton
  (vacant), tx-d26-menendez, tx-d28-king, tx-d30-hancock

This is **not necessarily a collector bug** — TX state senators publish
sporadically. But the project has no per-senator floor expectation
or alert. Without that, a regression that broke (say) Hancock's page
would never page. Recommend a per-senator stale alert similar to the
US Senate `STALE_DAYS` mechanism.

## Code-level findings

### Risk — title mutation for video items
`tx_senate_collector.py:193-194` prepends `"VIDEO: "` to titles that don't
already begin with `VIDEO`. This rewrites the source title before it
hits the DB. If TX changes its convention (e.g., titles start with
`Sen. X on Y`), our DB title diverges from source. Lower-risk
alternative: emit a separate `is_video` boolean and let presentation
prepend at render time.

### Risk — content_hash uses title|source_url only
`tx_senate_collector.py:89`: `content_hash(f"{item['title']}|{item['source_url']}")`.
This means a substantive edit to a release that keeps the same title
and URL produces an identical hash. The DB also has a `content_versions`
mechanism elsewhere in the project; TX appears to bypass it. Re-extraction
of bodies in `tx_extract_bodies.py:244` recomputes a sha256 over the
extracted text and stores it as `content_hash` — so the listing-side
hash gets immediately overwritten by the body-side hash. The two
collectors compute fundamentally different `content_hash` values; whatever
read code expects will get inconsistent semantics depending on whether
body extraction has run yet.

### Risk — year header drift in `_extract_items`
`tx_senate_collector.py:140-145`: walks `find_all(["h3", "p"])` in
document order, treating any `<h3>` whose text matches `\d{4}` as a year
header that contextualizes following `<p>` elements. If a senator's page
gains an unrelated `<h3>2024 Legislative Priorities</h3>` block of
nav/sidebar content, every following `<p>` would be tagged with that
year. The fallback to `datetime(current_year, 1, 1)` (line 188) would
then set `published_at` to `2024-01-01` for unrelated items. Today the
fallback fires zero times across 314 records, so the bug is latent. A
small hardening: only fall back to year if the `<p>` actually contains
a recognizable date-shaped string AND the listing parent has class
`.prlist` or sits under `<main>`. Or simpler: drop the fallback. If
we cannot read MM/DD/YYYY off the `<p>` itself, mark the date NULL
and surface in QA.

### Risk — selector accepts non-press hrefs
`tx_senate_collector.py:163-172` allows three URL shapes: `*.pdf`,
`/press/`, `videoplayer.php`, `press.php`. If a senator adds (e.g.) a
PDF to a sidebar that isn't a press release, it gets ingested. There is
no semantic check that the `<p>` is inside the press list container.
Low priority but worth noting if we expand to other states with similar
shapes.

### Risk — body extractor truncates at first match for video URL filter
`tx_extract_bodies.py:195`: WHERE clause excludes `videoplayer.php` URLs
correctly. Good.

### Inefficiency — extractor sleeps unconditionally
`tx_extract_bodies.py:222`: `time.sleep(0.6)` per row. For a one-time
backfill over 304 PDFs that's ~3 minutes — fine. But the same script
runs as cron daily; on a busy day with 5 new PDFs the sleep dominates
nothing, so it's harmless. Mention only because if we use the same
helper across 50 states it could matter.

### Inefficiency — extractor does not parallelize
Per-PDF synchronous fetch+pdfplumber. Acceptable for TX scale. Not
acceptable for 50-state scale with PDF-heavy chambers. Plan for an
async or process-pool variant before broad expansion.

### Maintainability — extractor lives outside the collector
`tx_extract_bodies.py` is a separate `commands/` script keyed on
`s.chamber = 'tx_senate'`. That hardcodes TX. As soon as a second
state ships, this either splits into `xx_extract_bodies.py` or grows
a chamber dispatch. Recommend a single `extract_bodies.py` parameterized
by content_type pattern (`pdf` vs `html` selector profile per chamber)
before adding the next state.

### Maintainability — truth-check parses with naive regex
`tx_truth_check.py:94`: `re.findall(r"(\d{1,2}/\d{1,2}/(\d{4}))", text)`
counts every MM/DD/YYYY substring on the rendered page. This will
include sidebar dates, footer "Page generated 4/27/2026" stamps,
calendar widgets, etc. The ±1 tolerance hides small inaccuracies. To
make this trustworthy, run the same `_extract_items` walker as the
collector and compare in-window items, not raw date matches.

### Maintainability — truth-check filters `photo_release` but collector never assigns it
`tx_truth_check.py:60`: `pr.content_type != 'photo_release'`. The TX
collector only emits `press_release` and `other` (line 192 of the
collector). The filter is dead. The truth-check should filter `'other'`
instead — currently DB count includes 10 video rows, while live count
matches all dates including non-video items. Net effect: live count is
likely systematically higher than DB count for senators with videos,
which is why the ±1 tolerance is so wide.

### Maintainability — env loader duplicated
Both `tx_extract_bodies.py:38-46` and `tx_truth_check.py:24-33` define
identical `_load_env`. Already duplicated in other commands too.
Centralize before adding state #2.

## Date confidence is misleading

Every TX record has `date_confidence = 1.0`. The collector sets 1.0
whenever a date string matched the regex (line 88). But the collector
then trusts the year header for `<p>` blocks that don't have MM/DD/YYYY
inline — and assigns Jan 1 of the year header with the same 1.0 confidence
because the assignment happens before the confidence is computed.
**Audit: zero rows have Jan-1 fallback dates today**, so this is latent.
But code-as-written would mark a year-header fallback as confidence 1.0,
which is not what the federal pipeline does. Fix: compute confidence after
the fallback step.

## Things working well

- `(senator_id, source_url)` is unique across all 314 rows. Upsert and dedup are sound.
- `pdfplumber` `x_tolerance=3` extraction handles the TX template's space-collapsed glyphs well — body texts are clean enough that no rows fail the 50-char floor.
- The `_rejoin_word_per_line` helper is genuinely useful prior art for other states with one-word-per-line PDF templates.
- Health-check shape matches the federal collectors, so `pipeline health` works against TX without special-casing.
- press.php URLs (HTML body) and PDF URLs both flow through one path with content-type sniff at extract time. Clean.

## Top fixes before broadening to other states

1. **Move date confidence after fallback** (3-line fix in `_extract_items`).
2. **Replace truth-check date regex with `_extract_items` reuse** (10-line fix).
3. **Fix truth-check content_type filter** (`photo_release` → `other`).
4. **Stop mutating video titles**, expose via `is_video` flag instead.
5. **Refactor body extractor into a chamber-agnostic helper** before the second state ships.
6. **Add per-senator stale alerts** (TX has no analog to `STALE_DAYS`).

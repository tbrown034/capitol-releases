---
name: onboard-senator
description: Propose a senate.json config entry for a new or re-seated senator by probing their site. Use when a new senator is sworn in, a seat changes hands, or a senator's URL moves.
argument-hint: <senator-id> <official-url>
disable-model-invocation: true
---

# Onboard Senator

Generate a draft `pipeline/seeds/senate.json` entry for a senator who isn't in config yet (or needs re-probing). This skill **proposes**; the user reviews and decides whether to apply.

## Inputs

- `$1`: proposed `senator_id` (kebab-case, `lastname-firstname` convention — match existing IDs). Example: `husted-jon`.
- `$2`: their `official_url` root (e.g. `https://www.husted.senate.gov`). No trailing slash.

If either arg is missing, ask the user — do not guess. If `$1` collides with an existing entry in `senate.json`, stop and report; the user likely wants `validate-senator` instead.

## Steps

1. **Probe candidate press-release URLs.** Senate sites cluster around a small set of path conventions. Try these in order, stopping at the first one that returns 200 with visible press-release-looking content:

   - `$2/newsroom/press-releases/`
   - `$2/newsroom/press-releases`
   - `$2/news/press-releases`
   - `$2/press-releases/`
   - `$2/press-releases`
   - `$2/news/`
   - `$2/newsroom/`
   - `$2/media/`

   Use `WebFetch` with a prompt like: "Does this page list press releases? If yes, count items on page 1 and report the dates of the first and last visible item. If no, say what this page is."

2. **Probe for RSS.** Try these in order:

   - `$2/rss/`
   - `$2/feed/`
   - `$2/press-releases/feed/`
   - `$2/newsroom/press-releases/feed/`
   - `$2/news/feed/`

   Use `WebFetch` asking: "Is this a valid RSS feed? If yes, how many items, and what's the date range?" Dead paths return 404 or HTML — note but continue probing.

3. **Identify the CMS family.** From the HTML source of the working press-release page, look for:

   - `wp-content`, `wp-json`, `elementor` → `senate-wordpress`
   - `drupal`, `sites/default/files` → `senate-drupal`
   - `cfm?`, `cfid=`, `cftoken=` → `senate-coldfusion`
   - `sf-events`, `ASP.NET` hidden fields → `senate-aspnet`
   - Anything else → `senate-generic`

   If WordPress, also probe `$2/wp-json/wp/v2/posts?per_page=1` — a 200 with JSON means the WP REST API is open, which is a superior future collector path.

4. **Pick collection method.** Decide in this order:

   - If RSS works and has ≥ 10 recent items spanning ≥ 2 weeks → `rss` (cheapest, most reliable).
   - Else if the HTML list page loads with visible items in non-JS source (check by re-fetching and confirming items are in raw HTML, not injected) → `httpx`.
   - Else → `playwright` (JS-rendered or selector-heavy).

5. **Draft the JSON entry.** Produce a block matching the shape of existing entries. Use `null` for selectors we'd need a collector dev-pass to fill in:

   ```json
   {
     "senator_id": "<$1>",
     "full_name": "<extracted from site header or ask user>",
     "party": "<?>",
     "state": "<?>",
     "official_url": "<$2>",
     "press_release_url": "<working URL from step 1>",
     "parser_family": "<from step 3>",
     "requires_js": <true if playwright, else false>,
     "pagination": { "type": "unknown" },
     "selectors": {
       "list_item": null,
       "title": null,
       "date": null,
       "detail_link": null
     },
     "confidence": <0.5 if probed cleanly; 0.3 if guessed>,
     "notes": "<one-line summary: CMS, items/page, date range observed, date verified>",
     "last_verified": "<today's date>",
     "recon_status": "discovered",
     "collection_method": "<from step 4>",
     "rss_feed_url": "<from step 2, or null>"
   }
   ```

   For `party` and `state`: if you cannot extract them from the site's "About" or masthead, **ask the user** — do not guess these fields, a wrong party is a visible product bug.

6. **Report.** Show the user:

   - The working press-release URL and how many items were visible.
   - The RSS URL (if any) and its item count.
   - The CMS family and whether WP JSON API is available.
   - The chosen `collection_method` and why.
   - The full JSON block, ready to paste into `pipeline/seeds/senate.json`.
   - A next-step line: "Run `pipeline/.venv/bin/python -m pipeline health --senators $1` after paste to confirm the collector picks this up."

## Guardrails

- This skill never writes to `senate.json`. The user pastes the block manually. Config changes are too consequential for auto-edits.
- Never fabricate selectors. If the HTML structure isn't obvious from a WebFetch, leave selectors `null` and flag that a collector dev-pass is needed.
- Expected-zero case: if the site has zero releases (e.g. a brand-new senator like Armstrong was on 2026-04-18), say so plainly and set `confidence: 0`. Still produce the entry — monitoring infrastructure needs the row.
- Never suggest running `pipeline update` or a backfill from this skill. Discovery first, then the user decides what to run.

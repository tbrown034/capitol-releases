---
name: validate-senator
description: Spot-check one senator's collector by diffing DB record count against their live press-release index. Use when a collector looks suspicious or after config changes.
argument-hint: <senator-id>
disable-model-invocation: true
---

# Validate Senator

On-demand check: does our DB hold roughly what this senator's site actually publishes?

Not a health check (that's `python -m pipeline health`). This is a sanity check when something looks off for a specific senator — low counts, stale last-seen, post-config-edit verification.

## Inputs

- `$1`: senator-id from `pipeline/seeds/senate.json` (e.g. `warren-elizabeth`, `king-angus`, `armstrong-alan`).

If no argument is given, ask the user which senator; do not guess.

## Steps

1. **Load config.** Read `pipeline/seeds/senate.json` and locate the member where `senator_id === $1`. If missing, stop and tell the user — don't proceed with a fuzzy match. Capture: `full_name`, `press_release_url`, `collection_method`, `rss_feed_url`, `selectors`, `notes`, and `confidence`.

2. **Count DB records for 2025-01-01 → today.** The project venv lives at `pipeline/.venv/` — system Python lacks `psycopg2`, so invoke the venv Python explicitly:

   ```bash
   pipeline/.venv/bin/python -c "
   import os, psycopg2
   from pathlib import Path
   env = Path('pipeline/.env')
   if env.exists():
       for line in env.read_text().splitlines():
           if '=' in line and not line.startswith('#'):
               k, v = line.split('=', 1); os.environ.setdefault(k.strip(), v.strip())
   conn = psycopg2.connect(os.environ['DATABASE_URL'])
   cur = conn.cursor()
   cur.execute(\"\"\"
     SELECT
       count(*) FILTER (WHERE deleted_at IS NULL),
       count(*) FILTER (WHERE deleted_at IS NULL AND published_at >= %s),
       max(published_at),
       max(scraped_at)
     FROM press_releases WHERE senator_id = %s
   \"\"\", ('2025-01-01', '$1'))
   print(cur.fetchone())
   "
   ```

   Record: total live, in-window, most recent published, most recent scraped. Note the column is `scraped_at`, not `collected_at`.

3. **Fetch the live index.** Use `WebFetch` on `press_release_url`. If the senator is RSS-first and the HTML page is a dead end, also fetch `rss_feed_url`.

   From the response, estimate visible count signals:
   - Items on page 1 and the **date range they span**. Use the span to derive a per-month rate, then multiply by the number of months since 2025-01-01. Don't multiply `per-page × total-pages` — that's all-time, not in-window, and most senator sites predate 2025.
   - RSS feed item count + date range (feeds usually cap at 20–100 most recent items).

   These are **estimates**, not truth. RSS undercounts history; HTML pagination overcounts (captures pre-2025 items). Note the method you used in the report.

4. **Compare.** Compute three signals:
   - **DB coverage:** in-window count vs any total the site exposes.
   - **Freshness:** days since `max(published_at)`. Flag if > 14 days and the senator isn't on the expected-zero list (Armstrong-ND as of 2026-04-18).
   - **Collected-vs-published gap:** if `max(collected_at)` is recent but `max(published_at)` is stale, the collector is running but returning nothing new — that's the interesting state.

5. **Classify.** Pick one:
   - **HEALTHY** — counts in range, freshness acceptable.
   - **STALE** — collector runs but nothing new for > 14 days, no expected-zero reason.
   - **UNDERCOUNTING** — DB materially below what the live page exposes.
   - **EXPECTED-ZERO** — matches known-bare senator (Armstrong).
   - **UNKNOWN** — live page unreadable, blocked, or too noisy to estimate.

6. **Report.** Keep it tight:

   ```
   <senator-id>  <full_name>
   status:     <HEALTHY | STALE | UNDERCOUNTING | EXPECTED-ZERO | UNKNOWN>
   db total:   <n>   in-window: <n>
   latest pub: <date>  (<n> days ago)
   latest run: <timestamp>
   live signal: <what the site suggests>
   method:     <rss|httpx|playwright>   confidence: <0–1>
   notes:      <one line, only if non-obvious>
   next step:  <specific, or "none">
   ```

   If `UNDERCOUNTING` or `STALE`, propose one concrete next step: re-run `python -m pipeline health --senators $1`, inspect selectors, or run the targeted backfill. Do not auto-run these — the user decides.

## Guardrails

- Read-only. This skill never writes to the DB, never edits `senate.json`, never triggers a scrape.
- One senator per invocation. For the full-fleet picture, use `python -m pipeline health` and `python -m pipeline stats`.
- Respect the expected-zero list. Armstrong-ND reporting zero is not a bug.
- If the live site blocks the fetch (Cloudflare, JS-only, 403), say so and fall back to RSS if available — don't fabricate a count.

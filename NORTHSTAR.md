# NORTHSTAR — Sunday, May 3, 2026

**One-line goal:** Reframe Capitol Releases from "US Senate archive" to "Full Congress, 535 members" and ship to production by EOD.

**One-line positioning:** *Every member of Congress. One archive. Every press release back to Jan 2025, updated 4x daily, with provenance.*

---

## Why today

Yesterday landed the technical foundation: 437 House members in the database, 35,687 records, schema renamed to `officials` / `official_site_items`, /house and /house/[id] routes live, daily cron updated. The data layer is Congress-wide. The product framing is still Senate-shaped. Today closes that gap.

This is also the strongest portfolio reframe available — "535 members of Congress" reads more decisively to a hiring manager than "100 senators" and matches what the product actually is now.

---

## Launch bar — bulletproof, not 80%

We do not ship at "80% and we'll figure out the rest." We ship after each House member's status is one of:

1. **CLEAN** — record_count ≥10, reaches Jan 2025, no internal gaps, mean confidence ≥85%
2. **OUTLIER (verified)** — collector works but the office publishes little or nothing. Verified via web search (resignation? recent appointment? quiet member?). Flagged in seed JSON with `expected_low_volume: true` or `expected_zero: true` + reason.
3. **KNOWN GAP (documented)** — collector struggles or fails. Investigation noted in `docs/coverage-troublesites-2026-05-03.md` with diagnosis + planned fix.

Categories 1+2 must hit ≥350/437 House members (80% truly clean). Category 3 is allowed but never silent — every member appears in the public methodology page with status.

**Senate keeps its existing 90/100 status.** Senate gap closure is a separate track this week.

---

## Tracks (parallel)

### Track A — Coverage push (Claude, ~2.5hr)

| ID | Action | Done when |
|---|---|---|
| A1 | Re-run 58 Bucket A House members blocked by Akamai cooldown yesterday. Concurrency 3, Chrome 130 headers. | Members report back into DB or return verified-zero |
| A2 | Deepen WP-JSON House rescue using broadened slug fallback (memory: Jeffries-style "press-release" singular) | All 10 WP House members re-fetched |
| A3 | Date-from-parent fallback in `pipeline/backfill.py extract_item_data` for heading-only listings | 15 null-dated records have populated `published_at` |
| A4 | Run new diagnostic script (Track D3 below) → produce per-member status JSON | `docs/coverage-diagnostic-2026-05-03.json` exists |
| A5 | Probe each "0 records" + "suspicious round number" House member with Playwright. Classify "they" (truly quiet) vs "us" (scraper bug). | All zero/round-number members triaged |

### Track B — Outlier infrastructure (Claude, ~1hr)

| ID | Action | Done when |
|---|---|---|
| B1 | Add `expected_low_volume: bool`, `expected_zero: bool`, `outlier_reason: string` fields to `pipeline/seeds/house.json` and `senate.json` schema | Schema updated, both seeds round-trip cleanly |
| B2 | Suppress P0 zero-record alerts for flagged members in `pipeline/lib/alerts.py` | Alert noise stops on confirmed outliers |
| B3 | Add JSON Schema doc for the new fields in `pipeline/seeds/SCHEMA.md` | Schema doc updated |
| B4 | Apply outlier flags to confirmed members from A5 web research | All researched outliers flagged |

### Track C — UI reframe (Claude, ~3hr)

| ID | Action | Done when |
|---|---|---|
| C1 | Homepage: hero copy "Every member of Congress" already done; add 535-member counts, House+Senate split, recent-records-by-chamber widget | Homepage reads Congress-wide |
| C2 | `/search` — add chamber filter pills (All / Senate / House), wire to query layer | `?chamber=house` returns House-only, etc. |
| C3 | `/trending` — same chamber filter pills | Trending honors chamber scope |
| C4 | `/social` — same chamber filter pills (verify Bluesky has House handles; if not, document) | Filter present even if House Bluesky is empty for now |
| C5 | New `/speeches` route surfacing Congressional Record floor speeches with chamber filter (currently Senate-only collector; House is a future expansion) | Route exists, Senate speeches render, chamber filter present (House shows "expansion coming") |
| C6 | `/methodology` page (Codex draft, Claude integrates, Trevor approves on preview) | Public, links from footer |
| C7 | Header nav audit: ensure /senators, /house, and a future /congress directory are discoverable; remove Senate-only language | Nav reads Congress-wide |

### Track D — Codex tasks (parallel, ~3hr Codex time)

See "Codex briefs" section below. Four tasks, run them in this order: D1 → D2 → D4 → D3 (D3 depends on B1's seed schema landing).

### Track E — Verification + ship (Claude, ~1hr)

| ID | Action | Done when |
|---|---|---|
| E1 | Vercel preview deploy. Smoke test: home, /search, /trending, /social, /speeches, /methodology, /senators, /house | All routes 200, no jurisdictional leaks visible |
| E2 | `python -m pipeline test` (26 Senate quality checks) | All pass |
| E3 | `python -m pipeline back-coverage` (Senate + House) | Senate 90/100, House categorized |
| E4 | `python -m pipeline coverage-diagnostic` (new from D3) | Final per-member status doc generated |
| E5 | Tag release `v1-congress`, push to prod | Live on capitolreleases.com |
| E6 | Devlog entry, push to GitHub | `docs/devlog.md` updated |

---

## Defer (not today, explicitly)

- 18 Next.js+GraphQL House Playwright collectors (~5% of corpus, document as known gap in methodology page)
- Senate's 10 known back-coverage gaps (separate this-week track)
- `017_official_sources.sql` migration (post-soak, not user-facing)
- `senators` / `press_releases` compat view drop (post-soak)
- `/brief` Congress-wide reframe (deferred; brief stays Senate-only voice for now)
- House floor speech collector (House Congressional Record path not yet built)
- House Bluesky handles (only Senate handles verified currently)

---

## Codex briefs (5.5 high reasoning)

Sequence: **D1 → D2 → D4 → D3** (D3 needs Track B1 seed schema landed first).

### D1 — Jurisdictional Leak Audit (read-only, full sweep)

> **Context:** Yesterday's schema rename (`senators` → `officials`, with new `chamber` and `jurisdiction` columns) shipped 4 known jurisdictional leaks that you caught in PR review. Today we're reframing the homepage as "Full Congress" and need confidence there are zero remaining leaks before going live.
>
> **Task:** Walk every SQL query in `app/` and `pipeline/` that references `officials`, `official_site_items`, `social_posts`, `floor_speeches`, or the legacy `senators`/`press_releases` view names. Classify each:
>
> - **Federal-only** — should filter `jurisdiction='us' AND (chamber IN ('senate','house') OR branch='executive')`
> - **Senate-only** — must filter `chamber='senate' AND jurisdiction='us'`
> - **House-only** — must filter `chamber='house' AND jurisdiction='us'`
> - **Cross-chamber federal** — must filter `jurisdiction='us'` only, no chamber filter
> - **State-scoped** — intentional, jurisdiction != 'us'
>
> **Output:** a markdown table at `docs/codex-leak-audit-2026-05-03.md` with columns: `file:line | query summary | current scope | intended scope | leak? (Y/N) | suggested fix`. Don't write the fixes — produce the audit only.
>
> **Files of interest:** `app/lib/queries.ts`, `app/lib/analytics.ts`, `app/lib/transparency.ts`, `app/lib/trending.ts`, `app/api/**/route.ts`, `pipeline/commands/brief.py`, `pipeline/commands/health_report.py`, `pipeline/commands/update.py`, `pipeline/lib/alerts.py`. Use ripgrep liberally.
>
> **Constraint:** This Next.js version has breaking changes from your training data — read `node_modules/next/dist/docs/` before commenting on any frontend pattern.

### D2 — Methodology Page (draft, Claude integrates)

> **Context:** Capitol Releases is launching as a 535-member Congress archive today. We need a public methodology page that holds up to journalist scrutiny — explains scope, exclusions, known low-volume offices, deletion handling, provenance. This page is one of the surfaces a hiring manager opens.
>
> **Task:** Read `CLAUDE.md` (project root), `GOALS.md`, `ABOUT.md`, the "Scope Decisions" + "Known Limits" sections of CLAUDE.md, and `pipeline/seeds/senate.json` + `pipeline/seeds/house.json` for any member with `expected_low_volume: true` or `expected_zero: true`.
>
> Draft `app/methodology/page.tsx` (Next.js 16 App Router, Server Component, Tailwind 4, TypeScript). Sections:
> 1. **What we collect** — original content from official .gov sites, content_type taxonomy
> 2. **What we don't** — third-party clippings, campaign content, predecessor coverage on seat changes
> 3. **How dates work** — date_source, date_confidence, provenance
> 4. **Known low-volume offices** — pull from seed flags, render as a sortable table with: name, chamber, district/state, status (LOW_VOLUME / ZERO_BLOCKED / KNOWN_GAP), reason, last_verified date
> 5. **Deletion + archival permanence** — deleted_at tombstones, content versioning
> 6. **Update cadence** — 4x daily cron, 13:00 / 17:00 / 21:00 / 01:00 UTC
> 7. **Coverage status** — link to the diagnostic doc D3 produces
>
> **Voice:** journalist voice (Trevor's, Roll Call/Axios brief shape) — readable, AP-clean, short paragraphs (1-3 sentences max). No corporate hedging. No marketing language. No emojis. Spaced em dashes only (` — `).
>
> **Constraint:** Read `node_modules/next/dist/docs/` before writing — this version has breaking changes.
>
> **Output:** the .tsx file + footer link wired into `app/components/Footer.tsx` (or wherever the footer lives — grep first).

### D3 — Coverage Diagnostic CLI (depends on B1)

> **Context:** We need a per-member diagnostic that classifies every active House and Senate member's coverage status. Output drives the methodology page (D2) and our own troubleshooting list. **Wait until Claude confirms Track B1 (seed schema) has landed before starting — you need to read the new `expected_low_volume` field.**
>
> **Task:** Write `pipeline/commands/coverage_diagnostic.py` that:
> 1. Queries `officials JOIN official_site_items` for every active member where `chamber IN ('senate','house') AND jurisdiction='us'`
> 2. Per member computes:
>    - `record_count`
>    - `date_min`, `date_max`
>    - `reaches_jan_2025` (boolean)
>    - `internal_gap_days_max`
>    - `last_record_age_days`
>    - `mean_date_confidence`
>    - `status_class`: one of CLEAN | SHALLOW | INTERNAL_GAP | LOW_VOLUME | NO_DATA | ZERO_BLOCKED | OUTLIER_VERIFIED
> 3. Cross-references seed: `collection_method`, `recon_status`, `last_verified`, `expected_low_volume`, `expected_zero`, `outlier_reason`
> 4. Outputs:
>    - `docs/coverage-diagnostic-2026-05-03.json` (machine-readable)
>    - `docs/coverage-troublesites-2026-05-03.md` (human-readable, grouped by status_class, sorted by severity, one row per troubled member: name, chamber, state/district, official URL, status_class, diagnosis, suggested fix)
>
> **The .md must be checkable by a human in <10 minutes.** Each row ≤2 sentences.
>
> **Constraint:** Reuse query logic from `pipeline/commands/back_coverage.py` and `pipeline/commands/health_check.py` — don't duplicate. Wire into the CLI as `python -m pipeline coverage-diagnostic`.

### D4 — Trouble-Site Web Research (post-D1, manual research)

> **Context:** The diagnostic in D3 will produce a list of ~80-100 House members with coverage problems. Before we manually probe each site with Playwright, we want to know if there's a real-world reason for the silence — recent appointment, resignation, vacancy, special election, major scandal, hospitalization, etc.
>
> **Task:** Claude will share the trouble-site list once D3 generates it. For each member:
> 1. Web search: `"<member name>" "<state>" district <N> 2025 2026` and review first-page results
> 2. Note any of: resignation, death, expulsion, appointment after Jan 2025, party switch, hospitalization, no-show member reputation, vacancy
> 3. Cross-check against bioguide.congress.gov and ballotpedia.org for term start date
>
> **Output:** `docs/trouble-site-context-2026-05-03.md` with columns: `member_id | name | state-district | term_start | situation | confidence (high/med/low) | source URL`.
>
> **Constraint:** Don't make up information. If you can't find verifying sources, mark `situation: unknown` and `confidence: low`. We'd rather have an honest "needs Trevor to investigate" than a fabricated explanation.

---

## Risk register

| Risk | Likelihood | Mitigation |
|---|---|---|
| Akamai re-blocks during A1 re-run | Medium | Concurrency 3 + 30s pacing; if 403s reappear, abort and retry tomorrow |
| Codex D1 finds dozens of leaks needing fixes | Low-Medium | If >5, scope to top-5 user-facing surfaces today, fix the rest Mon |
| 80% bar not met on House by EOD | Medium | Methodology page documents the gaps honestly; we still ship the reframe |
| `/speeches` route exposes Senate-only data without House parity | High | Render it with explicit "House expansion in progress" banner; ship anyway |
| Vercel deploy breaks compat views | Low | Smoke test E1 catches before prod |

---

## Stop conditions (cancel ship, defer to Mon)

- A1 hits Akamai again hard (>20 of 58 members re-403)
- D1 audit finds >10 user-facing jurisdictional leaks
- E2 data-quality tests fail (any of the 26)
- Vercel preview shows a UI regression on /senators or /house

---

*Status: locked-in plan. Updates land at the bottom as we go.*

## Live updates

- 12:36 PM EDT — Plan locked, starting Track A1 + briefing Codex on D1.

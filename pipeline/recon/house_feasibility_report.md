# House Expansion Feasibility — Synthesis Report

**Date:** 2026-04-24
**Prepared for:** decision on whether to ship Senate as-is, rearchitect, or keep polishing senator-by-senator.
**Inputs:** four parallel recon streams (Senate debt audit, House-readiness code audit, Senate RSS probe, House comprehensive probe) plus the existing `senate.json` seed and memory history.

---

## TL;DR

Three-way decision: **ship / refactor / polish**.

- **Ship Senate** — yes, after ~2 evenings of cron-scheduling and three named bug fixes. Corpus is archival-grade: 35,148 records, 99/100 senators covered, 100% date completeness, 21/22 data-quality tests green (the one failure is a test-logic bug, not a data bug).
- **Keep polishing senator-by-senator** — no. There is nothing material left. TRUNCATED bucket is empty, 0 TODO markers in code, null-date rate is 0.0%. Further per-senator work has diminishing returns.
- **Refactor before House** — unavoidable. CLAUDE.md's "House-ready" claim is aspirational, not factual. A House seed file (`house.json`, 437 rows) already exists but is unreachable from the CLI (`pipeline/lib/seeds.py:16-17`), and every UI query hardcodes `chamber='senate'`. Dropping House rows into today's DB would leave them silently invisible.

**Recommended path:** three sequential stages — ship → refactor → House — rather than parallel tracks. Estimated total: **6–9 weeks** calendar.

---

## Evidence summary

### Senate state (from `senate_debt_audit.md`)

| Metric | Value |
|---|---|
| Total records | 35,148 (32,612 Senate live + 1,126 tombstones + 1,410 White House) |
| Senators with data | 99 / 100 (Armstrong-OK expected-zero) |
| Date coverage | 100.0% (0 null of 32,612) |
| Body-text coverage | 99.98% |
| Data-quality tests | 21 pass / 1 fail (test-logic bug, not data) |
| Health canary | 100 / 101 pass (Armstrong expected-zero) |
| Back-coverage TRUNCATED | **0** (was 5 on 2026-04-19; all resolved) |
| TODO/FIXME markers in code | 0 |
| Last scrape | 2026-04-21 — 3 days stale because no cron |

**Verdict:** shippable. The single load-bearing gap is **scheduling**.

### Senate RSS opportunity (from `senate_rss_probe_report.md`)

| Slice | Count |
|---|---|
| Senators with any working RSS | 41 / 100 |
| Swap-eligible for daily updates | 23 |
| Would actually move (currently httpx/playwright) | 16 (14 httpx + 2 playwright) |
| Currently `rss` but broken | 4 (Boozman, Kennedy, Moran, Lummis) |

**Real bugs surfaced:**
1. **Boozman / Kennedy / Moran** — ColdFusion RSS emits malformed `pubDate` ("day-of-year" bug: `Thu, 113 Apr 2026`). Currently classified as `rss` but parse rate is 0%. These three senators are effectively running on a silent-failure path.
2. **Lummis** — RSS last updated 681 days ago. Likely broken upstream.
3. **Elementor WordPress "Hello world!" pollution** — 7 senators (Alsobrooks, Banks, Blunt-Rochester, Curtis, McCormick, Young, Kim) have `/feed/` endpoints that look valid but only emit a placeholder post. Existing httpx path handles these fine; any RSS-first logic must not fall into the trap.

**Surprise win:** Cornyn and Merkley are currently `playwright` but expose clean RSS feeds. Browser-rendering cost per day on those two could be dropped tomorrow.

### House code-readiness (from `house_readiness_audit.md`)

**Verdict:** heavy refactor required. Not light, not medium. The claim that "adding House members should be a config change" is false.

**What already exists:**
- `pipeline/seeds/house.json` — 437 rows in `member_id` + `district` format
- `senators.chamber` column in production (added ad-hoc, no migration)
- `senators.status` column in production (same story)

**What blocks House expansion today (citations from the audit):**
- `pipeline/lib/seeds.py:16-17` only enumerates `senate.json` — `house.json` is unreachable from every CLI command
- `pipeline/commands/detect_deletions.py:90` filters `source_url LIKE '%senate.gov%'` — House deletion detection would silently never run
- `app/lib/queries.ts` (lines 102, 113, 193, 230), `app/lib/analytics.ts` (29, 43, 115), `app/lib/transparency.ts` (27, 38, 50, 61, 81), `app/api/senators/activity/route.ts` (41, 53, 66, 80) — every user-facing query hardcodes `WHERE s.chamber = 'senate'`
- `app/components/state-cartogram.tsx:20-27` — 2-per-state color logic is structurally Senate-only
- `app/page.tsx`, `app/senators/page.tsx`, `app/layout.tsx` — UI copy hardcodes "100 senators"
- `senator_id` vs `member_id` — seed formats are not unified; senators table's primary key is `senator_id`
- Tests hardcode member count of 100

**Biggest single risk:** silent coverage failure. If House rows were inserted today, every page would render fine, no error would be logged, the 437 members would simply not appear anywhere in the UI. The data would exist but be invisible.

### House scraping reality (from `house_comprehensive_probe_report.md`)

**Headline finding: AkamaiGHost bot mitigation blocks async httpx at concurrency 15.**

- **401 of 436 members (92%)** returned HTTP 403 from AkamaiGHost
- **28 members (6.4%)** responded 200 — our only real sample
- **7 members** had DNS/connection failures (likely stale hostnames in `house_members.json`)
- Block persisted across UA rotation, full Chrome header sets, curl, urllib, curl_cffi with TLS impersonation
- Control calls to `example.com` and `*.senate.gov` succeeded — block is policy-targeted at `*.house.gov`

**From the 28-member sample:**
- Drupal shared template: 57% (consistent with delegation-decoded's ~65% claim)
- WordPress: 7% (2 of 28) — and only 2 expose `/wp-json/wp/v2/posts`
- Zero members on Evo WordPress theme (Senate's common template)
- Custom / unrecognized: 36%

**Key implication:** The Senate's WordPress JSON rescue pattern (3,644 records recovered, per memory) does **not** transfer. House is a Drupal-majority estate, not WordPress. And the collection stack itself must change — Playwright-first at low concurrency, not httpx-first.

**Projected House coverage under the Drupal-shared-template hypothesis (needs clean reprobe to confirm):**

| Phase | Method | Projected coverage |
|---|---|---|
| 1 | RSS only (where exposed) | ~60–65% |
| 2 | + Shared Drupal parser | ~85–95% |
| 3 | + Per-member Playwright | ~99% |

Note: Phase 1 and Phase 2 numbers match delegation-decoded's independent 62.5% RSS result. That's two independent observations of the same House-Drupal pattern.

---

## The three-way decision, answered

### Should we keep polishing Senate senator-by-senator?
**No.** The per-senator polish curve has flattened. TRUNCATED bucket empty, null-date rate 0.0%, zero code-level TODOs. The gains from here are architectural (scheduling, second-chamber) and cross-cutting, not per-senator.

### Is Senate "good enough" to declare done and move on?
**Yes, after closing a short debt list.** The corpus is the strongest it has ever been. The debt that remains is:

| Item | Effort | Blocks House? |
|---|---|---|
| Wire daily updater to cron (Vercel cron or launchd) | M (0.5–1 day) | Partial — House would inherit the same unscheduled state |
| Fix ColdFusion `pubDate` day-of-year bug (Boozman/Kennedy/Moran) | S (hours) | No |
| Investigate Lummis 681-day-stale RSS | S (hours) | No |
| Fix the `unique_days/total` test-logic bug | S (hours) | No |
| Update CLAUDE.md "Armstrong (ND)" typo — should be OK | XS | No |
| Move 16 senators from httpx/playwright to RSS | M (0.5 day) | No — optimization, not required |

### Do we need wholesale architecture changes?
**Yes, and more than CLAUDE.md implies.** The "House-ready" principle is intent, not state. The codebase is Senate-shaped at the schema, query, UI, and test layers. This is true *regardless* of whether we expand to House — the `senator_id` / `member_id` split, the ad-hoc `status` column without a migration, and the hardcoded `chamber='senate'` filters in queries are latent bugs even in the Senate-only world. House merely forces them to surface.

---

## Recommended path

Three sequential stages. Do not parallel-track.

### Stage 1 — Ship Senate (target: 1 week)

Close the Senate debt list above. Specifically:

1. Set up daily cron (Vercel cron recommended — the frontend is already there).
2. Fix ColdFusion `pubDate` parser in `pipeline.lib.rss` to handle malformed `day-of-year` values (or fall through to detail-page date extraction).
3. Investigate Lummis — confirm whether the feed is broken upstream or if we need to switch her back to httpx.
4. Fix the `unique_days/total` test-logic bug so the test suite is clean green.
5. Move the 16 swap-eligible senators to `collection_method="rss"` (optional quick win).
6. Run `pipeline test` and `pipeline health` nightly for a week; declare Senate v1 done.

**Exit criterion:** 22/22 tests green for 7 consecutive days, cron firing, zero alerts.

### Stage 2 — Refactor to member-agnostic (target: 2–3 weeks)

Do the refactor the codebase already claimed. Concretely:

1. **Schema migration** — add `members` table as the canonical name (or rename `senators` → `members`), make `chamber` NOT NULL, formalize `status` with a migration. Keep `senator_id` as a view or backwards-compat alias for as long as needed.
2. **Seed unification** — merge `senate.json` and `house.json` into `members.json` with `member_id` + `chamber` + `district`. Update `pipeline/lib/seeds.py` to load both. Fix the seven accent-stripping bugs in `house.json` noted by the seed-list agent.
3. **Query layer** — remove hardcoded `chamber='senate'` filters. Add a chamber-aware parameter. Update `app/lib/queries.ts`, `analytics.ts`, `transparency.ts`, and `api/senators/activity/route.ts`.
4. **Deletion detection** — remove the `source_url LIKE '%senate.gov%'` filter in `detect_deletions.py:90`; accept any domain consistent with the member's `official_url`.
5. **UI chamber-awareness** — redesign the cartogram for chamber-aware rendering (Senate: 2-per-state dots; House: district-level shading). Update `app/page.tsx`, `senators/page.tsx`, `layout.tsx` to stop hardcoding "100 senators".
6. **Test updates** — remove hardcoded count of 100; use `SELECT COUNT(*) FROM members` as the reference.

**Exit criterion:** a single House row can be inserted into the DB and surface correctly in every UI view and CLI command. No House collection yet — just proof the plumbing works.

### Stage 3 — House expansion (target: 4–6 weeks)

Only after Stage 2 is done. Concretely:

1. **Reprobe the House with Playwright at concurrency 2–3**, or from a residential IP pool that doesn't fingerprint as a bot. Produce a clean `house_members.json` with per-member `collection_method`, `cms_family`, and validated `press_release_url`.
2. **Write a shared-Drupal House collector**. Per-member-template checking says one collector likely covers 200+ members. This is the highest-leverage single piece of work in the whole project.
3. **Write an RSS-first bootstrap pass** — run the RSS probe from Stage 1 over the House estate to get 60–65% coverage in week 1 while the Drupal collector is being written.
4. **Long tail** — per-member Playwright for the ~50–80 custom-CMS holdouts. Same playbook as the Senate collector audit of 2026-04-18.
5. **Backfill to Jan 2025** — only after daily updates are stable. Expect this to take 2–3 weeks of overnight runs given Akamai rate-limiting. This is 4x the Senate backfill in volume but with more hostile rate-limiting.

**Exit criterion:** 99% House coverage, daily updates running, backfill complete to Jan 2025.

---

## Risks and unknowns

1. **Akamai cat-and-mouse.** The 92% block on async httpx is the biggest unknown. Playwright at low concurrency is the safe fallback but is expensive at 436 members daily. Investigating whether the Akamai policy is permanent or a response to our burst is worth a day of recon.
2. **House-member hostname decay.** 7 of 436 already have DNS failures. The House seed will need maintenance more actively than the Senate one — more member churn, more staffer turnover, more template changes.
3. **Drupal shared template is a hypothesis.** The 28-member sample supports it. Delegation-decoded's 62.5% supports it. But a clean reprobe is required before committing engineering effort to the shared collector.
4. **Backfill volume.** House will ~4x database size. Pagination of 100k+ records in current UI components (senator page, cartogram, feed) was not tested at that scale.
5. **Content classification at House scale.** House members produce more newsletters, weekly reports, and blog-like posts than senators. The existing content-type classification (tightened 2026-04-22 per git log) will need re-tuning on House data.

---

## Files produced by this recon sweep

- `pipeline/recon/house_members.json` — 436 current House members, schema-compatible with senate.json
- `pipeline/recon/house_members_summary.md` — seed-list agent summary
- `pipeline/recon/build_house_members.py` — deterministic rebuilder
- `pipeline/recon/senate_debt_audit.md` — Senate ship-readiness evidence
- `pipeline/recon/senate_rss_probe.py` / `.json` / `_report.md` — RSS probe + report for 100 senators
- `pipeline/recon/house_readiness_audit.md` — codebase audit with file:line citations
- `pipeline/recon/house_comprehensive_probe.py` / `.json` / `_report.md` — House sweep + Akamai finding
- `pipeline/recon/house_feasibility_report.md` — this document

No pipeline code, no seeds, no database writes were modified in this recon.

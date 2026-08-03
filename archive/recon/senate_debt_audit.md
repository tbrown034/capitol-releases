# Senate Debt Audit

**Date:** 2026-04-24
**Purpose:** Evidence base for deciding whether to ship Senate as-is or keep polishing before House expansion.
**Scope:** Read-only audit. No writes to DB, no changes to code or seeds.

---

## 1. Topline Numbers

| Metric | Value |
|---|---|
| Total records (all chambers, live + tombstoned) | 35,148 |
| Senate live records | 32,612 |
| Senate tombstones | 1,126 |
| White House live records | 1,410 |
| Senators with releases | 99 of 100 (Armstrong expected-zero) |
| Active senators with data ≥ 100 records | 92 |
| Date coverage (Senate) | 100.0% (0 null of 32,612) |
| Body-text coverage (Senate) | 99.98% (8 null of 32,612) |
| Data-quality tests | **21 pass / 1 fail** (see §5) |
| Back-coverage confidence mean / median / p10 | 90 / 90 / 82 |
| Health-check canary | 100 / 101 pass (Armstrong is the 1 fail, expected-zero) |
| Most recent scrape | 2026-04-21 22:21 UTC (3 days ago) |
| Collection methods (Senate active) | 70 httpx / 19 playwright / 11 rss |

Bottom line: corpus is dense (~326 records/senator average for the 99 active publishers), dates are effectively perfect, bodies are effectively perfect, tests are effectively green.

---

## 2. P0 Gaps — Senators Who Should Have Data and Don't

**None.**

The only zero-release senator is **armstrong-alan (R-OK)**, which is the documented expected-zero case — appointed 2026-03-24, site is a bare-shell WordPress with an empty `/press-releases/`, allowlisted in `test_minimum_senator_coverage`. Monitoring only.

Every other active senator has ≥ 45 records with earliest dates in early-to-mid January 2025 (or their seat-change start date for Moody 2025-03-05 / Husted 2025-02-18 / Justice 2025-01-20). Low-count senators are genuine low-cadence publishers, not collector failures.

---

## 3. Back-Coverage Debt — TRUNCATED Senators

`python -m pipeline back-coverage` flags **9 senators** below 100% confidence, but **zero are TRUNCATED**. All nine are verified-real publishing patterns, not collector bugs:

| Senator | Severity | Conf | Verified cause |
|---|---|---|---|
| thune-john | INTERNAL_GAP | 78% | Real silence weeks (SD cadence + recess). |
| schmitt-eric | INTERNAL_GAP | 84% | Feb 10–Mar 10 2025 silence confirmed via WP JSON `x-wp-total=0`. |
| murkowski-lisa | INTERNAL_GAP | 88% | Real low-publish stretches. |
| moran-jerry | LOW_VOLUME | 100% | Low-cadence but at parity with live site. |
| whitehouse (WH) | SHALLOW | 72% | New collector, Jan 20, 2025 admin-change floor. |
| moody-ashley | SHALLOW | 83% | Seat start 2025-01-21 (mid-window appointee). |
| husted-jon | SHALLOW | 93% | Seat start 2025-01-21 (mid-window appointee). |
| alsobrooks-angela | SHALLOW | 95% | New senator (sworn Jan 2025). |
| justice-james | SHALLOW | 98% | New senator. |

**TRUNCATED bucket is empty.** The previous 5 TRUNCATED senators from 2026-04-19 have all been closed. This section is the strongest signal that Senate collection is shippable.

---

## 4. Date-Quality Debt

Project "known limit" says ~1% missing dates. **Senate actual: 0.00%.** No senator is above the project average. No debt here.

Missing-date repair work (`repair_dates.py`) appears complete. The remaining non-date gap is 8 records (0.02%) with null `body_text`.

---

## 5. Known Bugs / TODOs

### 5.1 Codebase markers

Zero `TODO`, `FIXME`, `XXX`, or `HACK` markers across the entire `/pipeline` and `/app` tree. Clean.

### 5.2 Failing test — likely a false positive

`test_per_type_not_date_clumped` fails with:

```
per-type date clumping: press_release: 32551 records on 468 days (1%)
```

**Diagnosis:** The test uses `unique_days / total < 0.2` as a "clump detector," which works for small collectors that default-date to month-start but breaks at scale. 468 unique days across a ~475-day window (Jan 1, 2025 → Apr 20, 2026) is near-perfect calendar coverage; the ratio fails only because the denominator (32,551 records) is large. The other six content types pass the same check because their totals are 90–523.

**This is a test bug, not a data bug.** The assertion logic should be `unique_days / expected_span_days` or a floor like `unique_days >= min(total, span)*0.9`, not `unique_days / total`.

### 5.3 Other findings

- 3 senators have `collection_method = NULL`: `vance-jd`, `rubio-marco`, `mullin-markwayne`. All three are `status='former'` and correctly excluded from active collection. Cosmetic.
- `recon_status` in `senate.json` is `discovered` for all 100 senators. Field appears unused as a live signal (every senator has been worked post-recon; nothing advances to `verified`). Cosmetic.
- `confidence` scores in `senate.json` range 0.4–1.0 and reflect the initial 2026-04-15 recon, not current reality. Klobuchar is 0.55 but now has 292 records and 100% date coverage. The scores no longer reflect operational quality. Cosmetic but misleading if used for future triage.
- Playwright collector is not implemented. 19 senators configured as `playwright` silently fall through to `httpx` in `collectors/registry.py:42`. This works for page 1 — which is what daily updates need — but means no deep pagination for those 19 on live update. Historical coverage was rescued via `backfill_wp_json.py`.

---

## 6. Deferred Work from "Known Limits"

| Item | Status | Notes |
|---|---|---|
| ~1% missing dates | **Closed** | Senate is at 0.00%. CLAUDE.md wording is stale. |
| 29 senators partial back-coverage | **Largely closed** | TRUNCATED bucket is empty. 9 flagged are real publishing patterns or mid-window appointees. |
| Armstrong-ND zero-release | Open by design | Monitor only; weekly site check. Note: CLAUDE.md says "Armstrong (ND)" but the actual senator is Armstrong-OK (`armstrong-alan`). Typo in docs. |
| WP JSON API not wired as collector | **Open** | `backfill_wp_json.py` exists as a manual rescue tool. No `wp_json_collector.py` in `collectors/`, no registry entry. Daily updater still uses HTML scraping for all WP senators. |
| Daily updater not scheduled | **Open** | No `.github/workflows/`, no `vercel.json` cron, no launchd plist found. Last scrape run was 2026-04-21 (3 days stale). Manual invocation only. |
| Deletion detection not scheduled | **Open** | `python -m pipeline deletions` exists but no cron. Deletions accumulate silently between manual runs. |

---

## 7. Risk of Stopping Senate Work Today

If Senate work freezes and attention pivots to House:

| Risk | Severity | What rots |
|---|---|---|
| Daily updater unscheduled | **High** | Corpus goes stale immediately. 3 days stale already. Every day without a run is missed content that the page-1-only updater can usually still catch (items age off page 1 in ~1 week for high-volume senators). |
| Deletion detection unrun | **Medium** | Missed `deleted_at` tombstones erode the "no existing tool has this" differentiator. Signal goes cold. |
| Site redesigns | **Medium** | Historical rate on this project: 18 selector breakages diagnosed in one audit Apr 18. Senate CMS vendors do redesigns. Every un-attended week increases break probability. Without scheduled health-check + selector-break alerting, first warning is a user-visible "N releases" hole. |
| Alerts emitted to console only | **Medium** | Resend SMTP is wired (`pipeline/lib/alerts.py`) but depends on manual invocation. Nobody sees "paul-rand silent for 60 days" unless someone runs the command. |
| WP JSON migration debt | **Low** | Existing HTML scrapers still work; JSON would be cleaner but not blocking. Current approach handles 99+ senators adequately. |
| Playwright collector never shipped | **Low** | The 19 `playwright` senators fall to httpx, which works for page 1 daily updates. No daily loss. |
| confidence/recon_status fields stale | **Low** | Cosmetic. Won't hurt collection. |
| Test suite has 1 false positive | **Low** | Misleading CI signal but the real quality is evident in the other 21 passing tests. |

**The single load-bearing gap is scheduling.** Everything else is cosmetic or deferred-and-documented. If Armstrong monitoring, deletion sweeps, and daily updates ran on cron, Senate would be genuinely ship-and-forget.

---

## 8. Effort to Close Each Gap

| Item | Effort | Notes |
|---|---|---|
| Schedule daily updater | **S** | Vercel cron or launchd plist. 1 evening. Pipeline is stateless re: runs. |
| Schedule health-check + deletion detection weekly | **S** | Same mechanism as daily updater. 1 evening. |
| Fix `test_per_type_not_date_clumped` logic | **S** | One function; swap `unique_days/total` for `unique_days/span_days`. 30 min. |
| Fix Armstrong-ND → Armstrong-OK in CLAUDE.md | **S** | One-line doc edit. |
| Null out `confidence` / retire `recon_status` OR recompute from live data | **S** | Schema change or regeneration pass. Half-day. |
| WP JSON collector wired as first-class | **M** | `backfill_wp_json.py` logic exists. Wrap into `WpJsonCollector`, add to registry, set `collection_method = wp_json` for ~27 custom-post-type senators. 1–2 days. Meaningful reliability win for daily updates. |
| Playwright collector implementation | **M** | Covers deep-pagination for 19 senators on daily runs. 1–2 days. Current httpx fallback handles page-1 new items, so this is history-not-daily. |
| Update CLAUDE.md "Known Limits" to reflect actual state | **S** | The ~1% null-date claim and 29-senator back-coverage claim are both out of date. 30 min. |
| "Normalize former-senator `collection_method = NULL`" | **S** | Cosmetic. 5 min. |

Total effort to genuinely close shipping blockers: **~2 evenings** (scheduling + test fix + doc updates). Everything else is "better" not "required."

---

## 9. Gut Call

Senate is shippable as-is. The remaining work is scheduling (cron) and one false-positive test; the corpus itself is in the strongest state it has ever been. Go to House.

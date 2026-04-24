# House Readiness Audit

**Auditor**: Claude (read-only)
**Date**: 2026-04-24
**Scope**: Validate or falsify CLAUDE.md's claim that Capitol Releases is "House-ready" and that adding House members "should be a config change, not a rewrite."

---

## 1. Verdict

**Needs heavy refactor.** The `chamber` column exists and a 437-member `house.json` was already seeded, but the rest of the stack — column name `senator_id`, every frontend query, every D3 visualization, every test, every CLI command, every user-facing string, and the seed loader itself — is Senate-shaped. Dropping House rows into the current schema today would work at the DB layer and silently break everywhere else. The "House-ready" claim in `CLAUDE.md` is aspirational, not current.

---

## 2. Schema changes required

What already exists (good):

- `senators.chamber TEXT NOT NULL DEFAULT 'senate'` — `db/schema.sql:19`, `db/migrations/003_multi_chamber.sql:6`
- `idx_senators_chamber` — `db/migrations/003_multi_chamber.sql:11`
- `senators.chamber` is populated for the one non-Senate row (White House) via `pipeline/seeds/executive.json:8`

What's missing or wrong:

1. **Table name is still `senators`** — `db/schema.sql:5`. All FKs point at `senators(id)` (`db/schema.sql:27`, `:71`, `:88`, `:100`). Every query in the codebase joins on this table. The name leaks Senate semantics into 50+ files.
2. **FK column `press_releases.senator_id`** — `db/schema.sql:27`. Every index and query uses this name (`idx_pr_senator`, `idx_pr_senator_published` at `db/schema.sql:46,50`). Renaming requires a coordinated migration across Python + TS + 16 test queries.
3. **No `district` column.** Grep of `db/` for `district` returns zero hits. House requires `district TEXT` (not INT — at-large, delegate, resident commissioner). Must be NULL-allowed and indexed with `state` for `(state, district)` uniqueness.
4. **No uniqueness constraint enforcing "one active member per seat."** Today the only PK is `id TEXT` (a slug). Senate needs `(state, senate_class, status='active')` unique; House needs `(state, district, status='active')` unique. Neither is enforced.
5. **`senators.status` is referenced but never defined in any migration.** Used in `pipeline/tests/test_data_quality.py:276,328`, `pipeline/commands/check_back_coverage.py:92`, `app/lib/queries.ts:102,112,193,229,245`, `app/lib/transparency.ts:38`, `app/lib/analytics.ts:28,114`, `app/api/senators/activity/route.ts:40,52,79`. The column was added ad-hoc in prod — CLAUDE.md even calls this out ("senators.status is active/former, not current") but it's absent from `db/schema.sql` and all three migrations. Any House refactor must first formalize `status` in schema.
6. **`senators` has Senate-specific columns that should not apply to House** — `senate_class INT`, `first_term_start DATE`, `current_term_end DATE` (referenced at `app/lib/db.ts:16-18` and `app/senators/page.tsx:49`, `:225`). `senate_class` is meaningless for House. `current_term_end` is 2-year, not 6-year, for House. Either NULL these for House or move to a sub-table.
7. **`senators.bioguide_id` assumed but also not in schema.sql.** Referenced in `app/senators/page.tsx:65` and `app/senators/[id]/page.tsx:87`. Same ad-hoc column problem as `status`.
8. **Minimum DDL for House support:**

   ```sql
   -- Rename (or alias via view) — see options (A)/(B) below
   ALTER TABLE senators RENAME TO members;
   ALTER TABLE press_releases RENAME COLUMN senator_id TO member_id;
   -- Add House-specific columns
   ALTER TABLE members ADD COLUMN district TEXT;           -- NULL for Senate
   ALTER TABLE members ADD COLUMN status  TEXT NOT NULL DEFAULT 'active';
   ALTER TABLE members ADD COLUMN bioguide_id TEXT;
   ALTER TABLE members ADD CONSTRAINT chk_district
       CHECK (chamber != 'house' OR district IS NOT NULL);
   ALTER TABLE members ADD CONSTRAINT chk_senate_no_district
       CHECK (chamber != 'senate' OR district IS NULL);
   CREATE UNIQUE INDEX uq_active_house_seat
     ON members (state, district) WHERE chamber='house' AND status='active';
   CREATE UNIQUE INDEX uq_active_senate_seat
     ON members (state, senate_class) WHERE chamber='senate' AND status='active';
   ```

---

## 3. Rename surface (how large is the grep-and-replace?)

Raw volume:

- `senator` literal across Python: 1,646 hits across 50 files (many in JSON fixtures, but still load-bearing).
- `senator` literal across TS/TSX: 187 hits across 18 files.
- `senator_id` literal: 1,068 hits across ~50 files.

Semantic (non-fixture, non-comment) surface that must be renamed if the data model becomes member-agnostic:

- **Collectors (`pipeline/collectors/`)** — the `senator: dict` parameter name, `senator["senator_id"]` accessor, and `ReleaseRecord.senator_id`/`CollectorResult.senator_id`/`HealthCheckResult.senator_id` fields:
  - `pipeline/collectors/base.py:17,32,49,68` (Protocol signature + dataclass fields)
  - `pipeline/collectors/httpx_collector.py:48,49,50,51,160,195,196,197,198`
  - `pipeline/collectors/rss_collector.py:37,38,39,106,127,128,129`
  - `pipeline/collectors/whitehouse_collector.py:36,37,38,71`
  - `pipeline/collectors/registry.py:27,29,41,48,51`
- **Commands (`pipeline/commands/`)** — every command takes `senators: list[dict]`, loops on `senator["senator_id"]`, writes `senator_id` column:
  - `pipeline/commands/update.py:55,59,75,79,115,146,165,192,247,261,265`
  - `pipeline/commands/health_check.py:44-69,105,112,173,177`
  - `pipeline/commands/detect_deletions.py:46-95,138-152,167,175,198,210`
  - `pipeline/commands/repair.py:44-51,198 and many others`
  - `pipeline/commands/check_back_coverage.py:91-117,271-285,398-412`
  - `pipeline/commands/visual_verify.py:36,50,184,187`
  - `pipeline/commands/gen_report.py:27,31,41-42,55-56,65,261`
  - `pipeline/commands/review.py:40,71-75,109`
- **Frontend (`app/`)** — hardcoded SQL identifiers and filter copy:
  - `app/lib/db.ts:7 (type Senator)`, `:32,34,43,51 (types PressRelease, FeedItem, SenatorWithCount)`
  - `app/lib/queries.ts:31,70,79-80,94,101,108,113,130,135,140,145-161,164,193,201,227,243` (every query)
  - `app/lib/analytics.ts:9,24,29,40,43,77,82,93,98,109-115,125,160,179,189` (every query; one string-blocklist includes the literal word `senator` at `:63`)
  - `app/lib/transparency.ts:11,25-27,38,49-50,60-61,81`
  - `app/api/senators/activity/route.ts:35-84` (route path + every SQL query)
  - `app/components/release-card.tsx` (6 hits)
  - `app/components/senator-bars.tsx`, `senator-activity.tsx`, `senator-heatmap.tsx`, `swim-lane.tsx` — component filenames and `SenatorRow` type names (per-component senator-shaped data)
  - `app/components/state-cartogram.tsx:20-26,85-91` — hardcoded 2-party-per-state logic
  - `app/senators/page.tsx` — entire page is Senate-shaped (copy, columns, URL, `next election`/`Senate terms end Jan 3` at `:49`)
  - `app/senators/[id]/page.tsx:87 status='current'`, `:134-136 (all 100)`, all query imports
  - `app/page.tsx:68,73,79,196,218` (copy: "100 Senators. / One Archive.", "View all 100", "Showing X of 100 senators")
  - `app/layout.tsx:27` (meta description: "all 100 U.S. senators")

**Rough estimate of semantic rename scope**: ~250 load-bearing lines across ~25 Python files and ~15 TS/TSX files. An `s/senator/member/g` would touch thousands of lines but only a subset are meaning-bearing; the others are type/variable names that would need manual review.

---

## 4. UI impact

Every user-facing surface is Senate-shaped:

1. **Routes** — `/senators` (`app/senators/page.tsx`), `/senators/[id]` (`app/senators/[id]/page.tsx`), `/api/senators/activity/route.ts`. No `/members`, no chamber in URL. Must either:
   - Redirect `/senators` → `/members?chamber=senate`
   - Or add `/house`, `/members`, keep both.
   House detail pages would collide at `/senators/[id]` since House `member_id`s won't be in the senators table until the schema renames.
2. **Copy hardcoded to "100 senators"** — `app/page.tsx:68,73,79,196,218`, `app/senators/page.tsx:134`, `app/layout.tsx:27`. Would need to become chamber-aware strings everywhere.
3. **State cartogram is Senate-only** — `app/components/state-cartogram.tsx:9-18`. The tile grid encodes 2 senators/state and uses a 3-color scheme (`bg-blue-100` both-D, `bg-red-100` both-R, `bg-purple-100` split) at `:20-27`. A House-aware cartogram needs a different abstraction (cartogram by district, or hex-grid, or "senators + # of reps" layered). Fundamental redesign, not a tweak.
4. **Heatmap / bars / swim-lane are per-member, so they scale** — `app/components/senator-heatmap.tsx` renders one member's daily activity so it's chamber-agnostic at the data layer. `app/components/senator-bars.tsx` takes a `SenatorRow[]`, already slicing top-15; scales to 540 but labels say "senator." Renaming needed; logic fine.
5. **`/senators` directory table columns** — `app/senators/page.tsx:162-174` has `Yrs in office`, `Next election` ("Nov {endYear - 1}" assuming 6-year cycle at `:49`). For House, next election is every 2 years. Would need per-chamber column logic or a different table per chamber.
6. **Photos** — `app/lib/photos.ts` uses `bioguide_id` for the Congressional Bioguide, which works for both chambers. No change.
7. **All queries filter `chamber = 'senate'`** — hard-coded in `app/lib/queries.ts:102,113,193,230`, `app/lib/transparency.ts:27,38,50,61,81`, `app/lib/analytics.ts:29,43,115`, `app/api/senators/activity/route.ts:41,53,66,80`. Each needs a `chamber` parameter threaded through (or per-chamber variants).
8. **Missing filter UI** — `feed-filters.tsx` has party, state, type, but no chamber. `search-box.tsx` has none. Adding House data without a chamber filter would mix 540 members' releases into a single feed with no way to narrow.
9. **Type `Senator` in `app/lib/db.ts:7-20`** includes `senate_class: number | null` (line 16) — Senate-specific. Used by `app/senators/page.tsx:49` (`nextElection`).

---

## 5. Collector impact

The collectors take a `senator: dict` and read `senator["senator_id"]` (`pipeline/collectors/base.py:68`, `httpx_collector.py:48`, `rss_collector.py:37`, `whitehouse_collector.py:36`). The field is a dict — so in theory the registry would work if every House record had a `senator_id` key instead of `member_id`. In practice:

- **`senate.json` uses key `senator_id`** (100 records, 100% coverage); **`house.json` uses key `member_id`** (437 records, 100% coverage). Mismatched schemas — seed format is *not* unified.
- `pipeline/lib/seeds.py:16-17` only loads `senate.json` and `executive.json`. `house.json` is unreachable from `load_members()` — it's never iterated. **Enabling House is not a one-line config change — the seed loader doesn't load the file, and even if it did, the `senator_id`→`member_id` mismatch would make every collector crash on `KeyError`.**
- Collectors have zero Senate-domain logic. The `senate.gov` literal appears in URL normalization (`pipeline/lib/identity.py:42`) as an http→https rule, and that rule already falls through to all `.gov` domains, so `house.gov` gets the same upgrade. `senate.gov`-specific code exists only in legacy backfill scripts (`pipeline/backfill.py:253,337`, `pipeline/backfill_playwright.py:141`) and in a dead check in `pipeline/repair_dates.py:181` (which already accepts both senate.gov and house.gov). These are all extraction heuristics; port risk is low.
- **`pipeline/commands/detect_deletions.py:90` hard-codes** `AND source_url LIKE '%%senate.gov%%'`. House releases would be silently skipped by deletion detection. **Bug if House data is added naively.**

**Verdict**: collectors are *almost* chamber-agnostic. The one-line fix is renaming `senator_id`→`member_id` across the collector layer (~30 lines), plus changing `pipeline/lib/seeds.py:16-17` to include `house.json`. The `detect_deletions.py` URL filter must be relaxed or driven from config.

---

## 6. Test impact

`pipeline/tests/test_data_quality.py`:

- Line 46: `assert count >= 100` — would still pass with 100+437 but the intent is wrong; the bucket of "every senator" becomes "every member."
- Line 71: `count >= 95` senators with releases — needs to be chamber-scoped or will pass trivially at 540.
- Line 226: hardcoded round-number set `(10, 20, 30, 40, 50, 100, 200)` — House senators with 100 releases would false-positive the pagination-cap detector. Needs per-chamber calibration.
- Line 254: `assert count >= 30` senators reaching Jan-Feb 2025 — Senate-only framing.
- Lines 276, 328: queries select `FROM senators s WHERE s.status = 'active'` with no chamber filter. When House rows arrive the tests will suddenly evaluate over 540 members, and calibrated thresholds (e.g. the "< 8 clumped" soft assertion at line 294) will fire spuriously.
- Line 442: `_TYPE_FLOORS` for `press_release` is 30,000 — calibrated to current Senate volume. Adding House would ~6x the corpus; the floor would need rebaselining (or splitting).
- `test_back_coverage_not_truncated` (line 300) uses `overrides` with Senate seat-change cases only. Mid-term House vacancies (deaths, resignations) have their own start dates; the override list needs a House-aware source of truth.
- `test_no_stale_senators` (line 409) thresholds were set against Senate cadence. House freshmen may legitimately post less.
- `test_all_senators_in_db` docstring and assertion message (`"Expected >= 100 senators (includes former)"` at line 46) are Senate copy.

`pipeline/commands/check_back_coverage.py`:
- Line 92: `WHERE s.status = 'active'` — no chamber filter. Peer-median calc at line 347 would mix Senate (high-volume) and House (variable) into one number, producing poorly calibrated signals for both.

---

## 7. Alerts impact

`pipeline/lib/alerts.py:check_anomalies` is structurally chamber-agnostic — it groups by `senator_id` and doesn't encode Senate thresholds. But:

- Line 84: `HAVING COUNT(*) > 20` treats "senator with >20 historical records" as active-enough to alert on. House may have a different cadence profile.
- Line 90: `h.last_90 >= 30` (roughly 2.3/week) — Senate-calibrated. A low-cadence House freshman would false-negative (not alert on real silence).
- Line 127: `JOIN press_releases pr ON s.id = pr.senator_id` — no chamber filter, so once House rows exist the alerts will fire for them too. That's desirable behavior, but the message text ("{sid}: 0 releases…") is chamber-neutral only because the `senator_id` slug includes identifying info. Alert UI (none today) would need chamber column.
- The `Alert.senator_id` field name (`pipeline/lib/alerts.py:27`) leaks the senator assumption; same rename trajectory as everywhere else.

---

## 8. Biggest risks if House rows are dropped into the current schema without a refactor

Ranked by severity:

1. **Frontend renders nothing new.** Every public query filters `WHERE s.chamber = 'senate'` (`app/lib/queries.ts:102,113,193,230`, etc.). House rows would sit in the DB and be completely invisible in the UI. There would be no error, no warning — just data that never appears. **(Highest risk: silent coverage failure.)**
2. **`detect_deletions.py:90` filters `source_url LIKE '%senate.gov%'`.** House release deletions would never be detected. The entire journalistic-value pitch ("Senator X deleted 12 press releases") silently does not apply to the 437 House members.
3. **Seed loader doesn't load `house.json`** (`pipeline/lib/seeds.py:16-17`). Nothing iterates it in any CLI command. `python -m pipeline update` with House rows already in the DB would never refresh them — they'd grow stale and eventually trigger stale-senator alerts, but never update.
4. **Seed key mismatch** — `house.json` uses `member_id`, collectors read `senator_id`. First iteration attempt: `KeyError: 'senator_id'`, crashing `pipeline/commands/update.py:146`. Fails loudly, which is *better* than silently — but still blocks import.
5. **Test thresholds go sideways.** `test_no_suspicious_round_counts` (line 234), `test_no_anomalously_low_counts` (line 406), `test_no_date_clumping` (line 294) all use soft thresholds calibrated against 100 senators. With 540 members at lower cadence, these thresholds fail spuriously or mask real failures.
6. **Cartogram breaks visual semantics.** `app/components/state-cartogram.tsx:20-27` encodes 2-D, 2-R, 1-of-each as the only states. A House member in CA-12 added to a CA tile with 2 Democratic senators would be silently erased from the aggregate color. Not a crash; an incorrect picture.
7. **No uniqueness enforcement on `(state, district, status='active')`.** Nothing prevents inserting two active reps for MI-07. The house.json build script (`pipeline/recon/build_house_members.py`) does collision handling in `member_id` generation, but the DB itself doesn't.
8. **Senate-specific columns applied to House.** `senate_class INT` and `current_term_end DATE` (6-year-term) would have to be NULL for House or get misused. The directory page's `nextElection()` helper (`app/senators/page.tsx:46-51`) computes a Senate election cycle; would emit wrong years for House.

---

## 9. Minimum viable House path — two options

### Option A: Clean refactor first, then import House

Steps (estimated 4–6 full sessions):

1. Formalize ad-hoc columns in a new migration `004_member_model.sql`: add `status`, `bioguide_id`, `district` with check constraints.
2. Migration `005_rename_to_members.sql`: `RENAME TABLE senators TO members`; `RENAME COLUMN press_releases.senator_id TO member_id`. Keep a view `senators` and column alias if any external tooling still reads the old names.
3. Rename in collectors: `pipeline/collectors/base.py` dataclass fields (`senator_id` → `member_id`), Protocol signature, all three collector implementations, registry.
4. Unify seed format: introduce `members.json` or update `house.json` to use `senator_id`-compat key (better: rename both to `member_id` and update Senate-side call sites). Update `pipeline/lib/seeds.py` to load all three seed files.
5. Update every CLI command to read `member_id`. Add `--chamber` flag to `update.py`, `health_check.py`, `check_back_coverage.py` so Senate-only runs are still possible.
6. Fix `detect_deletions.py:90` URL filter — remove or make `.gov`-scoped.
7. Frontend: parameterize every query by `chamber`. Add `/members/[chamber]` or keep `/senators` as a Senate-shortcut that sets `chamber=senate`. Replace cartogram with a chamber-aware version or hide it on `/members?chamber=house`.
8. Update copy: "100 Senators. One Archive." → either two separate headlines or dynamic based on active chamber.
9. Rebaseline tests against member-level assertions; split floors per chamber where calibration differs.
10. Run a subset of House collectors (10–20 districts, one per CMS family) end-to-end before enabling all 437.

**Effort estimate**: 25–35 hours, one person. Low risk of regression because every change is mechanical + schema-backed.

### Option B: Parallel track — House as a second first-class citizen beside Senate

Steps (estimated 2–3 full sessions to ship first slice):

1. Migration `004_house_members.sql`: create new `house_members` table mirroring `senators` schema but with `district TEXT NOT NULL`. Create `house_releases` table mirroring `press_releases` with FK to `house_members`. (Expensive in duplicated query code, cheap in migration risk.)
2. Copy the collector layer: `pipeline/collectors/house/` reads from `house.json`, writes to `house_releases`. Keeps `member_id` naming on that side.
3. Second CLI: `python -m pipeline house update`, `python -m pipeline house health`. Existing `python -m pipeline update` continues to run Senate unchanged.
4. Frontend: add `/house` routes that query `house_releases`. Keep `/senators` untouched. Add nav entries.
5. Later, once both are shipping, do Option A-style unification.

**Effort estimate**: 15–20 hours for the first shipping slice; 30–40 hours total if you unify later. Higher long-term cost (duplicated queries, double the test surface), but ships House data visibly faster with less blast radius. Every Senate-only test keeps passing unchanged.

**Recommendation**: Option A is the principled call; Option B is the pragmatic call if the pressure is to show House data in weeks rather than months. The `chamber` column already in schema suggests the original intent was Option A — but the work to earn that was never done.

---

## 10. Summary of receipts

- Schema is 95% Senate-shaped despite the one `chamber` column. `db/schema.sql`, `db/migrations/003_multi_chamber.sql`
- Seed formats are not unified. `pipeline/seeds/senate.json` uses `senator_id`, `pipeline/seeds/house.json:4` uses `member_id` with `district`. Verified: 100/100 Senate, 437/437 House.
- `pipeline/lib/seeds.py:16-17` doesn't load `house.json` at all.
- Collectors read `senator["senator_id"]` everywhere (`pipeline/collectors/*.py`).
- `pipeline/commands/detect_deletions.py:90` explicitly filters `senate.gov`.
- Frontend hardcodes `chamber = 'senate'` in ~15 queries (`app/lib/queries.ts`, `analytics.ts`, `transparency.ts`, `api/senators/activity/route.ts`).
- UI copy hardcodes "100 senators" across five files.
- `senators.status` referenced by 14 call sites but defined in zero migrations.

The *plumbing* to support chambers exists. The *semantics and rename* are unfinished. CLAUDE.md's "House-ready" claim is wrong as stated; it reflects intent, not state.

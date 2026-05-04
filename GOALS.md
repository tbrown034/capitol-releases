# Capitol Releases — Goals & Roadmap

*Written May 1, 2026. Living document — update as scope evolves.*

This document is the canonical source for **what Capitol Releases is trying to be**. `CLAUDE.md` Mission covers the *why* (portfolio piece + product). This covers the *what*.

When earlier docs (`business_plan.md`, `business-strategy-2026-04-29.md`, `expansion-strategy-2026-04-29.md`) disagree with this file, this file wins.

---

## MVP — Achieved (alpha / beta)

**Original MVP:** Archive every press release, statement, op-ed, and blog post from the **100 current U.S. senators** since January 1, 2025, updated daily, with provenance and deletion detection.

**Status as of May 1, 2026:** Largely working at alpha / beta quality.

- 90 / 100 senators clean per `python -m pipeline back-coverage`
- ~30k press records, ~11k Bluesky posts collected
- Daily cron (GitHub Actions, 13:00 UTC) running and healthy
- Deletion detection + content versioning live
- 26-test data quality suite passing
- Frontend live at `app/` with `/brief`, `/social`, senator pages, search

**Known gaps** (refining, not bug-proof yet):
- 10 senators with coverage gaps (4 INTERNAL_GAP, 5 SHALLOW, 1 LOW_VOLUME)
- 1 NO_DATA (Armstrong, expected — pre-publishing state)
- State legislature collectors are seeded but undertested
- Newer features (Bluesky, brief, newsletter signup) are mid-build

**This is the foundation.** Everything below is expansion on top of a working MVP.

---

## North Star (stretch goal)

Become the canonical **"on the record" archive for every elected official in the United States at the state and federal level**.

For each official, capture every official communication channel we can collect:

1. **Press releases / statements** from official .gov sites *(MVP-level for Senate)*
2. **Social media** — Bluesky now (44 verified handles, 11k posts since Jan 2026); Twitter/X possible later if APIs cooperate
3. **Official records** — Senate floor speeches via Congressional Record (CREC) collector shipped 2026-04-30; House floor speeches + committee statements as expansion targets
4. **Search + trending** — full-text keyword search, trending topics, time-series visualization across all of the above

### Coverage targets

Expansion order is **TBD** — Trevor hasn't picked one yet (2026-05-01). The list below is the universe of expansion targets; their numbering is not a priority ranking. When the time comes to pick the next coverage push, weigh: (a) how much it strengthens the portfolio story, (b) how much new collector work it implies, (c) what's most timely for 2026 elections and the briefing product.

| Scope | Status |
|---|---|
| US Senate (100 members) | **MVP achieved, refining** |
| Federal executive (POTUS, cabinet) | Partial — White House collector live |
| State governors + state executive (AGs, lt. govs, treasurers) | Recon done; collectors not built |
| State senates (50 chambers) | Seeds for CA, MO, NE, OH, TX, WV started; undertested |
| US House (435 members) | Recon done (`house_raw.json`); collectors not built |
| State houses (49 chambers) | Recon done; collectors not built |

### What "on the record" includes — and doesn't (decided 2026-05-01)

The four communication channels above (press releases / social / floor + Congressional Record / search-trending across all of it) **are** the goal. Capturing those well across every elected official is the stretch target. Additional channels are expansion possibilities, not part of the current goal — and Trevor hasn't identified a specific extra one yet.

Out of scope:
- Local officials — mayors, city councils, school boards. Maybe someday; not now.
- Campaign-side content — campaign websites, campaign mailers. Only official .gov + verified social.
- Third-party media — interviews, podcast hits, "In the News" clippings.
- Voting records, bill tracking, financial disclosures, stock trades — these exist elsewhere (Congress.gov, FEC, Senate Stock Watcher). We may *join* via `bioguide_id` later, but we do not collect these directly.
- Constituent newsletters (DCinbox already does this well), public testimony, committee opening statements, letters to agencies — not part of current scope. The `letter` and `floor_statement` content_types remain in the schema for items that surface on official press pages, but we don't actively go collect them from outside those pages.
- Predecessor coverage when seats change hands mid-window.
- **Committee press output (v2 stretch — see below).**

---

## v2 stretch — Committee + leadership press surfaces

**Why this isn't v1:** Discovered 2026-05-03 that some committee chairs (confirmed: Jordan/House Judiciary) shift their press output to the committee site after assuming the chair. Personal-site coverage goes near-zero while the committee site fills up. The current architecture treats each member's personal .gov site as the canonical archive, which means we systematically under-cover sitting committee chairs and ranking members.

**Why we're deferring:**

1. **Attribution is genuinely complicated.** A committee press release isn't authored by one person — it's the committee speaking, with the chair (or ranking member) as spokesperson. Some are joint statements. Quoting one person on the chair's archive misrepresents the editorial reality.
2. **Duplication risk.** Many member sites re-syndicate committee statements they led. Collecting both creates near-duplicates we'd have to dedup.
3. **Scope creep.** Once committees are in, the natural next ask is leadership statements (Speaker, Minority Leader), then caucus statements (Freedom Caucus, CBC, Hispanic, Progressive), then joint statements, etc. The line keeps moving.

**v1 mitigation (shipped 2026-05-03):** per-member coverage banner on `/house/[id]` that surfaces a `committee_chair_url` when the seed has it. Currently only Jordan tagged; broaden as we identify other affected chairs.

**v2 plan when triggered:**

1. **Recon** all 23 House + 16 Senate standing committee press URLs and CMS families. Codex D5 prompt drafted — runs the survey and recommends an attribution model.
2. **Schema:** likely `content_type='committee_release'` on the existing `official_site_items` table with new `committee_id` and `member_role` columns ('chair' / 'ranking' / 'member' / 'joint'). Avoids a second table; keeps full-text search unified. Alternative: separate `committee_releases` table — cleaner separation but more code.
3. **Collectors:** mostly EvoGov-Drupal — re-use existing collector with a different seed file (`committees.json`).
4. **Seed:** `pipeline/seeds/committees.json` with 39 entries (each: committee_id, name, chamber, press_release_url, parser_family, selectors, current_chair_member_id, current_ranking_member_id). Refreshed at the start of each Congress when chairs rotate.
5. **UI:**
   - Each committee gets a directory entry (e.g. `/committees/house-judiciary`) showing chair + ranking member + recent releases.
   - Each member who chairs or ranks a committee gets a "Committee work" tab on their personal page (`/house/jordan-jim?tab=committee` or similar).
   - Cross-chamber search includes committee output as a filterable content type.
6. **Leadership / caucus:** evaluate after committee work ships. If a Speaker / Minority Leader has substantial standalone .gov press output (Codex D5 will check), apply the same pattern. Caucuses are likely a v3 question.

**Trigger conditions for starting v2 work:**
- Capitol Releases launches publicly (Product Hunt / r/dataisbeautiful / HN).
- User feedback or journalist inquiries surface "where's the committee output?" as a real ask.
- Playwright collector for the 19 NextJS+GraphQL House members ships first (related infra investment).

**Risk register:**
- Attribution disputes ("you tagged this as Jordan's release; the ranking member co-issued it") — mitigate via `member_role: 'joint'` + show both.
- Politicization ("you only collect chair output, you're amplifying Republicans") — mitigate by collecting chair AND ranking member output equally and labeling both.
- Maintenance ("chairs rotate every 2 years") — mitigate by tagging seed entries with the active Congress number; refresh script at the start of each Congress.

---

## Product moats

What makes Capitol Releases different from LegiStorm, Quorum, Plural, BGOV, FiscalNote, etc.:

1. **Clean UI / UX.** Editorial-grade Next.js + React 19 + Tailwind 4. Mobile-first, accessible, modern typography, real motion craft. Competitors look like 2010 enterprise software.

2. **First-class data visualization.** D3-driven sparklines, heatmaps, timelines, network graphs, scrollytelling. Data viz is a headline feature, not an afterthought.

3. **Tools designed for real users.** When persona surfaces conflict, **journalists win** and **hiring managers** are a co-equal first-tier consideration (the project is also Trevor's flagship portfolio piece — every page is implicitly being read by someone considering him for a job). Each persona gets surfaces built for them:
   - **Journalists (primary)** — quote search, topic alerts, citation export, AP-clean copy
   - **Hiring managers (primary)** — visible craft, clean code, methodology page, fast load times, "this is what production newsroom-tech looks like"
   - **Lobbyists / gov-affairs** — issue alignment, messaging shifts
   - **Politicians / staff** — see how peers are messaging
   - **Members of the public** — plain-language briefs, follow-your-senator flows

4. **Full provenance + archival permanence.** `date_source`, `date_confidence`, `scrape_run`, `scraped_at` on every record. Deletion detection with `deleted_at` tombstones. Content versioning. Public methodology page. Citable canonical URLs per record.

5. **Focus.** This is the whole product, not a feature buried inside a CRM / advocacy / lobbyist suite.

---

## Newsletter / briefing product (in development)

AI-generated daily and weekly summaries of recent communications across the corpus. Groups by topic, surfaces trends, cites every claim back to source records. Functions as:

- An editorial product in its own right (Politico Playbook–shaped)
- An acquisition surface for the underlying archive
- A demonstration of what the corpus enables analytically

**Currently shipping:** `/brief` (daily), weekly editions, RSS feed at `/brief/rss.xml`, email send via Resend on cron, public archive at `/brief/archive`, newsletter signup with double-opt-in unsubscribe tokens.

**Voice + format (decided 2026-05-01):** Trevor's voice — readable, skimmable, **Roll Call / Axios-style briefing**, not a neutral wire-service summary. Reference: Trevor's prior newsletter work at Oklahoma Watch. Skim-friendly hierarchy (bold leads, short bullets, scannable), point of view OK, journalism-shaped not editorializing. The brief should feel like a person wrote it, not a model.

**Still maturing:** citation validation rigor, retraction-on-republish handling, editorial voice consistency, gated-vs-free decisions.

---

## Monetization — gating planned, specifics undecided

Some content and features **will be gated** as part of launch. Trevor confirmed 2026-05-01: free archive + free brief preview, with **premium gating on something** TBD. Likely candidates from the menu:

- Free archive + paid intelligence layer (alerts, advanced search, API access)
- Free recent + paid historical archive
- Free read + paid bulk export / API
- Free for verified journalists + 501(c)(3) + paid for everyone else
- Free newsletter + premium briefing tier (deeper analysis, exclusive editions)
- Free public surfaces + paid power-user tools (saved searches, custom alerts, dashboards)

The mix is open. Decision can be made closer to launch — what matters is that *some* gating ships at launch, so paid is a real product surface from day one rather than a "we'll figure it out later" promise.

**No revenue targets.** Per `CLAUDE.md` Mission: any side income is success; none is required.

---

## Launch goal (decided 2026-05-01)

**Rough target: ship a public launch in 1 to 3 weeks** (mid-to-late May 2026). **This is a rough target, not a deadline.** Could land sooner if patterns click; could slip later if a launch-blocker (auth, payments, a coverage gap) takes longer than expected. The discipline is "ready-when-ready, but actively pushing toward ready" — not "ship by date X regardless."

### Why a soft date is realistic

Build velocity here is genuinely high. Reference points (verified 2026-05-01):

- **193 total commits in 17 days** since the Next.js initial commit (2026-04-15)
- **102 commits in the last 7 days alone**
- In that window, shipped: full Senate scraping pipeline, daily cron, deletion detection, content versioning, Bluesky integration with 11k posts, Congressional Record floor-speech collector, AI-generated daily + weekly brief, RSS feed, email send via Resend, newsletter signup with double-opt-in, Better Auth with Google OAuth, /admin dashboard, state expansion recon + first wave of state seeds

This is faster than a typical solo founder's pace because Trevor is using Claude Code (Max plan) and OpenAI in concert — the cycle of plan → ship → review → iterate compresses an order of magnitude when the AI tools are well-pattern-matched. Velocity should keep accelerating as patterns and skills stabilize.

**Implication:** propose ambitious work, not conservative work. "This will take 2 hours" is usually closer to truth than "this will take a day." Don't pad estimates; Trevor finishes in minutes what the model quotes in tens of minutes (already a recorded feedback memory).

### Launch channels

- **r/dataisbeautiful** — data viz showcase post (the moat in flag form)
- **Product Hunt** — full product launch
- **Hacker News** — Show HN post
- Probably also: Bluesky journalism circles, Twitter/X if useful, journalism Slack groups

### What needs to be true at launch

- Senate coverage gaps closed (10 known senators in `back-coverage`) so the "100/100 senators" claim is honest
- Premium gating actually live (not promised) — at least one concrete paid feature shipped
- `/brief` voice tuned to the Roll Call / Axios style above
- Public methodology / "how this works" page that holds up to journalist scrutiny
- UI polish on the surfaces a Product Hunt visitor sees in the first 30 seconds (homepage, brief, a senator detail page)
- D3 visualizations that hold up against r/dataisbeautiful's bar

**This is the bar to move Capitol Releases from alpha/beta to "production."** Not a perfect product — a real, public, gateable, journalism-rigor product with at least one premium hook live.

---

## How this doc relates to others

- `CLAUDE.md` Mission — *why* the project exists (portfolio + product framing)
- `GOALS.md` (this file) — *what* the project is trying to become
- `docs/business_plan.md` — cost models, scaling math, revenue scenarios
- `docs/expansion-strategy-2026-04-29.md` — technical recon for state expansion
- `docs/competitor-landscape-2026-04-29.md` — WIP competitor reference
- `docs/devlog.md` — chronological session log

---

*Last updated: May 1, 2026.*

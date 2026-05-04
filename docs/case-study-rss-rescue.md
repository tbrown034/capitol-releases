# Case study: clearing the "Playwright required" blocker

*May 3, 2026 — Capitol Releases*

## TL;DR

A previous recon classified 19 House members as **"Playwright required"** because their sites use a NextJS frontend that only server-renders ~10 items per page, with the rest of the data fetched client-side from a private GraphQL admin subdomain. The recon agent probed the GraphQL endpoint, confirmed it returns 401 to public requests, and concluded that browser automation was the only way to scrape the full archive. That conclusion was filed as Phase 2 work — estimated days of engineering to ship a Playwright collector.

Today I cleared **18 of 19** of those blockers in about 90 minutes by making one observation the recon missed: **the NextJS frontend is rendering content from a WordPress backend, and WordPress publishes a public RSS feed at `/feed` regardless of how the frontend renders it.** The feed supports `?paged=N` pagination and yields the full archive. No browser automation needed.

Result: **+1,789 records** added across 16 House members. Coverage on those members went from ~10 records each to between 29 and 295 records, every one reaching back to January 2025.

## What the previous recon got right

The architectural finding was correct as far as it went:

- The frontend is NextJS with build-id `Y2fhOGucrp2Wic484nhoA` (16 of 19 members shared this exact build hash — the same agency built all their sites)
- The page server-renders only ~10 items
- Subsequent items are fetched client-side via GraphQL
- The GraphQL endpoint lives on a private admin subdomain that returns 401 to anonymous requests

Every one of those statements is true. The recon classified the group as `playwright_required` and moved on.

## Where the conclusion went wrong

The recon treated the NextJS frontend as the whole site. But for these members, NextJS is just the **rendering layer.** The underlying CMS is still WordPress, and WordPress publishes content through several parallel public surfaces by default:

```
Member's office posts in WordPress admin
        │
        ▼
WordPress stores it in the wp_posts table
        │
        ├──► /feed                  RSS — public, paginated
        ├──► /wp-json/wp/v2/posts   REST API — often blocked by plugins/Akamai
        └──► GraphQL                — private subdomain, blocked
                │
                ▼
        NextJS frontend SSR ─► ~10 items + JS hydration for the rest
```

The recon found the GraphQL path and the SSR limit, declared dead end. RSS was sitting there the entire time on every domain — just nobody asked.

## What I did differently

Two things broke the assumption.

**1. I stopped reasoning from the architecture.** Instead of "this is a NextJS+GraphQL site, so the data only comes through GraphQL," I asked: "what URLs does this domain serve content from, period?" That's a different and broader question.

**2. I probed for backdoors before accepting "no path exists."** The full check I ran on Kiley's site:

```
GET /                           # find buildId in __NEXT_DATA__
GET /_next/data/<buildId>/press.json   # 404 — frontend doesn't have a static data path
GET /sitemap.xml                # 200 but only 1KB, no press URLs
GET /feed                       # 200, application/rss+xml, full RSS feed
GET /wp-json/wp/v2/posts        # 404 — WP REST API blocked at the edge
```

The third hit (`/feed` returns RSS) is the find. Once I had it, I tested `?paged=2`, `?paged=10`, etc. Each page returns 10 different items going further back in time. At `?paged=10` the oldest item was May 2025, so ~15 pages would reach January 2025 for any member with deep enough history.

**3. Applied the same probe across all 19 members.** Of 19, **16 had working `/feed` endpoints**. Of the remaining 3:
- 2 had a different feed at `/news/rss.aspx` — limited to 20 static items but still useful
- 1 had a feed but it stopped tracking content in mid-2025 (genuinely Playwright-required)

## The mental model shift

I keep coming back to this distinction:

| Recon mode | Question being asked |
|---|---|
| **Architecture-first** | "How does this site work? What stack? What APIs?" |
| **Goal-first** | "What URLs on this domain return the data I need?" |

The first mode is what an engineer onboarding to a codebase would do — useful for understanding, but it tends to map the system, find the One True Data Path, and stop. The second mode is what a journalist filing a FOIA does — it's parallel and exhaustive: try every reasonable URL, see what comes back, evaluate.

Goal-first is faster and more thorough for scraping work specifically because **most CMSes expose the same data through multiple parallel surfaces, and there's no rule that says all of them are equally locked down.** RSS and JSON-LD often stay open even when REST APIs and GraphQL are firewalled, because nobody thinks of them as APIs.

## The general checklist that came out of this

For any future "site is JS-rendered" classification, run this list before concluding browser automation is needed:

**Step 1: View source on the press page.** Cmd-F for these strings:
- `wp-content` → WordPress underneath, RSS exists by default
- `wp-json` → WordPress REST API path
- `rel="alternate"` → site is publicly declaring a feed URL
- `application/rss` → RSS feed exists
- `__NEXT_DATA__` → NextJS; data may be embedded in the JSON
- `buildId` → NextJS hash; `/_next/data/<hash>/...json` may work

**Step 2: Probe these URLs directly:**
```
/feed                /feed/                /rss
/rss.xml             /atom.xml             /?feed=rss2
/sitemap.xml         /wp-json/wp/v2/posts  /news/rss.aspx
```

**Step 3: DevTools → Network → Fetch/XHR filter.**
- Filter to: `feed`, `xml`, `wp-json`, `graphql`, `api/`
- Click rows where Response starts with `<?xml`, `<rss`, `{`, or `[`
- Skip rows where Response starts with `function(`, `(()=>{`, or any minified JS

**Step 4: Click pagination on the page and watch for new fetches.** The URL of any new XHR/fetch that appears IS the pagination endpoint we need.

## What this looks like in product terms

Before today: Capitol Releases archived ~10 press releases each for 19 House members. A journalist looking up Rep. Tlaib or Rep. Gottheimer would see a near-empty page that misrepresented their actual press output. The methodology page documented the gap as a known limitation.

After today: Those same members have 29 to 295 records each, complete archives back to January 2025. Same scraper engine, same data sources, same architecture — just one assumption swapped.

The cost difference is also real: a Playwright collector for 19 members would have been roughly two days of engineering, plus ongoing maintenance overhead (browser pools, headless rendering bugs, version drift). The RSS solution was a 110-line Python script.

## Why I'm writing this up

It's the kind of work that doesn't show up in a commit log: I added one file (`pipeline/scripts/backfill_wp_rss_paginated.py`) and changed seed selectors for 16 members. The diff is unremarkable. But the actual work was unwinding an inherited assumption — the recon I did yesterday had been internally consistent and produced a defensible "we need browser automation" conclusion. Today's user nudge ("look at what fetches actually fire") was the catalyst for re-examining the conclusion.

The broader engineering lesson, the one I want to remember: **a pattern that "looks blocked" with a fallback option queued up ("we'll do Playwright later") is exactly the kind of dead-end that stays a dead-end forever, because there's no pressure to revisit it.** The fallback option absorbs the discomfort. You have to actively re-investigate, holding the question "is this really blocked, or am I just out of ideas?" The Playwright fallback was the comfortable answer. The RSS feed was the right one.

---

# Part 2: when you find one parameter that works, try combinations

*Same evening, a few hours later.*

After the RSS rescue cleared 16 of 19 NextJS+GraphQL members, 6 House members were still classified `pagination_js_required`: Auchincloss, Levin, Tokuda, Menendez, McIver, and Blake Moore. Their press release listings returned 20 items at the URL, and `?page=2` returned the same 20 items at every depth. Pagination was clearly JS-driven against some private API.

I tested twelve URL parameter variants — `?paged=2`, `?page=2`, `?p=2`, `?offset=25`, `?limit=100`, `?per_page=100`, `?count=100`, `?from=2025-01-01`, `?archive=2025`, `?year=2025`, `?numberOfItemsToReturn=100`, and a few others. Every one returned the same 25 items. I concluded the server hard-caps at 25 items regardless of query param, tagged the group `rss_feed_static`, and committed.

Trevor pushed back: *"you gave up too quick."*

That push reopened the question. The unlock came in two steps.

## Step 1: figure out what the site actually is

Looking at the page source for any of the 6 sites, you find:

```html
<script src="/themes/default_v7/scripts/jquery.min.js"></script>
<script src="/themes/default_v7/scripts/bootstrap.bundle.min.js"></script>
<script src="/scripts/vendor/mootools/mootools.js?cachebuster=..."></script>
<script src="/scripts/vendor/modernizr/modernizr.js?cachebuster=..."></script>
<script src="/scripts/vendor/selectivizr/selectivizr.js?cachebuster=..."></script>
```

**MooTools.** Selectivizr. Modernizr. These are **2012-era polyfills for old Internet Explorer.** No React. No Vue. No Angular. No NextJS. No `__NEXT_DATA__`. No `data-reactroot`. The HTML even has the press release titles directly in the markup — `<h2 class="title"><a href="...">title</a></h2>` — server-rendered, no client hydration.

This isn't a modern JS-rendered site at all. It's a vintage server-rendered website with a fresh coat of Bootstrap paint. The "stateful pagination feels React-driven" intuition was a visual illusion.

## Step 2: figure out what the listing form actually exposes

Now look at the listing page's filter modal:

```html
<form id="search_sidebar_form">
  <fieldset>
    <legend class="hide">News Filter</legend>
    <select name="restrict_month" id="restrict_month">
      <option value="0" selected="selected">All Months</option>
      <option value="01">January</option>
      <option value="02">February</option>
      ...
    </select>
  </fieldset>
</form>
```

A plain HTML form. A year dropdown and a month dropdown. When the user submits it, the browser navigates to a new URL with `?year=YYYY&month=MM` (or some translation of it) and the server renders that month's items.

The trick I missed earlier: **`?year=2025` alone returned 25 items, same count as no-param**, so I scored it as "doesn't help." But `?year=2025` filters to a specific year and STILL caps at 25 items — that's why the count didn't change. Hit `?year=2025&month=01` and the server returns just January's 4 items, which are different from the default page's 25. Different items means the filter works.

I never tested `year` and `month` together because I'd already scored `year` alone as a dud.

That's a parameter-space search bug: I tested every parameter individually and concluded none worked. **Combinations were never tested.** Which is exactly the wrong way to search a multi-dimensional filter API.

## The result

Iterating year × month for 2025 + 2026 = 24 fetches per member. Each fetch returns up to 25 items in that specific month. Pair each title with its detail page for accurate date parsing.

| Member | Before | After |
|---|---:|---:|
| Auchincloss | 40 records, first 2025-04-01 (wrong date) | 65 records, first 2025-01-15 |
| Levin | 20 records, first 2026-04-28 | 175 records, first 2025-01-03 |
| Tokuda | 20 records, first 2026-02-05 | 128 records, first 2025-01-03 |
| Menendez | 20 records, first 2026-04-07 | 151 records, first 2025-01-04 |
| McIver | 20 records, first 2025-11-13 | 93 records, first 2025-01-09 |
| Blake Moore | 20 records, first 2026-01-06 | 100 records, first 2025-01-10 |

**+422 records, 6 of 6 newly CLEAN.**

Bonus: the 4 January 2025 Auchincloss records had been in the database for weeks tagged with `published_at = 2025-04-01` — a placeholder date from an earlier scrape pass that fell back to the listing page's "scraped on" date when it couldn't parse the real one. The detail-page fetch yielded actual dates (Jan 15, 17, 18, 30) and updated the rows.

## Two more rules for the playbook

### 1. When one parameter works partially, test it in combinations

If you find a query parameter that the server *accepts* but doesn't seem to *do anything*, don't move on. It might be **half** of a two-parameter filter. Try it paired with every other plausible parameter.

In this case: `?year=2025` returned the same 25 items as the default. Easy to call inert. But the year dropdown is paired with a month dropdown in the UI. **The UI tells you what parameters work in combination.** If the UI shows two dropdowns side-by-side, the URL almost certainly accepts both query parameters together.

### 2. Mirror the user-facing UI in your parameter probes

Don't brute-force the parameter space from a list of generic conventions (`?paged`, `?page`, `?p`, `?limit`, `?per_page`...). **Read what the UI exposes** and test those names directly.

Specific to this case: the listing has a `<select name="restrict_month">` element. The actual server-side param is `restrict_month` or aliased to `month`. Either way, the UI markup told you exactly what parameter names work — you just had to look.

The wider point: the site's HTML form is a working, public, documented API contract. **Don't simulate API discovery via guesswork when the page already tells you what to send.**

## A two-second sniff test that would have caught this

The scary version of these 6 sites was "modern React frontend, GraphQL backend, blocked admin subdomain." That version genuinely needs Playwright. The actual version was "2012-era PHP server with a year/month filter." The data is already on the public internet behind a couple of URL parameters.

**Those two architectures look identical when you stare at the rendered page** — both display tidy Bootstrap-styled card grids. The only way to tell them apart from the outside:

1. **View source (Cmd-U).** If the press release titles are directly in the HTML inside `<h2>` or `<article>` tags, it's server-rendered and scrapable. If you see empty `<div id="root"></div>` containers and the visible content only appears in `__NEXT_DATA__` or after JavaScript runs, it's client-rendered.

2. **Disable JavaScript and reload.** If the page still shows press release titles, the data is in the HTML (server-rendered, scrapable). If it shows empty placeholders or "Please enable JavaScript," it's client-rendered (needs Playwright).

Either check takes about ten seconds and prevents weeks of building a Playwright collector you didn't need.

## The meta-lesson

Both halves of this case study — the RSS rescue and the year/month filter — share the same shape:

- A previous recon classified a group of sites as needing browser automation
- The classification was based on a single failed test (GraphQL endpoint blocked / `?page=2` doesn't paginate)
- A user push got me to re-examine the assumption
- The actual data path was hiding in plain sight (RSS feed declared in `<link rel="alternate">` / form parameters declared in `<select>` markup)
- The fix was a 100-line Python script, not a multi-day Playwright build

The recurring failure mode: **stopping at the first plausible negative when a fallback option exists.** "We'll just use Playwright" is the comfortable answer that lets you file the work as deferred and move on. Every time that comfortable answer absorbs the discomfort of "is this really blocked," the dead end stays a dead end.

The recurring fix: re-read the page source slowly. The site's HTML, before any JavaScript runs, is the **most underrated artifact in scraping work.** It contains:

- The site's actual stack (CMS markers, JS framework references, theme paths)
- The site's data feeds (`<link rel="alternate">`)
- The site's filter API (form actions, `<select>` and `<input>` names)
- The site's error message style (which tells you what kind of CMS it is)

You can read the page source on your phone in ninety seconds. Most "this needs Playwright" classifications would be reversed by that read.

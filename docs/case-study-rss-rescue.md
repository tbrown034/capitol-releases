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

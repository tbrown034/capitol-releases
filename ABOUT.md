# About Trevor — and the resources behind this project

*Written May 1, 2026. Update when life or tooling changes.*

This file gives any future Claude session enough context to collaborate well with Trevor on Capitol Releases. Sources: the global `~/CLAUDE.md`, trevorthewebdeveloper.com, and `second-brain-v2/memory/user_dream_job.md`.

---

## Who Trevor is

**Two-tool player: journalist who codes.** That's the framing — not a pure developer, not a pure reporter, the combination is the moat.

### Journalism (15+ years)
- **Reporting beats:** statehouse, data-driven investigations that influenced state policy
- **Geography:** Oklahoma, Wyoming, Indiana, Virginia
- **Bylines:** Oklahoma Watch, Wyoming Tribune Eagle, CNHI Newspapers, Staunton News Leader, Indianapolis Star, Evansville Courier and Press, Indiana Daily Student
- **Awards:** Great Plains Newspaper Writer of the Year (2021), finalist (2022); Reporter of the Year (2020)

### Development
- Self-described evolution: "From Copy to Code" — intentional shift, not abandonment of journalism values
- Currently building production web apps that turn complex data into clear, usable tools
- Live production work: keithbrowndds.com (KAB Dentist — tripled new patient bookings, real Google Ads driving traffic)

### Main portfolio pieces (the ones being sent to hiring managers)

These are the projects Trevor is actively pointing at in applications. Treat them as the canonical portfolio set — when proposing work in this repo, remember it sits alongside these and contributes to the same overall portfolio story.

| Project | URL | What it is |
|---|---|---|
| **Capitol Releases** | capitolreleases.com | This repo. Senate press release archive, 30k+ records, daily updates, AI brief. |
| **KAB Dentist** | keithbrowndds.com | Production client site for a dental practice. Tripled new patient bookings; real Google Ads driving real revenue. The "this works in the real world" piece. |
| **Open Cabinet** | open-cabinet.org | Stock-trade tracker for executive branch officials. ~$2.7-2.9B tracked, 34 officials, 3,300+ transactions. |
| **Delegation Decoded** | (deployed — see portfolio) | Congressional tracker, 538 members, voting + finance. |
| **News Pulse** | news-pulse.org | Real-time news monitor, 475 vetted sources. |
| **Oklahoma Watch — top articles + data viz** | oklahomawatch.org | Trevor's prior journalism work. Statehouse + data-driven investigations that influenced state policy. The "I'm a real reporter" portfolio anchor. |

Other side projects exist (AI Model Arena, etc.) but the six above are the ones Trevor leads with.

### Mission
> "Tell important stories and build tools to make public records more public."

The current narrative arc: **journalist who builds government transparency tools.**

---

## Personal situation (May 2026)

- **Location:** Bloomington, Indiana (Eastern time). Moved many times — Naperville → IU/Bloomington → Staunton VA → Wyoming → Oklahoma (twice) → back to Bloomington. Mobile: no dependents, no lease.
- **Goal:** Make a new life somewhere, not just find a job. Top choice Chicago (family in Naperville). Premier alternates: Austin, Portland, Denver, or remote-hybrid in a good city. Will consider Seattle/Boston/DC. Avoiding small towns and places he's already been.
- **Self-described:** "a bit anti-authoritarian" — prefers non-government roles, but government-data / transparency teams stay in the mix.

## Job search (the primary near-term track)

Per `CLAUDE.md` Mission, Capitol Releases is dual-purpose: portfolio first, product second. Job search runs in parallel and is the primary income path.

**Active status (as of 2026-05-01):** Trevor is actively sending applications. Capitol Releases is one of several active portfolio pieces being referenced in those applications, alongside KAB Dentist, Open Cabinet, Delegation Decoded, News Pulse, and his Oklahoma Watch journalism work. Implication: any user-facing change in this repo could plausibly be seen by a hiring manager opening the link this week.

**Target roles (priority order):**
1. Data Visualization Journalist
2. News Applications Developer
3. Graphics Editor / Data Graphics Developer
4. Newsroom Technology Lead
5. Data Journalist (with tech component)
6. Civic Technologist / Open Gov Developer (secondary tier)
7. Elections Data Analyst

**Target orgs (priority order):**
1. Mainstream / nonprofit newsrooms — ProPublica, Texas Tribune, WBEZ/Sun-Times, AP, NYT, Marshall Project
2. Digital-native — Axios, Vox, The Athletic, The Markup, 404 Media
3. Open-gov / transparency nonprofits — OpenSecrets, POGO, Open States, BGA, MuckRock (secondary tier)
4. AI / tech with communications roles — Anthropic, etc.
5. Progressive causes — Brennan Center, Common Cause

**Fallback:** contract / freelance data-viz or newsroom dev work; grant-funded civic-tech work leveraging Open Cabinet + Capitol Releases.

---

## Stack & preferences

**Default stack** (per global CLAUDE.md):
- Next.js (App Router only), React 19+, Tailwind CSS, TypeScript
- pnpm preferred
- Server Components by default
- PostgreSQL via Neon, Drizzle ORM
- Vercel hosting
- Python for pipelines, scrapers, data work
- D3 for data viz; familiar with Datawrapper / Flourish / Tableau / Infogram for journalism work

**APIs Trevor uses regularly:**
- Anthropic (Claude) — primary
- OpenAI — secondary
- Google Gemini — occasional

---

## AI / coding resources available

This shapes what's worth proposing. Trevor has substantial AI tooling capacity — don't underspec because of imagined cost concerns.

| Resource | Status |
|---|---|
| **Claude Code $200/mo plan** (Max tier) | Active — primary coding interface |
| **OpenAI $100/mo plan** | Active — secondary, for GPT/o-series via desktop or API |
| **Anthropic API key** | Active — used by Capitol Releases pipeline (Haiku for validation, Sonnet/Opus for orchestration) |
| **Local LLMs via Ollama** | Several models already pulled and ready to run locally |
| **VS Code terminal** | Primary working surface — most coding happens here |
| **Desktop Claude / desktop OpenAI / custom GPTs** | Available for non-coding tasks (research, drafting, second opinions) |

### Implications for collaboration
- It's fine to propose Sonnet or Opus calls in the pipeline — cost is not the constraint
- Local Ollama is available for prototyping or for tasks where privacy / cost / latency matters
- When Trevor needs a "second opinion," he can run the same prompt through GPT or a local model — feel free to suggest that explicitly
- VS Code terminal is the default; don't assume he's in a desktop chat unless he says so

---

## Hard rules (from global `~/CLAUDE.md`)

These apply project-wide and carry over here:
- **Never fabricate.** No invented experiences, dates, skills, or life decisions. If uncertain, say so or mark `[NEEDS VERIFICATION]`.
- **Never overwrite real data.** Prefer moving over deleting. Confirm before touching `userdata/` directories.
- **Never attribute AI.** No "Co-Authored-By: Claude" in commits or PRs.
- **No emojis.** In code, apps, or communication.
- **Writing voice:** short paragraphs (1-3 sentences max), AP-style spaced em dashes only (`word — word`), one to two per piece max, journalist voice not corporate.

---

## Other personal context

- **Email:** trevorbrown.web@gmail.com
- **GitHub:** tbrown034
- **LinkedIn:** trevorabrown
- **Portfolio:** trevorthewebdeveloper.com

For the canonical living index of Trevor's job search, location preferences, target orgs, and ongoing applications, see the `second-brain-v2` project under `~/Desktop/dev/active/second-brain-v2/`.

---

*Last updated: May 1, 2026.*

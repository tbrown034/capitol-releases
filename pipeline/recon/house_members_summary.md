# House Members Seed — Recon Summary

- Source: https://clerk.house.gov/xml/lists/MemberData.xml
- Source publish-date: April 22, 2026
- Generated: 2026-04-24
- Output: `pipeline/recon/house_members.json`

## Counts

- Total current members: **436**
- Voting representatives: 430
- Non-voting delegates / resident commissioner: 6
- Vacancies excluded: 5

## By Party

- R: 220
- D: 215
- I: 1

## Top 10 States By Seat Count

- CA: 50
- TX: 37
- FL: 27
- NY: 26
- IL: 17
- PA: 17
- OH: 15
- NC: 14
- GA: 13
- MI: 13

## Vacancies (excluded)

- CA01 — vacant (no sitting member in XML)
- CA14 — vacant (no sitting member in XML)
- FL20 — vacant (no sitting member in XML)
- GA13 — vacant (no sitting member in XML)
- TX23 — vacant (no sitting member in XML)

## Non-Voting Delegates (included)

- AS Delegate: Aumua Amata Coleman Radewagen (R)
- DC Delegate: Eleanor Holmes Norton (D)
- GU Delegate: James C. Moylan (R)
- MP Delegate: Kimberlyn King-Hinds (R)
- PR Resident Commissioner: Pablo José Hernández (D)
- VI Delegate: Stacey E. Plaskett (D)

## Records Flagged `needs_verification`

- None

## Notes / Anomalies

- The Clerk XML publish-date is April 22, 2026; today is 2026-04-24. The file already reflects Rep. David Scott's death (GA-13, April 22 2026), so GA-13 is treated as vacant.
- GA-14 resolves to Clay Fuller (R), who was sworn in April 14 2026 after winning the runoff to replace Marjorie Taylor Greene (resigned Jan 5 2026).
- CA-01 vacant following Rep. Doug LaMalfa's death (Jan 6 2026); special election scheduled June 2 2026.
- `district` is stored as a string. Numbered districts use the bare numeral ("1", "12"), at-large states use "At-Large", and territories use "Delegate" / "Resident Commissioner" (Puerto Rico).
- `official_url` was carried over from `pipeline/seeds/house.json` by matching on (state, district). `press_release_url` is left `null` per task brief — downstream recon fills it.
- `member_id` is `lastname-firstname` (accents stripped, lowercased, hyphenated). Collisions append `-<state><district>` but none were observed in the current roster.
- Kevin Kiley (CA-3) is listed by the Clerk as party="I" but caucus="R". The seed preserves party="I" to match the authoritative source; downstream consumers that need caucus affiliation should pull it separately.
- Analilia Mejia (NJ-11) sworn in April 20, 2026 — too recent for the prior recon seed. Canonical https://mejia.house.gov supplied via MANUAL_OFFICIAL_URL override in build_house_members.py (HTTP 200 verified 2026-04-24).
- Four URLs in the prior `pipeline/seeds/house.json` had Unicode accents incorrectly stripped, producing dead subdomains (`snchez`, `barragn`, `velzquez`, `hernndez`). Fixed via manual overrides to the real `lindasanchez`, `barragan`, `velazquez`, `hernandez` subdomains (all HTTP 200 verified 2026-04-24). The prior seed file itself still carries the bad URLs and should be patched separately before it is used as a collector source.
- District encoding diverges slightly from the task brief ("AL" for at-large): this file uses "At-Large" (hyphenated) to match the existing `pipeline/seeds/house.json` convention, and uses "Delegate" / "Resident Commissioner" to distinguish non-voting seats — more precise than flattening them to at-large.

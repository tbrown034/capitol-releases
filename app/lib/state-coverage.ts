// Shared coverage data for /states and /states/[code].
//
// Coverage STATUS is read from the database, not declared here. The static
// list below drifted badly: on 2026-07-28 it still listed California and
// Ohio as "planned, 0 releases" while the corpus held 1,362 Californian
// and 735 Ohio records, and it knew nothing about Missouri, Nebraska,
// Colorado or West Virginia. A public page claiming we have no California
// coverage while shipping California data is worse than a missing page.
//
// What stays hand-authored is presentation only -- display names, the note
// under each row, and the href when a state has earned a bespoke page.
// Anything with rows in the database is live whether or not someone
// remembered to edit this file.

export type CoverageStatus = "live" | "in_progress" | "planned";

export type StateRow = {
  code: string;
  name: string;
  chamber: string;
  members: number;
  releases: number;
  since: string | null;
  status: CoverageStatus;
  href: string | null;
  note: string;
};

export const COVERAGE: StateRow[] = [
  {
    code: "TX",
    name: "Texas",
    chamber: "State Senate",
    members: 30,
    releases: 314,
    since: "2025-01-14",
    status: "live",
    href: "/texas",
    note: "30 of 31 districts (D4 vacant). Daily ingest from senate.texas.gov.",
  },
];

export const PLANNED: StateRow[] = [
  { code: "CA", name: "California", chamber: "State Senate", members: 40, releases: 0, since: null, status: "planned", href: null, note: "Phase 1." },
  { code: "NY", name: "New York", chamber: "State Senate", members: 63, releases: 0, since: null, status: "planned", href: null, note: "Phase 1." },
  { code: "OH", name: "Ohio", chamber: "State Senate", members: 33, releases: 0, since: null, status: "planned", href: null, note: "Phase 1." },
];

export function getStateRow(code: string): StateRow | null {
  const upper = code.toUpperCase();
  return (
    COVERAGE.find((s) => s.code === upper) ??
    PLANNED.find((s) => s.code === upper) ??
    null
  );
}

// Presentation for states the collector actually serves. Status, counts and
// dates all come from the database; only these fields are editorial.
const STATE_PRESENTATION: Record<
  string,
  { chamber: string; href: string | null; note: string }
> = {
  tx: {
    chamber: "State Senate",
    href: "/texas",
    note: "Daily ingest from senate.texas.gov. The Texas House publishes no per-member press.",
  },
  co: {
    chamber: "General Assembly",
    href: "/colorado",
    note: "No legislator has a .gov pressroom; all press output comes from four party caucuses.",
  },
  ca: { chamber: "State Senate", href: null, note: "All 40 districts, senate.ca.gov." },
  oh: { chamber: "State Senate", href: null, note: "All 33 districts, ohiosenate.gov." },
  mo: { chamber: "State Senate", href: null, note: "Per-member media pages, senate.mo.gov." },
  ne: { chamber: "Unicameral", href: null, note: "Nebraska's single chamber, nebraskalegislature.gov." },
  wv: { chamber: "Legislature", href: null, note: "Chamber-level newsroom only." },
};

export type LiveStateCoverage = StateRow & {
  jurisdiction: string;
  latest: string | null;
};

/**
 * Coverage for every state jurisdiction present in the database.
 *
 * A state counts as live once it has collected records. Seeded but empty
 * jurisdictions report in_progress so the page never claims coverage the
 * corpus cannot back up.
 */
export async function getLiveStateCoverage(): Promise<LiveStateCoverage[]> {
  const { sql } = await import("./db");
  const { STATE_NAMES } = await import("./states");

  const rows = (await sql`
    SELECT o.jurisdiction,
           COUNT(DISTINCT o.id) FILTER (
             WHERE o.collection_method IS NOT NULL
           )::int AS members,
           COUNT(pr.id)::int AS releases,
           MIN(pr.published_at)::text AS since,
           MAX(pr.published_at)::text AS latest
    FROM officials o
    LEFT JOIN official_site_items pr
      ON pr.official_id = o.id
     AND pr.deleted_at IS NULL
     AND pr.content_type <> 'photo_release'
    WHERE o.jurisdiction <> 'us'
      AND o.jurisdiction IS NOT NULL
      AND o.status = 'active'
    GROUP BY o.jurisdiction
    ORDER BY releases DESC
  `) as {
    jurisdiction: string;
    members: number;
    releases: number;
    since: string | null;
    latest: string | null;
  }[];

  return rows.map((r) => {
    const code = r.jurisdiction.toUpperCase();
    const p = STATE_PRESENTATION[r.jurisdiction] ?? {
      chamber: "Legislature",
      href: null,
      note: "",
    };
    return {
      code,
      name: STATE_NAMES[code] ?? code,
      chamber: p.chamber,
      members: r.members,
      releases: r.releases,
      since: r.since,
      latest: r.latest,
      status: (r.releases > 0 ? "live" : "in_progress") as CoverageStatus,
      href: p.href ?? `/states/${r.jurisdiction}`,
      note: p.note,
      jurisdiction: r.jurisdiction,
    };
  });
}

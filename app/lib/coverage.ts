// Seat counts fixed by law. They are denominators and sanity ceilings only.
// Every count of members we actually cover is read from the database
// (officials WHERE status = 'active' AND jurisdiction = 'us'), never from
// these numbers and never from raw seed-file row counts, which include
// non-voting delegates.
export const SENATE_SEATS = 100;
export const HOUSE_SEATS = 435;

// The House roster carries six non-voting delegates (437 seed rows, 435
// voting seats). Every House figure on the methodology page counts voting
// members only, on both sides of the fraction, so the denominator and the
// numerators describe the same population.
export const NON_VOTING_HOUSE_STATES = new Set([
  "AS",
  "DC",
  "GU",
  "MP",
  "PR",
  "VI",
]);

export function isVotingHouseMember(row: { state: string }): boolean {
  return !NON_VOTING_HOUSE_STATES.has(row.state.toUpperCase());
}

// Pure coverage arithmetic for the /about methodology table.
//
// Two bugs lived here before: the "clean senators" figure came from a
// GROUP BY query whose first row was one senator's release count (344), and
// "accounted for" added the documented-gap seed count to the clean count, so
// a member who was both clean and documented was counted twice — which put
// the House above 100% and drove the trouble list negative. Counting is now
// done over a per-member row set, so every figure is a subset of the total.

export type HouseCoverageRow = {
  id: string;
  state: string;
  reaches: boolean;
};

export type CoverageInput = {
  senateClean: number;
  senateTotal: number;
  senateDocumented: number;
  houseRows: HouseCoverageRow[];
  houseDocumentedIds: Set<string>;
  houseSeedRows: number;
};

export type CoverageRow = [metric: string, status: string, note: string];

// Runtime guard: no published figure may exceed its ceiling or go negative.
// There is no JS test harness in the deploy path, so a bad number logs and
// clamps rather than reaching the page.
function clamp(value: number, max: number, label: string): number {
  if (!Number.isFinite(value) || value < 0) {
    console.warn(`[coverage] ${label} was ${value}; clamped to 0`);
    return 0;
  }
  if (value > max) {
    console.warn(`[coverage] ${label} was ${value}, above ${max}; clamped`);
    return max;
  }
  return value;
}

export function buildCoverageRows(input: CoverageInput): CoverageRow[] {
  const senateTotal = clamp(input.senateTotal, SENATE_SEATS, "active senators");
  const senateClean = clamp(
    input.senateClean,
    senateTotal || SENATE_SEATS,
    "clean senators"
  );

  // Delegates are dropped before anything is counted. Clamping a 437-row
  // total down to 435 instead would have silently absorbed two real gaps.
  const votingRows = input.houseRows.filter(isVotingHouseMember);
  const houseTotal = clamp(
    votingRows.length,
    HOUSE_SEATS,
    "voting House members"
  );
  const reaches = clamp(
    votingRows.filter((r) => r.reaches).length,
    houseTotal,
    "House members reaching Jan. 2025"
  );
  const accountedFor = clamp(
    votingRows.filter((r) => r.reaches || input.houseDocumentedIds.has(r.id))
      .length,
    houseTotal,
    "House members accounted for"
  );
  const documentedGaps = Math.max(0, accountedFor - reaches);
  const troubleList = Math.max(0, houseTotal - accountedFor);

  const pct = (n: number) =>
    houseTotal === 0 ? "0.0" : ((n / houseTotal) * 100).toFixed(1);

  return [
    [
      "U.S. senators (clean)",
      `${senateClean} / ${senateTotal}`,
      `${input.senateDocumented} documented gaps; rest publishing on schedule.`,
    ],
    [
      "U.S. House (configured)",
      `${houseTotal} / ${HOUSE_SEATS}`,
      `Every voting seat has a source row. The seed file carries ${input.houseSeedRows} rows; the ${input.houseSeedRows - houseTotal} non-voting delegate seats are excluded from every figure in this table.`,
    ],
    [
      "House — reaches Jan. 2025",
      `${reaches} / ${houseTotal}`,
      `${pct(reaches)}% have 10 or more records reaching back to early 2025.`,
    ],
    [
      "House — bulletproof accounted for",
      `${accountedFor} / ${houseTotal}`,
      `${pct(accountedFor)}% — clean rows plus ${documentedGaps} members tagged as documented gaps (Phase 2 scrapers, scraper bugs, low-volume offices).`,
    ],
    [
      "House — open trouble list",
      `${troubleList}`,
      "Members with shallow archives where the cause is still under investigation.",
    ],
  ];
}

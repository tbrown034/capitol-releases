// Shared coverage data for /states and /states/[code]. Edit here to update
// both surfaces.

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
    href: "/states/tx",
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

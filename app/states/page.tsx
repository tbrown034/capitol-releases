import Link from "next/link";
import { CoverageCartogram } from "../components/coverage-cartogram";

export const metadata = {
  title: "States — Capitol Releases",
};

export const revalidate = 600;

type StateRow = {
  code: string;
  name: string;
  chamber: string;
  members: number;
  releases: number;
  since: string | null;
  status: "live" | "in_progress" | "planned";
  href: string | null;
  note: string;
};

const COVERAGE: StateRow[] = [
  {
    code: "TX",
    name: "Texas",
    chamber: "State Senate",
    members: 31,
    releases: 0,
    since: null,
    status: "in_progress",
    href: "/states/tx",
    note: "Backfilling press releases since Jan 1, 2025.",
  },
];

const PLANNED: StateRow[] = [
  { code: "CA", name: "California", chamber: "State Senate", members: 40, releases: 0, since: null, status: "planned", href: null, note: "Phase 1." },
  { code: "NY", name: "New York", chamber: "State Senate", members: 63, releases: 0, since: null, status: "planned", href: null, note: "Phase 1." },
  { code: "OH", name: "Ohio", chamber: "State Senate", members: 33, releases: 0, since: null, status: "planned", href: null, note: "Phase 1." },
];

export default async function StatesPage() {
  const cartogramData = COVERAGE.map((s) => ({
    code: s.code,
    name: s.name,
    href: s.href ?? "#",
    members: s.members,
    releases: s.releases,
    status: s.status as "live" | "in_progress",
  }));

  return (
    <div className="mx-auto max-w-5xl px-4 py-12">
      <h1 className="font-[family-name:var(--font-source-serif)] text-4xl text-neutral-900 mb-3">
        Every senator in America
      </h1>
      <p className="text-sm text-neutral-600 leading-relaxed mb-2 max-w-2xl">
        Capitol Releases archives the official press output of all 100 U.S.
        senators. We&apos;re extending the same treatment to state senates,
        starting with Texas.
      </p>
      <p className="text-xs text-neutral-500 leading-relaxed mb-8 max-w-2xl">
        Free tier covers every senator at every level. Original press releases,
        statements, op-eds and floor statements from official .gov sources, with
        provenance and deletion detection.
      </p>

      <CoverageCartogram coverage={cartogramData} />

      <div className="border-b border-neutral-200 my-8" />

      <h2 className="text-xs uppercase tracking-wider text-neutral-500 mb-4">
        In progress
      </h2>
      <div className="space-y-3 mb-10">
        {COVERAGE.map((s) => (
          <StateCard key={s.code} row={s} />
        ))}
      </div>

      <h2 className="text-xs uppercase tracking-wider text-neutral-500 mb-4">
        Planned next
      </h2>
      <div className="space-y-3">
        {PLANNED.map((s) => (
          <StateCard key={s.code} row={s} />
        ))}
      </div>

      <p className="text-xs text-neutral-400 mt-10 max-w-2xl leading-relaxed">
        Roadmap: state senates first, then governors and cabinet, then state
        houses. Coverage horizon: January 1, 2025 forward.
      </p>
    </div>
  );
}

function StateCard({ row }: { row: StateRow }) {
  const inner = (
    <div className="flex items-center gap-4 border border-neutral-200 px-4 py-3 transition-colors hover:border-neutral-400">
      <div
        className={`flex h-10 w-10 items-center justify-center border text-xs font-[family-name:var(--font-dm-mono)] font-medium ${
          row.status === "live"
            ? "bg-emerald-100 border-emerald-300 text-emerald-900"
            : row.status === "in_progress"
            ? "bg-amber-50 border-amber-200 text-amber-900"
            : "bg-neutral-50 border-neutral-200 text-neutral-400"
        }`}
      >
        {row.code}
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-baseline gap-2">
          <span className="text-sm text-neutral-900 font-medium">
            {row.name}
          </span>
          <span className="text-xs text-neutral-500">{row.chamber}</span>
        </div>
        <p className="text-xs text-neutral-500 mt-0.5 leading-snug">
          {row.note}
        </p>
      </div>
      <div className="hidden sm:flex flex-col items-end text-xs text-neutral-500 font-[family-name:var(--font-dm-mono)] tabular-nums">
        <span>{row.members} senators</span>
        {row.releases > 0 && (
          <span className="text-neutral-400">
            {row.releases.toLocaleString()} releases
          </span>
        )}
      </div>
    </div>
  );

  if (row.href) {
    return <Link href={row.href}>{inner}</Link>;
  }
  return <div className="opacity-70">{inner}</div>;
}

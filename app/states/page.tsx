import Link from "next/link";
import { CoverageCartogram } from "../components/coverage-cartogram";
import {
  PLANNED,
  getLiveStateCoverage,
  type StateRow,
} from "../lib/state-coverage";
import { formatReleaseDate } from "../lib/dates";

export const metadata = {
  title: "States — Capitol Releases",
};

export const revalidate = 600;

export default async function StatesPage() {
  // Every state jurisdiction in the corpus, counted at request time. The
  // previous version read a hand-edited list that only knew about Texas,
  // so California and Ohio were advertised as "planned, 0 releases" while
  // the collector was already storing thousands of their records.
  const enrichedCoverage = await getLiveStateCoverage();
  const liveCodes = new Set(enrichedCoverage.map((s) => s.code));
  const stillPlanned = PLANNED.filter((s) => !liveCodes.has(s.code));

  // Headline figures are computed, not written. The previous copy claimed
  // "all 100 U.S. senators" and a "January 1, 2025 forward" horizon while
  // the corpus already held 435 House members and records back to 2015.
  const liveRows = enrichedCoverage.filter((s) => s.status === "live");
  const totalRecords = liveRows.reduce((n, s) => n + s.releases, 0);
  const totalSources = liveRows.reduce((n, s) => n + s.members, 0);
  const liveStates = liveRows.length;
  const oldest = liveRows
    .map((s) => s.since)
    .filter((d): d is string => Boolean(d))
    .sort()[0];

  const cartogramData = enrichedCoverage
    .filter((s) => s.status === "live")
    .map((s) => ({
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
        State coverage
      </h1>
      <p className="text-sm text-neutral-600 leading-relaxed mb-2 max-w-2xl">
        The same archival method behind the U.S. Senate and House corpus,
        applied to state government:{" "}
        <span className="font-[family-name:var(--font-dm-mono)] tabular-nums">
          {totalRecords.toLocaleString()}
        </span>{" "}
        records from{" "}
        <span className="font-[family-name:var(--font-dm-mono)] tabular-nums">
          {totalSources}
        </span>{" "}
        {/* No line break before the comma: JSX renders one as a space. */}
        sources across {liveStates} states{oldest ? `, reaching back to ${formatReleaseDate(oldest)}.` : "."}
      </p>
      <p className="text-xs text-neutral-500 leading-relaxed mb-8 max-w-2xl">
        Original press releases, statements and op-eds, with full provenance
        and deletion detection on every record. Most sources are official .gov
        pressrooms. Colorado is the exception and the reason this page does not
        promise otherwise: no Colorado legislator publishes on a state site, so
        all of its output is collected from the four party caucus
        organizations, which run on commercial domains.
      </p>

      <CoverageCartogram coverage={cartogramData} />

      <div className="border-b border-neutral-200 my-8" />

      <h2 className="text-xs uppercase tracking-wider text-neutral-500 mb-4">
        Live
      </h2>
      <div className="space-y-3 mb-10">
        {enrichedCoverage.map((s) => (
          <StateCard key={s.code} row={s} />
        ))}
      </div>

      <h2 className="text-xs uppercase tracking-wider text-neutral-500 mb-4">
        Planned next
      </h2>
      <div className="space-y-3">
        {stillPlanned.map((s) => (
          <StateCard key={s.code} row={s} />
        ))}
      </div>

      <p className="text-xs text-neutral-500 mt-10 max-w-2xl leading-relaxed">
        Every chamber above is collected as deeply as its own archive allows,
        which is often further back than January 2025. A chamber ships only
        once its coverage is verifiable, and sources that publish nothing are
        labelled rather than hidden — the Texas House, for instance, is absent
        because all 150 of its members were checked and none publishes press
        releases at all.
      </p>
    </div>
  );
}

function StateCard({ row }: { row: StateRow }) {
  const inner = (
    <div className="flex items-center gap-4 border border-neutral-200 px-4 py-3 transition-colors hover:border-neutral-400">
      <div
        className={`flex size-10 items-center justify-center border text-xs font-[family-name:var(--font-dm-mono)] font-medium ${
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
        {/* "senators" is wrong for two of the live rows: Nebraska's chamber
            is unicameral and Colorado's sources are four party caucuses,
            not members. Count what the row actually holds. */}
        <span>
          {row.members} {row.members === 1 ? "source" : "sources"}
        </span>
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

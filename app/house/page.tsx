import Link from "next/link";
import { getHouseMembers } from "../lib/queries";
import type { SenatorWithCount } from "../lib/db";
import { STATE_NAMES } from "../lib/states";
import { formatMonthYear } from "../lib/dates";

export const metadata = {
  title: "US House — Capitol Releases",
  description:
    "Press releases, statements, op-eds, and newsletters from all 437 members of the US House of Representatives, archived since January 2025.",
};

export const revalidate = 600;

export default async function HousePage() {
  const members = await getHouseMembers();

  // Group by state for a tighter visual (437 in one flat list is too long).
  const byState = new Map<string, SenatorWithCount[]>();
  for (const m of members) {
    const list = byState.get(m.state) ?? [];
    list.push(m);
    byState.set(m.state, list);
  }
  // Sort states alphabetically by full name; within a state sort by district
  // (numeric where possible, "At-Large" last).
  const states = Array.from(byState.keys()).sort((a, b) =>
    (STATE_NAMES[a] ?? a).localeCompare(STATE_NAMES[b] ?? b),
  );

  const totalMembers = members.length;
  const totalReleases = members.reduce((s, m) => s + m.release_count, 0);
  const collecting = members.filter((m) => m.release_count > 0).length;

  return (
    <div className="mx-auto max-w-5xl px-4 py-12">
      <h1 className="font-[family-name:var(--font-source-serif)] text-4xl text-neutral-900 mb-3">
        US House of Representatives
      </h1>
      <p className="text-sm text-neutral-600 leading-relaxed mb-2 max-w-2xl">
        All {totalMembers.toLocaleString()} House members in the 119th Congress.
        Press releases, statements, op-eds, and newsletters from each
        member&apos;s official .gov site, collected since January 2025 with
        provenance and deletion detection.
      </p>
      <p className="text-xs text-neutral-500 leading-relaxed mb-8 max-w-2xl">
        Coverage: {collecting.toLocaleString()} of {totalMembers.toLocaleString()}{" "}
        members actively collecting (
        {Math.round((collecting / totalMembers) * 100)}%
        ).{" "}
        {totalReleases.toLocaleString()} records archived. The remaining members
        are recon-discovered but their listings haven&apos;t been wired up yet
        (wave-3 manual triage pending).
      </p>

      {states.map((state) => {
        const list = byState.get(state) ?? [];
        const stateName = STATE_NAMES[state] ?? state;
        return (
          <section key={state} className="mb-10">
            <h2 className="text-xs uppercase tracking-wider text-neutral-500 mb-3 font-[family-name:var(--font-dm-mono)]">
              {stateName} ({list.length})
            </h2>
            <div className="space-y-1">
              {list.map((m) => (
                <Link
                  key={m.id}
                  href={`/house/${m.id}`}
                  className="flex items-baseline gap-3 border-b border-neutral-100 py-2 hover:bg-neutral-50 transition-colors px-2 -mx-2"
                >
                  <span className="font-[family-name:var(--font-dm-mono)] text-xs text-neutral-500 tabular-nums w-12 shrink-0">
                    {formatDistrict(m.district)}
                  </span>
                  <span className="text-sm text-neutral-900 flex-1 truncate">
                    {m.full_name}
                  </span>
                  <span
                    className={`text-xs ${
                      m.party === "D"
                        ? "text-blue-600"
                        : m.party === "R"
                          ? "text-red-600"
                          : "text-amber-600"
                    } shrink-0 w-3`}
                  >
                    {m.party}
                  </span>
                  <span className="text-xs text-neutral-500 font-[family-name:var(--font-dm-mono)] tabular-nums w-20 text-right shrink-0">
                    {m.release_count > 0
                      ? m.release_count.toLocaleString()
                      : "—"}
                  </span>
                  <span className="hidden sm:inline text-xs text-neutral-400 w-24 text-right shrink-0">
                    {m.latest_release
                      ? formatMonthYear(m.latest_release)
                      : ""}
                  </span>
                </Link>
              ))}
            </div>
          </section>
        );
      })}

      <p className="text-xs text-neutral-500 mt-10 max-w-2xl leading-relaxed">
        Coverage horizon: January 1, 2025 forward. Members showing &quot;—&quot;
        for record count are recon-discovered but their listings need manual
        triage; the daily collector picks them up automatically once
        promoted.
      </p>
    </div>
  );
}

function formatDistrict(d: string | null | undefined): string {
  if (!d) return "—";
  const n = Number(d);
  return Number.isFinite(n) ? `D-${String(n).padStart(2, "0")}` : d;
}

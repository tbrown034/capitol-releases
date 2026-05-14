import Link from "next/link";
import Image from "next/image";
import {
  getSenators,
  CONTENT_TYPE_ORDER,
  CONTENT_TYPE_PLURAL,
} from "../../lib/queries";
import { sql } from "../../lib/db";
import type { SenatorWithCount, ContentType } from "../../lib/db";
import { formatMonthYear, formatShortDate } from "../../lib/dates";
import { STATE_NAMES } from "../../lib/states";

function formatBreakdown(
  breakdown: Partial<Record<ContentType, number>>
): string | null {
  const parts: string[] = [];
  for (const t of CONTENT_TYPE_ORDER) {
    const n = breakdown[t];
    if (n && n > 0) parts.push(`${n.toLocaleString()} ${CONTENT_TYPE_PLURAL[t]}`);
  }
  return parts.length > 0 ? parts.join(" · ") : null;
}

export const metadata = {
  title: "Senate — Capitol Releases",
  description:
    "All 100 U.S. senators with publishing volume, latest release, and term info.",
};

export const revalidate = 600;

type SortKey = "count" | "state" | "name";

export default async function SenateDirectoryPage({
  searchParams,
}: {
  searchParams: Promise<{ sort?: string; state?: string }>;
}) {
  const { sort, state: stateParam } = await searchParams;
  const sortKey: SortKey =
    sort === "state" ? "state" : sort === "name" ? "name" : "count";
  const activeState = stateParam?.toUpperCase();

  const [senators, bioguides] = await Promise.all([
    getSenators(),
    sql`SELECT id, bioguide_id FROM officials WHERE bioguide_id IS NOT NULL`,
  ]);
  const bioMap = new Map<string, string>();
  for (const row of bioguides as { id: string; bioguide_id: string }[]) {
    bioMap.set(row.id, row.bioguide_id);
  }

  const filtered = activeState
    ? senators.filter((s) => s.state === activeState)
    : senators;

  const sorted = [...filtered].sort((a, b) => {
    if (sortKey === "state") return a.state.localeCompare(b.state) || a.full_name.localeCompare(b.full_name);
    if (sortKey === "name") return a.full_name.localeCompare(b.full_name);
    return b.release_count - a.release_count;
  });

  const withReleases = senators.filter((s) => s.release_count > 0);

  return (
    <div className="mx-auto max-w-5xl px-4 py-12">
      <p className="text-[11px] uppercase tracking-wider text-neutral-500 mb-2">
        <Link href="/members" className="hover:text-neutral-900">
          Members
        </Link>{" "}
        / Senate
      </p>
      <h1 className="font-[family-name:var(--font-source-serif)] text-4xl text-neutral-900 mb-3">
        Every senator, every release
      </h1>
      <p className="text-sm text-neutral-600 leading-relaxed mb-2 max-w-2xl">
        Click a senator to see their full archive, publishing cadence and what
        they&apos;re talking about right now.
      </p>
      <p className="text-xs text-neutral-500 leading-relaxed mb-6 max-w-2xl">
        Tracking all 100 senators. {withReleases.length} publish press releases;
        Sen. Armstrong&apos;s office hasn&apos;t yet.{" "}
        <Link href="/members" className="underline hover:text-neutral-900">
          Browse by state →
        </Link>
      </p>

      <div className="mb-6 flex flex-wrap items-center gap-2 text-xs">
        <span className="uppercase tracking-wider text-neutral-400">Sort</span>
        <SortLink value="count" label="By volume" sortKey={sortKey} activeState={activeState} />
        <SortLink value="state" label="By state" sortKey={sortKey} activeState={activeState} />
        <SortLink value="name" label="A–Z" sortKey={sortKey} activeState={activeState} />
        {activeState && (
          <span className="ml-auto text-neutral-500">
            Showing{" "}
            <span className="text-neutral-900 font-medium">
              {STATE_NAMES[activeState] ?? activeState}
            </span>{" "}
            ({sorted.length})
            <Link
              href={`/members/senate${sort && sort !== "count" ? `?sort=${sort}` : ""}`}
              className="ml-2 underline hover:text-neutral-900"
            >
              Clear
            </Link>
          </span>
        )}
      </div>

      <div className="border-b border-neutral-200 mb-6" />

      <div className="-mx-4 overflow-x-auto px-4 sm:mx-0 sm:px-0">
      <table className="w-full min-w-[640px] text-sm">
        <thead>
          <tr className="border-b border-neutral-800 text-xs uppercase tracking-wider text-neutral-500">
            <th className="pb-2 pr-4 text-right font-medium w-12">#</th>
            <th className="pb-2 pr-4 text-left font-medium">Senator</th>
            <th className="pb-2 pr-4 text-left font-medium">State</th>
            <th className="pb-2 pr-4 text-left font-medium">Party</th>
            <th className="pb-2 pr-4 text-right font-medium">Releases</th>
            <th className="hidden sm:table-cell pb-2 text-right font-medium">Latest</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((s: SenatorWithCount, i: number) => {
            const bioId = bioMap.get(s.id);
            const breakdown = formatBreakdown(s.type_breakdown);
            const since = formatMonthYear(s.earliest_release);
            return (
              <tr
                key={s.id}
                className={`border-b border-neutral-100 ${i % 2 === 1 ? "bg-neutral-50/60" : ""}`}
              >
                <td className="py-2.5 pr-4 text-right font-[family-name:var(--font-dm-mono)] tabular-nums text-neutral-400 align-top">
                  {i + 1}
                </td>
                <td className="py-2.5 pr-4 align-top">
                  <Link
                    href={`/senators/${s.id}`}
                    className="flex items-center gap-3 hover:underline"
                  >
                    {bioId ? (
                      <Image
                        src={`/senators/${bioId}.jpg`}
                        alt={s.full_name}
                        width={32}
                        height={32}
                        className="h-8 w-8 object-cover object-top"
                        unoptimized
                      />
                    ) : (
                      <div className="h-8 w-8 bg-neutral-200 flex items-center justify-center text-[10px] text-neutral-400">
                        {s.full_name.split(" ").map(n => n[0]).join("").slice(0, 2)}
                      </div>
                    )}
                    <span className="text-neutral-900 font-medium">{s.full_name}</span>
                  </Link>
                  {breakdown && (
                    <p className="mt-1 ml-11 text-[11px] text-neutral-500 leading-snug">
                      {breakdown}
                      {since && <span className="text-neutral-300"> · since {since}</span>}
                    </p>
                  )}
                </td>
                <td className="py-2.5 pr-4 text-neutral-500 align-top">
                  <Link
                    href={`/members/${s.state.toLowerCase()}`}
                    className="hover:underline hover:text-neutral-900"
                  >
                    {s.state}
                  </Link>
                </td>
                <td className="py-2.5 pr-4 align-top">
                  <span className={`${
                    s.party === "D" ? "text-blue-600" : s.party === "R" ? "text-red-600" : "text-amber-600"
                  }`}>
                    {s.party === "D" ? "Democrat" : s.party === "R" ? "Republican" : "Independent"}
                  </span>
                </td>
                <td className="py-2.5 pr-4 text-right font-[family-name:var(--font-dm-mono)] tabular-nums text-neutral-600 align-top">
                  {s.release_count > 0 ? s.release_count.toLocaleString() : (
                    <span className="text-neutral-300">—</span>
                  )}
                </td>
                <td className="hidden sm:table-cell py-2.5 text-right font-[family-name:var(--font-dm-mono)] tabular-nums text-neutral-400 whitespace-nowrap align-top">
                  {s.latest_release ? formatShortDate(s.latest_release) : "---"}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      </div>
    </div>
  );
}

function SortLink({
  value,
  label,
  sortKey,
  activeState,
}: {
  value: SortKey;
  label: string;
  sortKey: SortKey;
  activeState: string | undefined;
}) {
  const params = new URLSearchParams();
  if (value !== "count") params.set("sort", value);
  if (activeState) params.set("state", activeState);
  const q = params.toString();
  return (
    <Link
      href={q ? `/members/senate?${q}` : "/members/senate"}
      className={`rounded-full border px-2.5 py-1 transition-colors ${
        sortKey === value
          ? "border-neutral-900 bg-neutral-900 text-white"
          : "border-neutral-200 text-neutral-500 hover:border-neutral-400 hover:text-neutral-900"
      }`}
    >
      {label}
    </Link>
  );
}

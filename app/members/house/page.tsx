import Link from "next/link";
import Image from "next/image";
import {
  getHouseMembers,
  CONTENT_TYPE_ORDER,
  CONTENT_TYPE_PLURAL,
} from "../../lib/queries";
import { sql } from "../../lib/db";
import type { SenatorWithCount, ContentType } from "../../lib/db";
import { formatShortDate, formatMonthYear } from "../../lib/dates";
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

function formatDistrict(d: string | null | undefined): string {
  if (!d) return "At-Large";
  const n = Number(d);
  return Number.isFinite(n) ? String(n) : d;
}

export const metadata = {
  title: "House, Capitol Releases",
  description:
    "All 437 U.S. House members with publishing volume, latest release, and district info.",
};

export const revalidate = 600;

type SortKey = "count" | "state" | "name";

export default async function HouseDirectoryPage({
  searchParams,
}: {
  searchParams: Promise<{ sort?: string; state?: string }>;
}) {
  const { sort, state: stateParam } = await searchParams;
  const sortKey: SortKey =
    sort === "state" ? "state" : sort === "name" ? "name" : "count";
  const activeState = stateParam?.toUpperCase();

  const [members, bioguides] = await Promise.all([
    getHouseMembers(),
    sql`SELECT id, bioguide_id FROM officials WHERE bioguide_id IS NOT NULL AND chamber = 'house' AND jurisdiction = 'us'`,
  ]);
  const bioMap = new Map<string, string>();
  for (const row of bioguides as { id: string; bioguide_id: string }[]) {
    bioMap.set(row.id, row.bioguide_id);
  }

  const filtered = activeState
    ? members.filter((m) => m.state === activeState)
    : members;

  const sorted = filtered.toSorted((a, b) => {
    if (sortKey === "state") {
      const s = a.state.localeCompare(b.state);
      if (s !== 0) return s;
      const aN = Number(a.district);
      const bN = Number(b.district);
      if (Number.isFinite(aN) && Number.isFinite(bN)) return aN - bN;
      return (a.district ?? "").localeCompare(b.district ?? "");
    }
    if (sortKey === "name") return a.full_name.localeCompare(b.full_name);
    return b.release_count - a.release_count;
  });

  const withReleases = members.filter((m) => m.release_count > 0);

  return (
    <div className="mx-auto max-w-5xl px-4 py-12">
      <p className="text-[11px] uppercase tracking-wider text-neutral-500 mb-2">
        <Link href="/members" className="hover:text-neutral-900">
          Members
        </Link>{" "}
        / House
      </p>
      <h1 className="font-[family-name:var(--font-source-serif)] text-4xl text-neutral-900 mb-3">
        Every House member, every release
      </h1>
      <p className="text-sm text-neutral-600 leading-relaxed mb-2 max-w-2xl">
        All {members.length.toLocaleString()} House members in the 119th
        Congress. Click any member to see their full archive, publishing cadence
        and what they&apos;re talking about right now.
      </p>
      <p className="text-xs text-neutral-500 leading-relaxed mb-6 max-w-2xl">
        {withReleases.length.toLocaleString()} of{" "}
        {members.length.toLocaleString()} actively publishing (
        {Math.round((withReleases.length / members.length) * 100)}%).{" "}
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
              href={`/members/house${sort && sort !== "count" ? `?sort=${sort}` : ""}`}
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
              <th className="pb-2 pr-4 text-left font-medium">Member</th>
              <th className="pb-2 pr-4 text-left font-medium">State</th>
              <th className="pb-2 pr-4 text-left font-medium">Dist.</th>
              <th className="pb-2 pr-4 text-left font-medium">Party</th>
              <th className="pb-2 pr-4 text-right font-medium">Releases</th>
              <th className="hidden sm:table-cell pb-2 text-right font-medium">Latest</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((m: SenatorWithCount, i: number) => {
              const bioId = bioMap.get(m.id);
              const breakdown = formatBreakdown(m.type_breakdown);
              const since = formatMonthYear(m.earliest_release);
              return (
                <tr
                  key={m.id}
                  className={`border-b border-neutral-100 ${i % 2 === 1 ? "bg-neutral-50/60" : ""}`}
                >
                  <td className="py-2.5 pr-4 text-right font-[family-name:var(--font-dm-mono)] tabular-nums text-neutral-400 align-top">
                    {i + 1}
                  </td>
                  <td className="py-2.5 pr-4 align-top">
                    <Link
                      href={`/house/${m.id}`}
                      className="flex items-center gap-3 hover:underline"
                    >
                      {bioId ? (
                        <Image
                          src={`/house/${bioId}.jpg`}
                          alt={m.full_name}
                          width={32}
                          height={32}
                          className="size-8 object-cover object-top"
                          unoptimized
                        />
                      ) : (
                        <div className="size-8 bg-neutral-200 flex items-center justify-center text-[10px] text-neutral-400">
                          {m.full_name.split(" ").map((n) => n[0]).join("").slice(0, 2)}
                        </div>
                      )}
                      <span className="text-neutral-900 font-medium">{m.full_name}</span>
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
                      href={`/members/${m.state.toLowerCase()}`}
                      className="hover:underline hover:text-neutral-900"
                    >
                      {m.state}
                    </Link>
                  </td>
                  <td className="py-2.5 pr-4 text-neutral-500 align-top font-[family-name:var(--font-dm-mono)] tabular-nums">
                    {formatDistrict(m.district)}
                  </td>
                  <td className="py-2.5 pr-4 align-top">
                    <span
                      className={`${
                        m.party === "D"
                          ? "text-blue-600"
                          : m.party === "R"
                            ? "text-red-600"
                            : "text-amber-600"
                      }`}
                    >
                      {m.party === "D" ? "Democrat" : m.party === "R" ? "Republican" : "Independent"}
                    </span>
                  </td>
                  <td className="py-2.5 pr-4 text-right font-[family-name:var(--font-dm-mono)] tabular-nums text-neutral-600 align-top">
                    {m.release_count > 0 ? (
                      m.release_count.toLocaleString()
                    ) : (
                      <span className="text-neutral-300">0</span>
                    )}
                  </td>
                  <td className="hidden sm:table-cell py-2.5 text-right font-[family-name:var(--font-dm-mono)] tabular-nums text-neutral-400 whitespace-nowrap align-top">
                    {m.latest_release ? formatShortDate(m.latest_release) : "---"}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <p className="text-xs text-neutral-500 mt-10 max-w-2xl leading-relaxed">
        Coverage horizon: January 1, 2025 forward. Members showing zero records are recon-discovered but their listings need manual
        triage; the daily collector picks them up automatically once promoted.
      </p>
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
      href={q ? `/members/house?${q}` : "/members/house"}
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

import Link from "next/link";
import Image from "next/image";
import { sql } from "../lib/db";
import {
  getSenators,
  getHouseMembers,
  CONTENT_TYPE_ORDER,
  CONTENT_TYPE_PLURAL,
} from "../lib/queries";
import { StateCartogram } from "../components/state-cartogram";
import { STATE_NAMES } from "../lib/states";
import { formatShortDate, formatMonthYear } from "../lib/dates";
import type { SenatorWithCount, ContentType } from "../lib/db";

export const metadata = {
  title: "Members, Capitol Releases",
  description:
    "All 100 U.S. senators and 437 U.S. House members, browsable by state, chamber, or party.",
};

export const revalidate = 600;

const PER_PAGE = 50;
type SortKey = "count" | "state" | "name";
type ChamberFilter = "all" | "senate" | "house";

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

export default async function MembersIndexPage({
  searchParams,
}: {
  searchParams: Promise<{
    sort?: string;
    state?: string;
    chamber?: string;
    page?: string;
  }>;
}) {
  const params = await searchParams;
  const sortKey: SortKey =
    params.sort === "state" ? "state" : params.sort === "name" ? "name" : "count";
  const activeState = params.state?.toUpperCase();
  const chamberFilter: ChamberFilter =
    params.chamber === "senate" || params.chamber === "house"
      ? params.chamber
      : "all";
  const page = Math.max(1, Number(params.page ?? "1"));

  const [senators, house, bioguides] = await Promise.all([
    getSenators(),
    getHouseMembers(),
    sql`SELECT id, bioguide_id, chamber FROM officials WHERE bioguide_id IS NOT NULL`,
  ]);
  const bioMap = new Map<string, { bioguide_id: string; chamber: string }>();
  for (const row of bioguides as { id: string; bioguide_id: string; chamber: string }[]) {
    bioMap.set(row.id, { bioguide_id: row.bioguide_id, chamber: row.chamber });
  }

  const senateReleases = senators.reduce((s, m) => s + m.release_count, 0);
  const houseReleases = house.reduce((s, m) => s + m.release_count, 0);

  // Combined per-state composition for the cartogram.
  const stateMap = new Map<string, { parties: ("D" | "R" | "I")[]; releaseCount: number }>();
  for (const m of [...senators, ...house]) {
    const entry = stateMap.get(m.state) ?? { parties: [], releaseCount: 0 };
    entry.parties.push(m.party);
    entry.releaseCount += m.release_count;
    stateMap.set(m.state, entry);
  }
  const stateInfo = Array.from(stateMap.entries()).map(([code, v]) => ({
    code,
    parties: v.parties,
    releaseCount: v.releaseCount,
  }));

  // Stamp chamber on each so the table can tag rows. getSenators returns
  // senators (chamber='senate'), getHouseMembers returns reps (chamber='house').
  type Row = SenatorWithCount & { chamber: "senate" | "house" };
  const senatorRows: Row[] = senators.map((s) => ({ ...s, chamber: "senate" }));
  const houseRows: Row[] = house.map((h) => ({ ...h, chamber: "house" }));
  let combined: Row[] = [...senatorRows, ...houseRows];

  if (activeState) combined = combined.filter((m) => m.state === activeState);
  if (chamberFilter !== "all")
    combined = combined.filter((m) => m.chamber === chamberFilter);

  combined.sort((a, b) => {
    if (sortKey === "state") {
      const s = a.state.localeCompare(b.state);
      if (s !== 0) return s;
      if (a.chamber !== b.chamber) return a.chamber === "senate" ? -1 : 1;
      return a.full_name.localeCompare(b.full_name);
    }
    if (sortKey === "name") return a.full_name.localeCompare(b.full_name);
    return b.release_count - a.release_count;
  });

  const totalRows = combined.length;
  const totalPages = Math.max(1, Math.ceil(totalRows / PER_PAGE));
  const safePage = Math.min(page, totalPages);
  const pageRows = combined.slice((safePage - 1) * PER_PAGE, safePage * PER_PAGE);
  const startIndex = (safePage - 1) * PER_PAGE;

  function buildHref(overrides: Partial<{ sort: string; state: string; chamber: string; page: string }>) {
    const sp = new URLSearchParams();
    const merged = {
      sort: sortKey === "count" ? undefined : sortKey,
      state: activeState,
      chamber: chamberFilter === "all" ? undefined : chamberFilter,
      page: safePage > 1 ? String(safePage) : undefined,
      ...overrides,
    };
    for (const [k, v] of Object.entries(merged)) {
      if (v) sp.set(k, v);
    }
    const qs = sp.toString();
    return qs ? `/members?${qs}` : "/members";
  }

  return (
    <div className="mx-auto max-w-5xl px-4 py-12">
      <h1 className="font-[family-name:var(--font-source-serif)] text-4xl text-neutral-900 mb-3">
        Members of Congress
      </h1>
      <p className="text-sm text-neutral-600 leading-relaxed mb-2 max-w-2xl">
        Every senator and U.S. House member, with the press releases,
        statements, and op-eds they&apos;ve published since January 2025. Pick a
        state on the map to see a delegation page.
      </p>
      <p className="text-xs text-neutral-500 leading-relaxed mb-8 max-w-2xl">
        {senators.length} senators · {house.length} House members ·{" "}
        {(senateReleases + houseReleases).toLocaleString()} releases archived.
      </p>

      <StateCartogram
        states={stateInfo}
        buildHref={(code) => (code ? `/members/${code.toLowerCase()}` : "/members")}
      />

      <div className="grid gap-4 sm:grid-cols-2 mb-12">
        <Link
          href="/members/senate"
          className="block border border-neutral-200 rounded-md p-5 hover:border-neutral-900 transition-colors group"
        >
          <p className="text-[11px] uppercase tracking-wider text-neutral-500 mb-1">
            Upper chamber
          </p>
          <h2 className="font-[family-name:var(--font-source-serif)] text-2xl text-neutral-900 group-hover:underline mb-2">
            Senate
          </h2>
          <p className="text-sm text-neutral-600 leading-snug mb-3">
            All 100 senators. Two per state, six-year terms, the most-covered
            chamber on this site.
          </p>
          <p className="text-xs text-neutral-500 font-[family-name:var(--font-dm-mono)] tabular-nums">
            {senateReleases.toLocaleString()} releases
          </p>
        </Link>

        <Link
          href="/members/house"
          className="block border border-neutral-200 rounded-md p-5 hover:border-neutral-900 transition-colors group"
        >
          <p className="text-[11px] uppercase tracking-wider text-neutral-500 mb-1">
            Lower chamber
          </p>
          <h2 className="font-[family-name:var(--font-source-serif)] text-2xl text-neutral-900 group-hover:underline mb-2">
            House
          </h2>
          <p className="text-sm text-neutral-600 leading-snug mb-3">
            All {house.length.toLocaleString()} U.S. House members, organized by
            state and district.
          </p>
          <p className="text-xs text-neutral-500 font-[family-name:var(--font-dm-mono)] tabular-nums">
            {houseReleases.toLocaleString()} releases
          </p>
        </Link>
      </div>

      <section>
        <h2 className="text-xs uppercase tracking-wider text-neutral-500 border-b border-neutral-900 pb-2 mb-4">
          All members
        </h2>

        <div className="mb-6 flex flex-wrap items-center gap-2 text-xs">
          <span className="uppercase tracking-wider text-neutral-400">Sort</span>
          <FilterPill
            href={buildHref({ sort: undefined, page: undefined })}
            active={sortKey === "count"}
            label="By volume"
          />
          <FilterPill
            href={buildHref({ sort: "state", page: undefined })}
            active={sortKey === "state"}
            label="By state"
          />
          <FilterPill
            href={buildHref({ sort: "name", page: undefined })}
            active={sortKey === "name"}
            label="A–Z"
          />
          <span className="ml-2 uppercase tracking-wider text-neutral-400">Chamber</span>
          <FilterPill
            href={buildHref({ chamber: undefined, page: undefined })}
            active={chamberFilter === "all"}
            label="All"
          />
          <FilterPill
            href={buildHref({ chamber: "senate", page: undefined })}
            active={chamberFilter === "senate"}
            label="Senate"
          />
          <FilterPill
            href={buildHref({ chamber: "house", page: undefined })}
            active={chamberFilter === "house"}
            label="House"
          />
          {activeState && (
            <span className="ml-auto text-neutral-500">
              {STATE_NAMES[activeState] ?? activeState} ({totalRows})
              <Link
                href={buildHref({ state: undefined, page: undefined })}
                className="ml-2 underline hover:text-neutral-900"
              >
                Clear
              </Link>
            </span>
          )}
        </div>

        <div className="-mx-4 overflow-x-auto px-4 sm:mx-0 sm:px-0">
          <table className="w-full min-w-[640px] text-sm">
            <thead>
              <tr className="border-b border-neutral-800 text-xs uppercase tracking-wider text-neutral-500">
                <th className="pb-2 pr-4 text-right font-medium w-12">#</th>
                <th className="pb-2 pr-4 text-left font-medium">Member</th>
                <th className="pb-2 pr-4 text-left font-medium">State</th>
                <th className="pb-2 pr-4 text-left font-medium">Role</th>
                <th className="pb-2 pr-4 text-left font-medium">Party</th>
                <th className="pb-2 pr-4 text-right font-medium">Releases</th>
                <th className="hidden sm:table-cell pb-2 text-right font-medium">Latest</th>
              </tr>
            </thead>
            <tbody>
              {pageRows.map((m, i) => {
                const idx = startIndex + i;
                const info = bioMap.get(m.id);
                const photoSrc = info
                  ? info.chamber === "house"
                    ? `/house/${info.bioguide_id}.jpg`
                    : `/senators/${info.bioguide_id}.jpg`
                  : null;
                const detailHref =
                  m.chamber === "house" ? `/house/${m.id}` : `/senators/${m.id}`;
                const breakdown = formatBreakdown(m.type_breakdown);
                const since = formatMonthYear(m.earliest_release);
                const role =
                  m.chamber === "senate"
                    ? "Sen."
                    : m.district
                      ? `Rep. (D-${m.district})`
                      : "Rep.";
                return (
                  <tr
                    key={`${m.chamber}-${m.id}`}
                    className={`border-b border-neutral-100 ${idx % 2 === 1 ? "bg-neutral-50/60" : ""}`}
                  >
                    <td className="py-2.5 pr-4 text-right font-[family-name:var(--font-dm-mono)] tabular-nums text-neutral-400 align-top">
                      {idx + 1}
                    </td>
                    <td className="py-2.5 pr-4 align-top">
                      <Link
                        href={detailHref}
                        className="flex items-center gap-3 hover:underline"
                      >
                        {photoSrc ? (
                          <Image
                            src={photoSrc}
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
                    <td className="py-2.5 pr-4 text-neutral-500 align-top whitespace-nowrap">
                      {role}
                    </td>
                    <td className="py-2.5 pr-4 align-top">
                      <span
                        className={
                          m.party === "D"
                            ? "text-blue-600"
                            : m.party === "R"
                              ? "text-red-600"
                              : "text-amber-600"
                        }
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

        {totalPages > 1 && (
          <div className="mt-6 flex items-center justify-between text-xs">
            <p className="text-neutral-500">
              Showing{" "}
              <span className="text-neutral-900 font-[family-name:var(--font-dm-mono)] tabular-nums">
                {startIndex + 1}–{Math.min(startIndex + pageRows.length, totalRows)}
              </span>{" "}
              of{" "}
              <span className="text-neutral-900 font-[family-name:var(--font-dm-mono)] tabular-nums">
                {totalRows.toLocaleString()}
              </span>
            </p>
            <div className="flex items-center gap-2">
              {safePage > 1 ? (
                <Link
                  href={buildHref({
                    page: safePage - 1 === 1 ? undefined : String(safePage - 1),
                  })}
                  className="rounded-full border border-neutral-200 px-3 py-1 text-neutral-700 hover:border-neutral-900 hover:text-neutral-900"
                >
                  ← Prev
                </Link>
              ) : (
                <span className="rounded-full border border-neutral-100 px-3 py-1 text-neutral-300">
                  ← Prev
                </span>
              )}
              <span className="text-neutral-500 font-[family-name:var(--font-dm-mono)] tabular-nums">
                {safePage} / {totalPages}
              </span>
              {safePage < totalPages ? (
                <Link
                  href={buildHref({ page: String(safePage + 1) })}
                  className="rounded-full border border-neutral-200 px-3 py-1 text-neutral-700 hover:border-neutral-900 hover:text-neutral-900"
                >
                  Next →
                </Link>
              ) : (
                <span className="rounded-full border border-neutral-100 px-3 py-1 text-neutral-300">
                  Next →
                </span>
              )}
            </div>
          </div>
        )}
      </section>
    </div>
  );
}

function FilterPill({
  href,
  active,
  label,
}: {
  href: string;
  active: boolean;
  label: string;
}) {
  return (
    <Link
      href={href}
      className={`rounded-full border px-2.5 py-1 transition-colors ${
        active
          ? "border-neutral-900 bg-neutral-900 text-white"
          : "border-neutral-200 text-neutral-500 hover:border-neutral-400 hover:text-neutral-900"
      }`}
    >
      {label}
    </Link>
  );
}

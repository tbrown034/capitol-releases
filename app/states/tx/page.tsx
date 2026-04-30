import Link from "next/link";
import Image from "next/image";
import { sql } from "../../lib/db";
import { formatShortDate } from "../../lib/dates";

export const metadata = {
  title: "Texas Senate — Capitol Releases",
};

export const revalidate = 600;

type TxRow = {
  id: string;
  full_name: string;
  party: "D" | "R" | "I";
  district: number;
  official_url: string;
  release_count: number;
  latest_release: string | null;
};

type SortKey = "district" | "count" | "name" | "party";

function partyLabel(p: "D" | "R" | "I"): string {
  return p === "D" ? "Democrat" : p === "R" ? "Republican" : "Independent";
}

function partyColor(p: "D" | "R" | "I"): string {
  return p === "D"
    ? "text-blue-600"
    : p === "R"
    ? "text-red-600"
    : "text-amber-600";
}

export default async function TexasStatePage({
  searchParams,
}: {
  searchParams: Promise<{ sort?: string }>;
}) {
  const { sort } = await searchParams;
  const sortKey: SortKey =
    sort === "count"
      ? "count"
      : sort === "name"
      ? "name"
      : sort === "party"
      ? "party"
      : "district";

  const rows = (await sql`
    SELECT
      s.id,
      s.full_name,
      s.party,
      (s.scrape_config->>'district')::int AS district,
      s.official_url,
      count(pr.id)::int AS release_count,
      max(pr.published_at) AS latest_release
    FROM senators s
    LEFT JOIN press_releases pr
      ON pr.senator_id = s.id
     AND pr.deleted_at IS NULL
     AND pr.content_type != 'photo_release'
    WHERE s.chamber = 'tx_senate'
    GROUP BY s.id
    ORDER BY (s.scrape_config->>'district')::int
  `) as TxRow[];

  // scrape_config may not carry district for legacy seeds; fall back to id parse.
  const enriched = rows.map((r) => {
    if (r.district == null) {
      const m = r.id.match(/^tx-d(\d{2})-/);
      return { ...r, district: m ? Number(m[1]) : 0 };
    }
    return r;
  });

  const sorted = [...enriched].sort((a, b) => {
    if (sortKey === "count") return b.release_count - a.release_count;
    if (sortKey === "name") return a.full_name.localeCompare(b.full_name);
    if (sortKey === "party") {
      const order = { D: 0, R: 1, I: 2 } as const;
      return order[a.party] - order[b.party] || a.district - b.district;
    }
    return a.district - b.district;
  });

  const TOTAL_SEATS = 31;
  const totalReleases = enriched.reduce((s, r) => s + r.release_count, 0);
  const publishing = enriched.filter((r) => r.release_count > 0).length;
  const dems = enriched.filter((r) => r.party === "D").length;
  const reps = enriched.filter((r) => r.party === "R").length;
  const inds = enriched.filter((r) => r.party === "I").length;
  const filledDistricts = new Set(enriched.map((r) => r.district));
  const vacantDistricts = Array.from(
    { length: TOTAL_SEATS },
    (_, n) => n + 1
  ).filter((d) => !filledDistricts.has(d));
  const latest = enriched
    .map((r) => r.latest_release)
    .filter((d): d is string => Boolean(d))
    .sort()
    .at(-1);

  const SortLink = ({ value, label }: { value: SortKey; label: string }) => {
    const params = new URLSearchParams();
    if (value !== "district") params.set("sort", value);
    const q = params.toString();
    const active = sortKey === value;
    return (
      <Link
        href={q ? `/states/tx?${q}` : "/states/tx"}
        aria-current={active ? "page" : undefined}
        className={`rounded-full border px-2.5 py-1 transition-colors ${
          active
            ? "border-neutral-900 bg-neutral-900 text-white"
            : "border-neutral-200 text-neutral-500 hover:border-neutral-400 hover:text-neutral-900"
        }`}
      >
        {label}
      </Link>
    );
  };

  return (
    <div className="mx-auto max-w-5xl px-4 py-12">
      <Link
        href="/states"
        className="text-xs text-neutral-500 hover:text-neutral-900 mb-6 inline-block"
      >
        ← All states
      </Link>

      <h1 className="font-[family-name:var(--font-source-serif)] text-4xl text-neutral-900 mb-3">
        Texas Senate
      </h1>
      <p className="text-sm text-neutral-600 leading-relaxed mb-2 max-w-2xl">
        {TOTAL_SEATS} seats. {enriched.length} currently filled
        {vacantDistricts.length > 0 && (
          <>
            {" "}— District{vacantDistricts.length === 1 ? " " : "s "}
            {vacantDistricts.join(", ")}{" "}
            {vacantDistricts.length === 1 ? "is" : "are"} vacant
          </>
        )}
        . Republican majority. Lieutenant Governor Dan Patrick presides. The
        chamber convenes in odd-numbered years for the regular biennial
        session, plus called special sessions.
      </p>
      <p className="text-xs text-neutral-500 leading-relaxed mb-8 max-w-2xl">
        Press releases scraped daily from each member&apos;s pressroom on{" "}
        <span translate="no">senate.texas.gov</span>. Backfilled to January 1,
        2025. District 9 was sworn in February 2026 and has not begun
        publishing. Photos are official portraits from{" "}
        <span translate="no">senate.texas.gov</span>.
      </p>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-10 max-w-2xl">
        <Stat label="Members tracked" value={enriched.length.toLocaleString()} />
        <Stat label="Releases" value={totalReleases.toLocaleString()} />
        <Stat label="Publishing" value={`${publishing} / ${enriched.length}`} />
        <Stat
          label="Latest release"
          value={latest ? formatShortDate(latest) : "—"}
        />
      </div>

      <div className="mb-6 flex flex-wrap items-center gap-2 text-xs">
        <span className="uppercase tracking-wider text-neutral-400">Sort</span>
        <SortLink value="district" label="By district" />
        <SortLink value="count" label="By volume" />
        <SortLink value="party" label="By party" />
        <SortLink value="name" label="A–Z" />
        <span className="ml-auto text-neutral-500 tabular-nums">
          {dems} D · {reps} R
          {inds > 0 && <> · {inds} I</>}
          {vacantDistricts.length > 0 && (
            <> · {vacantDistricts.length} vacant</>
          )}
        </span>
      </div>

      <div className="border-b border-neutral-200 mb-6" />

      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-neutral-800 text-xs uppercase tracking-wider text-neutral-500">
            <th scope="col" className="pb-2 pr-4 text-right font-medium w-12">
              District
            </th>
            <th scope="col" className="pb-2 pr-4 text-left font-medium">
              Senator
            </th>
            <th scope="col" className="pb-2 pr-4 text-left font-medium">
              Party
            </th>
            <th scope="col" className="pb-2 pr-4 text-right font-medium">
              Releases
            </th>
            <th
              scope="col"
              className="hidden sm:table-cell pb-2 text-right font-medium"
            >
              Latest
            </th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((r, i) => {
            const district = String(r.district).padStart(2, "0");
            return (
              <tr
                key={r.id}
                className={`border-b border-neutral-100 transition-colors hover:bg-neutral-100/70 ${
                  i % 2 === 1 ? "bg-neutral-50/60" : ""
                }`}
              >
                <td className="py-2.5 pr-4 text-right font-[family-name:var(--font-dm-mono)] tabular-nums text-neutral-500 align-top">
                  {r.district}
                </td>
                <td className="py-2.5 pr-4 align-top">
                  <Link
                    href={`/states/tx/${r.id}`}
                    className="flex items-center gap-3 hover:underline"
                  >
                    <Image
                      src={`/state-senators/tx/d${district}.jpg`}
                      alt={r.full_name}
                      width={32}
                      height={32}
                      className="h-8 w-8 object-cover object-top"
                      unoptimized
                    />
                    <span className="text-neutral-900 font-medium">
                      {r.full_name}
                    </span>
                  </Link>
                </td>
                <td className={`py-2.5 pr-4 align-top ${partyColor(r.party)}`}>
                  {partyLabel(r.party)}
                </td>
                <td className="py-2.5 pr-4 text-right font-[family-name:var(--font-dm-mono)] tabular-nums text-neutral-600 align-top">
                  {r.release_count > 0 ? (
                    r.release_count.toLocaleString()
                  ) : (
                    <span className="text-neutral-300">—</span>
                  )}
                </td>
                <td className="hidden sm:table-cell py-2.5 text-right font-[family-name:var(--font-dm-mono)] tabular-nums text-neutral-400 whitespace-nowrap align-top">
                  {r.latest_release ? formatShortDate(r.latest_release) : "—"}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs uppercase tracking-wider text-neutral-400 mb-1">
        {label}
      </p>
      <p className="text-2xl font-[family-name:var(--font-dm-mono)] tabular-nums text-neutral-900">
        {value}
      </p>
    </div>
  );
}

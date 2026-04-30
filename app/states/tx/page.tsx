import Link from "next/link";
import Image from "next/image";
import { sql } from "../../lib/db";
import { formatShortDate, formatLongMonthYear } from "../../lib/dates";
import { TxDistrictBars } from "../../components/tx-district-bars";
import { TxMonthlyVolume } from "../../components/tx-monthly-volume";

export const metadata = {
  title: "Texas Senate — Capitol Releases",
  description:
    "Press releases from the 31-member Texas State Senate, scraped daily from senate.texas.gov. Coverage, publishing patterns, and the silent caucus of senators who don't post online.",
};

export const revalidate = 600;

type TxRow = {
  id: string;
  full_name: string;
  party: "D" | "R" | "I";
  district: number;
  official_url: string;
  press_release_url: string | null;
  release_count: number;
  latest_release: string | null;
  earliest_release: string | null;
};

type SortKey = "district" | "count" | "name" | "party";

const TOTAL_SEATS = 31;

function partyLabel(p: "D" | "R" | "I"): string {
  return p === "D" ? "Democrat" : p === "R" ? "Republican" : "Independent";
}
function partyClass(p: "D" | "R" | "I"): string {
  return p === "D" ? "text-blue-600" : p === "R" ? "text-red-600" : "text-amber-600";
}

function familyName(full: string): string {
  return full.replace(/"[^"]+"/g, "").trim().split(/\s+/).at(-1) ?? full;
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

  const [rows, monthly, topics] = await Promise.all([
    sql`
      SELECT
        s.id, s.full_name, s.party,
        (s.scrape_config->>'district')::int AS district,
        s.official_url, s.press_release_url,
        count(pr.id)::int AS release_count,
        max(pr.published_at) AS latest_release,
        min(pr.published_at) AS earliest_release
      FROM senators s
      LEFT JOIN press_releases pr
        ON pr.senator_id = s.id
       AND pr.deleted_at IS NULL
       AND pr.content_type != 'photo_release'
      WHERE s.chamber = 'tx_senate'
      GROUP BY s.id
      ORDER BY (s.scrape_config->>'district')::int
    `,
    sql`
      SELECT to_char(date_trunc('month', published_at), 'YYYY-MM-DD') AS month,
             count(*)::int AS count
      FROM press_releases pr
      JOIN senators s ON s.id = pr.senator_id
      WHERE s.chamber = 'tx_senate'
        AND pr.deleted_at IS NULL
        AND pr.content_type != 'photo_release'
        AND pr.published_at >= '2025-01-01'
      GROUP BY month
      ORDER BY month
    `,
    sql`
      WITH stems AS (
        SELECT DISTINCT pr.id,
          regexp_replace(
            lower(unnest(string_to_array(
              regexp_replace(pr.title, '[^a-zA-Z ]', '', 'g'), ' '
            ))),
            's$', ''
          ) AS word
        FROM press_releases pr
        JOIN senators s ON s.id = pr.senator_id
        WHERE s.chamber = 'tx_senate'
          AND pr.deleted_at IS NULL
          AND pr.content_type != 'photo_release'
      ),
      surnames AS (
        SELECT DISTINCT regexp_replace(lower(split_part(full_name, ' ', -1)), 's$', '') AS s
        FROM senators WHERE chamber = 'tx_senate'
      )
      SELECT word, count(*)::int AS count
      FROM stems
      WHERE length(word) > 4
        AND word NOT IN (SELECT s FROM surnames)
        AND word NOT IN (
          'texas','senator','senate','press','release','statement','today',
          'about','their','after','would','should','which','where','these',
          'those','being','through','before','during','against','within',
          'among','sponsored','introduce','announce','support','passe',
          'announces','passes','passed','introduces','introduced','signed',
          'urging','urges','calls','statements','release','releases','letter',
          'committee','district','member','members','official','president',
          'governor'
        )
      GROUP BY word
      HAVING count(*) >= 4
      ORDER BY count DESC
      LIMIT 12
    `,
  ]);

  const rawRows = rows as TxRow[];
  const enriched: TxRow[] = rawRows.map((r) => {
    if (r.district == null) {
      const m = r.id.match(/^tx-d(\d{2})-/);
      return { ...r, district: m ? Number(m[1]) : 0 };
    }
    return r;
  });

  const sortedTable = [...enriched].sort((a, b) => {
    if (sortKey === "count") return b.release_count - a.release_count;
    if (sortKey === "name") return a.full_name.localeCompare(b.full_name);
    if (sortKey === "party") {
      const order = { D: 0, R: 1, I: 2 } as const;
      return order[a.party] - order[b.party] || a.district - b.district;
    }
    return a.district - b.district;
  });

  const totalReleases = enriched.reduce((s, r) => s + r.release_count, 0);
  const publishing = enriched.filter((r) => r.release_count > 0).length;
  const silent = enriched.filter((r) => r.release_count === 0);
  const filledDistricts = new Set(enriched.map((r) => r.district));
  const vacantDistricts = Array.from(
    { length: TOTAL_SEATS },
    (_, n) => n + 1
  ).filter((d) => !filledDistricts.has(d));
  const dems = enriched.filter((r) => r.party === "D").length;
  const reps = enriched.filter((r) => r.party === "R").length;

  const topPublishers = [...enriched]
    .filter((r) => r.release_count > 0)
    .sort((a, b) => b.release_count - a.release_count)
    .slice(0, 5);

  const earliest = enriched
    .map((r) => r.earliest_release)
    .filter((d): d is string => Boolean(d))
    .sort()
    .at(0);
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

      <p className="text-[11px] uppercase tracking-wider text-neutral-500 mb-2">
        State expansion · proof of concept
      </p>
      <h1 className="font-[family-name:var(--font-source-serif)] text-4xl text-neutral-900 mb-3">
        Texas Senate
      </h1>
      <p className="text-base text-neutral-700 leading-snug max-w-2xl mb-3">
        {publishing} of {enriched.length} Texas state senators publish press
        releases on senate.texas.gov. The other {silent.length} maintain
        pressrooms but rarely or never post.
      </p>
      <p className="text-sm text-neutral-600 leading-relaxed max-w-2xl mb-6">
        State legislatures publish on a fundamentally different cadence than
        Congress &mdash; output spikes during session and falls off in the
        interim. This page tracks every Texas senator&apos;s pressroom daily
        since January 2025, including the silent ones.
      </p>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-8 max-w-3xl">
        <Stat
          label="Records archived"
          value={totalReleases.toLocaleString()}
          sub={earliest ? `since ${formatLongMonthYear(earliest)}` : undefined}
        />
        <Stat
          label="Publishing"
          value={`${publishing} / ${enriched.length}`}
          sub={`${silent.length} silent`}
        />
        <Stat
          label="Composition"
          value={`${reps}R · ${dems}D`}
          sub={
            vacantDistricts.length > 0
              ? `D${vacantDistricts.join(", ")} vacant`
              : "no vacancies"
          }
        />
        <Stat
          label="Most recent"
          value={latest ? formatShortDate(latest) : "—"}
          sub="across all 30"
        />
      </div>

      {/* Per-district publishing volume — the headline chart. */}
      <section className="mb-12">
        <h2 className="text-xs uppercase tracking-wider text-neutral-500 border-b border-neutral-900 pb-2 mb-3">
          Press releases per senator
        </h2>
        <p className="text-xs text-neutral-500 leading-relaxed mb-4 max-w-2xl">
          Sorted by volume since Jan 2025. The 12 senators with no records
          aren&apos;t a collection failure &mdash; their pressrooms are live
          and we re-check daily. Click any senator to see their archive
          (or empty pressroom).
        </p>
        <TxDistrictBars
          rows={enriched.map((r) => ({
            id: r.id,
            full_name: r.full_name,
            party: r.party,
            district: r.district,
            release_count: r.release_count,
          }))}
        />
      </section>

      {/* Monthly volume — the session pulse. */}
      <section className="mb-12">
        <h2 className="text-xs uppercase tracking-wider text-neutral-500 border-b border-neutral-900 pb-2 mb-3">
          Volume by month
        </h2>
        <p className="text-xs text-neutral-500 leading-relaxed mb-4 max-w-2xl">
          The 89th Texas Legislature&apos;s regular session ran January 14 to
          June 2, 2025. That&apos;s when most senators publish &mdash; and
          when the silent caucus stays silent.
        </p>
        <TxMonthlyVolume data={monthly as { month: string; count: number }[]} />
      </section>

      {/* Top publishers strip — quick visual recognition. */}
      <section className="mb-12">
        <h2 className="text-xs uppercase tracking-wider text-neutral-500 border-b border-neutral-900 pb-2 mb-3">
          Top publishers
        </h2>
        <p className="text-xs text-neutral-500 leading-relaxed mb-4 max-w-2xl">
          Five senators account for{" "}
          {Math.round(
            (topPublishers.reduce((s, r) => s + r.release_count, 0) / Math.max(1, totalReleases)) * 100
          )}
          % of all Texas Senate press releases since January 2025.
        </p>
        <ol className="grid grid-cols-1 sm:grid-cols-2 gap-x-6">
          {topPublishers.map((r, i) => {
            const district = String(r.district).padStart(2, "0");
            const ringColor =
              r.party === "D"
                ? "ring-blue-500"
                : r.party === "R"
                  ? "ring-red-500"
                  : "ring-amber-500";
            return (
              <li
                key={r.id}
                className="flex items-center gap-3 py-2 border-b border-neutral-100 last:border-b-0"
              >
                <span className="w-5 text-right text-[11px] tabular-nums text-neutral-400 font-mono">
                  {i + 1}
                </span>
                <Image
                  src={`/state-senators/tx/d${district}.jpg`}
                  alt={r.full_name}
                  width={32}
                  height={32}
                  className={`h-8 w-8 object-cover object-top rounded-full ring-1 ${ringColor}`}
                  unoptimized
                />
                <div className="flex-1 min-w-0">
                  <Link
                    href={`/states/tx/${r.id}`}
                    className="text-sm text-neutral-900 hover:underline font-medium"
                  >
                    {familyName(r.full_name)}
                  </Link>{" "}
                  <span className={`text-xs ${partyClass(r.party)}`}>({r.party}-D{r.district})</span>
                </div>
                <span className="font-mono tabular-nums text-sm font-semibold text-neutral-900">
                  {r.release_count.toLocaleString()}
                </span>
              </li>
            );
          })}
        </ol>
      </section>

      {/* The silent caucus — explicit, not buried in the table. */}
      {silent.length > 0 && (
        <section className="mb-12">
          <h2 className="text-xs uppercase tracking-wider text-neutral-500 border-b border-neutral-900 pb-2 mb-3">
            The silent caucus
          </h2>
          <p className="text-xs text-neutral-500 leading-relaxed mb-4 max-w-2xl">
            These {silent.length} senators have published nothing on{" "}
            <span translate="no">senate.texas.gov</span> since January 2025.
            Each link below opens their actual pressroom &mdash; we&apos;re not
            missing the page; the page is empty.
          </p>
          <ul className="grid grid-cols-1 sm:grid-cols-2 gap-x-6">
            {silent
              .sort((a, b) => a.district - b.district)
              .map((r) => (
                <li
                  key={r.id}
                  className="flex items-center gap-3 py-1.5 border-b border-neutral-100 text-sm"
                >
                  <span className="font-mono tabular-nums text-[11px] text-neutral-400 w-8">
                    D{String(r.district).padStart(2, "0")}
                  </span>
                  <Link
                    href={`/states/tx/${r.id}`}
                    className="text-neutral-700 hover:underline flex-1 truncate"
                  >
                    {r.full_name}
                  </Link>
                  <span className={`text-xs ${partyClass(r.party)}`}>{r.party}</span>
                  {r.press_release_url && (
                    <a
                      href={r.press_release_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-[11px] text-neutral-400 hover:text-neutral-700 transition-colors"
                      title={`Open ${r.full_name}'s pressroom on senate.texas.gov`}
                    >
                      pressroom <span aria-hidden>↗</span>
                    </a>
                  )}
                </li>
              ))}
          </ul>
        </section>
      )}

      {/* Topics — what they actually talk about, when they do. */}
      {Array.isArray(topics) && (topics as { word: string; count: number }[]).length > 0 && (
        <section className="mb-12">
          <h2 className="text-xs uppercase tracking-wider text-neutral-500 border-b border-neutral-900 pb-2 mb-3">
            What they talk about
          </h2>
          <p className="text-xs text-neutral-500 leading-relaxed mb-4 max-w-2xl">
            Most-mentioned terms across {totalReleases.toLocaleString()} Texas
            Senate press releases since January 2025. Different vocabulary
            than Washington &mdash; this is school finance, water rights,
            property tax, legislative procedure.
          </p>
          <div className="flex flex-wrap gap-2">
            {(topics as { word: string; count: number }[]).map((t) => (
              <Link
                key={t.word}
                href={`/search?q=${encodeURIComponent(t.word)}`}
                className="inline-flex items-center gap-1.5 rounded-full border border-neutral-200 bg-white px-3 py-1.5 text-sm text-neutral-700 hover:border-neutral-400 hover:text-neutral-900 transition-colors"
              >
                {t.word}
                <span className="text-xs text-neutral-400 font-mono tabular-nums">
                  {t.count}
                </span>
              </Link>
            ))}
          </div>
        </section>
      )}

      {/* Full directory table */}
      <section>
        <div className="flex items-center justify-between border-b border-neutral-900 pb-2 mb-3 md:mb-4">
          <h2 className="text-xs uppercase tracking-wider text-neutral-500">
            Full directory
          </h2>
          <span className="text-[11px] text-neutral-400 tabular-nums">
            {enriched.length} members
          </span>
        </div>
        <div className="mb-4 flex flex-wrap items-center gap-2 text-xs">
          <span className="uppercase tracking-wider text-neutral-400">Sort</span>
          <SortLink value="district" label="By district" />
          <SortLink value="count" label="By volume" />
          <SortLink value="party" label="By party" />
          <SortLink value="name" label="A–Z" />
        </div>
        <div className="-mx-4 overflow-x-auto px-4 sm:mx-0 sm:px-0">
          <table className="w-full min-w-[640px] text-sm">
            <thead>
              <tr className="border-b border-neutral-800 text-xs uppercase tracking-wider text-neutral-500">
                <th scope="col" className="pb-2 pr-4 text-right font-medium w-12">
                  Dist.
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
              {sortedTable.map((r, i) => {
                const district = String(r.district).padStart(2, "0");
                const isZero = r.release_count === 0;
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
                        <span
                          className={
                            isZero
                              ? "text-neutral-500 font-medium"
                              : "text-neutral-900 font-medium"
                          }
                        >
                          {r.full_name}
                        </span>
                      </Link>
                    </td>
                    <td className={`py-2.5 pr-4 align-top ${partyClass(r.party)}`}>
                      {partyLabel(r.party)}
                    </td>
                    <td className="py-2.5 pr-4 text-right font-[family-name:var(--font-dm-mono)] tabular-nums text-neutral-600 align-top">
                      {isZero ? (
                        <span className="text-neutral-300">—</span>
                      ) : (
                        r.release_count.toLocaleString()
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
      </section>

      {/* Methodology footer */}
      <section className="mt-16 pt-6 border-t border-neutral-200">
        <p className="text-xs text-neutral-500 leading-relaxed max-w-2xl">
          Source: each member&apos;s pressroom on{" "}
          <a
            href="https://senate.texas.gov/"
            target="_blank"
            rel="noopener noreferrer"
            translate="no"
            className="underline hover:text-neutral-900"
          >
            senate.texas.gov
          </a>
          . Backfilled to January 1, 2025 and re-checked daily. District 4 is
          vacant pending the May 2026 special election. District 9 (Rehmet)
          was sworn in February 2026 and has not begun publishing. Photos are
          official portraits from senate.texas.gov.
        </p>
      </section>
    </div>
  );
}

function Stat({
  label,
  value,
  sub,
}: {
  label: string;
  value: string;
  sub?: string;
}) {
  return (
    <div>
      <p className="text-xs uppercase tracking-wider text-neutral-400 mb-1">
        {label}
      </p>
      <p className="text-2xl font-[family-name:var(--font-dm-mono)] tabular-nums text-neutral-900">
        {value}
      </p>
      {sub && (
        <p className="text-[11px] text-neutral-500 mt-0.5 leading-tight">
          {sub}
        </p>
      )}
    </div>
  );
}

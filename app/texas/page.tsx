import Link from "next/link";
import Image from "next/image";
import { Suspense } from "react";
import {
  getTxRoster,
  getTxStats,
  getTxLatestReleases,
  getTxMonthlyVolume,
  getTxTopicTrends,
  TX_TOTAL_SEATS,
} from "../lib/texas";
import { formatShortDate, formatLongMonthYear } from "../lib/dates";
import { TxDistrictBars } from "../components/tx-district-bars";
import { TxMonthlyVolume } from "../components/tx-monthly-volume";
import { HeroLetter } from "../components/hero-letter";
import { ReleaseCard } from "../components/release-card";
import type { FeedItem, ContentType } from "../lib/db";

export const metadata = {
  title: "Texas Senate — Capitol Releases",
  description:
    "Press releases from the 31-member Texas State Senate, scraped daily from senate.texas.gov. Coverage, publishing patterns, and the silent caucus of senators who don't post online.",
};

export const revalidate = 600;

type SortKey = "district" | "count" | "name" | "party";

function partyLabel(p: "D" | "R" | "I"): string {
  return p === "D" ? "Democrat" : p === "R" ? "Republican" : "Independent";
}
function partyClass(p: "D" | "R" | "I"): string {
  return p === "D" ? "text-blue-600" : p === "R" ? "text-red-600" : "text-amber-600";
}
function familyName(full: string): string {
  return full.replace(/"[^"]+"/g, "").trim().split(/\s+/).at(-1) ?? full;
}

export default async function TexasHubPage({
  searchParams,
}: {
  searchParams: Promise<{ sort?: string }>;
}) {
  const { sort } = await searchParams;
  const sortKey: SortKey =
    sort === "count" ? "count" :
    sort === "name" ? "name" :
    sort === "party" ? "party" :
    "district";

  const [roster, stats, latestPool, monthly, topics] = await Promise.all([
    getTxRoster(),
    getTxStats(),
    // Larger pool so diversifyFeed has range; TX volume is concentrated
    // (Blanco alone has 79 records since Jan 2025) so without diversification
    // the Latest section becomes "Blanco × 6 in a row".
    getTxLatestReleases(40),
    getTxMonthlyVolume(),
    getTxTopicTrends(10),
  ]);

  // Reorder so no senator appears more than maxRun times in a row in the
  // Latest section, preserving recency.
  function diversify<T extends { senator_id: string }>(items: T[], maxRun: number): T[] {
    const out: T[] = [];
    const queue = [...items];
    while (queue.length) {
      const lastId = out[out.length - 1]?.senator_id;
      let run = 0;
      for (let i = out.length - 1; i >= 0 && out[i].senator_id === lastId; i--) run++;
      let pickIdx = 0;
      if (lastId && run >= maxRun) {
        const alt = queue.findIndex((it) => it.senator_id !== lastId);
        pickIdx = alt === -1 ? 0 : alt;
      }
      out.push(queue.splice(pickIdx, 1)[0]);
    }
    return out;
  }

  const totalReleases = stats.total_releases;
  const publishing = stats.senators_with_releases;
  const filledDistricts = new Set(roster.map((r) => r.district));
  const vacantDistricts = Array.from(
    { length: TX_TOTAL_SEATS },
    (_, n) => n + 1
  ).filter((d) => !filledDistricts.has(d));
  const dems = roster.filter((r) => r.party === "D").length;
  const reps = roster.filter((r) => r.party === "R").length;
  const silent = roster.filter((r) => r.release_count === 0);

  const topPublishers = [...roster]
    .filter((r) => r.release_count > 0)
    .sort((a, b) => b.release_count - a.release_count)
    .slice(0, 5);

  const earliest = roster
    .map((r) => r.earliest_release)
    .filter((d): d is string => Boolean(d))
    .sort()
    .at(0);

  // HeroLetter items — pre-map to TX-specific photo paths.
  const heroItems = latestPool.slice(0, 6).map((it) => {
    const senator = roster.find((r) => r.id === it.senator_id);
    const district = senator ? String(senator.district).padStart(2, "0") : "00";
    return {
      id: it.id,
      title: it.title,
      senator_id: it.senator_id,
      senator_name: it.senator_name,
      party: it.party as "D" | "R" | "I",
      state: it.state,
      published_at: it.published_at,
      scraped_at: it.scraped_at,
      content_type: (it.content_type ?? "press_release") as ContentType,
      source_url: it.source_url,
      photo_url: `/state-senators/tx/d${district}.jpg`,
      title_prefix: "State Sen.",
      source_label: "senate.texas.gov",
    };
  });

  // Diversify with maxRun=2 so Blanco-flooded weeks don't fill the section.
  const latestForFeed = diversify(latestPool, 2).slice(0, 6) as FeedItem[];

  const sortedTable = [...roster].sort((a, b) => {
    if (sortKey === "count") return b.release_count - a.release_count;
    if (sortKey === "name") return a.full_name.localeCompare(b.full_name);
    if (sortKey === "party") {
      const order = { D: 0, R: 1, I: 2 } as const;
      return order[a.party] - order[b.party] || a.district - b.district;
    }
    return a.district - b.district;
  });

  const SortLink = ({ value, label }: { value: SortKey; label: string }) => {
    const params = new URLSearchParams();
    if (value !== "district") params.set("sort", value);
    const q = params.toString();
    const active = sortKey === value;
    return (
      <Link
        href={q ? `/texas?${q}` : "/texas"}
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
    <div className="mx-auto max-w-5xl px-4">
      {/* Hero */}
      <section className="pt-6 pb-4 md:pt-8 md:pb-5">
        <div className="grid grid-cols-1 md:grid-cols-12 gap-6 md:gap-10 items-center">
          <div className="md:col-span-7">
            <p className="text-[11px] uppercase tracking-wider text-neutral-500 mb-2">
              State expansion · Texas Senate
            </p>
            <h1 className="font-serif text-4xl sm:text-5xl md:text-[3.25rem] leading-[1.05] text-neutral-900 mb-3 md:mb-4">
              31 Senators.
              <br />
              The Same Method.
            </h1>
            <p className="text-base md:text-lg text-neutral-700 max-w-2xl leading-snug mb-3">
              Every press release from every Texas state senator&rsquo;s
              pressroom on senate.texas.gov, scraped daily, since January 2025.
            </p>
            <p className="text-sm md:text-base text-neutral-500 max-w-2xl leading-relaxed">
              Same archive, same provenance discipline as the U.S. Senate
              corpus &mdash; but a fundamentally different publishing pattern.
              Coverage starts thin: only {publishing} of {roster.length} TX
              senators publish online.
            </p>
          </div>
          {heroItems.length > 0 && (
            <div className="md:col-span-5 flex justify-center md:justify-end">
              <Suspense>
                <HeroLetter items={heroItems} asOf={null} />
              </Suspense>
            </div>
          )}
        </div>
      </section>

      {/* Stats */}
      <div className="border-b border-neutral-200 pb-3 mb-5 md:mb-6">
        <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:gap-x-8 sm:gap-y-2 text-sm text-neutral-500">
          <div>
            <span className="text-2xl font-semibold text-neutral-900 font-mono tabular-nums mr-1.5">
              {totalReleases.toLocaleString()}
            </span>
            press releases
          </div>
          <div>
            <span className="text-2xl font-semibold text-neutral-900 font-mono tabular-nums mr-1.5">
              {publishing}
            </span>
            of {roster.length} publishing
          </div>
          <div>
            <span className="text-2xl font-semibold text-neutral-900 font-mono tabular-nums mr-1.5">
              {silent.length}
            </span>
            silent
          </div>
          <div>
            <span className="text-2xl font-semibold text-neutral-900 font-mono tabular-nums mr-1.5">
              Jan 1, 2025
            </span>
            to present
          </div>
        </div>
        <p className="mt-3 text-xs text-neutral-500">
          {reps}R · {dems}D
          {vacantDistricts.length > 0 && (
            <> · D{vacantDistricts.join(", ")} vacant</>
          )}
          {earliest && (
            <>
              {" · "}archive begins{" "}
              {formatLongMonthYear(earliest)}
            </>
          )}
          {" · "}
          <Link href="/texas/feed" className="underline hover:text-neutral-900">
            full feed
          </Link>
          {" · "}
          <Link href="/texas/search" className="underline hover:text-neutral-900">
            search
          </Link>
        </p>
      </div>

      {/* Per-district publishing volume — the headline chart. */}
      <section className="mb-10 md:mb-14">
        <h2 className="text-xs uppercase tracking-wider text-neutral-500 border-b border-neutral-900 pb-2 mb-3">
          Press releases per senator
        </h2>
        <p className="text-xs text-neutral-500 leading-relaxed mb-4 max-w-2xl">
          Sorted by volume since Jan 2025. The {silent.length} senators with
          no records aren&apos;t a collection failure &mdash; their pressrooms
          are live and we re-check daily. Click any senator to see their
          archive (or empty pressroom).
        </p>
        <TxDistrictBars
          rows={roster.map((r) => ({
            id: r.id,
            full_name: r.full_name,
            party: r.party,
            district: r.district,
            release_count: r.release_count,
          }))}
        />
      </section>

      {/* Monthly volume — the session pulse. */}
      <section className="mb-10 md:mb-14">
        <h2 className="text-xs uppercase tracking-wider text-neutral-500 border-b border-neutral-900 pb-2 mb-3">
          Volume by month
        </h2>
        <p className="text-xs text-neutral-500 leading-relaxed mb-4 max-w-2xl">
          The 89th Texas Legislature&apos;s regular session ran January 14 to
          June 2, 2025. That&apos;s when most senators publish &mdash; and
          when the silent caucus stays silent.
        </p>
        <TxMonthlyVolume data={monthly} />
      </section>

      {/* Topics */}
      {topics.length > 0 && (
        <section className="mb-10 md:mb-14">
          <div className="flex items-center justify-between border-b border-neutral-900 pb-2 mb-3">
            <h2 className="text-xs uppercase tracking-wider text-neutral-500">
              What they talk about
            </h2>
            <Link
              href="/texas/trending"
              className="text-xs text-neutral-500 hover:text-neutral-900 transition-colors"
            >
              Explore all →
            </Link>
          </div>
          <p className="text-xs text-neutral-500 leading-relaxed mb-4 max-w-2xl">
            Most-mentioned terms across {totalReleases.toLocaleString()} Texas
            Senate press releases since January 2025. Different vocabulary
            than Washington &mdash; school finance, water rights, property
            tax, legislative procedure.
          </p>
          <div className="flex flex-wrap gap-2">
            {topics.map((t) => (
              <Link
                key={t.word}
                href={`/texas/search?q=${encodeURIComponent(t.word)}`}
                className="inline-flex items-center gap-1.5 rounded-full border border-neutral-200 bg-white px-3 py-1.5 text-sm text-neutral-700 hover:border-neutral-400 hover:text-neutral-900 transition-colors"
              >
                {t.word}
                <span className="text-xs text-neutral-500 font-mono tabular-nums">
                  {t.count}
                </span>
              </Link>
            ))}
          </div>
        </section>
      )}

      {/* Latest + Top publishers */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8 md:gap-12 mb-10 md:mb-14">
        <section className="lg:col-span-2">
          <div className="flex items-center justify-between border-b border-neutral-900 pb-2 mb-4">
            <h2 className="text-xs uppercase tracking-wider text-neutral-500">
              Latest from the Texas Senate
            </h2>
            <Link
              href="/texas/feed"
              className="text-xs text-neutral-500 hover:text-neutral-900 transition-colors"
            >
              View all
            </Link>
          </div>
          {latestForFeed.length === 0 ? (
            <p className="text-sm text-neutral-500">No records in the archive yet.</p>
          ) : (
            latestForFeed.map((item) => <ReleaseCard key={item.id} item={item} />)
          )}
        </section>

        <section>
          <div className="flex items-center justify-between border-b border-neutral-900 pb-2 mb-4">
            <h2 className="text-xs uppercase tracking-wider text-neutral-500">
              Top publishers
            </h2>
          </div>
          {topPublishers.length === 0 ? (
            <p className="text-sm text-neutral-500">No senators publishing yet.</p>
          ) : (
            <ol className="space-y-1">
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
                    className="flex items-center gap-3 py-1.5 border-b border-neutral-100 last:border-b-0"
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
                        href={`/texas/${r.id}`}
                        className="text-sm text-neutral-900 hover:underline font-medium"
                      >
                        {familyName(r.full_name)}
                      </Link>{" "}
                      <span className={`text-xs ${partyClass(r.party)}`}>
                        ({r.party}-D{r.district})
                      </span>
                    </div>
                    <span className="font-mono tabular-nums text-sm font-semibold text-neutral-900">
                      {r.release_count.toLocaleString()}
                    </span>
                  </li>
                );
              })}
            </ol>
          )}
          <p className="mt-4 text-xs text-neutral-500 leading-relaxed">
            5 senators account for{" "}
            {Math.round(
              (topPublishers.reduce((s, r) => s + r.release_count, 0) /
                Math.max(1, totalReleases)) *
                100
            )}
            % of all Texas Senate press releases since January 2025.
          </p>
        </section>
      </div>

      {/* The silent caucus */}
      {silent.length > 0 && (
        <section className="mb-10 md:mb-14">
          <h2 className="text-xs uppercase tracking-wider text-neutral-500 border-b border-neutral-900 pb-2 mb-3">
            The silent caucus
          </h2>
          <p className="text-xs text-neutral-500 leading-relaxed mb-4 max-w-2xl">
            These {silent.length} senators have published nothing on{" "}
            <span translate="no">senate.texas.gov</span>{" "}since January 2025.
            Each link below opens their actual pressroom &mdash; we&apos;re
            not missing the page; the page is empty.
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
                    href={`/texas/${r.id}`}
                    className="text-neutral-700 hover:underline flex-1 truncate"
                  >
                    {r.full_name}
                  </Link>
                  <span className={`text-xs ${partyClass(r.party)}`}>
                    {r.party}
                  </span>
                  {r.press_release_url && (
                    <a
                      href={r.press_release_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-[11px] text-neutral-500 hover:text-neutral-700 transition-colors"
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

      {/* Full directory */}
      <section className="mb-10">
        <div className="flex items-center justify-between border-b border-neutral-900 pb-2 mb-3 md:mb-4">
          <h2 className="text-xs uppercase tracking-wider text-neutral-500">
            Full directory
          </h2>
          <span className="text-[11px] text-neutral-500 tabular-nums">
            {roster.length} members
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
                <th scope="col" className="pb-2 pr-4 text-right font-medium w-12">Dist.</th>
                <th scope="col" className="pb-2 pr-4 text-left font-medium">Senator</th>
                <th scope="col" className="pb-2 pr-4 text-left font-medium">Party</th>
                <th scope="col" className="pb-2 pr-4 text-right font-medium">Releases</th>
                <th scope="col" className="hidden sm:table-cell pb-2 text-right font-medium">Latest</th>
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
                      <Link href={`/texas/${r.id}`} className="flex items-center gap-3 hover:underline">
                        <Image
                          src={`/state-senators/tx/d${district}.jpg`}
                          alt={r.full_name}
                          width={32}
                          height={32}
                          className="h-8 w-8 object-cover object-top"
                          unoptimized
                        />
                        <span className={isZero ? "text-neutral-500 font-medium" : "text-neutral-900 font-medium"}>
                          {r.full_name}
                        </span>
                      </Link>
                    </td>
                    <td className={`py-2.5 pr-4 align-top ${partyClass(r.party)}`}>
                      {partyLabel(r.party)}
                    </td>
                    <td className="py-2.5 pr-4 text-right font-[family-name:var(--font-dm-mono)] tabular-nums text-neutral-600 align-top">
                      {isZero ? <span className="text-neutral-300">—</span> : r.release_count.toLocaleString()}
                    </td>
                    <td className="hidden sm:table-cell py-2.5 text-right font-[family-name:var(--font-dm-mono)] tabular-nums text-neutral-500 whitespace-nowrap align-top">
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
      <section className="mt-12 mb-12 pt-6 border-t border-neutral-200">
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
          official portraits from senate.texas.gov. Body text is extracted
          from the linked PDF or HTML detail page on every record; videos
          link out. The DB count for every senator was verified against the
          live pressroom on April 29, 2026 (30/30 match).{" "}
          <Link href="/texas/methodology" className="underline hover:text-neutral-900">
            Full scraper methodology
          </Link>
          {" · "}
          <Link href="/about" className="underline hover:text-neutral-900">Methodology</Link>{" "}·{" "}
          <Link href="/" className="underline hover:text-neutral-900">Back to U.S. Senate archive</Link>
        </p>
      </section>
    </div>
  );
}

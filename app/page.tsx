import { Suspense } from "react";
import Link from "next/link";
import { getStats, getTopSenators, getPartyBreakdown, getFeed } from "./lib/queries";
import { getDailyVolume, getSenatorActivity } from "./lib/analytics";
import { ReleaseCard } from "./components/release-card";
import { SearchBox } from "./components/search-box";
import { ActivityChart } from "./components/activity-chart";
import { SwimLane } from "./components/swim-lane";
import type { FeedItem } from "./lib/db";

export const dynamic = "force-dynamic";

export default async function Home() {
  const [stats, topSenators, partyBreakdown, { items: latest }, dailyVolume, senatorActivity] =
    await Promise.all([
      getStats(),
      getTopSenators(10),
      getPartyBreakdown(),
      getFeed({ perPage: 8 }),
      getDailyVolume(90),
      getSenatorActivity(),
    ]);

  const senatorMap = new Map<
    string,
    {
      id: string;
      full_name: string;
      party: "D" | "R" | "I";
      state: string;
      weeks: { week: string; count: number }[];
      total: number;
    }
  >();
  for (const row of senatorActivity as { id: string; full_name: string; party: "D" | "R" | "I"; state: string; week: string; count: number }[]) {
    if (!senatorMap.has(row.id)) {
      senatorMap.set(row.id, { id: row.id, full_name: row.full_name, party: row.party, state: row.state, weeks: [], total: 0 });
    }
    const s = senatorMap.get(row.id)!;
    s.weeks.push({ week: row.week, count: row.count });
    s.total += row.count;
  }
  const swimLaneData = Array.from(senatorMap.values()).sort((a, b) => b.total - a.total).slice(0, 15);

  return (
    <div className="mx-auto max-w-5xl px-4">
      {/* Hero */}
      <section className="py-16">
        <h1 className="font-[family-name:var(--font-source-serif)] text-4xl md:text-5xl leading-tight text-neutral-900 mb-4">
          Capitol Releases
        </h1>
        <p className="text-sm text-neutral-500 max-w-lg leading-relaxed mb-6">
          A searchable archive of official press releases from all 100 U.S.
          senators. Normalized from {(stats.senators_with_releases ?? 0)} individual
          government websites into one feed. Updated daily.
        </p>
        <div className="max-w-md">
          <Suspense>
            <SearchBox />
          </Suspense>
        </div>
      </section>

      {/* Stat row */}
      <div className="flex flex-wrap gap-x-8 gap-y-2 text-sm text-neutral-500 border-b border-neutral-200 pb-6 mb-12">
        <div>
          <span className="text-2xl font-semibold text-neutral-900 font-[family-name:var(--font-dm-mono)] tabular-nums mr-1.5">
            {(stats.total_releases ?? 0).toLocaleString()}
          </span>
          press releases
        </div>
        <div>
          <span className="text-2xl font-semibold text-neutral-900 font-[family-name:var(--font-dm-mono)] tabular-nums mr-1.5">
            {stats.senators_with_releases ?? 0}
          </span>
          senators tracked
        </div>
        <div>
          <span className="text-2xl font-semibold text-neutral-900 font-[family-name:var(--font-dm-mono)] tabular-nums mr-1.5">
            {formatShortDate(stats.earliest)}
          </span>
          to
          <span className="text-2xl font-semibold text-neutral-900 font-[family-name:var(--font-dm-mono)] tabular-nums ml-1.5">
            {formatShortDate(stats.latest)}
          </span>
        </div>
        {(partyBreakdown as { party: string; count: number }[]).map((row) => (
          <div key={row.party}>
            <span className={`text-lg font-semibold font-[family-name:var(--font-dm-mono)] tabular-nums mr-1 ${
              row.party === "D" ? "text-blue-600" : row.party === "R" ? "text-red-600" : "text-amber-600"
            }`}>
              {row.count.toLocaleString()}
            </span>
            {row.party === "D" ? "Democratic" : row.party === "R" ? "Republican" : "Independent"}
          </div>
        ))}
      </div>

      {/* CTA cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-16">
        <CTACard href="/feed" title="Live Feed" desc="Reverse-chronological stream of all press releases." />
        <CTACard href="/senators" title="Senator Directory" desc="All 100 senators with release counts and archives." />
        <CTACard href="/about" title="Methodology" desc="How the data is collected, CMS patterns, known gaps." />
      </div>

      {/* Activity chart */}
      <section className="mb-16">
        <h2 className="font-[family-name:var(--font-source-serif)] text-2xl text-neutral-900 mb-1">
          Release Volume
        </h2>
        <p className="text-xs text-neutral-400 mb-4">Daily press releases over the past 90 days</p>
        <ActivityChart data={dailyVolume as { day: string; count: number }[]} />
      </section>

      {/* Swim lane */}
      <section className="mb-16">
        <h2 className="font-[family-name:var(--font-source-serif)] text-2xl text-neutral-900 mb-1">
          Senator Activity
        </h2>
        <p className="text-xs text-neutral-400 mb-4">
          Weekly release volume for the 15 most active senators.
          <span className="ml-3 inline-flex items-center gap-3">
            <span className="inline-flex items-center gap-1"><span className="inline-block h-2 w-2 rounded-full bg-blue-500" /> D</span>
            <span className="inline-flex items-center gap-1"><span className="inline-block h-2 w-2 rounded-full bg-red-500" /> R</span>
            <span className="inline-flex items-center gap-1"><span className="inline-block h-2 w-2 rounded-full bg-amber-500" /> I</span>
          </span>
        </p>
        <SwimLane data={swimLaneData} />
      </section>

      {/* Most active + latest releases side by side */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-12 mb-16">
        <section className="lg:col-span-2">
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-[family-name:var(--font-source-serif)] text-2xl text-neutral-900">
              Latest
            </h2>
            <Link href="/feed" className="text-sm text-neutral-400 hover:text-neutral-600 transition-colors">
              View all →
            </Link>
          </div>
          {latest.map((item: FeedItem) => (
            <ReleaseCard key={item.id} item={item} />
          ))}
        </section>

        <aside>
          <h2 className="font-[family-name:var(--font-source-serif)] text-2xl text-neutral-900 mb-4">
            Most Active
          </h2>
          <div className="space-y-1">
            {(topSenators as { id: string; full_name: string; party: string; state: string; count: number }[]).map(
              (row, i) => (
                <Link
                  key={row.id}
                  href={`/senators/${row.id}`}
                  className="flex items-center justify-between py-1.5 text-sm hover:bg-neutral-50 transition-colors -mx-2 px-2"
                >
                  <span className="flex items-center gap-2">
                    <span className="font-[family-name:var(--font-dm-mono)] text-xs text-neutral-300 w-4 text-right tabular-nums">
                      {i + 1}
                    </span>
                    <span className={`inline-block h-1.5 w-1.5 rounded-full ${
                      row.party === "D" ? "bg-blue-500" : row.party === "R" ? "bg-red-500" : "bg-amber-500"
                    }`} />
                    <span className="text-neutral-900">{row.full_name}</span>
                    <span className="text-neutral-400">({row.party}-{row.state})</span>
                  </span>
                  <span className="font-[family-name:var(--font-dm-mono)] text-neutral-500 tabular-nums">
                    {row.count}
                  </span>
                </Link>
              )
            )}
          </div>
        </aside>
      </div>
    </div>
  );
}

function CTACard({ href, title, desc }: { href: string; title: string; desc: string }) {
  return (
    <Link
      href={href}
      className="border border-neutral-200 bg-white px-5 py-4 hover:border-neutral-900 hover:bg-neutral-50 transition-colors group flex justify-between items-start"
    >
      <div>
        <div className="text-sm font-medium text-neutral-900 group-hover:underline">{title}</div>
        <p className="text-xs text-neutral-500 mt-1">{desc}</p>
      </div>
      <span className="text-neutral-300 group-hover:text-neutral-900 transition-colors text-lg mt-0.5 ml-3 shrink-0">
        →
      </span>
    </Link>
  );
}

function formatShortDate(d: string | null): string {
  if (!d) return "--";
  return new Date(d).toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

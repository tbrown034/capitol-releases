import { Suspense } from "react";
import Link from "next/link";
import { getStats, getTopSenators, getPartyBreakdown, getFeed } from "./lib/queries";
import { getDailyVolume, getSenatorActivity, getTopicTrends } from "./lib/analytics";
import { PartyDot } from "./components/party-badge";
import { ReleaseCard } from "./components/release-card";
import { SearchBox } from "./components/search-box";
import { ActivityChart } from "./components/activity-chart";
import { SwimLane } from "./components/swim-lane";
import type { FeedItem } from "./lib/db";

export const dynamic = "force-dynamic";

export default async function Home() {
  const [stats, topSenators, partyBreakdown, { items: latest }, dailyVolume, senatorActivity, topics] =
    await Promise.all([
      getStats(),
      getTopSenators(15),
      getPartyBreakdown(),
      getFeed({ perPage: 5 }),
      getDailyVolume(90),
      getSenatorActivity(),
      getTopicTrends(),
    ]);

  // Transform senator activity into swim lane data (top 20 by volume)
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
      senatorMap.set(row.id, {
        id: row.id,
        full_name: row.full_name,
        party: row.party,
        state: row.state,
        weeks: [],
        total: 0,
      });
    }
    const s = senatorMap.get(row.id)!;
    s.weeks.push({ week: row.week, count: row.count });
    s.total += row.count;
  }
  const swimLaneData = Array.from(senatorMap.values())
    .sort((a, b) => b.total - a.total)
    .slice(0, 20);

  return (
    <div className="mx-auto max-w-5xl px-4 py-8">
      {/* Hero */}
      <section className="mb-8">
        <div className="flex items-start justify-between">
          <div>
            <h1 className="text-3xl font-bold tracking-tight">
              Capitol Releases
            </h1>
            <p className="mt-2 max-w-xl text-stone-500">
              A searchable archive of official press releases from all 100 U.S.
              senators. Normalized, indexed, updated daily.
            </p>
          </div>
        </div>
        <div className="mt-5 max-w-lg">
          <Suspense>
            <SearchBox />
          </Suspense>
        </div>
      </section>

      {/* Stats bar */}
      <section className="mb-8 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatCard
          label="Press Releases"
          value={stats.total_releases ?? 0}
        />
        <StatCard
          label="Senators"
          value={stats.senators_with_releases ?? 0}
          suffix={`/ ${stats.total_senators ?? 100}`}
        />
        <StatCard label="Earliest" value={formatShortDate(stats.earliest)} />
        <StatCard label="Latest" value={formatShortDate(stats.latest)} />
      </section>

      {/* Activity chart */}
      <section className="mb-8 rounded-lg border border-stone-200 bg-white p-5">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-stone-400">
          Daily Release Volume (90 days)
        </h2>
        <div className="mt-3">
          <ActivityChart
            data={(dailyVolume as { day: string; count: number }[])}
          />
        </div>
      </section>

      {/* Swim lane */}
      <section className="mb-8 rounded-lg border border-stone-200 bg-white p-5">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-stone-400">
            Release Activity by Senator (Top 20)
          </h2>
          <div className="flex items-center gap-3 text-xs text-stone-400">
            <span className="flex items-center gap-1">
              <span className="inline-block h-2 w-2 rounded-full bg-blue-500" /> Democrat
            </span>
            <span className="flex items-center gap-1">
              <span className="inline-block h-2 w-2 rounded-full bg-red-500" /> Republican
            </span>
            <span className="flex items-center gap-1">
              <span className="inline-block h-2 w-2 rounded-full bg-amber-500" /> Independent
            </span>
          </div>
        </div>
        <div className="mt-3">
          <SwimLane data={swimLaneData} />
        </div>
      </section>

      <div className="grid gap-8 lg:grid-cols-3">
        {/* Latest releases */}
        <section className="lg:col-span-2">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-stone-400">
              Latest Releases
            </h2>
            <Link
              href="/feed"
              className="text-sm text-stone-500 hover:text-stone-900"
            >
              View all
            </Link>
          </div>
          <div className="mt-3 rounded-lg border border-stone-200 bg-white px-4">
            {latest.map((item: FeedItem) => (
              <ReleaseCard key={item.id} item={item} />
            ))}
          </div>
        </section>

        {/* Sidebar */}
        <aside className="space-y-6">
          {/* Party breakdown */}
          <div className="rounded-lg border border-stone-200 bg-white p-4">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-stone-400">
              By Party
            </h2>
            <div className="mt-3 space-y-2">
              {(partyBreakdown as { party: string; count: number }[]).map((row) => (
                <div
                  key={row.party}
                  className="flex items-center justify-between"
                >
                  <div className="flex items-center gap-2">
                    <PartyDot party={row.party as "D" | "R" | "I"} />
                    <span className="text-sm">
                      {row.party === "D"
                        ? "Democrat"
                        : row.party === "R"
                          ? "Republican"
                          : "Independent"}
                    </span>
                  </div>
                  <span className="text-sm font-semibold tabular-nums">
                    {row.count.toLocaleString()}
                  </span>
                </div>
              ))}
            </div>
          </div>

          {/* Most active */}
          <div className="rounded-lg border border-stone-200 bg-white p-4">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-stone-400">
              Most Active
            </h2>
            <div className="mt-3 space-y-1.5">
              {(topSenators as { id: string; full_name: string; party: string; state: string; count: number }[]).map(
                (row, i) => (
                  <Link
                    key={row.id}
                    href={`/senators/${row.id}`}
                    className="flex items-center justify-between rounded px-1.5 py-1 -mx-1.5 text-sm hover:bg-stone-50"
                  >
                    <span className="flex items-center gap-2">
                      <span className="w-5 text-right text-xs text-stone-300 tabular-nums">
                        {i + 1}
                      </span>
                      <PartyDot party={row.party as "D" | "R" | "I"} />
                      <span className="truncate">
                        {row.full_name}
                      </span>
                    </span>
                    <span className="ml-2 font-semibold tabular-nums">
                      {row.count}
                    </span>
                  </Link>
                )
              )}
            </div>
          </div>

          {/* Trending topics */}
          {(topics as { word: string; count: number }[]).length > 0 && (
            <div className="rounded-lg border border-stone-200 bg-white p-4">
              <h2 className="text-sm font-semibold uppercase tracking-wide text-stone-400">
                Trending Topics (30d)
              </h2>
              <div className="mt-3 flex flex-wrap gap-1.5">
                {(topics as { word: string; count: number }[])
                  .slice(0, 20)
                  .map((t) => (
                    <Link
                      key={t.word}
                      href={`/search?q=${encodeURIComponent(t.word)}`}
                      className="rounded-full border border-stone-200 bg-stone-50 px-2.5 py-0.5 text-xs text-stone-600 hover:border-stone-300 hover:bg-stone-100"
                    >
                      {t.word}{" "}
                      <span className="text-stone-400">{t.count}</span>
                    </Link>
                  ))}
              </div>
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}

function StatCard({
  label,
  value,
  suffix,
}: {
  label: string;
  value: number | string;
  suffix?: string;
}) {
  return (
    <div className="rounded-lg border border-stone-200 bg-white p-4">
      <p className="text-xs text-stone-400">{label}</p>
      <p className="mt-1 text-2xl font-bold tabular-nums">
        {typeof value === "number" ? value.toLocaleString() : value}
        {suffix && (
          <span className="ml-1 text-sm font-normal text-stone-400">
            {suffix}
          </span>
        )}
      </p>
    </div>
  );
}

function formatShortDate(d: string | null): string {
  if (!d) return "--";
  return new Date(d).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
  });
}

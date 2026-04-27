import { Suspense } from "react";
import Link from "next/link";
import { getStats, getTopSenators, getLeastActiveSenators, getFeed, getLatestRun } from "./lib/queries";
import { getChamberActivity, getDailyVolume, getSenatorActivity, getTopicTrends } from "./lib/analytics";
import { ReleaseCard } from "./components/release-card";
import { SearchBox } from "./components/search-box";
import { ActivityChart } from "./components/activity-chart";
import { SenateChamber } from "./components/senate-chamber";
import { SenatorBars } from "./components/senator-bars";
import { SenatorActivity } from "./components/senator-activity";
import type { FeedItem } from "./lib/db";

export const dynamic = "force-dynamic";

/** Reorder a date-sorted feed so no senator appears more than `maxRun` times
 *  consecutively. Items beyond the cap are deferred to the next slot where a
 *  different senator has appeared, preserving rough recency. */
function diversifyFeed(items: FeedItem[], maxRun: number): FeedItem[] {
  const out: FeedItem[] = [];
  const queue = [...items];
  while (queue.length) {
    const lastId = out[out.length - 1]?.senator_id;
    const runLength = (() => {
      let n = 0;
      for (let i = out.length - 1; i >= 0 && out[i].senator_id === lastId; i--) n++;
      return n;
    })();
    let pickIdx = 0;
    if (lastId && runLength >= maxRun) {
      const alt = queue.findIndex((it) => it.senator_id !== lastId);
      pickIdx = alt === -1 ? 0 : alt;
    }
    out.push(queue.splice(pickIdx, 1)[0]);
  }
  return out;
}

export default async function Home() {
  const [stats, topSenators, leastActive, { items: latestPool }, dailyVolume, senatorActivity, topicTrends, latestRun, chamber] =
    await Promise.all([
      getStats(),
      getTopSenators(10),
      getLeastActiveSenators(10),
      // Pull a larger pool than displayed; diversify keeps no senator with
      // more than 2 consecutive releases at the top (Apr 24 town-hall flood
      // had 8 Merkley posts in a row crowding everyone out).
      getFeed({ perPage: 36 }),
      getDailyVolume(90),
      getSenatorActivity(),
      getTopicTrends(),
      getLatestRun(),
      getChamberActivity(7),
    ]);

  const latest = diversifyFeed(latestPool, 2).slice(0, 12);

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
  for (const row of senatorActivity as {
    id: string;
    full_name: string;
    party: "D" | "R" | "I";
    state: string;
    week: string;
    count: number;
  }[]) {
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
    .slice(0, 15);

  return (
    <div className="mx-auto max-w-5xl px-4">
      {/* Hero */}
      <section className="pt-10 pb-8 md:pt-16 md:pb-12">
        <h1 className="font-serif text-4xl sm:text-5xl md:text-6xl leading-[1.05] text-neutral-900 mb-4 md:mb-5">
          100 Senators.
          <br />
          One Archive.
        </h1>
        <p className="text-sm md:text-base text-neutral-500 max-w-2xl leading-relaxed">
          Every official press release from all 100 U.S. senators, scraped
          daily from their individual senate.gov sites into one normalized,
          searchable archive.
        </p>
        <p className="text-xs text-neutral-400 mt-3">
          Collecting since January 2025 · {stats.senators_with_releases ?? 0}{" "}
          of 100 senators publishing
        </p>
        {latestRun?.finished_at && (
          <p className="text-xs text-neutral-400 mt-1">
            Last updated{" "}
            <time dateTime={latestRun.finished_at}>
              {new Date(latestRun.finished_at).toLocaleString("en-US", {
                month: "short",
                day: "numeric",
                hour: "numeric",
                minute: "2-digit",
                timeZone: "America/New_York",
                timeZoneName: "short",
              })}
            </time>
            {" · "}
            {latestRun.inserted.toLocaleString()} new release
            {latestRun.inserted === 1 ? "" : "s"} across{" "}
            {latestRun.senators_with_new} senator
            {latestRun.senators_with_new === 1 ? "" : "s"}
            {" · "}
            <Link href="/status" className="underline hover:text-neutral-900">
              run history
            </Link>
          </p>
        )}
      </section>

      {/* Stats */}
      <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:gap-x-8 sm:gap-y-2 text-sm text-neutral-500 border-b border-neutral-200 pb-4 mb-8 md:mb-12">
        <div>
          <span className="text-2xl font-semibold text-neutral-900 font-mono tabular-nums mr-1.5">
            {(stats.total_releases ?? 0).toLocaleString()}
          </span>
          press releases
        </div>
        <div>
          <span className="text-2xl font-semibold text-neutral-900 font-mono tabular-nums mr-1.5">
            {stats.total_senators ?? 0}
          </span>
          senators tracked
        </div>
        <div>
          <span className="text-2xl font-semibold text-neutral-900 font-mono tabular-nums mr-1.5">
            Jan 1, 2025
          </span>
          to present
        </div>
      </div>

      {/* Senate Chamber */}
      <section className="mb-10 md:mb-16">
        <h2 className="text-xs uppercase tracking-wider text-neutral-500 border-b border-neutral-900 pb-2 mb-4 md:mb-6">
          The Chamber, This Week
        </h2>
        <SenateChamber
          senators={chamber as { id: string; full_name: string; party: "D" | "R" | "I"; state: string; count: number }[]}
          days={7}
        />
      </section>

      {/* Release Volume */}
      <section className="mb-10 md:mb-16">
        <h2 className="text-xs uppercase tracking-wider text-neutral-500 border-b border-neutral-900 pb-2 mb-4 md:mb-6">
          Release Volume
        </h2>
        <p className="text-xs text-neutral-400 mb-4">
          Daily press releases over the past 90 days
        </p>
        <div className="overflow-x-auto -mx-4 px-4">
          <ActivityChart
            data={dailyVolume as { day: string; count: number }[]}
          />
        </div>
      </section>

      {/* Search */}
      <div className="mb-10 md:mb-16 md:max-w-lg">
        <Suspense>
          <SearchBox placeholder="Search release text — e.g. fentanyl, Ukraine, Medicaid" />
        </Suspense>
        <p className="mt-2 text-xs text-neutral-400">
          Searches the full text of every press release. Looking for a
          specific senator?{" "}
          <Link href="/senators" className="underline hover:text-neutral-900">
            Browse the directory
          </Link>
          .
        </p>
      </div>

      {/* Latest + Most active */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8 md:gap-12 mb-10 md:mb-16">
        <section className="lg:col-span-2">
          <div className="flex items-center justify-between border-b border-neutral-900 pb-2 mb-4">
            <h2 className="text-xs uppercase tracking-wider text-neutral-500">
              Latest
            </h2>
            <Link
              href="/feed"
              className="text-xs text-neutral-400 hover:text-neutral-900 transition-colors"
            >
              View all
            </Link>
          </div>
          {latest.map((item: FeedItem) => (
            <ReleaseCard key={item.id} item={item} />
          ))}
        </section>

        <SenatorActivity
          initialTop={topSenators as { id: string; full_name: string; party: string; state: string; count: number }[]}
          initialBottom={leastActive as { id: string; full_name: string; party: string; state: string; count: number }[]}
        />
      </div>

      {/* Trending Topics */}
      <section className="mb-10 md:mb-16">
        <h2 className="text-xs uppercase tracking-wider text-neutral-500 border-b border-neutral-900 pb-2 mb-4 md:mb-6">
          Trending Topics
        </h2>
        <p className="text-xs text-neutral-400 mb-4">
          Most mentioned terms in press releases over the past 30 days
        </p>
        <div className="flex flex-wrap gap-2">
          {(topicTrends as { word: string; count: number }[])
            .slice(0, 24)
            .map((topic) => (
              <Link
                key={topic.word}
                href={`/search?q=${encodeURIComponent(topic.word)}`}
                className="inline-flex items-center gap-1.5 rounded-full border border-neutral-200 bg-white px-3 py-1.5 text-sm text-neutral-700 hover:border-neutral-400 hover:text-neutral-900 transition-colors"
              >
                {topic.word}
                <span className="text-xs text-neutral-400 font-mono tabular-nums">
                  {topic.count}
                </span>
              </Link>
            ))}
        </div>
      </section>

      {/* Senator Rankings */}
      <section className="mb-10 md:mb-16">
        <div className="flex items-center justify-between border-b border-neutral-900 pb-2 mb-4 md:mb-6">
          <h2 className="text-xs uppercase tracking-wider text-neutral-500">
            Senator Rankings
          </h2>
          <Link
            href="/senators"
            className="text-xs text-neutral-400 hover:text-neutral-900 transition-colors"
          >
            View all 100
          </Link>
        </div>
        <p className="text-xs text-neutral-400 mb-6">
          Top 15 senators by release volume since January 2025
          <span className="ml-3 inline-flex items-center gap-3">
            <span className="inline-flex items-center gap-1">
              <span className="inline-block h-2 w-2 rounded-full bg-blue-500" />{" "}
              D
            </span>
            <span className="inline-flex items-center gap-1">
              <span className="inline-block h-2 w-2 rounded-full bg-red-500" />{" "}
              R
            </span>
            <span className="inline-flex items-center gap-1">
              <span className="inline-block h-2 w-2 rounded-full bg-amber-500" />{" "}
              I
            </span>
          </span>
        </p>
        <SenatorBars data={swimLaneData} />
        <div className="mt-4 pt-4 border-t border-neutral-200 flex items-center justify-between text-xs text-neutral-500">
          <span>Showing {swimLaneData.length} of 100 senators</span>
          <Link
            href="/senators"
            className="text-neutral-900 hover:underline font-medium"
          >
            See full rankings →
          </Link>
        </div>
      </section>

    </div>
  );
}


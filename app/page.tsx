import { Suspense } from "react";
import Link from "next/link";
import { getStats, getTopSenators, getLeastActiveSenators, getFeed } from "./lib/queries";
import { getDailyVolume, getSenatorActivity } from "./lib/analytics";
import { ReleaseCard } from "./components/release-card";
import { SearchBox } from "./components/search-box";
import { ActivityChart } from "./components/activity-chart";
import { SenatorBars } from "./components/senator-bars";
import type { FeedItem } from "./lib/db";

export const dynamic = "force-dynamic";

export default async function Home() {
  const [stats, topSenators, leastActive, { items: latest }, dailyVolume, senatorActivity] =
    await Promise.all([
      getStats(),
      getTopSenators(10),
      getLeastActiveSenators(10),
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
        <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-6 md:gap-8">
          <div>
            <h1 className="font-serif text-3xl sm:text-4xl md:text-5xl leading-tight text-neutral-900 mb-3 md:mb-4">
              What are your senators
              <br className="hidden sm:block" />
              {" "}saying?
            </h1>
            <p className="text-sm md:text-base text-neutral-500 max-w-xl leading-relaxed">
              Every official press release from all 100 U.S. senators, scraped
              from {stats.senators_with_releases ?? 0} individual senate.gov
              websites into one normalized, searchable archive.
            </p>
            <p className="text-xs text-neutral-400 mt-3">
              Updated daily · Collecting since January 2025
            </p>
          </div>
          <HeroGraphic />
        </div>
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
            {stats.senators_with_releases ?? 0}
          </span>
          senators tracked
        </div>
        <div>
          <span className="text-2xl font-semibold text-neutral-900 font-mono tabular-nums mr-1.5">
            2025
          </span>
          to present
        </div>
      </div>

      {/* Search */}
      <div className="mb-10 md:mb-16 md:max-w-lg">
        <Suspense>
          <SearchBox />
        </Suspense>
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

        <aside>
          <h2 className="text-xs uppercase tracking-wider text-neutral-500 border-b border-neutral-900 pb-2 mb-4">
            Most Active
          </h2>
          <div className="space-y-0.5">
            {(
              topSenators as {
                id: string;
                full_name: string;
                party: string;
                state: string;
                count: number;
              }[]
            ).map((row, i) => (
              <Link
                key={row.id}
                href={`/senators/${row.id}`}
                className="flex items-center justify-between py-1.5 text-sm hover:bg-neutral-50 transition-colors -mx-2 px-2"
              >
                <span className="flex items-center gap-2">
                  <span className="font-mono text-xs text-neutral-300 w-4 text-right tabular-nums">
                    {i + 1}
                  </span>
                  <span
                    className={`inline-block h-1.5 w-1.5 rounded-full ${
                      row.party === "D"
                        ? "bg-blue-500"
                        : row.party === "R"
                          ? "bg-red-500"
                          : "bg-amber-500"
                    }`}
                  />
                  <span className="text-neutral-900">{row.full_name}</span>
                  <span className="text-neutral-400 hidden sm:inline">
                    ({row.party}-{row.state})
                  </span>
                </span>
                <span className="font-mono text-neutral-500 tabular-nums">
                  {row.count}
                </span>
              </Link>
            ))}
          </div>
        </aside>
      </div>

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

      {/* Senator Rankings */}
      <section className="mb-10 md:mb-16">
        <h2 className="text-xs uppercase tracking-wider text-neutral-500 border-b border-neutral-900 pb-2 mb-4 md:mb-6">
          Senator Rankings
        </h2>
        <p className="text-xs text-neutral-400 mb-6">
          Total releases by senator
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
      </section>

      {/* Least Active */}
      <section className="mb-10 md:mb-16">
        <h2 className="text-xs uppercase tracking-wider text-neutral-500 border-b border-neutral-900 pb-2 mb-4 md:mb-6">
          Least Active
        </h2>
        <p className="text-xs text-neutral-400 mb-4">
          Senators with the fewest releases in the archive
        </p>
        <div className="space-y-0.5">
          {(
            leastActive as {
              id: string;
              full_name: string;
              party: string;
              state: string;
              count: number;
              last_release: string | null;
            }[]
          ).map((row, i) => (
            <Link
              key={row.id}
              href={`/senators/${row.id}`}
              className="flex items-center justify-between py-2 text-sm hover:bg-neutral-50 transition-colors -mx-2 px-2 border-b border-neutral-100 last:border-0"
            >
              <span className="flex items-center gap-2">
                <span className="font-mono text-xs text-neutral-300 w-4 text-right tabular-nums">
                  {i + 1}
                </span>
                <span
                  className={`inline-block h-1.5 w-1.5 rounded-full ${
                    row.party === "D"
                      ? "bg-blue-500"
                      : row.party === "R"
                        ? "bg-red-500"
                        : "bg-amber-500"
                  }`}
                />
                <span className="text-neutral-900">{row.full_name}</span>
                <span className="text-neutral-400 hidden sm:inline">
                  ({row.party}-{row.state})
                </span>
              </span>
              <span className="flex items-center gap-4">
                <span className="font-mono text-neutral-500 tabular-nums">
                  {row.count}
                </span>
                {row.last_release && (
                  <span className="text-xs text-neutral-400 hidden md:inline">
                    Last: {new Date(row.last_release).toLocaleDateString("en-US", { month: "short", day: "numeric" })}
                  </span>
                )}
              </span>
            </Link>
          ))}
        </div>
      </section>
    </div>
  );
}

function HeroGraphic() {
  // Stylized stack of press releases / official documents
  const docs = [
    { y: 0, w: 120, fill: "#e5e5e5", lines: 4 },
    { y: -6, w: 126, fill: "#d4d4d4", lines: 5 },
    { y: -12, w: 132, fill: "#a3a3a3", lines: 3 },
    { y: -18, w: 138, fill: "#737373", lines: 6 },
    { y: -24, w: 144, fill: "#292524", lines: 4 },
  ];

  return (
    <svg
      width={200}
      height={200}
      viewBox="0 0 200 200"
      fill="none"
      aria-hidden="true"
      className="hidden md:block shrink-0"
    >
      {/* Document stack */}
      <g transform="translate(30, 80)">
        {docs.map((doc, i) => (
          <g key={i} transform={`translate(${(144 - doc.w) / 2}, ${doc.y})`}>
            <rect
              width={doc.w}
              height={80}
              rx="2"
              fill="white"
              stroke={doc.fill}
              strokeWidth="1.5"
            />
            {/* Header bar (senate seal area) */}
            <rect width={doc.w} height={12} rx="2" fill={doc.fill} opacity="0.15" />
            <circle cx={doc.w / 2} cy={6} r={3} fill={doc.fill} opacity="0.4" />
            {/* Text lines */}
            {Array.from({ length: doc.lines }, (_, j) => (
              <rect
                key={j}
                x={10}
                y={20 + j * 12}
                width={doc.w - 20 - (j === doc.lines - 1 ? 30 : 0)}
                height={2}
                rx="1"
                fill={doc.fill}
                opacity="0.3"
              />
            ))}
          </g>
        ))}
      </g>
      {/* Party indicators */}
      <circle cx="45" cy="50" r="4" fill="#3b82f6" opacity="0.8" />
      <circle cx="100" cy="40" r="5" fill="#ef4444" opacity="0.8" />
      <circle cx="155" cy="50" r="3" fill="#f59e0b" opacity="0.8" />
      {/* Count badge */}
      <g transform="translate(150, 145)">
        <rect x="-16" y="-10" width="38" height="20" rx="10" fill="#292524" />
        <text
          x="3"
          y="4"
          textAnchor="middle"
          fill="white"
          fontSize="10"
          fontFamily="monospace"
          fontWeight="600"
        >
          100
        </text>
      </g>
    </svg>
  );
}

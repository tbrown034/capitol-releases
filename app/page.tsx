import { Suspense } from "react";
import Link from "next/link";
import { getStats, getTopSenators, getLeastActiveSenators, getFeed, getLatestRun } from "./lib/queries";
import { getChamberActivity, getSenatorActivity, getTopicTrends, getMailbag } from "./lib/analytics";
import { ReleaseCard } from "./components/release-card";
import { SenateChamber } from "./components/senate-chamber";
import { HouseChamber } from "./components/house-chamber";
import { SenatorBars } from "./components/senator-bars";
import { SenatorActivity } from "./components/senator-activity";
import { MailbagStrip } from "./components/mailbag-strip";
import { HeroLetter } from "./components/hero-letter";
import { AskAnyMember, type AskableMember } from "./components/ask-any-member";
import { formatTimestamp } from "./lib/dates";
import { sql } from "./lib/db";
import type { FeedItem, ContentType } from "./lib/db";

export const metadata = {
  title: "Capitol Releases",
  description:
    "Search and analyze official press releases from members of Congress, updated daily from source websites.",
};

// Daily-cron data; 10-min ISR is plenty and keeps the homepage off the
// request-time DB path (was 9 sequential SQL round-trips per visitor).
export const revalidate = 600;

/** Reorder a date-sorted feed so no senator appears more than `maxRun` times
 *  consecutively. Items beyond the cap are deferred to the next slot where a
 *  different senator has appeared, preserving rough recency. */
function diversifyFeed(items: FeedItem[], maxRun: number): FeedItem[] {
  const out: FeedItem[] = [];
  const queue = [...items];
  while (queue.length) {
    const lastId = out[out.length - 1]?.official_id;
    const runLength = (() => {
      let n = 0;
      for (let i = out.length - 1; i >= 0 && out[i].official_id === lastId; i--) n++;
      return n;
    })();
    let pickIdx = 0;
    if (lastId && runLength >= maxRun) {
      let alt = -1;
      for (let i = 0; i < queue.length; i++) {
        if (queue[i].official_id !== lastId) {
          alt = i;
          break;
        }
      }
      pickIdx = alt === -1 ? 0 : alt;
    }
    out.push(queue.splice(pickIdx, 1)[0]);
  }
  return out;
}

export default async function Home({
  searchParams,
}: {
  searchParams?: Promise<Record<string, string | undefined>>;
}) {
  const sp = (await searchParams) ?? {};
  const chamberView: "senate" | "house" = sp.chamber === "house" ? "house" : "senate";

  const [stats, topSenators, leastActive, { items: latestPool }, senatorActivity, topicTrends, latestRun, senateChamber, houseChamber, mailbag] =
    await Promise.all([
      getStats(),
      getTopSenators(10),
      getLeastActiveSenators(10),
      // Pull a larger pool than displayed; diversify keeps no senator with
      // more than 2 consecutive releases at the top (Apr 24 town-hall flood
      // had 8 Merkley posts in a row crowding everyone out).
      getFeed({ perPage: 36 }),
      getSenatorActivity(),
      getTopicTrends(),
      getLatestRun(),
      getChamberActivity(30, "senate"),
      getChamberActivity(30, "house"),
      getMailbag(7),
    ]);

  // Members with embedded passages, for the front-page ask box. Refreshes
  // with the same 10-minute ISR as the rest of the page.
  const askEnabled = Boolean(
    process.env.ANTHROPIC_API_KEY && process.env.OPENAI_API_KEY,
  );
  const askMembers = askEnabled
    ? ((await sql`
        SELECT s.id, s.full_name, s.party, s.state, s.chamber,
               count(p.id)::int AS passages
        FROM officials s
        JOIN rag_passages p
          ON p.official_id = s.id AND p.embedding IS NOT NULL
        WHERE s.status = 'active'
        GROUP BY s.id, s.full_name, s.party, s.state, s.chamber
        ORDER BY s.full_name
      `) as AskableMember[])
    : [];

  const heroItems = (latestPool as FeedItem[])
    .filter((it) => (it.content_type ?? "press_release") === "press_release")
    .slice(0, 6)
    .map((it) => ({
      id: it.id,
      title: it.title,
      official_id: it.official_id,
      senator_name: it.senator_name,
      party: it.party as "D" | "R" | "I",
      state: it.state,
      published_at: it.published_at,
      scraped_at: it.scraped_at,
      content_type: (it.content_type ?? "press_release") as ContentType,
      source_url: it.source_url,
      chamber: it.chamber,
      bioguide_id: it.bioguide_id,
    }));

  const latest = diversifyFeed(latestPool, 2).slice(0, 9);

  const senatorMap = new Map<
    string,
    {
      id: string;
      full_name: string;
      party: "D" | "R" | "I";
      state: string;
      weeks: { week: string; count: number }[];
      total: number;
      chamber: string | null;
    }
  >();
  for (const row of senatorActivity as {
    id: string;
    full_name: string;
    party: "D" | "R" | "I";
    state: string;
    chamber: string | null;
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
        chamber: row.chamber,
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
      <section className="pt-6 pb-4 md:pt-8 md:pb-5">
        <div className="grid grid-cols-1 md:grid-cols-12 gap-6 md:gap-10 items-center">
          <div className="md:col-span-7">
            <h1 className="font-serif text-4xl sm:text-5xl md:text-[3.25rem] leading-[1.05] text-neutral-900 mb-3 md:mb-4">
              Every member of Congress.
              <br />
              One archive.
            </h1>
            <p className="text-base md:text-lg text-neutral-700 max-w-2xl leading-snug mb-3">
              See who&rsquo;s posting most, on what topics, and how Congress&rsquo;s
              press machine moves day to day.
            </p>
            <p className="text-sm md:text-base text-neutral-500 max-w-2xl leading-relaxed">
              Every record each member&rsquo;s office publishes on their own
              .gov site, all 100 senators and 437 House representatives.
              Normalized, searchable, updated multiple times daily.
            </p>
          </div>
          {heroItems.length > 0 && (
            <div className="md:col-span-5 flex justify-center md:justify-end">
              <HeroLetter items={heroItems} asOf={latestRun?.finished_at ?? null} />
            </div>
          )}
        </div>
      </section>

      {/* Stats — slim one-line strip; the numbers speak, the words stay out
          of the way */}
      <div className="border-b border-neutral-200 pb-3 mb-5 md:mb-6">
        <p className="text-sm text-neutral-500 font-mono tabular-nums flex flex-wrap gap-x-2">
          <span>
            <span className="font-semibold text-neutral-900">
              {(stats.total_releases ?? 0).toLocaleString()}
            </span>{" "}
            records
          </span>
          <span className="text-neutral-300">|</span>
          <span>
            <span className="font-semibold text-neutral-900">
              {stats.total_senators ?? 0}
            </span>{" "}
            members
          </span>
          <span className="text-neutral-300">|</span>
          <span>since Jan 1, 2025</span>
        </p>
        {latestRun?.finished_at && (
          <p className="mt-2 text-xs text-neutral-400">
            Updated{" "}
            <time dateTime={latestRun.finished_at}>
              {formatTimestamp(latestRun.finished_at)}
            </time>
            {" · "}
            <Link href="/status" className="underline hover:text-neutral-600">
              run history
            </Link>
          </p>
        )}
      </div>

      {/* Ask the record — front-page entry: pick any member, ask their
          archive. Same component, statuses, and guardrails as member pages. */}
      {askEnabled && askMembers.length > 0 && (
        <section className="mb-10 md:mb-14 border border-neutral-200 bg-neutral-50/60 p-4 md:p-6">
          <h2 className="text-xs uppercase tracking-wider text-neutral-500 mb-3">
            Ask the record
          </h2>
          <AskAnyMember members={askMembers} />
        </section>
      )}

      {/* Chamber, visual anchor of the page. Toggle between Senate (100
          seats, default) and House (437 seats). Both render as semicircle
          heatmaps colored by party with opacity = activity. */}
      {/* House view gets a modest breakout on xl+ screens (just enough to
          give 437 dots a bit of breathing room without breaking smaller
          layouts). Senate stays at column width. */}
      <section
        className={`mb-10 md:mb-14 ${chamberView === "house" ? "xl:-mx-12" : ""}`}
      >
        <h2 className="text-3xl md:text-5xl font-serif tracking-tight mb-3">
          What is Congress talking about?
        </h2>
        <p className="text-lg md:text-2xl text-neutral-700 leading-snug mb-6 max-w-3xl">
          Tracking topics across every press release in the last 90 days, pick a term and see who&rsquo;s talking about it, by chamber.
        </p>
        <div className="flex items-center justify-between border-b border-neutral-900 pb-2 mb-3 md:mb-4">
          <h3 className="text-xs uppercase tracking-wider text-neutral-500">
            {chamberView === "house" ? "U.S. House" : "U.S. Senate"}
          </h3>
          <div className="flex gap-1">
            <Link
              href="/"
              className={`px-3 py-1 text-xs border ${chamberView === "senate" ? "border-neutral-900 bg-neutral-900 text-white" : "border-neutral-200 text-neutral-600 hover:border-neutral-400"}`}
            >
              Senate (100)
            </Link>
            <Link
              href="/?chamber=house"
              className={`px-3 py-1 text-xs border ${chamberView === "house" ? "border-neutral-900 bg-neutral-900 text-white" : "border-neutral-200 text-neutral-600 hover:border-neutral-400"}`}
            >
              House (437)
            </Link>
          </div>
        </div>
        <Suspense>
          {chamberView === "senate" ? (
            <SenateChamber
              senators={senateChamber as { id: string; full_name: string; party: "D" | "R" | "I"; state: string; count: number }[]}
              days={30}
            />
          ) : (
            <HouseChamber
              members={houseChamber as { id: string; full_name: string; party: "D" | "R" | "I"; state: string; count: number; bioguide_id: string | null }[]}
            />
          )}
        </Suspense>
      </section>

      {/* Mailbag */}
      <MailbagStrip
        items={mailbag as { content_type: ContentType; count: number }[]}
        days={7}
      />

      {/* Trending Topics, curated to ~10 chips so it fits one to two rows.
          Senator surnames + procedural vocabulary are filtered server-side
          (see analytics.ts). The "Explore all" link goes to the deeper
          /trending view. */}
      <section className="mb-10 md:mb-16">
        <div className="flex items-center justify-between border-b border-neutral-900 pb-2 mb-3 md:mb-4">
          <h2 className="text-xs uppercase tracking-wider text-neutral-500">
            Topics
          </h2>
          <Link
            href="/trending"
            className="text-xs text-neutral-500 hover:text-neutral-900 transition-colors"
          >
            Explore all →
          </Link>
        </div>
        <p className="text-xs text-neutral-500 mb-3">
          Most-mentioned terms in release titles, last 30 days. Click any term
          to search every release.
        </p>
        <div className="flex flex-wrap gap-2">
          {(topicTrends as { word: string; count: number }[])
            .slice(0, 10)
            .map((topic) => (
              <Link
                key={topic.word}
                href={`/search?q=${encodeURIComponent(topic.word)}`}
                className="inline-flex items-center gap-1.5 rounded-full border border-neutral-200 bg-white px-3 py-1.5 text-sm text-neutral-700 hover:border-neutral-400 hover:text-neutral-900 transition-colors"
              >
                {topic.word}
                <span className="text-xs text-neutral-500 font-mono tabular-nums">
                  {topic.count}
                </span>
              </Link>
            ))}
        </div>
      </section>

      {/* Latest + Most active */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8 md:gap-12 mb-10 md:mb-16">
        <section className="lg:col-span-2">
          <div className="flex items-center justify-between border-b border-neutral-900 pb-2 mb-4">
            <h2 className="text-xs uppercase tracking-wider text-neutral-500">
              Latest
            </h2>
            <Link
              href="/feed"
              className="text-xs text-neutral-500 hover:text-neutral-900 transition-colors"
            >
              View all
            </Link>
          </div>
          {latest.map((item: FeedItem) => (
            <ReleaseCard key={item.id} item={item} />
          ))}
        </section>

        <SenatorActivity
          initialTop={topSenators as { id: string; full_name: string; party: string; state: string; count: number; chamber?: string | null; bioguide_id?: string | null }[]}
          initialBottom={leastActive as { id: string; full_name: string; party: string; state: string; count: number; chamber?: string | null; bioguide_id?: string | null }[]}
        />
      </div>

      {/* Member Rankings, moved to bottom as the deep-dive view. */}
      <section className="mb-10 md:mb-16">
        <div className="flex items-center justify-between border-b border-neutral-900 pb-2 mb-4 md:mb-6">
          <h2 className="text-xs uppercase tracking-wider text-neutral-500">
            Frequency Rankings
          </h2>
          <div className="flex gap-3 text-xs text-neutral-500">
            <Link href="/senators" className="hover:text-neutral-900 transition-colors">
              All Senate
            </Link>
            <Link href="/house" className="hover:text-neutral-900 transition-colors">
              All House
            </Link>
          </div>
        </div>
        <p className="text-xs text-neutral-500 mb-6">
          Top 15 members of Congress by release volume since January 2025
          <span className="ml-3 inline-flex items-center gap-3">
            <span className="inline-flex items-center gap-1">
              <span className="inline-block size-2 rounded-full bg-blue-500" />{" "}
              D
            </span>
            <span className="inline-flex items-center gap-1">
              <span className="inline-block size-2 rounded-full bg-red-500" />{" "}
              R
            </span>
            <span className="inline-flex items-center gap-1">
              <span className="inline-block size-2 rounded-full bg-amber-500" />{" "}
              I
            </span>
          </span>
        </p>
        <SenatorBars data={swimLaneData} />
        <div className="mt-4 pt-4 border-t border-neutral-200 flex items-center justify-between text-xs text-neutral-500">
          <span>Showing top {swimLaneData.length} of 537 members of Congress</span>
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

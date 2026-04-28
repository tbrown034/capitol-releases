import Link from "next/link";
import { getTrendingWithDelta, getTopicOwnership, getPartySkew } from "../lib/trending";
import { TermChart } from "../components/term-chart";
import { TopicTimeline } from "../components/topic-timeline";
import { getSenatorPhotoUrl, getInitials } from "../lib/photos";
import { familyName } from "../lib/names";

export const metadata = {
  title: "Trending — Capitol Releases",
  description:
    "What U.S. senators are talking about now: trending terms, weekly frequency, who's pushing each topic, and party-coded vocabulary.",
};

export const revalidate = 600;

type TrendingRow = {
  word: string;
  recent_count: number;
  prior_count: number;
  delta: number;
};
type OwnerRow = {
  term: string;
  senator_id: string;
  full_name: string;
  party: "D" | "R" | "I";
  state: string;
  count: number;
};
type SkewRow = {
  word: string;
  d_count: number;
  r_count: number;
  log_odds: number | string;
  side: "D" | "R";
};

export default async function TrendingPage() {
  const [trendingRaw, skewRaw] = await Promise.all([
    getTrendingWithDelta(),
    getPartySkew(10),
  ]);

  const trending = trendingRaw as TrendingRow[];
  const skew = skewRaw as SkewRow[];

  const top5Terms = trending.slice(0, 5).map((t) => t.word);
  const ownership = (await getTopicOwnership(top5Terms)) as OwnerRow[];

  const ownersByTerm = new Map<string, OwnerRow[]>();
  for (const row of ownership) {
    const arr = ownersByTerm.get(row.term) ?? [];
    arr.push(row);
    ownersByTerm.set(row.term, arr);
  }

  const dSkew = skew.filter((r) => r.side === "D");
  const rSkew = skew.filter((r) => r.side === "R");

  const initialTimelineTerm = trending[0]?.word ?? "Trump";

  return (
    <div className="mx-auto max-w-5xl px-4 py-12">
      <h1 className="font-[family-name:var(--font-source-serif)] text-4xl md:text-5xl text-neutral-900 mb-3">
        Trending
      </h1>
      <p className="text-sm md:text-base text-neutral-600 leading-relaxed mb-2 max-w-2xl">
        What U.S. senators are talking about now — and how it&rsquo;s
        changing. Word stems pulled from release titles; trajectories use
        full text (title + body) with stemming.
      </p>
      <p className="text-xs text-neutral-400 mb-10">
        Stems collapse simple plurals (e.g. <em>family</em>/<em>families</em>
        ). Numbers are release-count, not raw word frequency, so a single
        release that uses a word ten times still counts once.
      </p>

      {/* Trending now */}
      <section className="mb-12 md:mb-16">
        <h2 className="text-xs uppercase tracking-wider text-neutral-500 border-b border-neutral-900 pb-2 mb-3">
          Trending now
        </h2>
        <p className="text-xs text-neutral-500 mb-4">
          Top stems in release titles over the last 30 days, with the change
          versus the 30 days before.
        </p>
        <ol className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-x-6">
          {trending.map((row, i) => {
            const direction =
              row.prior_count === 0 && row.recent_count >= 3
                ? "new"
                : row.delta > 0
                  ? "up"
                  : row.delta < 0
                    ? "down"
                    : "flat";
            const arrow =
              direction === "up" || direction === "new"
                ? "▲"
                : direction === "down"
                  ? "▼"
                  : "–";
            const tone =
              direction === "up"
                ? "text-emerald-600"
                : direction === "down"
                  ? "text-rose-600"
                  : direction === "new"
                    ? "text-indigo-600"
                    : "text-neutral-400";
            return (
              <li
                key={row.word}
                className="flex items-center justify-between gap-3 py-1.5 border-b border-neutral-100"
              >
                <span className="flex items-baseline gap-2 min-w-0">
                  <span className="w-5 text-right text-[11px] tabular-nums text-neutral-400 font-mono shrink-0">
                    {i + 1}
                  </span>
                  <Link
                    href={`/search?q=${encodeURIComponent(row.word)}`}
                    className="text-sm text-neutral-800 hover:underline truncate"
                  >
                    {row.word}
                  </Link>
                </span>
                <span className="flex items-center gap-2 font-mono tabular-nums text-xs shrink-0">
                  <span className="text-neutral-700">{row.recent_count}</span>
                  <span
                    className={tone}
                    title={
                      direction === "new"
                        ? "New in last 30 days"
                        : `${row.delta >= 0 ? "+" : ""}${row.delta} vs prior 30 days`
                    }
                  >
                    {arrow}
                    {direction !== "flat" && direction !== "new" && (
                      <span className="ml-0.5">{Math.abs(row.delta)}</span>
                    )}
                    {direction === "new" && <span className="ml-1">new</span>}
                  </span>
                </span>
              </li>
            );
          })}
        </ol>
      </section>

      {/* Frequency over time */}
      <section className="mb-12 md:mb-16">
        <h2 className="text-xs uppercase tracking-wider text-neutral-500 border-b border-neutral-900 pb-2 mb-3">
          Frequency over time
        </h2>
        <p className="text-xs text-neutral-500 mb-4">
          Weekly mentions of selected terms across all 100 senators&rsquo;
          releases. Add or remove terms to compare.
        </p>
        <TermChart initialTerms={top5Terms.length > 0 ? top5Terms : ["Trump"]} />
      </section>

      {/* Topic ownership */}
      <section className="mb-12 md:mb-16">
        <h2 className="text-xs uppercase tracking-wider text-neutral-500 border-b border-neutral-900 pb-2 mb-3">
          Who&rsquo;s pushing each topic
        </h2>
        <p className="text-xs text-neutral-500 mb-4">
          Top senators by full-text mentions of the current top-5 trending
          terms, since Jan 2025.
        </p>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-x-8 gap-y-6">
          {top5Terms.map((term) => {
            const owners = ownersByTerm.get(term) ?? [];
            return (
              <div key={term}>
                <div className="text-[11px] uppercase tracking-wider text-neutral-500 mb-2 border-b border-neutral-200 pb-1">
                  {term}
                </div>
                {owners.length === 0 ? (
                  <p className="text-xs text-neutral-400">No matches.</p>
                ) : (
                  <ol className="space-y-1.5">
                    {owners.map((o, i) => {
                      const photo = getSenatorPhotoUrl(o.full_name, o.senator_id);
                      const ringColor =
                        o.party === "D"
                          ? "ring-blue-500"
                          : o.party === "R"
                            ? "ring-red-500"
                            : "ring-amber-500";
                      return (
                        <li
                          key={o.senator_id}
                          className="flex items-center gap-2.5"
                        >
                          <span className="w-4 text-right text-[11px] tabular-nums text-neutral-400 font-mono">
                            {i + 1}
                          </span>
                          {photo ? (
                            // eslint-disable-next-line @next/next/no-img-element
                            <img
                              src={photo}
                              alt=""
                              width={20}
                              height={20}
                              className={`h-5 w-5 rounded-full object-cover ring-1 ${ringColor}`}
                            />
                          ) : (
                            <span
                              className={`flex h-5 w-5 items-center justify-center rounded-full bg-neutral-100 text-[8px] font-medium text-neutral-500 ring-1 ${ringColor}`}
                            >
                              {getInitials(o.full_name)}
                            </span>
                          )}
                          <Link
                            href={`/senators/${o.senator_id}`}
                            className="text-sm text-neutral-800 hover:underline truncate flex-1 min-w-0"
                          >
                            {familyName(o.full_name)}{" "}
                            <span className="text-xs text-neutral-500">
                              ({o.party}-{o.state})
                            </span>
                          </Link>
                          <span className="font-mono tabular-nums text-xs text-neutral-700">
                            {o.count}
                          </span>
                        </li>
                      );
                    })}
                  </ol>
                )}
              </div>
            );
          })}
        </div>
      </section>

      {/* Party skew */}
      <section className="mb-12 md:mb-16">
        <h2 className="text-xs uppercase tracking-wider text-neutral-500 border-b border-neutral-900 pb-2 mb-3">
          D vs R vocabulary
        </h2>
        <p className="text-xs text-neutral-500 mb-4">
          Words that tilt strongly toward one party in release titles, since
          Jan 2025. Ranked by log-odds with a Laplace prior; higher score
          means more party-coded.
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
          <div>
            <div className="text-[11px] uppercase tracking-wider mb-2 border-b border-blue-200 pb-1 text-blue-700">
              Democrat-coded
            </div>
            <ol className="space-y-1.5">
              {dSkew.map((r) => (
                <li
                  key={r.word}
                  className="flex items-center justify-between text-sm"
                >
                  <Link
                    href={`/search?q=${encodeURIComponent(r.word)}`}
                    className="text-neutral-800 hover:underline truncate"
                  >
                    {r.word}
                  </Link>
                  <span className="font-mono tabular-nums text-xs text-neutral-500">
                    <span className="text-blue-600">D {r.d_count}</span>
                    {" · "}
                    <span className="text-red-600">R {r.r_count}</span>
                  </span>
                </li>
              ))}
            </ol>
          </div>
          <div>
            <div className="text-[11px] uppercase tracking-wider mb-2 border-b border-red-200 pb-1 text-red-700">
              Republican-coded
            </div>
            <ol className="space-y-1.5">
              {rSkew.map((r) => (
                <li
                  key={r.word}
                  className="flex items-center justify-between text-sm"
                >
                  <Link
                    href={`/search?q=${encodeURIComponent(r.word)}`}
                    className="text-neutral-800 hover:underline truncate"
                  >
                    {r.word}
                  </Link>
                  <span className="font-mono tabular-nums text-xs text-neutral-500">
                    <span className="text-blue-600">D {r.d_count}</span>
                    {" · "}
                    <span className="text-red-600">R {r.r_count}</span>
                  </span>
                </li>
              ))}
            </ol>
          </div>
        </div>
      </section>

      {/* Topic timeline (single term focus) */}
      <section className="mb-12 md:mb-16">
        <h2 className="text-xs uppercase tracking-wider text-neutral-500 border-b border-neutral-900 pb-2 mb-3">
          Topic timeline
        </h2>
        <p className="text-xs text-neutral-500 mb-4">
          Pick a term and see when senators wrote about it most. Spike weeks
          (top 5 highest-volume) are highlighted; the headline that led each
          spike is below.
        </p>
        <TopicTimeline initialTerm={initialTimelineTerm} />
      </section>
    </div>
  );
}

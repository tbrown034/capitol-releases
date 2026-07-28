import Link from "next/link";
import {
  getCaucusSources,
  getColoradoLegislators,
  getColoradoFeed,
  getColoradoStats,
} from "../lib/colorado";
import { ReleaseCard } from "../components/release-card";
import { formatReleaseDate } from "../lib/dates";

export const revalidate = 600;

export const metadata = {
  title: "Colorado — Capitol Releases",
  description:
    "Every press release from the four Colorado General Assembly party caucuses, with the legislators named in each one.",
};

function partyDot(party: string) {
  return party === "D"
    ? "bg-blue-500"
    : party === "R"
      ? "bg-red-500"
      : "bg-amber-500";
}

export default async function ColoradoPage() {
  const [sources, legislators, feed, stats] = await Promise.all([
    getCaucusSources(),
    getColoradoLegislators(),
    getColoradoFeed(25),
    getColoradoStats(),
  ]);

  const quoted = legislators.filter((l) => l.quoted_count > 0);
  const neverQuoted = legislators.filter((l) => l.quoted_count === 0);

  return (
    <div className="mx-auto max-w-5xl px-4 py-12">
      <Link
        href="/states"
        className="text-xs text-neutral-500 hover:text-neutral-900 mb-6 inline-block"
      >
        ← All states
      </Link>

      <h1 className="font-[family-name:var(--font-source-serif)] text-4xl text-neutral-900 mb-3">
        Colorado
      </h1>

      <p className="text-sm text-neutral-600 leading-relaxed max-w-2xl">
        No Colorado legislator publishes a press page on a state government
        site. All legislative press output comes from the four party caucus
        organizations below, so every record here is bylined to a caucus. The
        legislators named inside each release are extracted from its text.
      </p>

      <dl className="mt-6 grid grid-cols-2 gap-4 sm:grid-cols-4">
        {[
          { label: "Releases", value: stats.items.toLocaleString() },
          { label: "Name mentions", value: stats.mentions.toLocaleString() },
          {
            label: "Legislators covered",
            value: `${stats.legislators_mentioned} / 100`,
          },
          {
            label: "Archive starts",
            value: stats.oldest ? formatReleaseDate(stats.oldest) : "—",
          },
        ].map((s) => (
          <div key={s.label} className="border-l-2 border-neutral-200 pl-3">
            <dt className="text-[10px] uppercase tracking-wider text-neutral-400">
              {s.label}
            </dt>
            <dd className="font-[family-name:var(--font-dm-mono)] text-lg text-neutral-900 tabular-nums">
              {s.value}
            </dd>
          </div>
        ))}
      </dl>

      <h2 className="font-[family-name:var(--font-source-serif)] text-2xl text-neutral-900 mt-12 mb-4">
        The four publishers
      </h2>
      <div className="grid gap-3 sm:grid-cols-2">
        {sources.map((s) => (
          <div
            key={s.id}
            className="border border-neutral-200 p-3 flex items-baseline justify-between gap-3"
          >
            <div className="min-w-0">
              <span
                className={`inline-block size-2 rounded-full ${partyDot(s.party)} mr-2`}
                aria-hidden
              />
              <span className="text-sm text-neutral-900">{s.full_name}</span>
              <p className="text-[11px] text-neutral-500 mt-0.5">
                Latest {s.latest ? formatReleaseDate(s.latest) : "—"}
              </p>
            </div>
            <span className="font-[family-name:var(--font-dm-mono)] text-sm text-neutral-700 tabular-nums shrink-0">
              {s.item_count.toLocaleString()}
            </span>
          </div>
        ))}
      </div>

      <h2 className="font-[family-name:var(--font-source-serif)] text-2xl text-neutral-900 mt-12 mb-2">
        Legislators
      </h2>
      <p className="text-xs text-neutral-500 mb-4 max-w-2xl">
        Ranked by how many caucus releases quote them directly. Being quoted is
        an editorial choice by a caucus press office; being listed as a bill
        sponsor is closer to automatic, so the two are counted separately.
      </p>

      <div className="border-t border-neutral-100">
        {quoted.map((l) => (
          <Link
            key={l.id}
            href={`/colorado/${l.id}`}
            className="flex items-baseline gap-3 border-b border-neutral-100 py-1.5 hover:bg-neutral-50 transition-colors"
          >
            <span
              className={`size-2 rounded-full ${partyDot(l.party)} shrink-0`}
              aria-hidden
            />
            <span className="text-sm text-neutral-900 flex-1 min-w-0 truncate">
              {l.full_name}
            </span>
            <span className="text-[11px] text-neutral-400 font-[family-name:var(--font-dm-mono)] shrink-0">
              {l.chamber === "senate" ? "SD" : "HD"} {l.district}
            </span>
            <span className="text-[11px] text-neutral-700 font-[family-name:var(--font-dm-mono)] tabular-nums w-20 text-right shrink-0">
              {l.quoted_count} quoted
            </span>
          </Link>
        ))}
      </div>

      {neverQuoted.length > 0 && (
        <details className="mt-6">
          <summary className="text-xs text-neutral-500 cursor-pointer hover:text-neutral-900">
            {neverQuoted.length} legislators never quoted in a collected release
          </summary>
          <div className="mt-3 flex flex-wrap gap-1.5">
            {neverQuoted.map((l) => (
              <Link
                key={l.id}
                href={`/colorado/${l.id}`}
                className="border border-neutral-200 bg-neutral-50 px-1.5 py-0.5 text-[11px] text-neutral-500 hover:border-neutral-400 transition-colors"
              >
                {l.full_name}
              </Link>
            ))}
          </div>
        </details>
      )}

      <h2 className="font-[family-name:var(--font-source-serif)] text-2xl text-neutral-900 mt-12 mb-1">
        Recent releases
      </h2>
      <p className="text-xs text-neutral-500 mb-3 max-w-2xl">
        Joint releases are published by both Democratic caucuses under
        separate URLs. Both copies are archived; the feed shows one and names
        the other publishers.
      </p>
      <div>
        {feed.map((item) => {
          const alsoBy = item.publishers.filter((p) => p !== item.senator_name);
          return (
            <div key={item.id}>
              <ReleaseCard item={item} />
              {alsoBy.length > 0 && (
                <p className="-mt-1 mb-1.5 pl-[42px] text-[10px] text-neutral-400">
                  Also published by {alsoBy.join(", ")}
                </p>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

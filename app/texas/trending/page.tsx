import Link from "next/link";
import { getTxTopicTrends, getTxStats } from "../../lib/texas";

export const metadata = {
  title: "Trending in the Texas Senate — Capitol Releases",
  description:
    "Most-mentioned terms in Texas Senate press release titles since January 2025.",
};

export const revalidate = 600;

export default async function TexasTrendingPage() {
  const [topics, stats] = await Promise.all([
    getTxTopicTrends(48),
    getTxStats(),
  ]);

  return (
    <div className="mx-auto max-w-3xl px-4 py-12">
      <Link
        href="/texas"
        className="text-xs text-neutral-500 hover:text-neutral-900 mb-6 inline-block"
      >
        ← Texas Senate
      </Link>

      <h1 className="font-[family-name:var(--font-source-serif)] text-4xl text-neutral-900 mb-3">
        What the Texas Senate is talking about
      </h1>
      <p className="text-sm text-neutral-600 leading-relaxed mb-2 max-w-2xl">
        Most-mentioned terms across {stats.total_releases.toLocaleString()}{" "}
        Texas Senate press release titles since January 2025. Senator surnames
        and procedural vocabulary are filtered out so subject matter surfaces
        first.
      </p>
      <p className="text-xs text-neutral-500 leading-relaxed mb-8 max-w-2xl">
        Click any term to search the full text (title + body) of every record.
        Counts are document-level &mdash; if a term appears multiple times in
        one release, it&apos;s counted once.
      </p>

      <div className="border-b border-neutral-200 mb-6" />

      {topics.length === 0 ? (
        <p className="text-sm text-neutral-500">
          Not enough data to surface trending terms yet. The TX corpus is
          still small (~314 records) and most volume concentrates in
          regular-session months.
        </p>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-1">
          {topics.map((t, i) => (
            <Link
              key={t.word}
              href={`/texas/search?q=${encodeURIComponent(t.word)}`}
              className="flex items-center gap-3 py-2 border-b border-neutral-100 hover:bg-neutral-50 transition-colors"
            >
              <span className="w-6 text-right text-[11px] tabular-nums text-neutral-400 font-mono">
                {i + 1}
              </span>
              <span className="flex-1 text-neutral-900">{t.word}</span>
              <span className="font-mono tabular-nums text-sm text-neutral-500">
                {t.count}
              </span>
            </Link>
          ))}
        </div>
      )}

      <p className="mt-12 text-xs text-neutral-500 leading-relaxed max-w-2xl border-t border-neutral-200 pt-6">
        Methodology: title-only word extraction with single trailing-s
        stemming (so &ldquo;water&rdquo; and &ldquo;waters&rdquo; collapse).
        Words shorter than 5 characters and a curated stopword list (Texas
        senator surnames, procedural verbs, government-process vocabulary)
        are excluded. Words are deduplicated within a release before counting,
        so the score is closer to {`"how many releases mention this"`} than
        {` "how many times is this said."`}{" "}
        <Link href="/about" className="underline hover:text-neutral-900">
          More on methodology
        </Link>
        .
      </p>
    </div>
  );
}

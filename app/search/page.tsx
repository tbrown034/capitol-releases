import { Suspense } from "react";
import Link from "next/link";
import { getFeed } from "../lib/queries";
import { ReleaseCard } from "../components/release-card";
import { SearchBox } from "../components/search-box";
import { Pagination } from "../components/pagination";
import type { FeedItem } from "../lib/db";

export const metadata = {
  title: "Search — Capitol Releases",
};

const EXAMPLE_TOPICS = [
  "healthcare",
  "immigration",
  "trade",
  "veterans",
  "inflation",
  "border",
  "Ukraine",
  "Israel",
  "fentanyl",
  "China",
  "energy",
  "climate",
];

export default async function SearchPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | undefined>>;
}) {
  const params = await searchParams;
  const query = params.q ?? "";
  const page = Number(params.page ?? "1");
  const perPage = 25;

  const hasQuery = query.trim().length > 0;
  const { items, total } = hasQuery
    ? await getFeed({ page, perPage, search: query })
    : { items: [], total: 0 };

  return (
    <div className="mx-auto max-w-3xl px-4 py-12">
      <h1 className="font-[family-name:var(--font-source-serif)] text-4xl text-neutral-900 mb-3">
        Search
      </h1>
      <p className="text-sm text-neutral-600 leading-relaxed mb-6 max-w-2xl">
        Full-text search across every press release in the archive. Matches
        the title and body; ranked by date.
      </p>

      <div className="mb-8">
        <SearchBox basePath="/search" />
      </div>

      {hasQuery ? (
        <>
          <p className="text-xs text-neutral-400 leading-relaxed mb-4 max-w-2xl">
            <span className="font-[family-name:var(--font-dm-mono)] tabular-nums text-neutral-900 font-semibold">
              {total.toLocaleString()}
            </span>{" "}
            result{total !== 1 ? "s" : ""} for{" "}
            <span className="text-neutral-900">&ldquo;{query}&rdquo;</span>
          </p>

          <div className="border-b border-neutral-200 mb-2" />

          {items.length === 0 ? (
            <p className="py-12 text-center text-sm text-neutral-400">
              No matches. Try different keywords.
            </p>
          ) : (
            <div>
              {items.map((item: FeedItem) => (
                <ReleaseCard key={item.id} item={item} />
              ))}
            </div>
          )}

          <Suspense>
            <Pagination total={total} perPage={perPage} basePath="/search" />
          </Suspense>
        </>
      ) : (
        <section>
          <p className="text-xs uppercase tracking-wider text-neutral-500 border-b border-neutral-900 pb-2 mb-4">
            Try a topic
          </p>
          <div className="flex flex-wrap gap-2">
            {EXAMPLE_TOPICS.map((topic) => (
              <Link
                key={topic}
                href={`/search?q=${encodeURIComponent(topic)}`}
                className="inline-flex items-center rounded-full border border-neutral-200 bg-white px-3 py-1.5 text-sm text-neutral-700 hover:border-neutral-400 hover:text-neutral-900 transition-colors"
              >
                {topic}
              </Link>
            ))}
          </div>
          <p className="mt-6 text-xs text-neutral-400 max-w-xl leading-relaxed">
            Search uses Postgres full-text matching with English stemming —
            &ldquo;vote&rdquo; also catches &ldquo;voted&rdquo; and &ldquo;voting.&rdquo;
          </p>
        </section>
      )}
    </div>
  );
}

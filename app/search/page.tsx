import { Suspense } from "react";
import Link from "next/link";
import { getFeed } from "../lib/queries";
import { ReleaseCard } from "../components/release-card";
import { SearchBox } from "../components/search-box";
import { Pagination } from "../components/pagination";
import { EmptyState } from "../components/empty-state";
import { STATE_NAMES } from "../lib/states";
import type { FeedItem, ContentType } from "../lib/db";

const VALID_TYPES = new Set<ContentType>([
  "press_release",
  "statement",
  "op_ed",
  "blog",
  "letter",
  "floor_statement",
  "presidential_action",
  "other",
]);

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
  const party = params.party;
  const state = params.state;
  const type =
    params.type && VALID_TYPES.has(params.type as ContentType)
      ? (params.type as ContentType)
      : undefined;
  const perPage = 25;

  const hasQuery = query.trim().length > 0;
  const { items, total } = hasQuery
    ? await getFeed({ page, perPage, search: query, party, state, type })
    : { items: [], total: 0 };

  const activeFilters: string[] = [];
  if (party)
    activeFilters.push(
      party === "D" ? "Democrats" : party === "R" ? "Republicans" : "Independents"
    );
  if (state) activeFilters.push(STATE_NAMES[state] ?? state);
  if (type) activeFilters.push(type.replace("_", " "));

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
          <p className="text-xs text-neutral-400 leading-relaxed mb-2 max-w-2xl">
            <span className="font-[family-name:var(--font-dm-mono)] tabular-nums text-neutral-900 font-semibold">
              {total.toLocaleString()}
            </span>{" "}
            result{total !== 1 ? "s" : ""} for{" "}
            <span className="text-neutral-900">&ldquo;{query}&rdquo;</span>
            {activeFilters.length > 0 && (
              <> filtered to {activeFilters.join(", ")}</>
            )}
          </p>

          {activeFilters.length > 0 && (
            <p className="text-xs mb-4 max-w-2xl">
              <Link
                href={`/search?q=${encodeURIComponent(query)}`}
                className="text-neutral-500 underline underline-offset-2 hover:text-neutral-900"
              >
                Search all senators instead
              </Link>
            </p>
          )}

          <div className="border-b border-neutral-200 mb-2" />

          {items.length === 0 ? (
            <EmptyState
              message={`No matches for \u201C${query}\u201D${activeFilters.length > 0 ? ` in ${activeFilters.join(", ")}` : ""}.`}
              clearHref={
                activeFilters.length > 0
                  ? `/search?q=${encodeURIComponent(query)}`
                  : "/search"
              }
              suggestions={
                activeFilters.length > 0
                  ? []
                  : [{ label: "Browse the feed", href: "/feed" }]
              }
            />
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

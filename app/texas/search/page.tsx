import { Suspense } from "react";
import Link from "next/link";
import { getFeed } from "../../lib/queries";
import { getTxRoster, getTxSearchFacets } from "../../lib/texas";
import { ReleaseCard } from "../../components/release-card";
import { SearchBox } from "../../components/search-box";
import { TxFeedFilters } from "../../components/tx-feed-filters";
import { Pagination } from "../../components/pagination";
import { EmptyState } from "../../components/empty-state";
import { CONTENT_TYPE_LABEL } from "../../lib/content-types";
import type { ContentType, FeedItem } from "../../lib/db";

const VALID_TYPES = new Set<ContentType>([
  "press_release",
  "statement",
  "op_ed",
  "blog",
  "letter",
  "floor_statement",
  "other",
]);

export const metadata = {
  title: "Texas Senate Search — Capitol Releases",
  description:
    "Full-text search across every Texas state senator's press releases since January 2025.",
};

const EXAMPLE_TOPICS = [
  "school finance",
  "water",
  "property tax",
  "border",
  "session",
  "appropriations",
  "redistricting",
  "Medicaid",
  "energy",
  "fentanyl",
];

type SearchFeedItem = Awaited<ReturnType<typeof getFeed>>["items"][number];

type Params = {
  q?: string;
  page?: string;
  party?: string;
  senator?: string;
  type?: string;
  sort?: string;
};

export default async function TexasSearchPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | undefined>>;
}) {
  const sp = (await searchParams) as Params;
  const query = sp.q ?? "";
  const page = Number(sp.page ?? "1");
  const party = sp.party;
  const senator = sp.senator;
  const type =
    sp.type && VALID_TYPES.has(sp.type as ContentType)
      ? (sp.type as ContentType)
      : undefined;
  const sort: "date" | "relevance" =
    sp.sort === "relevance" ? "relevance" : "date";
  const perPage = 25;

  const hasQuery = query.trim().length > 0;

  const [{ items, total }, facets, roster] = hasQuery
    ? await Promise.all([
        getFeed({
          chamber: "tx_senate",
          page,
          perPage,
          search: query,
          party,
          senator,
          type,
          sort,
        }),
        getTxSearchFacets({ search: query, party, type }),
        getTxRoster(),
      ])
    : await Promise.all([
        Promise.resolve({
          items: [] as Awaited<ReturnType<typeof getFeed>>["items"],
          total: 0,
        }),
        Promise.resolve(null),
        getTxRoster(),
      ]);

  const buildHref = (overrides: Record<string, string | null | undefined>) => {
    const u = new URLSearchParams();
    if (query) u.set("q", query);
    if (party) u.set("party", party);
    if (senator) u.set("senator", senator);
    if (type) u.set("type", type);
    if (sort !== "date") u.set("sort", sort);
    for (const [k, v] of Object.entries(overrides)) {
      if (v === null || v === undefined) u.delete(k);
      else u.set(k, v);
    }
    u.delete("page");
    const s = u.toString();
    return s ? `/texas/search?${s}` : "/texas/search";
  };

  return (
    <div className="mx-auto max-w-3xl px-4 py-12">
      <Link
        href="/texas"
        className="text-xs text-neutral-500 hover:text-neutral-900 mb-6 inline-block"
      >
        ← Texas Senate
      </Link>

      <h1 className="font-[family-name:var(--font-source-serif)] text-4xl text-neutral-900 mb-3">
        Search the Texas Senate
      </h1>
      <p className="text-sm text-neutral-600 leading-relaxed mb-2 max-w-2xl">
        Search across every Texas state senator&apos;s press releases since
        January 2025. English stemming.
      </p>
      <p className="text-xs text-neutral-500 leading-relaxed mb-6 max-w-2xl">
        Texas Senate releases are mostly published as PDFs; we archive the
        listing title + date but not the body text. Searches match against
        titles. To search the full body, open the original PDF on
        senate.texas.gov from the result.
      </p>

      <div className="mb-6">
        <Suspense>
          <SearchBox basePath="/texas/search" />
        </Suspense>
      </div>

      {!hasQuery ? (
        <div className="mt-8">
          <p className="text-xs uppercase tracking-wider text-neutral-500 mb-3">
            Try a topic
          </p>
          <div className="flex flex-wrap gap-2">
            {EXAMPLE_TOPICS.map((q) => (
              <Link
                key={q}
                href={`/texas/search?q=${encodeURIComponent(q)}`}
                className="rounded-full border border-neutral-200 bg-white px-3 py-1.5 text-sm text-neutral-700 hover:border-neutral-400 hover:text-neutral-900 transition-colors"
              >
                {q}
              </Link>
            ))}
          </div>
          <p className="mt-6 text-xs text-neutral-500 max-w-xl leading-relaxed">
            The Texas corpus is much smaller than the U.S. Senate one
            (~314 records vs ~35,000) and concentrated in regular-session
            months. Common terms like {`"committee" or "session"`} return
            high counts; specific bill subjects return tighter slices.
          </p>
        </div>
      ) : (
        <>
          <div className="mb-6">
            <Suspense>
              <TxFeedFilters basePath="/texas/search" senators={roster} />
            </Suspense>
          </div>

          {/* Sort + facet bar */}
          <div className="mb-4 flex flex-wrap items-center gap-x-4 gap-y-2 text-xs">
            <span className="text-neutral-500 tabular-nums">
              {total.toLocaleString()} match{total !== 1 ? "es" : ""}
            </span>
            <span className="text-neutral-300">·</span>
            <span className="text-neutral-500 uppercase tracking-wider">Sort</span>
            <Link
              href={buildHref({ sort: null })}
              className={`rounded-full border px-2.5 py-1 transition-colors ${
                sort === "date"
                  ? "border-neutral-900 bg-neutral-900 text-white"
                  : "border-neutral-200 text-neutral-500 hover:border-neutral-400 hover:text-neutral-900"
              }`}
            >
              Newest
            </Link>
            <Link
              href={buildHref({ sort: "relevance" })}
              className={`rounded-full border px-2.5 py-1 transition-colors ${
                sort === "relevance"
                  ? "border-neutral-900 bg-neutral-900 text-white"
                  : "border-neutral-200 text-neutral-500 hover:border-neutral-400 hover:text-neutral-900"
              }`}
            >
              Most relevant
            </Link>
            {facets && Object.keys(facets.type).length > 0 && (
              <span className="text-neutral-500 ml-auto">
                {Object.entries(facets.type)
                  .sort((a, b) => b[1] - a[1])
                  .slice(0, 4)
                  .map(([t, n]) => `${CONTENT_TYPE_LABEL[t as ContentType]} ${n}`)
                  .join(" · ")}
              </span>
            )}
          </div>

          <div className="border-b border-neutral-200 mb-2" />

          {items.length === 0 ? (
            <EmptyState
              message={`No matches for "${query}" in the Texas Senate corpus.`}
              suggestions={[
                { label: "Search the U.S. Senate corpus", href: `/search?q=${encodeURIComponent(query)}` },
                { label: "Browse the Texas feed", href: "/texas/feed" },
              ]}
            />
          ) : (
            <div>
              {(items as (FeedItem & { snippet?: string | null })[]).map((item) => (
                <ReleaseCardWithSnippet key={item.id} item={item} />
              ))}
            </div>
          )}

          <Suspense>
            <Pagination total={total} perPage={perPage} basePath="/texas/search" />
          </Suspense>
        </>
      )}
    </div>
  );
}

function ReleaseCardWithSnippet({ item }: { item: SearchFeedItem }) {
  return (
    <div className="group">
      <ReleaseCard item={item} />
      {item.snippet && (
        <div className="mb-4 -mt-3 ml-14 pl-4 border-l-2 border-neutral-200 text-sm text-neutral-600 leading-relaxed">
          <span
            className="[&>mark]:bg-yellow-100 [&>mark]:text-neutral-900 [&>mark]:px-0.5"
            dangerouslySetInnerHTML={{ __html: item.snippet }}
          />
        </div>
      )}
    </div>
  );
}

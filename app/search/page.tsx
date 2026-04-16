import { Suspense } from "react";
import { getFeed } from "../lib/queries";
import { ReleaseCard } from "../components/release-card";
import { SearchBox } from "../components/search-box";
import { Pagination } from "../components/pagination";
import type { FeedItem } from "../lib/db";

export const metadata = {
  title: "Search -- Capitol Releases",
};

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
    <div className="mx-auto max-w-3xl px-4 py-8">
      <h1 className="text-2xl font-bold">Search</h1>
      <p className="mt-1 text-sm text-gray-500">
        Full-text search across all archived press releases.
      </p>

      <div className="mt-6">
        <SearchBox basePath="/search" />
      </div>

      {hasQuery && (
        <div className="mt-6">
          <p className="text-sm text-gray-600">
            {total.toLocaleString()} result{total !== 1 ? "s" : ""} for{" "}
            <span className="font-medium">&ldquo;{query}&rdquo;</span>
          </p>

          <div className="mt-4">
            {items.length === 0 ? (
              <p className="py-12 text-center text-gray-400">
                No results found. Try different keywords.
              </p>
            ) : (
              items.map((item: FeedItem) => (
                <ReleaseCard key={item.id} item={item} />
              ))
            )}
          </div>

          <Suspense>
            <Pagination total={total} perPage={perPage} basePath="/search" />
          </Suspense>
        </div>
      )}

      {!hasQuery && (
        <div className="mt-12 text-center text-gray-400">
          <p className="text-lg">Enter a search term above.</p>
          <p className="mt-2 text-sm">
            Try topics like &ldquo;healthcare&rdquo;, &ldquo;trade&rdquo;, or
            &ldquo;veterans&rdquo;.
          </p>
        </div>
      )}
    </div>
  );
}

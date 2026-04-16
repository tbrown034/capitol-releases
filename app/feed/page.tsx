import { Suspense } from "react";
import { getFeed } from "../lib/queries";
import { ReleaseCard } from "../components/release-card";
import { FeedFilters } from "../components/feed-filters";
import { Pagination } from "../components/pagination";
import { SearchBox } from "../components/search-box";
import type { FeedItem } from "../lib/db";

export const metadata = {
  title: "Feed -- Capitol Releases",
};

export default async function FeedPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | undefined>>;
}) {
  const params = await searchParams;
  const page = Number(params.page ?? "1");
  const party = params.party;
  const state = params.state;
  const perPage = 25;

  const { items, total } = await getFeed({ page, perPage, party, state });

  return (
    <div className="mx-auto max-w-3xl px-4 py-8">
      <h1 className="text-2xl font-bold">Press Release Feed</h1>
      <p className="mt-1 text-sm text-gray-500">
        Reverse-chronological feed of official press releases from all 100
        senators.
      </p>

      <div className="mt-6 space-y-4">
        <SearchBox basePath="/search" />
        <Suspense>
          <FeedFilters basePath="/feed" />
        </Suspense>
      </div>

      <div className="mt-6">
        {items.length === 0 ? (
          <p className="py-12 text-center text-gray-400">
            No press releases found with these filters.
          </p>
        ) : (
          items.map((item: FeedItem) => (
            <ReleaseCard key={item.id} item={item} />
          ))
        )}
      </div>

      <Suspense>
        <Pagination total={total} perPage={perPage} basePath="/feed" />
      </Suspense>
    </div>
  );
}

import { Suspense } from "react";
import Link from "next/link";
import { getFeed, CONTENT_TYPE_LABEL, CONTENT_TYPE_PLURAL } from "../lib/queries";
import { ReleaseCard } from "../components/release-card";
import { FeedFilters } from "../components/feed-filters";
import { Pagination } from "../components/pagination";
import { SearchBox } from "../components/search-box";
import { EmptyState } from "../components/empty-state";
import { STATE_NAMES } from "../lib/states";
import type { FeedItem, ContentType } from "../lib/db";

export const metadata = {
  title: "Feed — Capitol Releases",
};

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

export default async function FeedPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | undefined>>;
}) {
  const params = await searchParams;
  const page = Number(params.page ?? "1");
  const party = params.party;
  const state = params.state;
  const type =
    params.type && VALID_TYPES.has(params.type as ContentType)
      ? (params.type as ContentType)
      : undefined;
  const perPage = 25;

  const { items, total } = await getFeed({ page, perPage, party, state, type });

  const filterSummary: string[] = [];
  if (type) filterSummary.push(CONTENT_TYPE_LABEL[type].toLowerCase());
  if (party) {
    filterSummary.push(
      party === "D" ? "Democrats" : party === "R" ? "Republicans" : "Independents"
    );
  }
  if (state) filterSummary.push(STATE_NAMES[state] ?? state);

  const noun = type ? CONTENT_TYPE_PLURAL[type] : "record";

  return (
    <div className="mx-auto max-w-3xl px-4 py-12">
      <h1 className="font-[family-name:var(--font-source-serif)] text-4xl text-neutral-900 mb-3">
        Feed
      </h1>
      <p className="text-sm text-neutral-600 leading-relaxed mb-2 max-w-2xl">
        Every official release from every senator, reverse-chronological. Filter
        by type, party, or state; search the full text at{" "}
        <Link href="/search" className="underline hover:text-neutral-900">
          /search
        </Link>
        .
      </p>
      <p className="text-xs text-neutral-400 leading-relaxed mb-6 max-w-2xl">
        <span className="font-[family-name:var(--font-dm-mono)] tabular-nums text-neutral-900 font-semibold">
          {total.toLocaleString()}
        </span>{" "}
        {type ? noun : `${noun}${total !== 1 ? "s" : ""}`}
        {filterSummary.length > 0 && !type && <> from {filterSummary.join(", ")}</>}
        {filterSummary.length > 0 && type && (
          <>
            {filterSummary.length > 1 ? " from " : ""}
            {filterSummary.slice(1).join(", ")}
          </>
        )}
        .
      </p>

      <div className="mb-6">
        <Suspense>
          <SearchBox basePath="/search" />
        </Suspense>
      </div>

      <div className="mb-8">
        <Suspense>
          <FeedFilters basePath="/feed" />
        </Suspense>
      </div>

      <div className="border-b border-neutral-200 mb-2" />

      {items.length === 0 ? (
        (() => {
          const hasFilters = Boolean(type || party || state);
          const suggestions: { label: string; href: string }[] = [];
          if (type && (party || state)) {
            const keep = new URLSearchParams();
            if (party) keep.set("party", party);
            if (state) keep.set("state", state);
            suggestions.push({
              label: `All releases${state ? ` from ${STATE_NAMES[state] ?? state}` : ""}`,
              href: `/feed${keep.toString() ? `?${keep.toString()}` : ""}`,
            });
          }
          return (
            <EmptyState
              message={
                hasFilters
                  ? "No records match these filters."
                  : "No records yet."
              }
              clearHref={hasFilters ? "/feed" : undefined}
              suggestions={suggestions}
            />
          );
        })()
      ) : (
        <div>
          {items.map((item: FeedItem) => (
            <ReleaseCard key={item.id} item={item} />
          ))}
        </div>
      )}

      <Suspense>
        <Pagination total={total} perPage={perPage} basePath="/feed" />
      </Suspense>
    </div>
  );
}

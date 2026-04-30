import { Suspense } from "react";
import Link from "next/link";
import { getFeed, CONTENT_TYPE_LABEL, CONTENT_TYPE_PLURAL } from "../../lib/queries";
import { getTxRoster } from "../../lib/texas";
import { ReleaseCard } from "../../components/release-card";
import { TxFeedFilters } from "../../components/tx-feed-filters";
import { Pagination } from "../../components/pagination";
import { SearchBox } from "../../components/search-box";
import { EmptyState } from "../../components/empty-state";
import type { FeedItem, ContentType } from "../../lib/db";

export const metadata = {
  title: "Texas Senate Feed — Capitol Releases",
  description:
    "Every press release from every Texas state senator, reverse-chronological. Filter by senator, party, or content type.",
};

const VALID_TYPES = new Set<ContentType>([
  "press_release",
  "statement",
  "op_ed",
  "blog",
  "letter",
  "floor_statement",
  "other",
]);

export default async function TexasFeedPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | undefined>>;
}) {
  const params = await searchParams;
  const page = Number(params.page ?? "1");
  const party = params.party;
  const senator = params.senator;
  const type =
    params.type && VALID_TYPES.has(params.type as ContentType)
      ? (params.type as ContentType)
      : undefined;
  const perPage = 25;

  const [{ items, total }, roster] = await Promise.all([
    getFeed({
      page,
      perPage,
      chamber: "tx_senate",
      party,
      senator,
      type,
    }),
    getTxRoster(),
  ]);

  const filterSummary: string[] = [];
  if (type) filterSummary.push(CONTENT_TYPE_LABEL[type].toLowerCase());
  if (party) {
    filterSummary.push(
      party === "D" ? "Democrats" : party === "R" ? "Republicans" : "Independents"
    );
  }
  if (senator) {
    const s = roster.find((r) => r.id === senator);
    if (s) filterSummary.push(s.full_name);
  }

  const noun = type ? CONTENT_TYPE_PLURAL[type] : "record";

  return (
    <div className="mx-auto max-w-3xl px-4 py-12">
      <Link
        href="/texas"
        className="text-xs text-neutral-500 hover:text-neutral-900 mb-6 inline-block"
      >
        ← Texas Senate
      </Link>

      <h1 className="font-[family-name:var(--font-source-serif)] text-4xl text-neutral-900 mb-3">
        Texas Senate feed
      </h1>
      <p className="text-sm text-neutral-600 leading-relaxed mb-2 max-w-2xl">
        Every release from every Texas state senator&apos;s pressroom on
        senate.texas.gov, reverse-chronological. Filter by senator, party, or
        type; search the full text at{" "}
        <Link href="/texas/search" className="underline hover:text-neutral-900">
          /texas/search
        </Link>
        .
      </p>
      <p className="text-xs text-neutral-500 leading-relaxed mb-6 max-w-2xl">
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
          <SearchBox basePath="/texas/search" />
        </Suspense>
      </div>

      <div className="mb-8">
        <Suspense>
          <TxFeedFilters basePath="/texas/feed" senators={roster} />
        </Suspense>
      </div>

      <div className="border-b border-neutral-200 mb-2" />

      {items.length === 0 ? (
        (() => {
          const hasFilters = Boolean(type || party || senator);
          const suggestions: { label: string; href: string }[] = [];
          if (type && (party || senator)) {
            const keep = new URLSearchParams();
            if (party) keep.set("party", party);
            if (senator) keep.set("senator", senator);
            suggestions.push({
              label: "All releases (clear type)",
              href: `/texas/feed${keep.toString() ? `?${keep.toString()}` : ""}`,
            });
          }
          return (
            <EmptyState
              message={hasFilters ? "No records match these filters." : "No records yet."}
              clearHref={hasFilters ? "/texas/feed" : undefined}
              suggestions={suggestions}
            />
          );
        })()
      ) : (
        <div>
          {(items as FeedItem[]).map((item) => (
            <ReleaseCard key={item.id} item={item} />
          ))}
        </div>
      )}

      <Suspense>
        <Pagination total={total} perPage={perPage} basePath="/texas/feed" />
      </Suspense>
    </div>
  );
}

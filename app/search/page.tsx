import { Suspense } from "react";
import Link from "next/link";
import { getFeed, getSearchFacets } from "../lib/queries";
import { ReleaseCard } from "../components/release-card";
import { SearchBox } from "../components/search-box";
import { Pagination } from "../components/pagination";
import { EmptyState } from "../components/empty-state";
import { CONTENT_TYPE_LABEL } from "../lib/content-types";
import { STATE_NAMES } from "../lib/states";
import type { ContentType, FeedItem } from "../lib/db";

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

const ARCHIVE_START = "2025-01-01";

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

type Params = {
  q?: string;
  page?: string;
  party?: string;
  state?: string;
  type?: string;
  from?: string;
  to?: string;
  sort?: string;
};

function todayISO(): string {
  return new Date().toISOString().slice(0, 10);
}

function isValidDate(s: string | undefined): string | undefined {
  if (!s) return undefined;
  return /^\d{4}-\d{2}-\d{2}$/.test(s) ? s : undefined;
}

export default async function SearchPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | undefined>>;
}) {
  const sp = (await searchParams) as Params;
  const query = sp.q ?? "";
  const page = Number(sp.page ?? "1");
  const party = sp.party;
  const state = sp.state;
  const type =
    sp.type && VALID_TYPES.has(sp.type as ContentType)
      ? (sp.type as ContentType)
      : undefined;
  const from = isValidDate(sp.from);
  const to = isValidDate(sp.to);
  const sort: "date" | "relevance" =
    sp.sort === "relevance" ? "relevance" : "date";
  const perPage = 25;

  const hasQuery = query.trim().length > 0;
  const filters = {
    page,
    perPage,
    search: query,
    party,
    state,
    type,
    from,
    to,
    sort,
  };

  const [{ items, total }, facets] = hasQuery
    ? await Promise.all([getFeed(filters), getSearchFacets(filters)])
    : [{ items: [] as Awaited<ReturnType<typeof getFeed>>["items"], total: 0 }, null];

  const buildHref = (overrides: Record<string, string | null | undefined>) => {
    const u = new URLSearchParams();
    if (query) u.set("q", query);
    if (party) u.set("party", party);
    if (state) u.set("state", state);
    if (type) u.set("type", type);
    if (from) u.set("from", from);
    if (to) u.set("to", to);
    if (sort !== "date") u.set("sort", sort);
    for (const [k, v] of Object.entries(overrides)) {
      if (v === null || v === undefined) u.delete(k);
      else u.set(k, v);
    }
    u.delete("page");
    const s = u.toString();
    return s ? `/search?${s}` : "/search";
  };

  const activeFilters: string[] = [];
  if (party)
    activeFilters.push(
      party === "D" ? "Democrats" : party === "R" ? "Republicans" : "Independents"
    );
  if (state) activeFilters.push(STATE_NAMES[state] ?? state);
  if (type) activeFilters.push(CONTENT_TYPE_LABEL[type].toLowerCase());
  if (from || to) {
    activeFilters.push(
      `${from ?? "start"} → ${to ?? "today"}`
    );
  }

  return (
    <div className="mx-auto max-w-6xl px-4 py-12">
      <h1 className="font-[family-name:var(--font-source-serif)] text-4xl text-neutral-900 mb-3">
        Search
      </h1>
      <p className="text-sm text-neutral-600 leading-relaxed mb-6 max-w-2xl">
        Full-text search across every press release in the archive. Matches the
        title and body, with English stemming — &ldquo;vote&rdquo; catches
        &ldquo;voted&rdquo; and &ldquo;voting.&rdquo;
      </p>

      <div className="mb-8 max-w-3xl">
        <SearchBox basePath="/search" />
      </div>

      {hasQuery ? (
        <div className="grid grid-cols-1 lg:grid-cols-[220px_1fr] gap-8">
          {/* Facet sidebar */}
          <aside className="space-y-6 text-sm">
            {/* Sort */}
            <section>
              <h3 className="text-[10px] uppercase tracking-wider text-neutral-500 mb-2">
                Sort
              </h3>
              <div className="flex gap-1">
                <Link
                  href={buildHref({ sort: null })}
                  className={`px-2 py-1 text-xs border ${sort === "date" ? "border-neutral-900 bg-neutral-900 text-white" : "border-neutral-200 text-neutral-600 hover:border-neutral-400"}`}
                >
                  Newest
                </Link>
                <Link
                  href={buildHref({ sort: "relevance" })}
                  className={`px-2 py-1 text-xs border ${sort === "relevance" ? "border-neutral-900 bg-neutral-900 text-white" : "border-neutral-200 text-neutral-600 hover:border-neutral-400"}`}
                >
                  Relevance
                </Link>
              </div>
            </section>

            {/* Date range */}
            <section>
              <h3 className="text-[10px] uppercase tracking-wider text-neutral-500 mb-2">
                Date range
              </h3>
              <form action="/search" method="get" className="space-y-2">
                <input type="hidden" name="q" value={query} />
                {party && <input type="hidden" name="party" value={party} />}
                {state && <input type="hidden" name="state" value={state} />}
                {type && <input type="hidden" name="type" value={type} />}
                {sort !== "date" && (
                  <input type="hidden" name="sort" value={sort} />
                )}
                <label className="block text-[11px] text-neutral-500">
                  From
                  <input
                    type="date"
                    name="from"
                    defaultValue={from ?? ""}
                    min={ARCHIVE_START}
                    max={todayISO()}
                    className="mt-0.5 w-full border border-neutral-300 px-2 py-1 text-xs font-[family-name:var(--font-dm-mono)] tabular-nums focus:border-neutral-900 focus:outline-none"
                  />
                </label>
                <label className="block text-[11px] text-neutral-500">
                  To
                  <input
                    type="date"
                    name="to"
                    defaultValue={to ?? ""}
                    min={ARCHIVE_START}
                    max={todayISO()}
                    className="mt-0.5 w-full border border-neutral-300 px-2 py-1 text-xs font-[family-name:var(--font-dm-mono)] tabular-nums focus:border-neutral-900 focus:outline-none"
                  />
                </label>
                <div className="flex gap-1.5">
                  <button
                    type="submit"
                    className="px-2 py-1 text-xs border border-neutral-900 bg-neutral-900 text-white hover:bg-white hover:text-neutral-900 transition-colors"
                  >
                    Apply
                  </button>
                  {(from || to) && (
                    <Link
                      href={buildHref({ from: null, to: null })}
                      className="px-2 py-1 text-xs border border-neutral-200 text-neutral-500 hover:border-neutral-400"
                    >
                      Clear
                    </Link>
                  )}
                </div>
              </form>
            </section>

            {/* Party */}
            {facets && (
              <section>
                <h3 className="text-[10px] uppercase tracking-wider text-neutral-500 mb-2">
                  Party
                </h3>
                <ul className="space-y-1">
                  <FacetLink
                    href={buildHref({ party: null })}
                    label="All parties"
                    count={facets.party.D + facets.party.R + facets.party.I}
                    active={!party}
                  />
                  <FacetLink
                    href={buildHref({ party: "D" })}
                    label="Democrats"
                    count={facets.party.D}
                    active={party === "D"}
                  />
                  <FacetLink
                    href={buildHref({ party: "R" })}
                    label="Republicans"
                    count={facets.party.R}
                    active={party === "R"}
                  />
                  {facets.party.I > 0 && (
                    <FacetLink
                      href={buildHref({ party: "I" })}
                      label="Independents"
                      count={facets.party.I}
                      active={party === "I"}
                    />
                  )}
                </ul>
              </section>
            )}

            {/* Type */}
            {facets && Object.keys(facets.type).length > 0 && (
              <section>
                <h3 className="text-[10px] uppercase tracking-wider text-neutral-500 mb-2">
                  Type
                </h3>
                <ul className="space-y-1">
                  <FacetLink
                    href={buildHref({ type: null })}
                    label="All types"
                    count={Object.values(facets.type).reduce(
                      (a, b) => a + (b ?? 0),
                      0
                    )}
                    active={!type}
                  />
                  {(Object.entries(facets.type) as [ContentType, number][])
                    .sort((a, b) => b[1] - a[1])
                    .map(([t, c]) => (
                      <FacetLink
                        key={t}
                        href={buildHref({ type: t })}
                        label={CONTENT_TYPE_LABEL[t]}
                        count={c}
                        active={type === t}
                      />
                    ))}
                </ul>
              </section>
            )}

            {/* State (top 10) */}
            {facets && facets.state.length > 0 && (
              <section>
                <h3 className="text-[10px] uppercase tracking-wider text-neutral-500 mb-2">
                  Top states
                </h3>
                <ul className="space-y-1">
                  {state && (
                    <FacetLink
                      href={buildHref({ state: null })}
                      label="All states"
                      count={facets.state.reduce((a, b) => a + b.count, 0)}
                      active={false}
                    />
                  )}
                  {facets.state.slice(0, 10).map((s) => (
                    <FacetLink
                      key={s.state}
                      href={buildHref({ state: s.state })}
                      label={`${STATE_NAMES[s.state] ?? s.state}`}
                      count={s.count}
                      active={state === s.state}
                    />
                  ))}
                </ul>
              </section>
            )}
          </aside>

          {/* Results column */}
          <div className="min-w-0">
            <p className="text-xs text-neutral-500 leading-relaxed mb-2">
              <span className="font-[family-name:var(--font-dm-mono)] tabular-nums text-neutral-900 font-semibold">
                {total.toLocaleString()}
              </span>{" "}
              result{total !== 1 ? "s" : ""} for{" "}
              <span className="text-neutral-900">&ldquo;{query}&rdquo;</span>
              {activeFilters.length > 0 && (
                <> · {activeFilters.join(" · ")}</>
              )}
              {sort === "relevance" && <> · ranked by relevance</>}
            </p>

            {activeFilters.length > 0 && (
              <p className="text-xs mb-4">
                <Link
                  href={`/search?q=${encodeURIComponent(query)}`}
                  className="text-neutral-500 underline underline-offset-2 hover:text-neutral-900"
                >
                  Clear all filters
                </Link>
              </p>
            )}

            <div className="border-b border-neutral-200 mb-2" />

            {items.length === 0 ? (
              <EmptyState
                message={`No matches for \u201C${query}\u201D${activeFilters.length > 0 ? ` with these filters` : ""}.`}
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
                {items.map((item) => (
                  <ReleaseCard
                    key={item.id}
                    item={item as FeedItem}
                    snippet={item.snippet ?? null}
                  />
                ))}
              </div>
            )}

            <Suspense>
              <Pagination total={total} perPage={perPage} basePath="/search" />
            </Suspense>
          </div>
        </div>
      ) : (
        <section className="max-w-2xl">
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
          <p className="mt-6 text-xs text-neutral-500 max-w-xl leading-relaxed">
            After running a search you can filter by party, state, content type,
            or date range, and sort by relevance instead of date.
          </p>
        </section>
      )}
    </div>
  );
}

function FacetLink({
  href,
  label,
  count,
  active,
}: {
  href: string;
  label: string;
  count: number;
  active: boolean;
}) {
  return (
    <li>
      <Link
        href={href}
        aria-current={active ? "true" : undefined}
        className={`flex items-center justify-between gap-2 rounded px-1.5 py-0.5 text-xs transition-colors ${
          active
            ? "bg-neutral-900 text-white"
            : "text-neutral-700 hover:bg-neutral-100"
        }`}
      >
        <span className="truncate">{label}</span>
        <span
          className={`font-[family-name:var(--font-dm-mono)] tabular-nums ${active ? "text-neutral-200" : "text-neutral-400"}`}
        >
          {count.toLocaleString()}
        </span>
      </Link>
    </li>
  );
}

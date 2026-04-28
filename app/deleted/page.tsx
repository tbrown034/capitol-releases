import { Suspense } from "react";
import Link from "next/link";
import { getDeletedReleases } from "../lib/queries";
import { Pagination } from "../components/pagination";
import { TypeBadge } from "../components/type-badge";
import { EmptyState } from "../components/empty-state";
import { formatReleaseDate, formatTimestamp } from "../lib/dates";
import { STATE_NAMES } from "../lib/states";
import { normalizeTitle } from "../lib/titles";

export const metadata = {
  title: "Confirmed deletions — Capitol Releases",
  description:
    "Press releases confirmed removed from senate.gov, preserved here.",
};

export const revalidate = 600;

export default async function DeletedPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | undefined>>;
}) {
  const params = await searchParams;
  const page = Number(params.page ?? "1");
  const perPage = 50;
  const { items, total } = await getDeletedReleases(page, perPage);

  return (
    <div className="mx-auto max-w-4xl px-4 py-12">
      <h1 className="font-[family-name:var(--font-source-serif)] text-4xl text-neutral-900 mb-3">
        Confirmed deletions
      </h1>
      <p className="text-sm text-neutral-600 leading-relaxed mb-2 max-w-2xl">
        Press releases that have returned 404 or 410 on multiple consecutive
        re-checks from the senator&apos;s official site. We preserve the
        captured body text on Capitol Releases.
      </p>
      <p className="text-xs text-neutral-500 leading-relaxed mb-2 max-w-2xl">
        <span className="font-[family-name:var(--font-dm-mono)] tabular-nums text-neutral-900 font-semibold">
          {total.toLocaleString()}
        </span>{" "}
        record{total !== 1 ? "s" : ""} confirmed deleted.
      </p>
      <p className="text-xs text-neutral-400 leading-relaxed mb-8 max-w-2xl border-l-2 border-neutral-200 pl-3">
        Note: the deletion detector requires three independent 404/410 hits
        spaced apart before tombstoning a record. Senate sites sit behind
        Akamai and occasionally return transient 404s that resolve within
        seconds; the multi-confirmation gate filters those out. A 2026-04-19
        run created 1,286 unconfirmed tombstones; on re-verification with a
        browser User-Agent, 1,283 returned 200 and were restored.
      </p>

      <div className="border-b border-neutral-200 mb-2" />

      {items.length === 0 ? (
        <EmptyState
          message="No deleted releases on record."
          suggestions={[{ label: "Browse the feed", href: "/feed" }]}
        />
      ) : (
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-neutral-800 text-xs uppercase tracking-wider text-neutral-500">
              <th className="pb-2 pr-4 text-left font-medium">Removed</th>
              <th className="pb-2 pr-4 text-left font-medium">Senator</th>
              <th className="pb-2 text-left font-medium">Title</th>
            </tr>
          </thead>
          <tbody>
            {items.map((pr, i) => (
              <tr
                key={pr.id}
                className={`border-b border-neutral-100 align-top ${i % 2 === 1 ? "bg-neutral-50/60" : ""}`}
              >
                <td
                  className="py-2.5 pr-4 font-[family-name:var(--font-dm-mono)] tabular-nums text-neutral-500 whitespace-nowrap"
                  title={pr.deleted_at ? formatTimestamp(pr.deleted_at) : ""}
                >
                  {pr.deleted_at ? formatReleaseDate(pr.deleted_at) : "—"}
                </td>
                <td className="py-2.5 pr-4 whitespace-nowrap">
                  <Link
                    href={`/senators/${pr.senator_id}`}
                    className="text-neutral-700 hover:underline"
                  >
                    {pr.senator_name}
                  </Link>
                  <span className="ml-1.5 text-xs text-neutral-400">
                    ({pr.party}-{pr.state})
                  </span>
                  <span className="sr-only">
                    , {STATE_NAMES[pr.state] ?? pr.state}
                  </span>
                </td>
                <td className="py-2.5 text-neutral-900">
                  <Link
                    href={`/releases/${pr.id}`}
                    className="hover:underline"
                  >
                    {normalizeTitle(pr.title)}
                  </Link>
                  {pr.content_type !== "press_release" && (
                    <span className="ml-2 inline-block align-middle">
                      <TypeBadge type={pr.content_type} size="xs" />
                    </span>
                  )}
                  {pr.published_at && (
                    <span className="ml-2 text-[11px] text-neutral-400 font-[family-name:var(--font-dm-mono)] tabular-nums">
                      orig. {formatReleaseDate(pr.published_at)}
                    </span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <Suspense>
        <Pagination total={total} perPage={perPage} basePath="/deleted" />
      </Suspense>
    </div>
  );
}

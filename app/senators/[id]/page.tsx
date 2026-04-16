import { notFound } from "next/navigation";
import Link from "next/link";
import { getSenator, getSenatorReleases } from "../../lib/queries";
import { PartyBadge } from "../../components/party-badge";
import type { PressRelease } from "../../lib/db";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const senator = await getSenator(id);
  if (!senator) return { title: "Not Found" };
  return {
    title: `${senator.full_name} -- Capitol Releases`,
    description: `Press releases from ${senator.full_name} (${senator.party}-${senator.state}).`,
  };
}

export default async function SenatorPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<Record<string, string | undefined>>;
}) {
  const { id } = await params;
  const sp = await searchParams;
  const page = Number(sp.page ?? "1");
  const perPage = 25;

  const senator = await getSenator(id);
  if (!senator) notFound();

  const { items, total } = await getSenatorReleases(id, page, perPage);
  const totalPages = Math.ceil(total / perPage);

  return (
    <div className="mx-auto max-w-3xl px-4 py-8">
      <Link
        href="/senators"
        className="text-sm text-gray-500 hover:text-gray-800"
      >
        All Senators
      </Link>

      <div className="mt-4 flex items-start gap-4">
        <div>
          <h1 className="text-2xl font-bold">{senator.full_name}</h1>
          <div className="mt-1 flex items-center gap-3">
            <PartyBadge party={senator.party} size="lg" />
            <span className="text-gray-600">{senator.state}</span>
            <a
              href={senator.official_url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-sm text-blue-600 hover:underline"
            >
              Official site
            </a>
          </div>
        </div>
      </div>

      <div className="mt-2 text-sm text-gray-500">
        {total} press release{total !== 1 ? "s" : ""} archived
      </div>

      {/* Releases */}
      <div className="mt-6 space-y-0">
        {items.length === 0 ? (
          <p className="py-12 text-center text-gray-400">
            No press releases scraped yet for this senator.
          </p>
        ) : (
          items.map((pr: PressRelease) => (
            <article
              key={pr.id}
              className="border-b border-gray-100 py-4 last:border-0"
            >
              <div className="flex items-start justify-between gap-4">
                <div className="min-w-0 flex-1">
                  <h3 className="text-sm font-medium text-gray-900">
                    <a
                      href={pr.source_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="hover:text-blue-600"
                    >
                      {pr.title}
                    </a>
                  </h3>
                  {pr.body_text && (
                    <p className="mt-1 text-xs text-gray-500 line-clamp-2">
                      {pr.body_text.slice(0, 250)}
                    </p>
                  )}
                </div>
                <time className="shrink-0 text-xs text-gray-400 tabular-nums">
                  {pr.published_at
                    ? new Date(pr.published_at).toLocaleDateString("en-US", {
                        month: "short",
                        day: "numeric",
                        year: "numeric",
                      })
                    : "--"}
                </time>
              </div>
            </article>
          ))
        )}
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <nav className="mt-6 flex items-center justify-between border-t border-gray-200 pt-4">
          <p className="text-sm text-gray-600">
            Page {page} of {totalPages}
          </p>
          <div className="flex gap-2">
            {page > 1 && (
              <Link
                href={`/senators/${id}?page=${page - 1}`}
                className="rounded border border-gray-300 px-3 py-1.5 text-sm hover:bg-gray-50"
              >
                Previous
              </Link>
            )}
            {page < totalPages && (
              <Link
                href={`/senators/${id}?page=${page + 1}`}
                className="rounded border border-gray-300 px-3 py-1.5 text-sm hover:bg-gray-50"
              >
                Next
              </Link>
            )}
          </div>
        </nav>
      )}
    </div>
  );
}

import { notFound } from "next/navigation";
import Link from "next/link";
import Image from "next/image";
import { getSenator, getSenatorReleases } from "../../lib/queries";
import { sql } from "../../lib/db";
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

  // Get bioguide ID for photo
  const bioRows = await sql`SELECT bioguide_id, status, left_date, left_reason FROM senators WHERE id = ${id}`;
  const bio = bioRows[0] as { bioguide_id: string | null; status: string | null; left_date: string | null; left_reason: string | null } | undefined;

  const partyLabel = senator.party === "D" ? "Democrat" : senator.party === "R" ? "Republican" : "Independent";
  const partyColor = senator.party === "D" ? "text-blue-600" : senator.party === "R" ? "text-red-600" : "text-amber-600";

  return (
    <div className="mx-auto max-w-5xl px-4 py-12">
      <Link
        href="/senators"
        className="text-sm text-neutral-400 hover:text-neutral-600 transition-colors"
      >
        ← Back to directory
      </Link>

      {/* Profile header */}
      <div className="mt-6 flex items-start gap-4">
        {bio?.bioguide_id ? (
          <Image
            src={`/senators/${bio.bioguide_id}.jpg`}
            alt={senator.full_name}
            width={72}
            height={72}
            className="h-[72px] w-[72px] object-cover object-top shrink-0"
            unoptimized
          />
        ) : (
          <div className="h-[72px] w-[72px] bg-neutral-200 flex items-center justify-center text-neutral-400 text-lg shrink-0">
            {senator.full_name.split(" ").map(n => n[0]).join("").slice(0, 2)}
          </div>
        )}
        <div>
          <h1 className="font-[family-name:var(--font-source-serif)] text-3xl text-neutral-900">
            {senator.full_name}
          </h1>
          <div className="mt-1 flex items-center gap-3 text-sm">
            <span className={partyColor}>{partyLabel}</span>
            <span className="text-neutral-400">{senator.state}</span>
            {bio?.status === "former" && (
              <span className="text-xs text-amber-700 bg-amber-50 border border-amber-200 px-2 py-0.5">
                Former
              </span>
            )}
            <a
              href={senator.official_url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-neutral-400 hover:text-neutral-600 transition-colors underline"
            >
              Official site
            </a>
          </div>
          {bio?.left_reason && (
            <p className="mt-1 text-xs text-neutral-400">
              Left: {bio.left_reason} ({bio.left_date ? new Date(bio.left_date).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" }) : ""})
            </p>
          )}
        </div>
      </div>

      {/* Bio summary */}
      <p className="text-sm text-neutral-600 leading-relaxed border-l-2 border-neutral-200 pl-4 mt-6 mb-8">
        {total} press release{total !== 1 ? "s" : ""} archived from {senator.full_name}&apos;s
        official website. Data collected from{" "}
        <span className="font-[family-name:var(--font-dm-mono)] text-neutral-500">
          {senator.press_release_url?.replace(/https?:\/\//, "").split("/")[0] ?? "senate.gov"}
        </span>.
      </p>

      {/* Stat row */}
      <div className="flex flex-wrap gap-x-8 gap-y-2 text-sm text-neutral-500 border-b border-neutral-200 pb-6 mb-8">
        <div>
          <span className="text-lg font-semibold text-neutral-900 font-[family-name:var(--font-dm-mono)] tabular-nums mr-1">
            {total}
          </span>
          releases
        </div>
      </div>

      {/* Release table */}
      {items.length === 0 ? (
        <p className="py-12 text-center text-sm text-neutral-400">
          No press releases archived yet.
        </p>
      ) : (
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-neutral-800 text-xs uppercase tracking-wider text-neutral-500">
              <th className="pb-2 pr-4 text-left font-medium">Date</th>
              <th className="pb-2 text-left font-medium">Title</th>
            </tr>
          </thead>
          <tbody>
            {items.map((pr: PressRelease, i: number) => (
              <tr
                key={pr.id}
                className={`border-b border-neutral-100 ${i % 2 === 1 ? "bg-neutral-50/60" : ""}`}
              >
                <td className="py-2.5 pr-4 font-[family-name:var(--font-dm-mono)] tabular-nums text-neutral-500 whitespace-nowrap align-top">
                  {pr.published_at
                    ? new Date(pr.published_at).toLocaleDateString("en-US", {
                        month: "short",
                        day: "numeric",
                        year: "numeric",
                      })
                    : "---"}
                </td>
                <td className="py-2.5 text-neutral-900">
                  <a
                    href={pr.source_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="hover:underline"
                  >
                    {pr.title}
                  </a>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {/* Pagination */}
      {totalPages > 1 && (
        <nav className="mt-6 flex items-center justify-between border-t border-neutral-200 pt-4">
          <p className="text-xs text-neutral-400">
            Page {page} of {totalPages}
          </p>
          <div className="flex gap-2">
            {page > 1 && (
              <Link
                href={`/senators/${id}?page=${page - 1}`}
                className="text-sm text-neutral-500 hover:text-neutral-900 transition-colors"
              >
                ← Previous
              </Link>
            )}
            {page < totalPages && (
              <Link
                href={`/senators/${id}?page=${page + 1}`}
                className="text-sm text-neutral-500 hover:text-neutral-900 transition-colors"
              >
                Next →
              </Link>
            )}
          </div>
        </nav>
      )}
    </div>
  );
}

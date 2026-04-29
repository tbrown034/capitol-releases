import { Suspense } from "react";
import { notFound } from "next/navigation";
import Link from "next/link";
import Image from "next/image";
import { sql } from "../../../lib/db";
import type { PressRelease } from "../../../lib/db";
import { Pagination } from "../../../components/pagination";
import { TypeBadge } from "../../../components/type-badge";
import { EmptyState } from "../../../components/empty-state";
import { formatLongMonthYear, formatReleaseDate } from "../../../lib/dates";

export const revalidate = 600;

type TxSenator = {
  id: string;
  full_name: string;
  party: "D" | "R" | "I";
  state: string;
  official_url: string;
  press_release_url: string | null;
  scrape_config: { district?: number; expect_empty?: boolean; notes?: string | null } | null;
  status: string;
};

export async function generateMetadata({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const rows = (await sql`
    SELECT full_name, party FROM senators WHERE id = ${id} AND chamber = 'tx_senate'
  `) as { full_name: string; party: string }[];
  if (!rows[0]) return { title: "Not found — Capitol Releases" };
  return {
    title: `${rows[0].full_name} — Texas Senate — Capitol Releases`,
    description: `Press releases from Texas State Senator ${rows[0].full_name} (${rows[0].party}-TX).`,
  };
}

const PER_PAGE = 25;

export default async function TxSenatorPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ page?: string }>;
}) {
  const { id } = await params;
  const sp = await searchParams;
  const page = Math.max(1, Number(sp.page ?? "1") || 1);
  const offset = (page - 1) * PER_PAGE;

  const senatorRows = (await sql`
    SELECT id, full_name, party, state, official_url, press_release_url,
           scrape_config, status
    FROM senators
    WHERE id = ${id} AND chamber = 'tx_senate'
  `) as TxSenator[];
  const senator = senatorRows[0];
  if (!senator) notFound();

  const district = senator.scrape_config?.district ?? null;
  const expectEmpty = Boolean(senator.scrape_config?.expect_empty);
  const districtPad = district ? String(district).padStart(2, "0") : "00";

  const [releaseStats, items] = await Promise.all([
    sql`
      SELECT count(*)::int AS total,
             min(published_at) AS earliest,
             max(published_at) AS latest
      FROM press_releases
      WHERE senator_id = ${id}
        AND deleted_at IS NULL
        AND content_type != 'photo_release'
    `,
    sql`
      SELECT * FROM press_releases
      WHERE senator_id = ${id}
        AND deleted_at IS NULL
        AND content_type != 'photo_release'
      ORDER BY LEAST(published_at, scraped_at) DESC NULLS LAST
      LIMIT ${PER_PAGE} OFFSET ${offset}
    `,
  ]);
  const releases = items as unknown as PressRelease[];

  const stats = releaseStats[0] as { total: number; earliest: string | null; latest: string | null };
  const total = Number(stats.total);
  const earliest = stats.earliest;
  const sinceLabel = earliest ? formatLongMonthYear(earliest) : null;

  const partyLabel =
    senator.party === "D" ? "Democrat" : senator.party === "R" ? "Republican" : "Independent";
  const partyColor =
    senator.party === "D"
      ? "text-blue-600"
      : senator.party === "R"
      ? "text-red-600"
      : "text-amber-600";

  return (
    <div className="mx-auto max-w-5xl px-4 py-12">
      <Link
        href="/states/tx"
        className="text-sm text-neutral-400 hover:text-neutral-600 transition-colors"
      >
        ← Back to Texas Senate
      </Link>

      <div className="mt-6 flex items-start gap-4">
        <Image
          src={`/state-senators/tx/d${districtPad}.jpg`}
          alt={senator.full_name}
          width={72}
          height={72}
          className="h-[72px] w-[72px] object-cover object-top shrink-0"
          unoptimized
        />
        <div>
          <h1 className="font-[family-name:var(--font-source-serif)] text-3xl text-neutral-900">
            {senator.full_name}
          </h1>
          <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-neutral-500">
            <span className={partyColor}>{partyLabel}</span>
            <span className="text-neutral-300">·</span>
            <span>
              Texas Senate, District{" "}
              <span className="font-[family-name:var(--font-dm-mono)] tabular-nums text-neutral-700">
                {district ?? "?"}
              </span>
            </span>
            <span className="text-neutral-300">·</span>
            <a
              href={senator.official_url}
              target="_blank"
              rel="noopener noreferrer"
              className="font-[family-name:var(--font-dm-mono)] text-neutral-500 hover:text-neutral-900 transition-colors underline underline-offset-2"
            >
              {senator.official_url
                .replace(/^https?:\/\//, "")
                .replace(/\/$/, "")}
              <span aria-hidden="true"> ↗</span>
            </a>
          </div>
        </div>
      </div>

      <p className="text-sm text-neutral-600 leading-relaxed border-l-2 border-neutral-200 pl-4 mt-6 mb-6">
        <span className="font-[family-name:var(--font-dm-mono)] tabular-nums text-neutral-900 font-semibold">
          {total.toLocaleString()}
        </span>{" "}
        record{total !== 1 ? "s" : ""} archived
        {sinceLabel && <> since {sinceLabel}</>}. Scraped daily from
        senate.texas.gov.
      </p>

      <div className="mb-8 flex flex-wrap items-center gap-x-4 gap-y-2 text-xs">
        <span className="text-neutral-400 uppercase tracking-wider">Sources</span>
        <a
          href={senator.official_url}
          target="_blank"
          rel="noopener noreferrer"
          className="text-neutral-700 hover:text-neutral-900 hover:underline"
        >
          Member page<span aria-hidden> ↗</span>
        </a>
        {senator.press_release_url && (
          <a
            href={senator.press_release_url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-neutral-700 hover:text-neutral-900 hover:underline"
          >
            Pressroom<span aria-hidden> ↗</span>
          </a>
        )}
      </div>

      {releases.length === 0 ? (
        expectEmpty ? (
          <EmptyState
            message={`${senator.full_name} has not published a press release on senate.texas.gov yet. We check daily — releases will appear here as soon as the office begins publishing.`}
            suggestions={[
              { label: "Browse Texas Senate directory", href: "/states/tx" },
            ]}
          />
        ) : total === 0 ? (
          <EmptyState
            message={`No 2025-or-later releases archived for ${senator.full_name}. The pressroom may carry older content; we collect from January 1, 2025 forward.`}
            suggestions={[
              { label: "Browse Texas Senate directory", href: "/states/tx" },
            ]}
          />
        ) : (
          <EmptyState message="No releases on this page." />
        )
      ) : (
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-neutral-800 text-xs uppercase tracking-wider text-neutral-500">
              <th className="pb-2 pr-4 text-left font-medium">Date</th>
              <th className="pb-2 text-left font-medium">Title</th>
            </tr>
          </thead>
          <tbody>
            {releases.map((pr, i) => (
              <tr
                key={pr.id}
                className={`border-b border-neutral-100 ${
                  i % 2 === 1 ? "bg-neutral-50/60" : ""
                }`}
              >
                <td className="py-2.5 pr-4 font-[family-name:var(--font-dm-mono)] tabular-nums text-neutral-500 whitespace-nowrap align-top">
                  {pr.published_at ? formatReleaseDate(pr.published_at) : "---"}
                </td>
                <td className="py-2.5 text-neutral-900">
                  <Link
                    href={`/releases/${pr.id}`}
                    className="hover:underline"
                  >
                    {pr.title}
                  </Link>
                  {pr.content_type && pr.content_type !== "press_release" && (
                    <span className="ml-2 inline-block align-middle">
                      <TypeBadge type={pr.content_type} size="xs" />
                    </span>
                  )}
                  <a
                    href={pr.source_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="ml-2 text-[10px] text-neutral-400 hover:text-neutral-700"
                    title="Open original on senate.texas.gov"
                  >
                    source <span aria-hidden>↗</span>
                  </a>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <Suspense>
        <Pagination
          total={total}
          perPage={PER_PAGE}
          basePath={`/states/tx/${id}`}
          currentPage={page}
        />
      </Suspense>
    </div>
  );
}

import { Suspense } from "react";
import { notFound } from "next/navigation";
import Link from "next/link";
import Image from "next/image";
import { sql } from "../../../lib/db";
import type { PressRelease } from "../../../lib/db";
import { Pagination } from "../../../components/pagination";
import { TypeBadge } from "../../../components/type-badge";
import { TxSenatorSparkline } from "../../../components/tx-senator-sparkline";
import {
  formatLongMonthYear,
  formatReleaseDate,
  formatShortDate,
} from "../../../lib/dates";

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
    description: `Press releases from Texas State Senator ${rows[0].full_name} (${rows[0].party}-TX) on senate.texas.gov, archived since January 2025.`,
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

  const [releaseStats, items, weekly, chamberCount] = await Promise.all([
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
    sql`
      SELECT to_char(date_trunc('week', published_at), 'YYYY-MM-DD') AS week,
             count(*)::int AS count
      FROM press_releases
      WHERE senator_id = ${id}
        AND deleted_at IS NULL
        AND content_type != 'photo_release'
        AND published_at IS NOT NULL
        AND published_at >= '2025-01-01'
      GROUP BY week
      ORDER BY week
    `,
    sql`
      SELECT count(*)::int AS chamber_total
      FROM press_releases pr
      JOIN senators s ON s.id = pr.senator_id
      WHERE s.chamber = 'tx_senate'
        AND pr.deleted_at IS NULL
        AND pr.content_type != 'photo_release'
    `,
  ]);
  const releases = items as unknown as PressRelease[];

  const stats = releaseStats[0] as { total: number; earliest: string | null; latest: string | null };
  const total = Number(stats.total);
  const earliest = stats.earliest;
  const latest = stats.latest;
  const sinceLabel = earliest ? formatLongMonthYear(earliest) : null;
  const chamberTotal = Number((chamberCount[0] as { chamber_total: number }).chamber_total);
  const sharePct = chamberTotal > 0 ? Math.round((total / chamberTotal) * 100) : 0;

  const partyLabel =
    senator.party === "D" ? "Democrat" : senator.party === "R" ? "Republican" : "Independent";
  const partyColor =
    senator.party === "D"
      ? "text-blue-600"
      : senator.party === "R"
        ? "text-red-600"
        : "text-amber-600";

  const weeklyData = weekly as { week: string; count: number }[];

  return (
    <div className="mx-auto max-w-3xl px-4 py-12">
      <Link
        href="/states/tx"
        className="text-sm text-neutral-500 hover:text-neutral-900 transition-colors"
      >
        ← Back to Texas Senate
      </Link>

      {/* Identity card */}
      <div className="mt-6 flex items-start gap-4">
        <Image
          src={`/state-senators/tx/d${districtPad}.jpg`}
          alt={senator.full_name}
          width={80}
          height={80}
          className="h-20 w-20 object-cover object-top shrink-0 rounded"
          priority
          unoptimized
        />
        <div className="min-w-0">
          <h1 className="font-[family-name:var(--font-source-serif)] text-3xl text-neutral-900 leading-tight">
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
          </div>
        </div>
      </div>

      {/* Headline stat band */}
      {total > 0 ? (
        <div className="mt-6 grid grid-cols-2 sm:grid-cols-4 gap-4">
          <Stat label="Records" value={total.toLocaleString()} />
          <Stat
            label="Share of TX"
            value={`${sharePct}%`}
            sub={`of ${chamberTotal.toLocaleString()} total`}
          />
          <Stat
            label="Earliest"
            value={earliest ? formatShortDate(earliest) : "—"}
          />
          <Stat
            label="Latest"
            value={latest ? formatShortDate(latest) : "—"}
          />
        </div>
      ) : (
        <div className="mt-6 grid grid-cols-2 sm:grid-cols-4 gap-4">
          <Stat label="Records" value="0" sub="since Jan 2025" />
          <Stat label="Share of TX" value="—" />
          <Stat label="Earliest" value="—" />
          <Stat label="Latest" value="—" />
        </div>
      )}

      {/* Sparkline — only if there's data */}
      {weeklyData.length > 0 && (
        <section className="mt-8">
          <p className="text-[11px] uppercase tracking-wider text-neutral-500 mb-2">
            Weekly volume since Jan 2025
          </p>
          <TxSenatorSparkline data={weeklyData} />
        </section>
      )}

      {/* Sources */}
      <div className="mt-8 mb-8 flex flex-wrap items-center gap-x-4 gap-y-2 text-xs">
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

      {/* Releases or empty-state */}
      {releases.length === 0 ? (
        <SilentEmptyState
          senator={senator}
          expectEmpty={expectEmpty}
          total={total}
          chamberTotal={chamberTotal}
          sinceLabel={sinceLabel}
        />
      ) : (
        <>
          <p className="text-xs text-neutral-500 mb-3 max-w-2xl leading-relaxed">
            <span className="font-[family-name:var(--font-dm-mono)] tabular-nums text-neutral-900 font-semibold">
              {total.toLocaleString()}
            </span>{" "}
            record{total !== 1 ? "s" : ""} archived
            {sinceLabel && <> since {sinceLabel}</>}. Re-checked daily on{" "}
            <span translate="no">senate.texas.gov</span>.
          </p>
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-neutral-800 text-xs uppercase tracking-wider text-neutral-500">
                <th scope="col" className="pb-2 pr-4 text-left font-medium">
                  Date
                </th>
                <th scope="col" className="pb-2 text-left font-medium">
                  Title
                </th>
              </tr>
            </thead>
            <tbody>
              {releases.map((pr, i) => (
                <tr
                  key={pr.id}
                  className={`border-b border-neutral-100 transition-colors hover:bg-neutral-100/70 ${
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
          <Suspense>
            <Pagination
              total={total}
              perPage={PER_PAGE}
              basePath={`/states/tx/${id}`}
              currentPage={page}
            />
          </Suspense>
        </>
      )}
    </div>
  );
}

function SilentEmptyState({
  senator,
  expectEmpty,
  total,
  chamberTotal,
  sinceLabel,
}: {
  senator: TxSenator;
  expectEmpty: boolean;
  total: number;
  chamberTotal: number;
  sinceLabel: string | null;
}) {
  // Three flavors:
  //   1. expectEmpty (e.g. Rehmet, recently sworn-in) — soft framing
  //   2. zero records, page 1 — the silent caucus framing
  //   3. zero this page only (paginated past the end) — handled by parent
  if (expectEmpty) {
    return (
      <div className="rounded-md border border-amber-200 bg-amber-50 px-5 py-5 max-w-2xl">
        <p className="text-[11px] uppercase tracking-wider text-amber-900 mb-1.5 font-semibold">
          Recently seated
        </p>
        <p className="text-sm text-amber-900 leading-relaxed mb-2">
          {senator.full_name} was sworn in recently and has not begun
          publishing press releases on{" "}
          <span translate="no">senate.texas.gov</span>. We re-check daily;
          records will appear here as soon as the office begins publishing.
        </p>
        {senator.press_release_url && (
          <a
            href={senator.press_release_url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs text-amber-900 underline hover:text-amber-700"
          >
            Verify the empty pressroom on senate.texas.gov ↗
          </a>
        )}
      </div>
    );
  }
  if (total === 0) {
    return (
      <div className="rounded-md border border-neutral-200 bg-neutral-50 px-5 py-5 max-w-2xl">
        <p className="text-[11px] uppercase tracking-wider text-neutral-500 mb-1.5 font-semibold">
          The silent caucus
        </p>
        <p className="text-sm text-neutral-700 leading-relaxed mb-2">
          {senator.full_name}&apos;s pressroom on{" "}
          <span translate="no">senate.texas.gov</span>
          {" "}is live but empty. We&apos;ve re-checked daily
          {sinceLabel ? ` since ${sinceLabel}` : ""}{" "}
          and {chamberTotal > 0
            ? `archived ${chamberTotal.toLocaleString()} releases from other Texas senators in that window`
            : "found no records yet"}{" "}
          &mdash; this office has chosen not to publish.
        </p>
        <p className="text-xs text-neutral-500 leading-relaxed mb-3">
          State legislators are not required to publish online; many use
          social media, district office mailings, or local press exclusively.
        </p>
        {senator.press_release_url && (
          <a
            href={senator.press_release_url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs text-neutral-700 underline hover:text-neutral-900"
          >
            Verify the empty pressroom on senate.texas.gov ↗
          </a>
        )}
      </div>
    );
  }
  return (
    <p className="text-sm text-neutral-500">
      No releases on this page.{" "}
      <Link href={`/states/tx/${senator.id}`} className="underline hover:text-neutral-900">
        Back to first page
      </Link>
      .
    </p>
  );
}

function Stat({
  label,
  value,
  sub,
}: {
  label: string;
  value: string;
  sub?: string;
}) {
  return (
    <div>
      <p className="text-[10px] uppercase tracking-wider text-neutral-400 mb-1">
        {label}
      </p>
      <p className="text-xl font-[family-name:var(--font-dm-mono)] tabular-nums text-neutral-900">
        {value}
      </p>
      {sub && (
        <p className="text-[11px] text-neutral-500 mt-0.5 leading-tight">
          {sub}
        </p>
      )}
    </div>
  );
}

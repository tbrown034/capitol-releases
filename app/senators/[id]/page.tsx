import { Suspense } from "react";
import { notFound } from "next/navigation";
import Link from "next/link";
import Image from "next/image";
import {
  getSenator,
  getSenatorReleases,
  getSenatorTypeBreakdown,
  CONTENT_TYPE_ORDER,
  CONTENT_TYPE_LABEL,
} from "../../lib/queries";
import {
  getSenatorDailyActivity,
  getSenatorTopicTrends,
  getSenatorSignatureTopics,
} from "../../lib/analytics";
import { sql } from "../../lib/db";
import type { PressRelease, ContentType } from "../../lib/db";
import { SenatorHeatmap } from "../../components/senator-heatmap";
import { Pagination } from "../../components/pagination";
import { TypeBadge } from "../../components/type-badge";
import { STATE_NAMES } from "../../lib/states";

const VALID_TYPES = new Set<ContentType>([
  "press_release",
  "statement",
  "op_ed",
  "letter",
  "floor_statement",
  "presidential_action",
  "other",
]);

export async function generateMetadata({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const senator = await getSenator(id);
  if (!senator) return { title: "Not Found" };
  return {
    title: `${senator.full_name} — Capitol Releases`,
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
  const activeType =
    sp.type && VALID_TYPES.has(sp.type as ContentType)
      ? (sp.type as ContentType)
      : undefined;
  const perPage = 25;

  const senator = await getSenator(id);
  if (!senator) notFound();

  // Derive name tokens to exclude from signature topics (senator's own name
  // shouldn't count as a distinctive word).
  const nameTokens = senator.full_name
    .toLowerCase()
    .split(/[^a-z]+/)
    .filter((t) => t.length > 2);

  const [
    { items, total },
    { breakdown, earliest },
    dailyActivity,
    topicTrends,
    signatureTopics,
    bioRows,
  ] = await Promise.all([
    getSenatorReleases(id, page, perPage, activeType),
    getSenatorTypeBreakdown(id),
    getSenatorDailyActivity(id),
    getSenatorTopicTrends(id, nameTokens, 12),
    getSenatorSignatureTopics(id, nameTokens, 12),
    sql`SELECT bioguide_id, status, left_date, left_reason FROM senators WHERE id = ${id}`,
  ]);
  const grandTotal = Object.values(breakdown).reduce(
    (sum: number, n) => sum + (n ?? 0),
    0
  );
  const activeTypes = CONTENT_TYPE_ORDER.filter((t) => (breakdown[t] ?? 0) > 0);
  const sinceLabel = earliest
    ? new Date(earliest).toLocaleDateString("en-US", {
        month: "long",
        year: "numeric",
      })
    : null;
  const buildTypeHref = (t?: ContentType) => {
    const params = new URLSearchParams();
    if (t) params.set("type", t);
    const q = params.toString();
    return q ? `/senators/${id}?${q}` : `/senators/${id}`;
  };
  const bio = bioRows[0] as { bioguide_id: string | null; status: string | null; left_date: string | null; left_reason: string | null } | undefined;

  const daily = dailyActivity as { day: string; count: number }[];
  const topics = topicTrends as {
    word: string;
    recent_count: number;
    prior_count: number;
  }[];
  const signature = signatureTopics as {
    word: string;
    self_count: number;
    rest_count: number;
    log_odds: string;
  }[];

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
        {bio?.bioguide_id || senator.chamber === "executive" ? (
          <Image
            src={`/senators/${bio?.bioguide_id ?? senator.id}.jpg`}
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
          <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-neutral-500">
            <span className={partyColor}>{partyLabel}</span>
            <span className="text-neutral-300">·</span>
            <span>{STATE_NAMES[senator.state] ?? senator.state}</span>
            <span className="text-neutral-300">·</span>
            <a
              href={senator.official_url}
              target="_blank"
              rel="noopener noreferrer"
              className="font-[family-name:var(--font-dm-mono)] text-neutral-500 hover:text-neutral-900 transition-colors underline underline-offset-2"
            >
              {senator.official_url.replace(/^https?:\/\//, "").replace(/\/$/, "")}
              <span aria-hidden="true"> ↗</span>
            </a>
            {bio?.status === "former" && (
              <span className="text-xs text-amber-700 bg-amber-50 border border-amber-200 px-2 py-0.5">
                Former
              </span>
            )}
          </div>
          {bio?.left_reason && (
            <p className="mt-1 text-xs text-neutral-400">
              Left: {bio.left_reason} ({bio.left_date ? new Date(bio.left_date).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" }) : ""})
            </p>
          )}
        </div>
      </div>

      {/* Bio summary */}
      <p className="text-sm text-neutral-600 leading-relaxed border-l-2 border-neutral-200 pl-4 mt-6 mb-4">
        <span className="font-[family-name:var(--font-dm-mono)] tabular-nums text-neutral-900 font-semibold">
          {grandTotal.toLocaleString()}
        </span>{" "}
        record{grandTotal !== 1 ? "s" : ""} archived
        {sinceLabel && <> since {sinceLabel}</>}
        {activeTypes.length > 1 && (
          <>
            , including{" "}
            {activeTypes.map((t, i) => {
              const n = breakdown[t] ?? 0;
              const label =
                t === "press_release"
                  ? n === 1 ? "press release" : "press releases"
                  : t === "op_ed"
                    ? n === 1 ? "op-ed" : "op-eds"
                    : t === "letter"
                      ? n === 1 ? "letter" : "letters"
                      : t === "statement"
                        ? n === 1 ? "statement" : "statements"
                        : t === "floor_statement"
                          ? n === 1 ? "floor statement" : "floor statements"
                          : t === "photo_release"
                            ? n === 1 ? "photo release" : "photo releases"
                            : t === "presidential_action"
                              ? n === 1 ? "presidential action" : "presidential actions"
                              : "other";
              return (
                <span key={t}>
                  {i === 0 ? "" : i === activeTypes.length - 1 ? " and " : ", "}
                  <span className="font-[family-name:var(--font-dm-mono)] tabular-nums text-neutral-900">
                    {n.toLocaleString()}
                  </span>{" "}
                  {label}
                </span>
              );
            })}
          </>
        )}
        . Scraped daily.
      </p>

      {/* Content-type tabs */}
      {activeTypes.length > 1 && (
        <div className="mb-8 flex flex-wrap items-center gap-1.5 text-xs">
          <Link
            href={buildTypeHref(undefined)}
            className={`rounded-full border px-2.5 py-1 transition-colors ${
              !activeType
                ? "border-neutral-900 bg-neutral-900 text-white"
                : "border-neutral-200 text-neutral-500 hover:border-neutral-400 hover:text-neutral-900"
            }`}
          >
            All <span className="tabular-nums">({grandTotal.toLocaleString()})</span>
          </Link>
          {activeTypes.map((t) => (
            <Link
              key={t}
              href={buildTypeHref(t)}
              className={`rounded-full border px-2.5 py-1 transition-colors ${
                activeType === t
                  ? "border-neutral-900 bg-neutral-900 text-white"
                  : "border-neutral-200 text-neutral-500 hover:border-neutral-400 hover:text-neutral-900"
              }`}
            >
              {CONTENT_TYPE_LABEL[t]}{" "}
              <span className="tabular-nums">({(breakdown[t] ?? 0).toLocaleString()})</span>
            </Link>
          ))}
        </div>
      )}

      {/* Publishing activity — calendar heatmap */}
      {daily.length > 0 && (
        <section className="mb-10">
          <h2 className="text-xs uppercase tracking-wider text-neutral-500 border-b border-neutral-900 pb-2 mb-3">
            Release cadence
          </h2>
          <p className="text-xs text-neutral-400 mb-3">
            Daily release count. Darker = more active.
          </p>
          <div className="overflow-x-auto -mx-4 px-4">
            <SenatorHeatmap data={daily} party={senator.party} />
          </div>
        </section>
      )}

      {/* Trending topics */}
      {topics.length > 0 && (
        <section className="mb-10">
          <h2 className="text-xs uppercase tracking-wider text-neutral-500 border-b border-neutral-900 pb-2 mb-3">
            What they&apos;re talking about lately
          </h2>
          <p className="text-xs text-neutral-400 mb-4">
            Most-used words over the last 30 days, compared to the 30 days before. Arrows show the change.
          </p>
          <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {topics.map((t) => {
              const delta = t.recent_count - t.prior_count;
              const direction =
                t.prior_count === 0 && t.recent_count >= 2
                  ? "new"
                  : delta > 0
                  ? "up"
                  : delta < 0
                  ? "down"
                  : "flat";
              const arrow =
                direction === "up" || direction === "new"
                  ? "▲"
                  : direction === "down"
                  ? "▼"
                  : "–";
              const tone =
                direction === "up"
                  ? "text-emerald-600"
                  : direction === "down"
                  ? "text-rose-600"
                  : direction === "new"
                  ? "text-indigo-600"
                  : "text-neutral-400";
              return (
                <li
                  key={t.word}
                  className="flex items-center justify-between border border-neutral-200 bg-white px-3 py-2 hover:border-neutral-400 transition-colors"
                >
                  <Link
                    href={`/search?q=${encodeURIComponent(t.word)}`}
                    className="text-sm text-neutral-800 hover:underline"
                  >
                    {t.word}
                  </Link>
                  <span className="flex items-center gap-2 font-[family-name:var(--font-dm-mono)] tabular-nums text-xs">
                    <span className="text-neutral-500">{t.recent_count}</span>
                    <span className={tone} title={
                      direction === "new"
                        ? "New in the last 30 days"
                        : `${delta >= 0 ? "+" : ""}${delta} vs prior 30 days`
                    }>
                      {arrow}
                      {direction !== "flat" && direction !== "new" && (
                        <span className="ml-0.5">{Math.abs(delta)}</span>
                      )}
                    </span>
                  </span>
                </li>
              );
            })}
          </ul>
        </section>
      )}

      {/* Signature topics — what this senator talks about that others don't */}
      {signature.length > 0 && (
        <section className="mb-10">
          <h2 className="text-xs uppercase tracking-wider text-neutral-500 border-b border-neutral-900 pb-2 mb-3">
            Topics they own
          </h2>
          <p className="text-xs text-neutral-400 mb-4">
            Words they use disproportionately compared to the rest of the Senate. Ranked by log-odds; higher score means more distinctive.
          </p>
          <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {signature.map((t) => {
              const odds = Number(t.log_odds);
              return (
                <li
                  key={t.word}
                  className="flex items-center justify-between border border-neutral-200 bg-white px-3 py-2 hover:border-neutral-400 transition-colors"
                >
                  <Link
                    href={`/search?q=${encodeURIComponent(t.word)}`}
                    className="text-sm text-neutral-800 hover:underline"
                  >
                    {t.word}
                  </Link>
                  <span
                    className="flex items-center gap-2 font-[family-name:var(--font-dm-mono)] tabular-nums text-xs text-neutral-400"
                    title={`Appears ${t.self_count}× in this senator's titles vs ${t.rest_count}× across the other 99 senators`}
                  >
                    <span className="text-neutral-600">{t.self_count}</span>
                    <span className="text-neutral-300">vs</span>
                    <span>{t.rest_count}</span>
                    <span className="ml-1 text-emerald-600">
                      +{odds.toFixed(1)}
                    </span>
                  </span>
                </li>
              );
            })}
          </ul>
        </section>
      )}

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
                  {pr.content_type && pr.content_type !== "press_release" && (
                    <span className="ml-2 inline-block align-middle">
                      <TypeBadge type={pr.content_type} size="xs" />
                    </span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <Suspense>
        <Pagination
          total={total}
          perPage={perPage}
          basePath={`/senators/${id}`}
          currentPage={page}
        />
      </Suspense>
    </div>
  );
}

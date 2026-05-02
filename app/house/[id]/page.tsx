import { notFound } from "next/navigation";
import Link from "next/link";
import Image from "next/image";
import { sql } from "../../lib/db";
import { getHouseMember, getSenatorReleases, getSenatorTypeBreakdown } from "../../lib/queries";
import type { PressRelease, ContentType } from "../../lib/db";
import { Pagination } from "../../components/pagination";
import { TypeBadge } from "../../components/type-badge";
import { EmptyState } from "../../components/empty-state";
import { STATE_NAMES } from "../../lib/states";
import { formatLongMonthYear, formatReleaseDate } from "../../lib/dates";

export const revalidate = 600;

const VALID_TYPES = new Set<ContentType>([
  "press_release",
  "statement",
  "op_ed",
  "blog",
  "letter",
  "floor_statement",
  "newsletter",
  "other",
] as ContentType[]);

export async function generateMetadata({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const member = await getHouseMember(id);
  if (!member) return { title: "Not Found — Capitol Releases" };
  const district = formatDistrict(member.district);
  return {
    title: `${member.full_name} — US House — Capitol Releases`,
    description: `Press releases, statements, and op-eds from Rep. ${member.full_name} (${member.party}-${member.state}${district ? `-${district}` : ""}), archived since January 2025.`,
  };
}

export default async function HouseMemberPage({
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

  const member = await getHouseMember(id);
  if (!member) notFound();

  const [{ items, total }, { breakdown, earliest }, bioRows] = await Promise.all([
    getSenatorReleases(id, page, perPage, activeType),
    getSenatorTypeBreakdown(id),
    sql`SELECT bioguide_id FROM officials WHERE id = ${id}`,
  ]);
  const bioguideId =
    (bioRows[0] as { bioguide_id: string | null } | undefined)?.bioguide_id ??
    null;

  const grandTotal = Object.values(breakdown).reduce<number>(
    (sum, n) => sum + (n ?? 0),
    0,
  );
  const sinceLabel = earliest ? formatLongMonthYear(earliest) : null;
  const districtLabel = formatDistrict(member.district);
  const partyLabel =
    member.party === "D"
      ? "Democrat"
      : member.party === "R"
        ? "Republican"
        : "Independent";
  const partyColor =
    member.party === "D"
      ? "text-blue-600"
      : member.party === "R"
        ? "text-red-600"
        : "text-amber-600";

  const releases = items as unknown as PressRelease[];

  const buildTypeHref = (t?: ContentType) => {
    const params = new URLSearchParams();
    if (t) params.set("type", t);
    const q = params.toString();
    return q ? `/house/${id}?${q}` : `/house/${id}`;
  };

  return (
    <div className="mx-auto max-w-3xl px-4 py-12">
      <Link
        href="/house"
        className="text-sm text-neutral-500 hover:text-neutral-900 transition-colors"
      >
        ← Back to House directory
      </Link>

      {/* Profile header */}
      <div className="mt-6 flex items-start gap-4">
        {bioguideId ? (
          <Image
            src={`/house/${bioguideId}.jpg`}
            alt={member.full_name}
            width={72}
            height={72}
            className="h-[72px] w-[72px] object-cover object-top shrink-0"
            unoptimized
          />
        ) : (
          <div className="h-[72px] w-[72px] bg-neutral-200 flex items-center justify-center text-neutral-400 text-lg shrink-0">
            {member.full_name
              .split(" ")
              .map((n) => n[0])
              .join("")
              .slice(0, 2)}
          </div>
        )}
        <div className="min-w-0">
        <h1 className="font-[family-name:var(--font-source-serif)] text-3xl text-neutral-900 leading-tight">
          {member.full_name}
        </h1>
        <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-neutral-500">
          <span className={partyColor}>{partyLabel}</span>
          <span className="text-neutral-300">·</span>
          <span>
            {STATE_NAMES[member.state] ?? member.state}
            {districtLabel && (
              <>
                ,{" "}
                <span className="font-[family-name:var(--font-dm-mono)] tabular-nums text-neutral-700">
                  District {member.district}
                </span>
              </>
            )}
          </span>
          <span className="text-neutral-300">·</span>
          <a
            href={member.official_url}
            target="_blank"
            rel="noopener noreferrer"
            className="font-[family-name:var(--font-dm-mono)] text-neutral-500 hover:text-neutral-900 transition-colors underline underline-offset-2"
          >
            {member.official_url
              .replace(/^https?:\/\//, "")
              .replace(/\/$/, "")}
            <span aria-hidden="true"> ↗</span>
          </a>
        </div>
        </div>
      </div>

      {/* Summary line */}
      <p className="text-sm text-neutral-600 leading-relaxed border-l-2 border-neutral-200 pl-4 mt-6 mb-6">
        <span className="font-[family-name:var(--font-dm-mono)] tabular-nums text-neutral-900 font-semibold">
          {grandTotal.toLocaleString()}
        </span>{" "}
        record{grandTotal !== 1 ? "s" : ""} archived
        {sinceLabel && <> since {sinceLabel}</>}.
      </p>

      {/* Type filter chips */}
      {grandTotal > 0 && (
        <div className="flex flex-wrap gap-2 mb-6 text-xs">
          <Link
            href={buildTypeHref(undefined)}
            className={`px-3 py-1 border ${
              !activeType
                ? "border-neutral-900 text-neutral-900"
                : "border-neutral-200 text-neutral-500 hover:border-neutral-400"
            }`}
          >
            All ({grandTotal.toLocaleString()})
          </Link>
          {(Object.entries(breakdown) as [ContentType, number][])
            .filter(([, n]) => n > 0)
            .sort((a, b) => b[1] - a[1])
            .map(([t, n]) => (
              <Link
                key={t}
                href={buildTypeHref(t)}
                className={`px-3 py-1 border ${
                  activeType === t
                    ? "border-neutral-900 text-neutral-900"
                    : "border-neutral-200 text-neutral-500 hover:border-neutral-400"
                }`}
              >
                {labelFor(t)} ({n.toLocaleString()})
              </Link>
            ))}
        </div>
      )}

      {/* Release list */}
      {releases.length === 0 ? (
        <EmptyState
          message="No records yet. This House member's press-release listing has not been wired into the daily collector. Once the recon promotes them, releases will appear here automatically."
        />
      ) : (
        <ul className="space-y-4">
          {releases.map((r) => (
            <li
              key={r.id}
              className="border-b border-neutral-100 pb-3 last:border-0"
            >
              <div className="flex items-baseline gap-2 text-xs text-neutral-500 mb-1">
                <span className="font-[family-name:var(--font-dm-mono)] tabular-nums">
                  {r.published_at ? formatReleaseDate(r.published_at) : "no date"}
                </span>
                {r.content_type && r.content_type !== "press_release" && (
                  <TypeBadge type={r.content_type} />
                )}
              </div>
              <Link
                href={`/releases/${r.id}`}
                className="text-base text-neutral-900 hover:underline leading-snug block"
              >
                {r.title}
              </Link>
            </li>
          ))}
        </ul>
      )}

      {total > perPage && (
        <Pagination
          currentPage={page}
          perPage={perPage}
          total={total}
          basePath={`/house/${id}`}
        />
      )}
    </div>
  );
}

function formatDistrict(d: string | null | undefined): string | null {
  if (!d) return null;
  return d;
}

function labelFor(t: ContentType): string {
  const map: Partial<Record<ContentType, string>> = {
    press_release: "Press releases",
    statement: "Statements",
    op_ed: "Op-eds",
    blog: "Blog",
    floor_statement: "Floor statements",
    letter: "Letters",
    other: "Other",
  };
  return map[t] ?? t;
}

import { notFound } from "next/navigation";
import Link from "next/link";
import Image from "next/image";
import { sql } from "../../lib/db";
import { getHouseMember, getSenatorReleases, getSenatorTypeBreakdown } from "../../lib/queries";
import type { PressRelease, ContentType } from "../../lib/db";
import { Pagination } from "../../components/pagination";
import { TypeBadge } from "../../components/type-badge";
import { EmptyState } from "../../components/empty-state";
import { AskRecord } from "../../components/ask-record";
import { STATE_NAMES } from "../../lib/states";
import { formatLongMonthYear, formatReleaseDate } from "../../lib/dates";
import houseSeed from "../../../pipeline/seeds/house.json";

// Seed-side coverage flags surfaced in the page banner. Methodology page
// reads the same fields. Single source of truth: pipeline/seeds/house.json.
type CoverageFlags = {
  coverage_status?: string;
  coverage_note?: string;
  expected_zero?: boolean;
  expected_low_volume?: boolean;
  low_volume_reason?: string;
  committee_chair_url?: string;
  committee_chair_name?: string;
};
function getCoverageFlags(memberId: string): CoverageFlags | null {
  for (const m of (houseSeed as { members: Array<CoverageFlags & { member_id?: string; official_id?: string }> }).members) {
    if (m.member_id === memberId || m.official_id === memberId) {
      const hasFlag =
        m.coverage_status ||
        m.expected_zero ||
        m.expected_low_volume ||
        m.committee_chair_url;
      if (!hasFlag) return null;
      return {
        coverage_status: m.coverage_status,
        coverage_note: m.coverage_note,
        expected_zero: m.expected_zero,
        expected_low_volume: m.expected_low_volume,
        low_volume_reason: m.low_volume_reason,
        committee_chair_url: m.committee_chair_url,
        committee_chair_name: m.committee_chair_name,
      };
    }
  }
  return null;
}

export const revalidate = 600;

// House bioguides whose photo is genuinely absent from the upstream
// Library-of-Congress mirror at bioguide.congress.gov/bioguide/photo/...
// AND from congress.gov/img/member/..., confirmed 2026-05-02 wave-3
// during the bulk download of 437 photos. Treat these as photo-less
// at render time so the page renders the initials placeholder rather
// than a broken-image icon. Hand-source replacements in a follow-up
// pass and remove from this set as they become available.
const MISSING_PHOTOS = new Set([
  "B001306", // Troy Balderson (R-OH-12)
  "C001115", // Michael Cloud (R-TX-27)
  "G000583", // Josh Gottheimer (D-NJ-5)
  "S001200", // Darren Soto (D-FL-9)
]);

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
  if (!member) return { title: "Not Found, Capitol Releases" };
  const district = formatDistrict(member.district);
  return {
    title: `${member.full_name}, US House, Capitol Releases`,
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
  const [{ id }, sp] = await Promise.all([params, searchParams]);
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
  const coverage = getCoverageFlags(id);

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
        {bioguideId && !MISSING_PHOTOS.has(bioguideId) ? (
          <Image
            src={`/house/${bioguideId}.jpg`}
            alt={member.full_name}
            width={72}
            height={72}
            className="size-[72px] object-cover object-top shrink-0"
            unoptimized
          />
        ) : (
          <div className="size-[72px] bg-neutral-200 flex items-center justify-center text-neutral-400 text-lg shrink-0">
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

      {/* Coverage transparency banner, surfaced when the seed has a
          coverage_status, expected_low_volume, or expected_zero flag.
          Methodology page documents the full taxonomy; this is the
          per-member explanation a journalist sees on landing. */}
      {coverage && (
        <aside className="mb-6 rounded-md border border-amber-200 bg-amber-50 p-4 text-sm leading-relaxed text-amber-950">
          <p className="text-xs uppercase tracking-wider text-amber-900 font-semibold mb-2">
            Coverage note
          </p>
          {coverage.coverage_status === "publishes_via_committee" && coverage.committee_chair_url ? (
            <>
              <p className="mb-2">
                {member.full_name.split(" ").slice(-1)[0]}&rsquo;s personal
                site has not posted original press releases since late 2024.
                As {coverage.committee_chair_name
                  ? `chair of the ${coverage.committee_chair_name}`
                  : "a committee chair"}
                , current press output runs through the committee site:
              </p>
              <p>
                <a
                  href={coverage.committee_chair_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="underline hover:text-amber-900 font-[family-name:var(--font-dm-mono)] text-[13px]"
                >
                  {coverage.committee_chair_url.replace(/^https?:\/\//, "").replace(/\/$/, "")}
                  <span aria-hidden="true"> ↗</span>
                </a>
              </p>
              <p className="mt-2 text-xs text-neutral-600">
                Committee output is not currently included in this archive
               , that&rsquo;s scoped for v2. See the{" "}
                <Link href="/about" className="underline">about page</Link>{" "}
                for the full coverage taxonomy.
              </p>
            </>
          ) : coverage.coverage_status === "playwright_required" ? (
            <p>
              This member&rsquo;s site uses a JavaScript-rendered listing
              (Next.js + GraphQL) that returns only the most recent ~10
              items via standard scraping. Full archive collection requires
              a Playwright collector, tracked as v2 work. The records
              shown are real; they&rsquo;re just the visible recent slice.
            </p>
          ) : coverage.coverage_status === "pagination_js_required" ? (
            <p>
              This member&rsquo;s listing is JavaScript-paginated, the
              server returns the same 20 items at every page request.
              Full archive collection requires a Playwright collector
              (v2 work). Records shown are real; they&rsquo;re the
              visible recent slice.
            </p>
          ) : coverage.coverage_status === "listing_horizon" ? (
            <p>
              This member&rsquo;s site listing caps at the records shown
             , deeper pagination doesn&rsquo;t expose earlier content.
              Likely a CMS migration cutoff. The records shown are real
              and complete from the listing&rsquo;s earliest visible date.
            </p>
          ) : coverage.expected_zero || coverage.expected_low_volume ? (
            <p>{coverage.low_volume_reason || coverage.coverage_note}</p>
          ) : (
            <p>{coverage.coverage_note}</p>
          )}
        </aside>
      )}

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

      {/* Ask the record — RAG Q&A over this member's collected releases */}
      {grandTotal > 0 && (
        <section className="mb-8">
          <h2 className="text-xs uppercase tracking-wider text-neutral-500 border-b border-neutral-900 pb-2 mb-3">
            Ask the record
          </h2>
          <AskRecord officialId={member.id} memberName={member.full_name} />
        </section>
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

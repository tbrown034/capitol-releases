import Link from "next/link";
import { notFound, redirect } from "next/navigation";
import { STATE_NAMES } from "../../lib/states";
import { getStateRow, getLiveStateCoverage } from "../../lib/state-coverage";
import { sql } from "../../lib/db";
import type { FeedItem } from "../../lib/db";
import { ReleaseCard } from "../../components/release-card";
import { formatReleaseDate } from "../../lib/dates";

export const revalidate = 600;

export async function generateMetadata({
  params,
}: {
  params: Promise<{ code: string }>;
}) {
  const { code } = await params;
  const upper = code.toUpperCase();
  const name = STATE_NAMES[upper];
  if (!name) return { title: "State not found — Capitol Releases" };
  return { title: `${name} — Capitol Releases` };
}

type StateMember = {
  id: string;
  full_name: string;
  party: string | null;
  chamber: string | null;
  district: number | null;
  releases: number;
  latest: string | null;
};

async function getStateMembers(jurisdiction: string): Promise<StateMember[]> {
  return (await sql`
    SELECT o.id, o.full_name, o.party, o.chamber, o.district,
           COUNT(pr.id)::int AS releases,
           MAX(pr.published_at)::text AS latest
    FROM officials o
    LEFT JOIN official_site_items pr
      ON pr.official_id = o.id
     AND pr.deleted_at IS NULL
     AND pr.content_type <> 'photo_release'
    WHERE o.jurisdiction = ${jurisdiction}
      AND o.status = 'active'
      AND o.collection_method IS NOT NULL
    GROUP BY o.id, o.full_name, o.party, o.chamber, o.district
    ORDER BY releases DESC, o.full_name
  `) as StateMember[];
}

async function getStateFeed(jurisdiction: string): Promise<FeedItem[]> {
  return (await sql`
    SELECT pr.*, o.full_name AS senator_name, o.party, o.state, o.chamber,
           o.bioguide_id
    FROM official_site_items pr
    JOIN officials o ON o.id = pr.official_id
    WHERE o.jurisdiction = ${jurisdiction}
      AND pr.deleted_at IS NULL
      AND pr.content_type <> 'photo_release'
    ORDER BY pr.published_at DESC NULLS LAST
    LIMIT 15
  `) as FeedItem[];
}

export default async function StateCodePage({
  params,
}: {
  params: Promise<{ code: string }>;
}) {
  const { code } = await params;
  const upper = code.toUpperCase();
  const lower = code.toLowerCase();
  const name = STATE_NAMES[upper];
  if (!name) notFound();

  // A state with a bespoke page (Texas, Colorado) owns its own route.
  const coverage = await getLiveStateCoverage();
  const liveRow = coverage.find((c) => c.jurisdiction === lower);
  if (liveRow?.href && liveRow.href !== `/states/${lower}`) {
    redirect(liveRow.href);
  }

  const staticRow = getStateRow(upper);
  if (staticRow?.href && staticRow.href !== `/states/${lower}`) {
    redirect(staticRow.href);
  }

  // Anything with collected records renders as live, whatever the static
  // roadmap says. This page previously told visitors that California was
  // "on the Phase 1 roadmap" while the corpus already held 1,362
  // Californian releases.
  if (!liveRow || liveRow.releases === 0) {
    return (
      <div className="mx-auto max-w-5xl px-4 py-12">
        <Link
          href="/states"
          className="text-xs text-neutral-500 hover:text-neutral-900 mb-6 inline-block"
        >
          ← All states
        </Link>
        <h1 className="font-[family-name:var(--font-source-serif)] text-4xl text-neutral-900 mb-3">
          {name}
        </h1>
        <p className="text-sm text-neutral-600 leading-relaxed max-w-2xl">
          {name} is not collected yet. Coverage expands chamber by chamber;
          each one ships only once its archive reaches January 1, 2025 with
          the same provenance the federal corpus carries.
        </p>
        <Link
          href="/states"
          className="mt-6 inline-block text-sm text-neutral-700 underline hover:text-neutral-900"
        >
          See what is live now
        </Link>
      </div>
    );
  }

  const [members, feed] = await Promise.all([
    getStateMembers(lower),
    getStateFeed(lower),
  ]);
  const silent = members.filter((m) => m.releases === 0);

  return (
    <div className="mx-auto max-w-5xl px-4 py-12">
      <Link
        href="/states"
        className="text-xs text-neutral-500 hover:text-neutral-900 mb-6 inline-block"
      >
        ← All states
      </Link>

      <h1 className="font-[family-name:var(--font-source-serif)] text-4xl text-neutral-900 mb-2">
        {name}
      </h1>
      <p className="text-sm text-neutral-600 leading-relaxed max-w-2xl">
        {liveRow.chamber}. {liveRow.note}
      </p>

      <dl className="mt-6 grid grid-cols-2 gap-4 sm:grid-cols-4">
        {[
          { label: "Releases", value: liveRow.releases.toLocaleString() },
          { label: "Sources", value: String(liveRow.members) },
          {
            label: "Archive starts",
            value: liveRow.since ? formatReleaseDate(liveRow.since) : "—",
          },
          {
            label: "Most recent",
            value: liveRow.latest ? formatReleaseDate(liveRow.latest) : "—",
          },
        ].map((s) => (
          <div key={s.label} className="border-l-2 border-neutral-200 pl-3">
            <dt className="text-[10px] uppercase tracking-wider text-neutral-400">
              {s.label}
            </dt>
            <dd className="font-[family-name:var(--font-dm-mono)] text-lg text-neutral-900 tabular-nums">
              {s.value}
            </dd>
          </div>
        ))}
      </dl>

      <h2 className="font-[family-name:var(--font-source-serif)] text-2xl text-neutral-900 mt-12 mb-4">
        Sources
      </h2>
      <div className="border-t border-neutral-100">
        {members.map((m) => (
          <div
            key={m.id}
            className="flex items-baseline gap-3 border-b border-neutral-100 py-1.5"
          >
            <span
              className={`size-2 rounded-full shrink-0 ${
                m.party === "D"
                  ? "bg-blue-500"
                  : m.party === "R"
                    ? "bg-red-500"
                    : "bg-amber-500"
              }`}
              aria-hidden
            />
            <span className="text-sm text-neutral-900 flex-1 min-w-0 truncate">
              {m.full_name}
            </span>
            {m.district != null && (
              <span className="text-[11px] text-neutral-400 font-[family-name:var(--font-dm-mono)] shrink-0">
                D{m.district}
              </span>
            )}
            <span className="text-[11px] text-neutral-400 shrink-0 hidden sm:inline">
              {m.latest ? formatReleaseDate(m.latest) : "no releases"}
            </span>
            <span className="text-[11px] text-neutral-700 font-[family-name:var(--font-dm-mono)] tabular-nums w-14 text-right shrink-0">
              {m.releases.toLocaleString()}
            </span>
          </div>
        ))}
      </div>

      {silent.length > 0 && (
        <p className="mt-3 text-[11px] text-neutral-400">
          {silent.length} configured{" "}
          {silent.length === 1 ? "source has" : "sources have"} produced no
          records yet. Stated rather than hidden: an empty source is either a
          member who does not publish or a collector still being built.
        </p>
      )}

      <h2 className="font-[family-name:var(--font-source-serif)] text-2xl text-neutral-900 mt-12 mb-4">
        Recent releases
      </h2>
      <div>
        {feed.map((item) => (
          <ReleaseCard key={item.id} item={item} />
        ))}
      </div>
    </div>
  );
}

import Link from "next/link";
import { sql } from "../lib/db";
import senateSeed from "../../pipeline/seeds/senate.json";
import houseSeed from "../../pipeline/seeds/house.json";
import { buildCoverageRows, type CoverageRow } from "../lib/coverage";

export const metadata = {
  title: "About — Capitol Releases",
  description:
    "How Capitol Releases collects, classifies, verifies and preserves official congressional press releases.",
};

export const revalidate = 3600;

type SeedMember = {
  official_id?: string;
  member_id?: string;
  full_name: string;
  party: string;
  state: string;
  district?: string | number | null;
  notes?: string | null;
  last_verified?: string | null;
  expected_low_volume?: boolean;
  expected_zero?: boolean;
  low_volume_reason?: string | null;
};

type LowVolumeRow = {
  id: string;
  name: string;
  chamber: "Senate" | "House";
  districtState: string;
  status: string;
  reason: string;
  lastVerified: string;
};

type SortKey = "name" | "chamber" | "district" | "status" | "verified";

const CONTENT_TYPES = [
  {
    type: "press_release",
    label: "Press release",
    definition:
      "The default class for original announcements from a member's news, media or press section.",
  },
  {
    type: "statement",
    label: "Statement",
    definition:
      "A public statement posted by the office, usually without a separate legislative action attached.",
  },
  {
    type: "op_ed",
    label: "Op-ed",
    definition:
      "Signed commentary or opinion writing republished on the official site.",
  },
  {
    type: "blog",
    label: "Blog post",
    definition:
      "Original posts from member blog, diary, newsletter or similar site sections.",
  },
  {
    type: "floor_statement",
    label: "Floor statement",
    definition:
      "Floor remarks when a member's office publishes them on its own press page.",
  },
  {
    type: "letter",
    label: "Letter",
    definition:
      "Published letters to agencies, officials, colleagues or constituents.",
  },
  {
    type: "photo_release",
    label: "Photo release",
    definition:
      "Photo-only or media-advisory items. Stored, but excluded from default public feeds.",
  },
  {
    type: "presidential_action",
    label: "Presidential action",
    definition:
      "White House actions stored in the same schema for federal executive coverage.",
  },
  {
    type: "other",
    label: "Other",
    definition:
      "Original official content that does not fit a more specific class. Reviewed during cleanup.",
  },
];

async function getCoverageRows(): Promise<CoverageRow[]> {
  // One row per active senator, then count the qualifying rows. The previous
  // version selected count(*) with GROUP BY s.id and read the first row, which
  // published a single senator's release count as "clean senators".
  const [senateStats] = (await sql`
    WITH counts AS (
      SELECT s.id,
             count(pr.id) FILTER (WHERE pr.deleted_at IS NULL
                                  AND pr.content_type != 'photo_release') as rec,
             min(pr.published_at) FILTER (WHERE pr.deleted_at IS NULL
                                          AND pr.content_type != 'photo_release') as first_dt
      FROM officials s
      LEFT JOIN official_site_items pr ON pr.official_id = s.id
      WHERE s.status = 'active'
        AND s.chamber = 'senate' AND s.jurisdiction = 'us'
      GROUP BY s.id
    )
    SELECT count(*)::int as total,
           count(*) FILTER (WHERE rec >= 10 AND first_dt < '2025-02-01')::int as clean
    FROM counts
  `) as { total: number; clean: number }[];

  // Per-member rows, not pre-aggregated totals: "accounted for" has to be a
  // union of clean members and documented-gap members, and adding two counts
  // double-counts everyone who is both.
  const houseRows = (await sql`
    WITH counts AS (
      SELECT s.id,
             count(pr.id) FILTER (WHERE pr.deleted_at IS NULL
                                  AND pr.content_type != 'photo_release') as rec,
             min(pr.published_at) FILTER (WHERE pr.deleted_at IS NULL
                                          AND pr.content_type != 'photo_release') as first_dt
      FROM officials s
      LEFT JOIN official_site_items pr ON pr.official_id = s.id
      WHERE s.status = 'active'
        AND s.chamber = 'house' AND s.jurisdiction = 'us'
      GROUP BY s.id
    )
    SELECT id,
           COALESCE(rec >= 10 AND first_dt < '2025-02-01', false) as reaches
    FROM counts
  `) as { id: string; reaches: boolean }[];

  const senateMembers = senateSeed.members as SeedMember[];
  const senateDocumented = senateMembers.filter(
    (m) => m.expected_zero || m.expected_low_volume || (m as { coverage_status?: string }).coverage_status
  ).length;

  const houseMembers = houseSeed.members as SeedMember[];
  const houseDocumentedIds = new Set(
    houseMembers.flatMap((m) =>
      (m.expected_zero || m.expected_low_volume || (m as { coverage_status?: string }).coverage_status) && m.member_id
        ? [m.member_id]
        : []
    )
  );

  return buildCoverageRows({
    senateClean: senateStats?.clean ?? 0,
    senateTotal: senateStats?.total ?? 0,
    senateDocumented,
    houseRows,
    houseDocumentedIds,
    houseSeedRows: houseMembers.length,
  });
}

function normalizeRows(): LowVolumeRow[] {
  const senateRows = (senateSeed.members as SeedMember[]).flatMap((m) =>
    m.expected_low_volume || m.expected_zero
      ? [{
      id: m.official_id ?? m.full_name,
      name: m.full_name,
      chamber: "Senate" as const,
      districtState: m.state,
      status: m.expected_zero ? "Expected zero" : "Expected low volume",
      reason: m.low_volume_reason ?? m.notes ?? "Seed reason pending",
      lastVerified: m.last_verified ?? "Pending",
    }]
      : []
  );

  const houseRows = (houseSeed.members as SeedMember[]).flatMap((m) =>
    m.expected_low_volume || m.expected_zero
      ? [{
      id: m.member_id ?? m.full_name,
      name: m.full_name,
      chamber: "House" as const,
      districtState:
        m.district == null ? m.state : `${m.state}-${String(m.district)}`,
      status: m.expected_zero ? "Expected zero" : "Expected low volume",
      reason: m.low_volume_reason ?? m.notes ?? "Seed reason pending",
      lastVerified: m.last_verified ?? "Pending",
    }]
      : []
  );

  return [...senateRows, ...houseRows];
}

function sortRows(rows: LowVolumeRow[], sort: SortKey): LowVolumeRow[] {
  return rows.toSorted((a, b) => {
    if (sort === "chamber") {
      return a.chamber.localeCompare(b.chamber) || a.name.localeCompare(b.name);
    }
    if (sort === "district") {
      return (
        a.districtState.localeCompare(b.districtState) ||
        a.name.localeCompare(b.name)
      );
    }
    if (sort === "status") {
      return a.status.localeCompare(b.status) || a.name.localeCompare(b.name);
    }
    if (sort === "verified") {
      return (
        b.lastVerified.localeCompare(a.lastVerified) ||
        a.name.localeCompare(b.name)
      );
    }
    return a.name.localeCompare(b.name);
  });
}

function SortLink({
  sort,
  active,
  children,
}: {
  sort: SortKey;
  active: SortKey;
  children: React.ReactNode;
}) {
  return (
    <Link
      href={`/about?sort=${sort}`}
      className={`hover:text-neutral-900 ${
        active === sort ? "text-neutral-900" : "text-neutral-500"
      }`}
    >
      {children}
    </Link>
  );
}

export default async function AboutPage({
  searchParams,
}: {
  searchParams: Promise<{ sort?: string }>;
}) {
  const params = await searchParams;
  const sort: SortKey =
    params.sort === "chamber" ||
    params.sort === "district" ||
    params.sort === "status" ||
    params.sort === "verified"
      ? params.sort
      : "name";
  const [lowVolumeRows, coverageRows] = await Promise.all([
    Promise.resolve(sortRows(normalizeRows(), sort)),
    getCoverageRows(),
  ]);

  return (
    <div className="mx-auto max-w-3xl px-4 py-12">
      <p className="mb-2 text-xs uppercase tracking-wider text-neutral-500">
        About &amp; methodology
      </p>
      <h1 className="mb-3 font-[family-name:var(--font-source-serif)] text-4xl leading-tight text-neutral-900 md:text-5xl">
        How Capitol Releases works
      </h1>
      <p className="mb-8 max-w-2xl text-sm leading-relaxed text-neutral-600">
        Capitol Releases archives official press output from all 100 U.S.
        senators and 435 U.S. representatives. The goal is a searchable public
        record with enough provenance that a reporter can cite it and a
        developer can audit it.
      </p>

      <Section title="What we collect">
        <p>
          We collect original content from official .gov member websites:
          press releases, statements, op-eds, blog posts, floor statements,
          letters and photo releases.
        </p>
        <p>
          The collection window starts Jan. 1, 2025. For seat changes, the
          archive follows the current officeholder only from the day that
          person took office.
        </p>
        <div className="overflow-x-auto">
          <table className="mt-4 w-full text-left text-sm">
            <thead>
              <tr className="border-b border-neutral-900 text-xs uppercase tracking-wider text-neutral-500">
                <th className="py-2 pr-4 font-medium">Type</th>
                <th className="py-2 font-medium">Definition</th>
              </tr>
            </thead>
            <tbody>
              {CONTENT_TYPES.map((row) => (
                <tr key={row.type} className="border-b border-neutral-100">
                  <td className="py-2.5 pr-4 align-top">
                    <code className="font-[family-name:var(--font-dm-mono)] text-[13px] text-neutral-900">
                      {row.type}
                    </code>
                    <div className="mt-0.5 text-xs text-neutral-500">
                      {row.label}
                    </div>
                  </td>
                  <td className="py-2.5 align-top text-neutral-700">
                    {row.definition}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Section>

      <Section title="What we don't">
        <p>
          We do not collect third-party clippings, &quot;In the News&quot;
          mentions, campaign content, campaign websites, interviews or outside
          media hits.
        </p>
        <p>
          We do not backfill predecessor coverage when a seat changes hands.
          We also do not collect voting records, bill tracking or campaign
          finance records. Those records already exist elsewhere, including
          Congress.gov and the FEC.
        </p>
      </Section>

      <Section title="How dates work">
        <p>
          Every record can carry two date fields beyond the timestamp itself:{" "}
          <code className="font-[family-name:var(--font-dm-mono)] text-[13px] text-neutral-900">
            date_source
          </code>{" "}
          and{" "}
          <code className="font-[family-name:var(--font-dm-mono)] text-[13px] text-neutral-900">
            date_confidence
          </code>
          . They record where the date came from and how much the parser trusts
          it.
        </p>
        <p>
          Most dates come from metadata, listing text or page-level date
          elements. About 1% of records have null dates, mostly ColdFusion
          sites where the date is embedded in body text rather than exposed as
          metadata.
        </p>
      </Section>

      <Section title="Provenance">
        <p>
          Every record stores{" "}
          <code className="font-[family-name:var(--font-dm-mono)] text-[13px] text-neutral-900">
            source_url
          </code>
          ,{" "}
          <code className="font-[family-name:var(--font-dm-mono)] text-[13px] text-neutral-900">
            scrape_run
          </code>{" "}
          and{" "}
          <code className="font-[family-name:var(--font-dm-mono)] text-[13px] text-neutral-900">
            scraped_at
          </code>
          . The source URL is the office&apos;s page. The scrape run ties the row
          back to a collector pass. The scrape timestamp says when Capitol
          Releases saw it.
        </p>
        <p>
          Records are never hard-deleted. If a source URL stops resolving on
          repeated checks, the row stays in the archive and gets a{" "}
          <code className="font-[family-name:var(--font-dm-mono)] text-[13px] text-neutral-900">
            deleted_at
          </code>{" "}
          tombstone.
        </p>
      </Section>

      <Section title="Update cadence">
        <p>
          GitHub Actions runs collection four times a day: 13:00, 17:00, 21:00
          and 01:00 UTC. The same schedule refreshes WordPress JSON silos used
          for op-eds, newsletters, blogs and related official sections.
        </p>
        <p>
          A health check runs before every collection pass. It verifies that
          configured source pages respond, selectors still find items and dates
          remain parseable.
        </p>
      </Section>

      <Section title="Coverage status">
        <p>
          The table below is computed at request time from the database and the
          seed files. The per-site writeup behind it:
        </p>
        <p>
          <a
            href="https://github.com/tbrown034/capitol-releases/blob/main/docs/coverage-troublesites-2026-05-03.md"
            target="_blank"
            rel="noopener noreferrer"
            className="underline hover:text-neutral-900"
          >
            House coverage trouble sites, May 3, 2026
          </a>
        </p>
        <div className="overflow-x-auto">
          <table className="mt-4 w-full text-left text-sm">
            <thead>
              <tr className="border-b border-neutral-900 text-xs uppercase tracking-wider text-neutral-500">
                <th className="py-2 pr-4 font-medium">Metric</th>
                <th className="py-2 pr-4 font-medium">Status</th>
                <th className="py-2 font-medium">Note</th>
              </tr>
            </thead>
            <tbody>
              {coverageRows.map(([metric, status, note]) => (
                <tr key={metric} className="border-b border-neutral-100">
                  <td className="py-2.5 pr-4 text-neutral-900">{metric}</td>
                  <td className="py-2.5 pr-4 font-[family-name:var(--font-dm-mono)] text-neutral-900">
                    {status}
                  </td>
                  <td className="py-2.5 text-neutral-700">{note}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Section>

      <Section title="Known low-volume offices">
        <p>
          Some offices publish rarely or not at all. The rows below are the
          members carrying an{" "}
          <code className="font-[family-name:var(--font-dm-mono)] text-[13px] text-neutral-900">
            expected_low_volume
          </code>{" "}
          or{" "}
          <code className="font-[family-name:var(--font-dm-mono)] text-[13px] text-neutral-900">
            expected_zero
          </code>{" "}
          flag in the seed files.
        </p>
        <div className="overflow-x-auto">
          <table className="mt-4 w-full text-left text-sm">
            <thead>
              <tr className="border-b border-neutral-900 text-xs uppercase tracking-wider">
                <th className="py-2 pr-4 font-medium">
                  <SortLink sort="name" active={sort}>
                    Name
                  </SortLink>
                </th>
                <th className="py-2 pr-4 font-medium">
                  <SortLink sort="chamber" active={sort}>
                    Chamber
                  </SortLink>
                </th>
                <th className="py-2 pr-4 font-medium">
                  <SortLink sort="district" active={sort}>
                    District/state
                  </SortLink>
                </th>
                <th className="py-2 pr-4 font-medium">
                  <SortLink sort="status" active={sort}>
                    Status
                  </SortLink>
                </th>
                <th className="py-2 pr-4 font-medium">Reason</th>
                <th className="py-2 font-medium">
                  <SortLink sort="verified" active={sort}>
                    Last verified
                  </SortLink>
                </th>
              </tr>
            </thead>
            <tbody>
              {lowVolumeRows.length > 0 ? (
                lowVolumeRows.map((row) => (
                  <tr key={row.id} className="border-b border-neutral-100">
                    <td className="py-2.5 pr-4 text-neutral-900">
                      {row.name}
                    </td>
                    <td className="py-2.5 pr-4">{row.chamber}</td>
                    <td className="py-2.5 pr-4 font-[family-name:var(--font-dm-mono)] text-[13px]">
                      {row.districtState}
                    </td>
                    <td className="py-2.5 pr-4">{row.status}</td>
                    <td className="py-2.5 pr-4">{row.reason}</td>
                    <td className="py-2.5">{row.lastVerified}</td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td
                    colSpan={6}
                    className="py-4 text-sm text-neutral-500"
                  >
                    No seed rows are flagged low-volume or expected-zero.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </Section>

      <Section title="Schema history">
        <p>
          The schema was renamed in May 2026 as the project moved from a
          Senate-only archive to Congress-wide coverage. The old{" "}
          <code className="font-[family-name:var(--font-dm-mono)] text-[13px] text-neutral-900">
            senators
          </code>{" "}
          table became{" "}
          <code className="font-[family-name:var(--font-dm-mono)] text-[13px] text-neutral-900">
            officials
          </code>
          , and{" "}
          <code className="font-[family-name:var(--font-dm-mono)] text-[13px] text-neutral-900">
            press_releases
          </code>{" "}
          became{" "}
          <code className="font-[family-name:var(--font-dm-mono)] text-[13px] text-neutral-900">
            official_site_items
          </code>
          . Compatibility views remain during the transition.
        </p>
      </Section>
    </div>
  );
}

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  const anchor = title.toLowerCase().replace(/[^a-z0-9]+/g, "-");
  return (
    <section id={anchor} className="mb-10 scroll-mt-8">
      <h2 className="mb-4 border-b border-neutral-900 pb-2 text-xs uppercase tracking-wider text-neutral-500">
        {title}
      </h2>
      <div className="max-w-2xl space-y-3 text-sm leading-relaxed text-neutral-700">
        {children}
      </div>
    </section>
  );
}

import { sql } from "./db";
import type { FeedItem } from "./db";

// Colorado is the first jurisdiction with no per-member pressroom. All 100
// legislators publish through one of four party caucus organizations, so a
// record's author is always a caucus and never a person. Individual
// legislators reach the corpus through item_mentions instead -- see
// db/migrations/018_item_mentions.sql and pipeline/lib/co_attribution.py.
//
// Every query here keeps that separation intact: a caucus is the byline, a
// legislator is a filter.

export const MENTION_ROLES = ["primary", "quoted", "mentioned"] as const;
export type MentionRole = (typeof MENTION_ROLES)[number];

export type CaucusSource = {
  id: string;
  full_name: string;
  party: "D" | "R";
  chamber: string | null;
  item_count: number;
  latest: string | null;
};

export type CoLegislator = {
  id: string;
  full_name: string;
  party: "D" | "R" | "I";
  chamber: string | null;
  district: number | null;
  official_url: string | null;
  quoted_count: number;
  mentioned_count: number;
};

export type ReleaseMention = {
  official_id: string;
  full_name: string;
  party: "D" | "R" | "I";
  chamber: string | null;
  district: number | null;
  role: MentionRole;
  matched_text: string | null;
};

const CAUCUS = "caucus_pressroom";

/** The four caucus pressrooms, with how much each has published. */
export async function getCaucusSources(): Promise<CaucusSource[]> {
  return (await sql`
    SELECT o.id, o.full_name, o.party, o.chamber,
           COUNT(i.id)::int AS item_count,
           MAX(i.published_at)::text AS latest
    FROM officials o
    LEFT JOIN official_site_items i
      ON i.official_id = o.id AND i.deleted_at IS NULL
    WHERE o.jurisdiction = 'co' AND o.office_type = ${CAUCUS}
    GROUP BY o.id, o.full_name, o.party, o.chamber
    ORDER BY item_count DESC
  `) as CaucusSource[];
}

/**
 * The 100-seat roster, ranked by how often each member is quoted.
 *
 * quoted_count and mentioned_count are deliberately separate. "Named in a
 * release" is close to meaningless in a caucus corpus that lists bipartisan
 * sponsors by the dozen; "quoted in a release" is an editorial choice by the
 * caucus press shop, and it is the number worth ranking on.
 */
export async function getColoradoLegislators(): Promise<CoLegislator[]> {
  return (await sql`
    SELECT o.id, o.full_name, o.party, o.chamber, o.district, o.official_url,
           COUNT(*) FILTER (WHERE m.role = 'quoted')::int    AS quoted_count,
           COUNT(*) FILTER (WHERE m.role = 'mentioned')::int AS mentioned_count
    FROM officials o
    LEFT JOIN item_mentions m ON m.official_id = o.id
    WHERE o.jurisdiction = 'co'
      AND o.office_type <> ${CAUCUS}
      AND o.status = 'active'
    GROUP BY o.id, o.full_name, o.party, o.chamber, o.district, o.official_url
    ORDER BY quoted_count DESC, o.full_name
  `) as CoLegislator[];
}

export async function getColoradoLegislator(
  officialId: string
): Promise<CoLegislator | null> {
  const rows = (await sql`
    SELECT o.id, o.full_name, o.party, o.chamber, o.district, o.official_url,
           COUNT(*) FILTER (WHERE m.role = 'quoted')::int    AS quoted_count,
           COUNT(*) FILTER (WHERE m.role = 'mentioned')::int AS mentioned_count
    FROM officials o
    LEFT JOIN item_mentions m ON m.official_id = o.id
    WHERE o.id = ${officialId}
      AND o.jurisdiction = 'co'
      AND o.office_type <> ${CAUCUS}
    GROUP BY o.id, o.full_name, o.party, o.chamber, o.district, o.official_url
  `) as CoLegislator[];
  return rows[0] ?? null;
}

/** Who is named in one release, and how. Powers the badges on a record. */
export async function getReleaseMentions(
  releaseId: string
): Promise<ReleaseMention[]> {
  return (await sql`
    SELECT m.official_id, o.full_name, o.party, o.chamber, o.district,
           m.role, m.matched_text
    FROM item_mentions m
    JOIN officials o ON o.id = m.official_id
    WHERE m.item_id = ${releaseId}::uuid
    ORDER BY
      CASE m.role WHEN 'primary' THEN 0 WHEN 'quoted' THEN 1 ELSE 2 END,
      o.full_name
  `) as ReleaseMention[];
}

/**
 * Releases naming a given legislator, bylined to the publishing caucus.
 *
 * senator_name is the CAUCUS name on purpose -- ReleaseCard renders that
 * field as the byline, and attributing a caucus release to the member it
 * mentions is exactly the misattribution this whole model exists to avoid.
 */
export async function getReleasesMentioning(
  officialId: string,
  role?: MentionRole,
  limit = 50
): Promise<(FeedItem & { mention_role: MentionRole })[]> {
  // The role filter is a nullable predicate rather than an interpolated SQL
  // fragment. The Neon driver binds a nested sql`` template as a PARAMETER,
  // so `${sql`AND m.role = ...`}` compiles to a bare $2 and Postgres rejects
  // the statement with a syntax error.
  const roleParam = role ?? null;
  return (await sql`
    SELECT i.*, caucus.full_name AS senator_name, caucus.party, caucus.state,
           caucus.chamber, caucus.bioguide_id, m.role AS mention_role
    FROM item_mentions m
    JOIN official_site_items i ON i.id = m.item_id
    JOIN officials caucus ON caucus.id = i.official_id
    WHERE m.official_id = ${officialId}
      AND i.deleted_at IS NULL
      AND (${roleParam}::text IS NULL OR m.role = ${roleParam})
    ORDER BY i.published_at DESC NULLS LAST
    LIMIT ${limit}
  `) as (FeedItem & { mention_role: MentionRole })[];
}

/** Recent caucus output for the Colorado landing page. */
export async function getColoradoFeed(limit = 40): Promise<FeedItem[]> {
  return (await sql`
    SELECT i.*, o.full_name AS senator_name, o.party, o.state, o.chamber,
           o.bioguide_id
    FROM official_site_items i
    JOIN officials o ON o.id = i.official_id
    WHERE o.jurisdiction = 'co'
      AND o.office_type = ${CAUCUS}
      AND i.deleted_at IS NULL
    ORDER BY i.published_at DESC NULLS LAST
    LIMIT ${limit}
  `) as FeedItem[];
}

/** Headline totals for the Colorado landing page. */
export async function getColoradoStats(): Promise<{
  items: number;
  mentions: number;
  legislators_mentioned: number;
  oldest: string | null;
  newest: string | null;
}> {
  const rows = (await sql`
    SELECT
      (SELECT COUNT(*)::int FROM official_site_items i
        JOIN officials o ON o.id = i.official_id
        WHERE o.jurisdiction = 'co' AND i.deleted_at IS NULL) AS items,
      (SELECT COUNT(*)::int FROM item_mentions) AS mentions,
      (SELECT COUNT(DISTINCT official_id)::int FROM item_mentions)
        AS legislators_mentioned,
      (SELECT MIN(i.published_at)::text FROM official_site_items i
        JOIN officials o ON o.id = i.official_id
        WHERE o.jurisdiction = 'co' AND i.deleted_at IS NULL) AS oldest,
      (SELECT MAX(i.published_at)::text FROM official_site_items i
        JOIN officials o ON o.id = i.official_id
        WHERE o.jurisdiction = 'co' AND i.deleted_at IS NULL) AS newest
  `) as {
    items: number;
    mentions: number;
    legislators_mentioned: number;
    oldest: string | null;
    newest: string | null;
  }[];
  return rows[0];
}

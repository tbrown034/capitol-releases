import { sql } from "./db";

export async function getDataQuality() {
  // Scoped to active US senators only — without the join we'd surface
  // tombstoned/former-senator carryover (e.g. Rubio→Moody, Vance→Husted),
  // which inflates "senators with data" to 118/100 and reads as a math
  // error on the methodology page.
  const result = await sql`
    SELECT
      count(*)::int as total,
      count(*) FILTER (WHERE pr.published_at IS NOT NULL)::int as has_date,
      count(*) FILTER (WHERE pr.published_at IS NULL)::int as null_date,
      count(*) FILTER (WHERE pr.body_text IS NOT NULL AND length(pr.body_text) > 50)::int as has_body,
      count(*) FILTER (WHERE pr.body_text IS NULL OR length(pr.body_text) <= 50)::int as no_body,
      count(DISTINCT pr.senator_id)::int as senators_with_data
    FROM press_releases pr
    JOIN senators s ON s.id = pr.senator_id
    WHERE s.chamber = 'senate' AND s.status = 'active'
      AND pr.deleted_at IS NULL AND pr.content_type != 'photo_release'
  `;
  return result[0];
}

export async function getCoverageByFamily() {
  return sql`
    SELECT s.parser_family,
           count(DISTINCT s.id)::int as senator_count,
           count(pr.id)::int as release_count,
           count(*) FILTER (WHERE pr.published_at IS NOT NULL)::int as dated,
           count(*) FILTER (WHERE pr.published_at IS NULL)::int as undated,
           count(*) FILTER (WHERE pr.body_text IS NOT NULL AND length(pr.body_text) > 50)::int as has_body
    FROM senators s
    LEFT JOIN press_releases pr ON pr.senator_id = s.id
    WHERE s.chamber = 'senate'
    GROUP BY s.parser_family
    ORDER BY release_count DESC
  `;
}

export async function getCollectionMethodBreakdown() {
  return sql`
    SELECT collection_method,
           count(*)::int as senator_count
    FROM senators
    WHERE chamber = 'senate' AND status = 'active' AND collection_method IS NOT NULL
    GROUP BY collection_method
    ORDER BY senator_count DESC
  `;
}

export async function getContentTypeBreakdown() {
  return sql`
    SELECT pr.content_type,
           count(*)::int as count
    FROM press_releases pr
    JOIN senators s ON s.id = pr.senator_id
    WHERE s.chamber = 'senate' AND pr.deleted_at IS NULL
    GROUP BY pr.content_type
    ORDER BY count DESC
  `;
}

export async function getDeletionCount() {
  const result = await sql`
    SELECT count(*)::int as count
    FROM press_releases pr
    JOIN senators s ON s.id = pr.senator_id
    WHERE s.chamber = 'senate' AND pr.deleted_at IS NOT NULL
  `;
  return Number(result[0]?.count ?? 0);
}

export async function getCoverageDepth() {
  return sql`
    SELECT s.full_name, s.party, s.state, s.parser_family,
           count(pr.id)::int as total,
           count(*) FILTER (WHERE pr.published_at IS NOT NULL)::int as dated,
           to_char(min(pr.published_at), 'YYYY-MM-DD') as earliest,
           to_char(max(pr.published_at), 'YYYY-MM-DD') as latest,
           CASE
             WHEN min(pr.published_at)::date <= '2025-02-01' THEN 'complete'
             WHEN min(pr.published_at) IS NULL AND count(pr.id) > 50 THEN 'undated'
             WHEN count(pr.id) = 0 THEN 'empty'
             ELSE 'partial'
           END as coverage
    FROM senators s
    LEFT JOIN press_releases pr ON pr.senator_id = s.id
    WHERE s.chamber = 'senate'
    GROUP BY s.id, s.full_name, s.party, s.state, s.parser_family
    ORDER BY s.state, s.full_name
  `;
}

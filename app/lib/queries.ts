import { sql } from "./db";
import type {
  FeedItem,
  SenatorWithCount,
  PressRelease,
  Senator,
  ContentType,
  TypeBreakdown,
} from "./db";

// Photo releases are classified and stored, but excluded from every user-facing
// surface -- they're photo-only media advisories, not substantive communications.
const ALLOWED_TYPES: ContentType[] = [
  "press_release",
  "statement",
  "op_ed",
  "letter",
  "floor_statement",
  "presidential_action",
  "other",
];

const EXCLUDED_FROM_UI = "photo_release";

function normalizeType(t?: string): ContentType | undefined {
  if (!t) return undefined;
  return (ALLOWED_TYPES as string[]).includes(t) ? (t as ContentType) : undefined;
}

// SELECT columns for all feed queries -- keep in sync with FeedItem.
const FEED_COLUMNS = `pr.id, pr.senator_id, pr.title, pr.published_at, pr.body_text, pr.source_url, pr.scraped_at, pr.content_type, s.full_name as senator_name, s.party, s.state`;

export async function getFeed({
  page = 1,
  perPage = 25,
  party,
  state,
  senator,
  search,
  type,
}: {
  page?: number;
  perPage?: number;
  party?: string;
  state?: string;
  senator?: string;
  search?: string;
  type?: string;
} = {}): Promise<{ items: FeedItem[]; total: number }> {
  const offset = (page - 1) * perPage;
  const ctype = normalizeType(type);

  // Build WHERE predicates + parameters dynamically. Every user value goes
  // through the Neon driver as a $N parameter -- no string interpolation.
  // The two literal filters (deleted_at, photo_release exclusion) are always
  // applied and are the product-level invariants.
  const preds: string[] = [
    "pr.deleted_at IS NULL",
    "pr.content_type != 'photo_release'",
  ];
  const params: unknown[] = [];
  const push = (pred: string, value: unknown) => {
    params.push(value);
    preds.push(pred.replace("$?", `$${params.length}`));
  };

  if (search) push("pr.fts @@ plainto_tsquery('english', $?)", search);
  if (party) push("s.party = $?", party);
  if (state) push("s.state = $?", state);
  if (senator) push("pr.senator_id = $?", senator);
  if (ctype) push("pr.content_type = $?", ctype);

  const where = preds.join(" AND ");
  params.push(perPage);
  const limitIdx = `$${params.length}`;
  params.push(offset);
  const offsetIdx = `$${params.length}`;

  const countText = `SELECT count(*)::int AS total FROM press_releases pr JOIN senators s ON s.id = pr.senator_id WHERE ${where}`;
  const itemsText = `SELECT ${FEED_COLUMNS} FROM press_releases pr JOIN senators s ON s.id = pr.senator_id WHERE ${where} ORDER BY pr.published_at DESC NULLS LAST LIMIT ${limitIdx} OFFSET ${offsetIdx}`;

  // Count query uses only the filter params; items query uses all of them.
  const countParams = params.slice(0, params.length - 2);
  const [countResult, items] = await Promise.all([
    sql.query(countText, countParams),
    sql.query(itemsText, params),
  ]);
  return {
    items: items as FeedItem[],
    total: Number((countResult as { total: number }[])[0].total),
  };
}

export async function getSenators(): Promise<SenatorWithCount[]> {
  const base = (await sql`
    SELECT s.*,
           count(pr.id)::int as release_count,
           max(pr.published_at) as latest_release,
           min(pr.published_at) as earliest_release
    FROM senators s
    LEFT JOIN press_releases pr ON pr.senator_id = s.id AND pr.deleted_at IS NULL AND pr.content_type != 'photo_release'
    WHERE s.status = 'active' AND s.chamber = 'senate'
    GROUP BY s.id
    ORDER BY s.state, s.full_name
  `) as (SenatorWithCount & { type_breakdown: never })[];

  const rows = (await sql`
    SELECT pr.senator_id, pr.content_type, count(*)::int as count
    FROM press_releases pr
    JOIN senators s ON s.id = pr.senator_id
    WHERE pr.deleted_at IS NULL AND pr.content_type != 'photo_release'
      AND s.status = 'active'
      AND s.chamber = 'senate'
    GROUP BY pr.senator_id, pr.content_type
  `) as { senator_id: string; content_type: ContentType; count: number }[];

  const breakdown = new Map<string, TypeBreakdown>();
  for (const r of rows) {
    const b = breakdown.get(r.senator_id) ?? {};
    b[r.content_type] = r.count;
    breakdown.set(r.senator_id, b);
  }

  return base.map((s) => ({
    ...s,
    type_breakdown: breakdown.get(s.id) ?? {},
  }));
}

export async function getSenator(id: string): Promise<Senator | null> {
  const rows = await sql`SELECT * FROM senators WHERE id = ${id}`;
  return (rows[0] as Senator) ?? null;
}

export async function getSenatorReleases(
  senatorId: string,
  page = 1,
  perPage = 25,
  type?: string
): Promise<{ items: PressRelease[]; total: number }> {
  const offset = (page - 1) * perPage;
  const ctype = normalizeType(type);

  if (ctype) {
    const countResult = await sql`SELECT count(*) as total FROM press_releases WHERE senator_id = ${senatorId} AND deleted_at IS NULL AND content_type = ${ctype}`;
    const items = (await sql`
      SELECT * FROM press_releases
      WHERE senator_id = ${senatorId} AND deleted_at IS NULL AND content_type = ${ctype}
      ORDER BY published_at DESC NULLS LAST
      LIMIT ${perPage} OFFSET ${offset}
    `) as PressRelease[];
    return { items, total: Number(countResult[0].total) };
  }

  const countResult = await sql`SELECT count(*) as total FROM press_releases WHERE senator_id = ${senatorId} AND deleted_at IS NULL AND content_type != 'photo_release'`;
  const items = (await sql`
    SELECT * FROM press_releases WHERE senator_id = ${senatorId} AND deleted_at IS NULL AND content_type != 'photo_release'
    ORDER BY published_at DESC NULLS LAST
    LIMIT ${perPage} OFFSET ${offset}
  `) as PressRelease[];
  return { items, total: Number(countResult[0].total) };
}

export async function getSenatorTypeBreakdown(
  senatorId: string
): Promise<{ breakdown: TypeBreakdown; earliest: string | null }> {
  const rows = (await sql`
    SELECT content_type, count(*)::int as count, min(published_at) as earliest
    FROM press_releases
    WHERE senator_id = ${senatorId} AND deleted_at IS NULL AND content_type != 'photo_release'
    GROUP BY content_type
  `) as { content_type: ContentType; count: number; earliest: string | null }[];

  const breakdown: TypeBreakdown = {};
  let earliest: string | null = null;
  for (const r of rows) {
    breakdown[r.content_type] = r.count;
    if (r.earliest && (!earliest || r.earliest < earliest)) earliest = r.earliest;
  }
  return { breakdown, earliest };
}

export async function getStats() {
  const result = await sql`
    SELECT
      count(DISTINCT pr.id)::int as total_releases,
      count(DISTINCT pr.senator_id)::int as senators_with_releases,
      count(DISTINCT s.id)::int as total_senators,
      min(pr.published_at) as earliest,
      max(pr.published_at) as latest
    FROM senators s
    LEFT JOIN press_releases pr ON pr.senator_id = s.id AND pr.deleted_at IS NULL AND pr.content_type != 'photo_release'
    WHERE s.status = 'active' AND s.chamber = 'senate'
  `;
  return result[0];
}

export async function getPartyBreakdown() {
  return sql`
    SELECT s.party, count(pr.id)::int as count
    FROM press_releases pr
    JOIN senators s ON s.id = pr.senator_id
    WHERE pr.deleted_at IS NULL AND pr.content_type != 'photo_release'
    GROUP BY s.party
    ORDER BY count DESC
  `;
}

export async function getWeeklyVolume() {
  return sql`
    SELECT date_trunc('week', published_at)::date as week,
           count(*)::int as count
    FROM press_releases
    WHERE published_at IS NOT NULL
      AND deleted_at IS NULL
      AND content_type != 'photo_release'
    GROUP BY week
    ORDER BY week
  `;
}

export async function getTopSenators(limit = 10) {
  return sql`
    SELECT s.full_name, s.party, s.state, s.id,
           count(pr.id)::int as count
    FROM press_releases pr
    JOIN senators s ON s.id = pr.senator_id
    WHERE pr.deleted_at IS NULL AND pr.content_type != 'photo_release'
      AND s.status = 'active'
      AND s.chamber = 'senate'
    GROUP BY s.id, s.full_name, s.party, s.state
    ORDER BY count DESC
    LIMIT ${limit}
  `;
}

export async function getLeastActiveSenators(limit = 10) {
  return sql`
    SELECT s.full_name, s.party, s.state, s.id,
           count(pr.id)::int as count,
           max(pr.published_at) as last_release
    FROM senators s
    LEFT JOIN press_releases pr ON s.id = pr.senator_id AND pr.deleted_at IS NULL AND pr.content_type != 'photo_release'
    WHERE s.collection_method IS NOT NULL
      AND s.status = 'active'
    GROUP BY s.id, s.full_name, s.party, s.state
    ORDER BY count ASC
    LIMIT ${limit}
  `;
}

// getStates moved to ./states.ts to avoid client-side neon() evaluation
export { getStates } from "./states";

/**
 * Stable label / style metadata for each content_type. Centralized so the badge
 * on the feed card, the filter chip, and the per-senator breakdown all render
 * consistently.
 */
export const CONTENT_TYPE_LABEL: Record<ContentType, string> = {
  press_release: "Press release",
  statement: "Statement",
  op_ed: "Op-ed",
  letter: "Letter",
  photo_release: "Photo release",
  floor_statement: "Floor statement",
  presidential_action: "Presidential action",
  other: "Other",
};

export const CONTENT_TYPE_LABEL_SHORT: Record<ContentType, string> = {
  press_release: "Press",
  statement: "Statement",
  op_ed: "Op-ed",
  letter: "Letter",
  photo_release: "Photo",
  floor_statement: "Floor",
  presidential_action: "Pres. action",
  other: "Other",
};

export const CONTENT_TYPE_PLURAL: Record<ContentType, string> = {
  press_release: "press releases",
  statement: "statements",
  op_ed: "op-eds",
  letter: "letters",
  photo_release: "photo releases",
  floor_statement: "floor statements",
  presidential_action: "presidential actions",
  other: "other",
};

/** Display order for filter chips + breakdowns. Press release leads.
 *  photo_release is intentionally omitted -- it's excluded from every UI surface. */
export type LatestRun = {
  id: string;
  started_at: string;
  finished_at: string | null;
  inserted: number;
  senators_with_new: number;
  senators_processed: number;
  errors: number;
};

export async function getLatestRun(): Promise<LatestRun | null> {
  const rows = (await sql`
    SELECT id,
           started_at,
           finished_at,
           COALESCE((stats->>'total_inserted')::int, 0)    AS inserted,
           COALESCE((stats->>'senators_with_new')::int, 0) AS senators_with_new,
           COALESCE((stats->>'senators_processed')::int, 0) AS senators_processed,
           COALESCE((stats->>'total_errors')::int, 0)      AS errors
    FROM scrape_runs
    WHERE run_type = 'daily' AND finished_at IS NOT NULL
    ORDER BY finished_at DESC
    LIMIT 1
  `) as LatestRun[];
  return rows[0] ?? null;
}

export async function getRecentRuns(limit = 30): Promise<LatestRun[]> {
  return (await sql`
    SELECT id,
           started_at,
           finished_at,
           COALESCE((stats->>'total_inserted')::int, 0)    AS inserted,
           COALESCE((stats->>'senators_with_new')::int, 0) AS senators_with_new,
           COALESCE((stats->>'senators_processed')::int, 0) AS senators_processed,
           COALESCE((stats->>'total_errors')::int, 0)      AS errors
    FROM scrape_runs
    WHERE run_type = 'daily'
    ORDER BY started_at DESC
    LIMIT ${limit}
  `) as LatestRun[];
}

export const CONTENT_TYPE_ORDER: ContentType[] = [
  "press_release",
  "statement",
  "op_ed",
  "letter",
  "floor_statement",
  "presidential_action",
  "other",
];

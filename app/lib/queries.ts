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
  "blog",
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

// Sort key that defends against upstream date typos (e.g. a senator's
// office putting "May 04" on a release captured April 28). The display
// date stays whatever the office published, but ordering uses the lesser
// of {published_at, scraped_at} so a future-dated outlier can't pin to the
// top of /feed or the homepage hero. A release we captured today can't
// truly have been published in the future, regardless of what their meta
// tag claims.
const EFFECTIVE_DATE_SQL = `LEAST(pr.published_at, pr.scraped_at)`;

export type FeedFilters = {
  page?: number;
  perPage?: number;
  party?: string;
  state?: string;
  senator?: string;
  search?: string;
  type?: string;
  from?: string;
  to?: string;
  sort?: "date" | "relevance";
};

export type SearchFeedItem = FeedItem & { snippet?: string | null };

function buildFeedPredicates(f: FeedFilters): {
  preds: string[];
  params: unknown[];
} {
  const preds: string[] = [
    "pr.deleted_at IS NULL",
    "pr.content_type != 'photo_release'",
    "s.status = 'active'",
    "s.chamber = 'senate'",
  ];
  const params: unknown[] = [];
  const push = (pred: string, value: unknown) => {
    params.push(value);
    preds.push(pred.replace("$?", `$${params.length}`));
  };
  const ctype = normalizeType(f.type);
  if (f.search) push("pr.fts @@ plainto_tsquery('english', $?)", f.search);
  if (f.party) push("s.party = $?", f.party);
  if (f.state) push("s.state = $?", f.state);
  if (f.senator) push("pr.senator_id = $?", f.senator);
  if (ctype) push("pr.content_type = $?", ctype);
  if (f.from) push("pr.published_at >= $?::date", f.from);
  if (f.to) push("pr.published_at < ($?::date + INTERVAL '1 day')", f.to);
  return { preds, params };
}

export async function getFeed(
  f: FeedFilters = {}
): Promise<{ items: SearchFeedItem[]; total: number }> {
  const page = f.page ?? 1;
  const perPage = f.perPage ?? 25;
  const offset = (page - 1) * perPage;
  const sort = f.sort ?? "date";
  const wantSnippet = Boolean(f.search);

  const { preds, params } = buildFeedPredicates(f);
  const where = preds.join(" AND ");

  const cols = wantSnippet
    ? `${FEED_COLUMNS},
       ts_headline('english', COALESCE(pr.body_text, ''),
         plainto_tsquery('english', $1),
         'StartSel=<mark>,StopSel=</mark>,MaxFragments=2,MaxWords=18,MinWords=6,ShortWord=3,FragmentDelimiter=" \u2026 "'
       ) AS snippet`
    : FEED_COLUMNS;

  const orderBy =
    sort === "relevance" && f.search
      ? `ts_rank(pr.fts, plainto_tsquery('english', $1)) DESC, ${EFFECTIVE_DATE_SQL} DESC NULLS LAST`
      : `${EFFECTIVE_DATE_SQL} DESC NULLS LAST`;

  params.push(perPage);
  const limitIdx = `$${params.length}`;
  params.push(offset);
  const offsetIdx = `$${params.length}`;

  const countText = `SELECT count(*)::int AS total FROM press_releases pr JOIN senators s ON s.id = pr.senator_id WHERE ${where}`;
  const itemsText = `SELECT ${cols} FROM press_releases pr JOIN senators s ON s.id = pr.senator_id WHERE ${where} ORDER BY ${orderBy} LIMIT ${limitIdx} OFFSET ${offsetIdx}`;

  const countParams = params.slice(0, params.length - 2);
  const [countResult, items] = await Promise.all([
    sql.query(countText, countParams),
    sql.query(itemsText, params),
  ]);
  return {
    items: items as SearchFeedItem[],
    total: Number((countResult as { total: number }[])[0].total),
  };
}

export type SearchFacets = {
  party: { D: number; R: number; I: number };
  type: Partial<Record<ContentType, number>>;
  state: { state: string; count: number }[];
};

export async function getSearchFacets(
  f: FeedFilters
): Promise<SearchFacets> {
  // Facet counts ignore the facet's own filter — we want "if you removed
  // this filter, here's the count". For party facet, we omit party from
  // the predicate, etc.
  async function countBy(omit: keyof FeedFilters, groupCol: string) {
    const filtered: FeedFilters = { ...f, [omit]: undefined };
    const { preds, params } = buildFeedPredicates(filtered);
    const where = preds.join(" AND ");
    const text = `SELECT ${groupCol} as key, count(*)::int as count FROM press_releases pr JOIN senators s ON s.id = pr.senator_id WHERE ${where} GROUP BY ${groupCol}`;
    return (await sql.query(text, params)) as { key: string; count: number }[];
  }

  const [partyRows, typeRows, stateRows] = await Promise.all([
    countBy("party", "s.party"),
    countBy("type", "pr.content_type"),
    countBy("state", "s.state"),
  ]);

  const party = { D: 0, R: 0, I: 0 };
  for (const r of partyRows) {
    if (r.key === "D" || r.key === "R" || r.key === "I") {
      party[r.key] = r.count;
    }
  }
  const type: Partial<Record<ContentType, number>> = {};
  for (const r of typeRows) {
    if (r.key && r.key !== EXCLUDED_FROM_UI) {
      type[r.key as ContentType] = r.count;
    }
  }
  const state = stateRows
    .filter((r) => r.key)
    .sort((a, b) => b.count - a.count)
    .map((r) => ({ state: r.key, count: r.count }));

  return { party, type, state };
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

export type ReleaseDetail = FeedItem & {
  deleted_at: string | null;
  last_seen_live: string | null;
  updated_at: string | null;
  version_count: number;
};

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export async function getReleaseById(
  id: string
): Promise<ReleaseDetail | null> {
  if (!UUID_RE.test(id)) return null;
  const rows = await sql`
    SELECT pr.id, pr.senator_id, pr.title, pr.published_at, pr.body_text,
           pr.source_url, pr.scraped_at, pr.content_type,
           pr.deleted_at, pr.last_seen_live, pr.updated_at,
           s.full_name as senator_name, s.party, s.state,
           (SELECT count(*)::int FROM content_versions cv WHERE cv.press_release_id = pr.id) as version_count
    FROM press_releases pr
    JOIN senators s ON s.id = pr.senator_id
    WHERE pr.id = ${id}
  `;
  return (rows[0] as ReleaseDetail) ?? null;
}

export type ReleaseVersion = {
  id: number;
  press_release_id: string;
  body_text: string | null;
  content_hash: string | null;
  captured_at: string;
};

export async function getReleaseVersions(
  releaseId: string
): Promise<ReleaseVersion[]> {
  if (!UUID_RE.test(releaseId)) return [];
  const rows = await sql`
    SELECT id, press_release_id, body_text, content_hash, captured_at
    FROM content_versions
    WHERE press_release_id = ${releaseId}
    ORDER BY captured_at DESC
  `;
  return rows as ReleaseVersion[];
}

export async function getRelatedReleases(
  release: { id: string; published_at: string | null; senator_id: string },
  limit = 6
): Promise<FeedItem[]> {
  if (!release.published_at) return [];
  const text = `
    SELECT ${FEED_COLUMNS}
    FROM press_releases pr
    JOIN senators s ON s.id = pr.senator_id
    WHERE pr.deleted_at IS NULL
      AND pr.content_type != 'photo_release'
      AND s.status = 'active'
      AND s.chamber = 'senate'
      AND pr.id != $1
      AND pr.senator_id != $2
      AND pr.published_at IS NOT NULL
      AND pr.published_at BETWEEN ($3::timestamptz - INTERVAL '24 hours')
                              AND ($3::timestamptz + INTERVAL '24 hours')
    ORDER BY ABS(EXTRACT(EPOCH FROM (pr.published_at - $3::timestamptz)))
    LIMIT $4
  `;
  const rows = await sql.query(text, [
    release.id,
    release.senator_id,
    release.published_at,
    limit,
  ]);
  return rows as FeedItem[];
}

export async function getReleaseIdsForSitemap(
  offset: number,
  limit: number
): Promise<{ id: string; updated_at: string | null; published_at: string | null }[]> {
  const rows = await sql`
    SELECT pr.id, pr.updated_at, pr.published_at
    FROM press_releases pr
    JOIN senators s ON s.id = pr.senator_id
    WHERE pr.deleted_at IS NULL
      AND pr.content_type != 'photo_release'
      AND s.status = 'active'
      AND s.chamber = 'senate'
    ORDER BY pr.published_at DESC NULLS LAST
    LIMIT ${limit} OFFSET ${offset}
  `;
  return rows as { id: string; updated_at: string | null; published_at: string | null }[];
}

export async function getReleaseCountForSitemap(): Promise<number> {
  const rows = await sql`
    SELECT count(*)::int as total
    FROM press_releases pr
    JOIN senators s ON s.id = pr.senator_id
    WHERE pr.deleted_at IS NULL
      AND pr.content_type != 'photo_release'
      AND s.status = 'active'
      AND s.chamber = 'senate'
  `;
  return Number((rows[0] as { total: number }).total);
}

export async function getActiveSenatorIds(): Promise<string[]> {
  const rows = await sql`
    SELECT id FROM senators WHERE status = 'active' AND chamber = 'senate' ORDER BY id
  `;
  return rows.map((r) => (r as { id: string }).id);
}

export async function getDeletedReleases(
  page = 1,
  perPage = 50
): Promise<{ items: ReleaseDetail[]; total: number }> {
  const offset = (page - 1) * perPage;
  const countResult = await sql`
    SELECT count(*)::int as total FROM press_releases pr
    JOIN senators s ON s.id = pr.senator_id
    WHERE pr.deleted_at IS NOT NULL
      AND pr.content_type != 'photo_release'
      AND s.status = 'active'
      AND s.chamber = 'senate'
  `;
  const items = await sql`
    SELECT pr.id, pr.senator_id, pr.title, pr.published_at, pr.body_text,
           pr.source_url, pr.scraped_at, pr.content_type,
           pr.deleted_at, pr.last_seen_live, pr.updated_at,
           s.full_name as senator_name, s.party, s.state,
           0 as version_count
    FROM press_releases pr
    JOIN senators s ON s.id = pr.senator_id
    WHERE pr.deleted_at IS NOT NULL
      AND pr.content_type != 'photo_release'
      AND s.status = 'active'
      AND s.chamber = 'senate'
    ORDER BY pr.deleted_at DESC
    LIMIT ${perPage} OFFSET ${offset}
  `;
  return {
    items: items as ReleaseDetail[],
    total: Number(countResult[0].total),
  };
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
      ORDER BY LEAST(published_at, scraped_at) DESC NULLS LAST
      LIMIT ${perPage} OFFSET ${offset}
    `) as PressRelease[];
    return { items, total: Number(countResult[0].total) };
  }

  const countResult = await sql`SELECT count(*) as total FROM press_releases WHERE senator_id = ${senatorId} AND deleted_at IS NULL AND content_type != 'photo_release'`;
  const items = (await sql`
    SELECT * FROM press_releases WHERE senator_id = ${senatorId} AND deleted_at IS NULL AND content_type != 'photo_release'
    ORDER BY LEAST(published_at, scraped_at) DESC NULLS LAST
    LIMIT ${perPage} OFFSET ${offset}
  `) as PressRelease[];
  return { items, total: Number(countResult[0].total) };
}

export async function getSenatorSections(
  senatorId: string
): Promise<{ url: string; count: number; label: string }[]> {
  const rows = (await sql`
    WITH paths AS (
      SELECT
        regexp_replace(source_url, '^(https?://[^/]+/[^/]+(?:/[^/]+)?/).*$', '\\1') AS section_url,
        source_url
      FROM press_releases
      WHERE senator_id = ${senatorId} AND deleted_at IS NULL
    )
    SELECT section_url AS url, count(*)::int AS count
    FROM paths
    WHERE section_url ~ '/(press|news|newsroom|op|letters|releases|briefings|presidential)'
    GROUP BY section_url
    HAVING count(*) >= 5
    ORDER BY count(*) DESC
    LIMIT 6
  `) as { url: string; count: number }[];

  return rows.map((r) => {
    const path = r.url.replace(/^https?:\/\/[^/]+/, "").replace(/\/$/, "");
    const last = path.split("/").filter(Boolean).pop() ?? path;
    const label = last
      .replace(/-/g, " ")
      .replace(/\b\w/g, (c) => c.toUpperCase());
    return { url: r.url, count: r.count, label };
  });
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
      AND s.chamber = 'senate'
    GROUP BY s.id, s.full_name, s.party, s.state
    ORDER BY count ASC
    LIMIT ${limit}
  `;
}

// Content-type display metadata moved to ./content-types.ts so client
// components can import without dragging in the DB runtime.
export {
  CONTENT_TYPE_LABEL,
  CONTENT_TYPE_PLURAL,
  CONTENT_TYPE_ORDER,
} from "./content-types";

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


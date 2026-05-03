import { sql } from "./db";
import type {
  FeedItem,
  SenatorWithCount,
  PressRelease,
  Senator,
  ContentType,
  TypeBreakdown,
  Brief,
  BriefCitation,
  SocialFeedItem,
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
const FEED_COLUMNS = `pr.id, pr.official_id, pr.title, pr.published_at, pr.body_text, pr.source_url, pr.scraped_at, pr.content_type, s.full_name as senator_name, s.party, s.state`;

// Sort key that defends against upstream date typos (e.g. a senator's
// office putting "May 04" on a release captured April 28). The display
// date stays whatever the office published, but ordering uses the lesser
// of {published_at, scraped_at} so a future-dated outlier can't pin to the
// top of /feed or the homepage hero. A release we captured today can't
// truly have been published in the future, regardless of what their meta
// tag claims.
const EFFECTIVE_DATE_SQL = `LEAST(pr.published_at, pr.scraped_at)`;

export type RosterScope = "us-congress" | "us-senate" | "us-house" | "tx-senate";

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
  // Roster scope. Defaults to "us-congress" (US Senate + US House). Set to
  // "us-senate" / "us-house" to narrow to one chamber, or "tx-senate" for
  // the Texas state corpus. Single point of override so /texas/* feeds and
  // chamber-filter pills reuse all the existing query logic. Post-2026-05-02
  // schema: state legislators sit under (chamber, jurisdiction); the legacy
  // overloaded chamber='tx_senate' value was normalized away in migration 012.
  roster?: RosterScope;
};

export type SearchFeedItem = FeedItem & { snippet?: string | null };

function buildFeedPredicates(f: FeedFilters): {
  preds: string[];
  params: unknown[];
} {
  const roster = f.roster ?? "us-congress";
  const preds: string[] = [
    "pr.deleted_at IS NULL",
    "pr.content_type != 'photo_release'",
    "s.status = 'active'",
  ];
  const params: unknown[] = [];
  const push = (pred: string, value: unknown) => {
    params.push(value);
    preds.push(pred.replace("$?", `$${params.length}`));
  };
  // Search MUST be pushed first so its parameter is $1 — getFeed builds a
  // ts_headline snippet column referencing $1 by index. The chamber filter
  // and any other facets follow.
  if (f.search) push("pr.fts @@ plainto_tsquery('english', $?)", f.search);
  // Roster scope. us-congress fans across both chambers; the others pin to
  // one. Keeping these as a literal IN list (no parameter) is intentional —
  // it lets the planner use the chamber index and matches the shape of
  // the existing single-chamber predicate.
  if (roster === "us-congress") {
    preds.push("s.chamber IN ('senate','house')");
    preds.push("s.jurisdiction = 'us'");
  } else if (roster === "us-house") {
    preds.push("s.chamber = 'house'");
    preds.push("s.jurisdiction = 'us'");
  } else if (roster === "tx-senate") {
    preds.push("s.chamber = 'senate'");
    preds.push("s.jurisdiction = 'tx'");
  } else {
    // us-senate
    preds.push("s.chamber = 'senate'");
    preds.push("s.jurisdiction = 'us'");
  }
  const ctype = normalizeType(f.type);
  if (f.party) push("s.party = $?", f.party);
  if (f.state) push("s.state = $?", f.state);
  if (f.senator) push("pr.official_id = $?", f.senator);
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

  const countText = `SELECT count(*)::int AS total FROM official_site_items pr JOIN officials s ON s.id = pr.official_id WHERE ${where}`;
  const itemsText = `SELECT ${cols} FROM official_site_items pr JOIN officials s ON s.id = pr.official_id WHERE ${where} ORDER BY ${orderBy} LIMIT ${limitIdx} OFFSET ${offsetIdx}`;

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
    const text = `SELECT ${groupCol} as key, count(*)::int as count FROM official_site_items pr JOIN officials s ON s.id = pr.official_id WHERE ${where} GROUP BY ${groupCol}`;
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
    FROM officials s
    LEFT JOIN official_site_items pr ON pr.official_id = s.id AND pr.deleted_at IS NULL AND pr.content_type != 'photo_release'
    WHERE s.status = 'active' AND s.chamber = 'senate' AND s.jurisdiction = 'us'
    GROUP BY s.id
    ORDER BY s.state, s.full_name
  `) as (SenatorWithCount & { type_breakdown: never })[];

  const rows = (await sql`
    SELECT pr.official_id, pr.content_type, count(*)::int as count
    FROM official_site_items pr
    JOIN officials s ON s.id = pr.official_id
    WHERE pr.deleted_at IS NULL AND pr.content_type != 'photo_release'
      AND s.status = 'active'
      AND s.chamber = 'senate' AND s.jurisdiction = 'us'
    GROUP BY pr.official_id, pr.content_type
  `) as { official_id: string; content_type: ContentType; count: number }[];

  const breakdown = new Map<string, TypeBreakdown>();
  for (const r of rows) {
    const b = breakdown.get(r.official_id) ?? {};
    b[r.content_type] = r.count;
    breakdown.set(r.official_id, b);
  }

  return base.map((s) => ({
    ...s,
    type_breakdown: breakdown.get(s.id) ?? {},
  }));
}

export async function getSenator(id: string): Promise<Senator | null> {
  // Hard-scope to chamber='senate' so /senators/[id] cannot render a House,
  // executive, or state-chamber member as a US senator. Other chambers have
  // their own routes (e.g. /texas/[id], /house/[id]); this loader is
  // US-Senate-only.
  const rows = await sql`
    SELECT * FROM officials
    WHERE id = ${id}
      AND chamber = 'senate' AND jurisdiction = 'us'
  `;
  return (rows[0] as Senator) ?? null;
}

export async function getHouseMember(id: string): Promise<Senator | null> {
  // Mirror of getSenator() for US House. Hard-scoped so /house/[id]
  // cannot render a state-house member as a US Rep.
  const rows = await sql`
    SELECT * FROM officials
    WHERE id = ${id}
      AND chamber = 'house'
      AND jurisdiction = 'us'
  `;
  return (rows[0] as Senator) ?? null;
}

export async function getHouseMembers(): Promise<SenatorWithCount[]> {
  // US House roster with per-member release counts. Mirrors getSenators()
  // shape so the same downstream rendering helpers work.
  const base = (await sql`
    SELECT s.*,
           count(pr.id)::int as release_count,
           max(pr.published_at) as latest_release,
           min(pr.published_at) as earliest_release
    FROM officials s
    LEFT JOIN official_site_items pr
      ON pr.official_id = s.id
     AND pr.deleted_at IS NULL
     AND pr.content_type != 'photo_release'
    WHERE s.status = 'active'
      AND s.chamber = 'house'
      AND s.jurisdiction = 'us'
    GROUP BY s.id
    ORDER BY s.state, s.district NULLS LAST, s.full_name
  `) as (SenatorWithCount & { type_breakdown: never })[];

  const rows = (await sql`
    SELECT pr.official_id, pr.content_type, count(*)::int as count
    FROM official_site_items pr
    JOIN officials s ON s.id = pr.official_id
    WHERE pr.deleted_at IS NULL
      AND pr.content_type != 'photo_release'
      AND s.status = 'active'
      AND s.chamber = 'house'
      AND s.jurisdiction = 'us'
    GROUP BY pr.official_id, pr.content_type
  `) as { official_id: string; content_type: ContentType; count: number }[];

  const breakdown = new Map<string, TypeBreakdown>();
  for (const r of rows) {
    const b = breakdown.get(r.official_id) ?? {};
    b[r.content_type] = r.count;
    breakdown.set(r.official_id, b);
  }

  return base.map((s) => ({
    ...s,
    type_breakdown: breakdown.get(s.id) ?? {},
  }));
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
    SELECT pr.id, pr.official_id, pr.title, pr.published_at, pr.body_text,
           pr.source_url, pr.scraped_at, pr.content_type,
           pr.deleted_at, pr.last_seen_live, pr.updated_at,
           s.full_name as senator_name, s.party, s.state,
           (SELECT count(*)::int FROM content_versions cv WHERE cv.official_site_item_id = pr.id) as version_count
    FROM official_site_items pr
    JOIN officials s ON s.id = pr.official_id
    WHERE pr.id = ${id}
  `;
  return (rows[0] as ReleaseDetail) ?? null;
}

export type ReleaseVersion = {
  id: number;
  official_site_item_id: string;
  body_text: string | null;
  content_hash: string | null;
  captured_at: string;
};

export async function getReleaseVersions(
  releaseId: string
): Promise<ReleaseVersion[]> {
  if (!UUID_RE.test(releaseId)) return [];
  const rows = await sql`
    SELECT id, official_site_item_id, body_text, content_hash, captured_at
    FROM content_versions
    WHERE official_site_item_id = ${releaseId}
    ORDER BY captured_at DESC
  `;
  return rows as ReleaseVersion[];
}

export async function getRelatedReleases(
  release: { id: string; published_at: string | null; official_id: string },
  limit = 6
): Promise<FeedItem[]> {
  if (!release.published_at) return [];
  // Scope "related" to the same chamber AND jurisdiction the release came
  // from. Without the jurisdiction match, a US-Senate release could pull
  // a TX state-senator release as "related" because both are chamber=senate.
  // Pinning to (chamber, jurisdiction) keeps the editorial frame honest —
  // "what else was happening in the same body."
  const text = `
    SELECT ${FEED_COLUMNS}
    FROM official_site_items pr
    JOIN officials s ON s.id = pr.official_id
    JOIN officials rel ON rel.id = $2
    WHERE pr.deleted_at IS NULL
      AND pr.content_type != 'photo_release'
      AND s.status = 'active'
      AND s.chamber = rel.chamber
      AND s.jurisdiction = rel.jurisdiction
      AND pr.id != $1
      AND pr.official_id != $2
      AND pr.published_at IS NOT NULL
      AND pr.published_at BETWEEN ($3::timestamptz - INTERVAL '24 hours')
                              AND ($3::timestamptz + INTERVAL '24 hours')
    ORDER BY ABS(EXTRACT(EPOCH FROM (pr.published_at - $3::timestamptz)))
    LIMIT $4
  `;
  const rows = await sql.query(text, [
    release.id,
    release.official_id,
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
    FROM official_site_items pr
    JOIN officials s ON s.id = pr.official_id
    WHERE pr.deleted_at IS NULL
      AND pr.content_type != 'photo_release'
      AND s.status = 'active'
      AND s.chamber IN ('senate','house')
      AND s.jurisdiction = 'us'
    ORDER BY pr.published_at DESC NULLS LAST
    LIMIT ${limit} OFFSET ${offset}
  `;
  return rows as { id: string; updated_at: string | null; published_at: string | null }[];
}

export async function getReleaseCountForSitemap(): Promise<number> {
  const rows = await sql`
    SELECT count(*)::int as total
    FROM official_site_items pr
    JOIN officials s ON s.id = pr.official_id
    WHERE pr.deleted_at IS NULL
      AND pr.content_type != 'photo_release'
      AND s.status = 'active'
      AND s.chamber IN ('senate','house')
      AND s.jurisdiction = 'us'
  `;
  return Number((rows[0] as { total: number }).total);
}

export async function getActiveSenatorIds(
  scope: RosterScope = "us-congress"
): Promise<string[]> {
  // Post-2026-05-02 schema: members live under (chamber, jurisdiction).
  // The legacy chamber='tx_senate' value was normalized away in migration 012;
  // every Texas state senator is now (chamber='senate', jurisdiction='tx').
  if (scope === "us-congress") {
    const rows = await sql`
      SELECT id FROM officials
      WHERE status = 'active'
        AND chamber IN ('senate','house')
        AND jurisdiction = 'us'
      ORDER BY id
    `;
    return rows.map((r) => (r as { id: string }).id);
  }
  const [chamber, jurisdiction] =
    scope === "tx-senate"
      ? ["senate", "tx"]
      : scope === "us-house"
        ? ["house", "us"]
        : ["senate", "us"];
  const rows = await sql`
    SELECT id FROM officials
    WHERE status = 'active'
      AND chamber = ${chamber}
      AND jurisdiction = ${jurisdiction}
    ORDER BY id
  `;
  return rows.map((r) => (r as { id: string }).id);
}

export async function getDeletedReleases(
  page = 1,
  perPage = 50
): Promise<{ items: ReleaseDetail[]; total: number }> {
  const offset = (page - 1) * perPage;
  const countResult = await sql`
    SELECT count(*)::int as total FROM official_site_items pr
    JOIN officials s ON s.id = pr.official_id
    WHERE pr.deleted_at IS NOT NULL
      AND pr.content_type != 'photo_release'
      AND s.status = 'active'
      AND s.chamber IN ('senate','house')
      AND s.jurisdiction = 'us'
  `;
  const items = await sql`
    SELECT pr.id, pr.official_id, pr.title, pr.published_at, pr.body_text,
           pr.source_url, pr.scraped_at, pr.content_type,
           pr.deleted_at, pr.last_seen_live, pr.updated_at,
           s.full_name as senator_name, s.party, s.state,
           0 as version_count
    FROM official_site_items pr
    JOIN officials s ON s.id = pr.official_id
    WHERE pr.deleted_at IS NOT NULL
      AND pr.content_type != 'photo_release'
      AND s.status = 'active'
      AND s.chamber IN ('senate','house')
      AND s.jurisdiction = 'us'
    ORDER BY pr.deleted_at DESC
    LIMIT ${perPage} OFFSET ${offset}
  `;
  return {
    items: items as ReleaseDetail[],
    total: Number(countResult[0].total),
  };
}

export async function getSenatorReleases(
  officialId: string,
  page = 1,
  perPage = 25,
  type?: string
): Promise<{ items: PressRelease[]; total: number }> {
  const offset = (page - 1) * perPage;
  const ctype = normalizeType(type);

  if (ctype) {
    const countResult = await sql`SELECT count(*) as total FROM official_site_items WHERE official_id = ${officialId} AND deleted_at IS NULL AND content_type = ${ctype}`;
    const items = (await sql`
      SELECT * FROM official_site_items
      WHERE official_id = ${officialId} AND deleted_at IS NULL AND content_type = ${ctype}
      ORDER BY LEAST(published_at, scraped_at) DESC NULLS LAST
      LIMIT ${perPage} OFFSET ${offset}
    `) as PressRelease[];
    return { items, total: Number(countResult[0].total) };
  }

  const countResult = await sql`SELECT count(*) as total FROM official_site_items WHERE official_id = ${officialId} AND deleted_at IS NULL AND content_type != 'photo_release'`;
  const items = (await sql`
    SELECT * FROM official_site_items WHERE official_id = ${officialId} AND deleted_at IS NULL AND content_type != 'photo_release'
    ORDER BY LEAST(published_at, scraped_at) DESC NULLS LAST
    LIMIT ${perPage} OFFSET ${offset}
  `) as PressRelease[];
  return { items, total: Number(countResult[0].total) };
}

export async function getSenatorSections(
  officialId: string
): Promise<{ url: string; count: number; label: string }[]> {
  const rows = (await sql`
    WITH paths AS (
      SELECT
        regexp_replace(source_url, '^(https?://[^/]+/[^/]+(?:/[^/]+)?/).*$', '\\1') AS section_url,
        source_url
      FROM official_site_items
      WHERE official_id = ${officialId} AND deleted_at IS NULL
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
  officialId: string
): Promise<{ breakdown: TypeBreakdown; earliest: string | null }> {
  const rows = (await sql`
    SELECT content_type, count(*)::int as count, min(published_at) as earliest
    FROM official_site_items
    WHERE official_id = ${officialId} AND deleted_at IS NULL AND content_type != 'photo_release'
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

// Homepage corpus stats. Cross-chamber federal — both US Senate and US House.
// Senate-only and House-only chamber pages have their own dedicated queries
// (getSenators / getHouseMembers) that include per-member breakdowns.
export async function getStats() {
  const result = await sql`
    SELECT
      count(DISTINCT pr.id)::int as total_releases,
      count(DISTINCT pr.official_id)::int as senators_with_releases,
      count(DISTINCT s.id)::int as total_senators,
      count(DISTINCT s.id) FILTER (WHERE s.chamber = 'senate')::int as senate_count,
      count(DISTINCT s.id) FILTER (WHERE s.chamber = 'house')::int as house_count,
      min(pr.published_at) as earliest,
      max(pr.published_at) as latest
    FROM officials s
    LEFT JOIN official_site_items pr ON pr.official_id = s.id AND pr.deleted_at IS NULL AND pr.content_type != 'photo_release'
    WHERE s.status = 'active'
      AND s.chamber IN ('senate','house')
      AND s.jurisdiction = 'us'
  `;
  return result[0];
}

export async function getTopSenators(limit = 10) {
  return sql`
    SELECT s.full_name, s.party, s.state, s.id, s.chamber, s.district,
           count(pr.id)::int as count
    FROM official_site_items pr
    JOIN officials s ON s.id = pr.official_id
    WHERE pr.deleted_at IS NULL AND pr.content_type != 'photo_release'
      AND s.status = 'active'
      AND s.chamber IN ('senate','house')
      AND s.jurisdiction = 'us'
    GROUP BY s.id, s.full_name, s.party, s.state, s.chamber, s.district
    ORDER BY count DESC
    LIMIT ${limit}
  `;
}

export async function getLeastActiveSenators(limit = 10) {
  return sql`
    SELECT s.full_name, s.party, s.state, s.id, s.chamber, s.district,
           count(pr.id)::int as count,
           max(pr.published_at) as last_release
    FROM officials s
    LEFT JOIN official_site_items pr ON s.id = pr.official_id AND pr.deleted_at IS NULL AND pr.content_type != 'photo_release'
    WHERE s.collection_method IS NOT NULL
      AND s.status = 'active'
      AND s.chamber IN ('senate','house')
      AND s.jurisdiction = 'us'
    GROUP BY s.id, s.full_name, s.party, s.state, s.chamber, s.district
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

// --- Briefs --------------------------------------------------------------

export async function getLatestBrief(): Promise<Brief | null> {
  // Latest of either edition. Weekly often comes Thursday-night and should
  // surface as the homepage of /brief until the next daily lands.
  const rows = (await sql`
    SELECT id::text, brief_date::text, edition, status, model_version,
           headline, dek, lede, sections, signals, silent, quotes,
           source_release_ids::text[] AS source_release_ids,
           cited_release_ids::text[] AS cited_release_ids,
           generated_at, published_at
    FROM briefs
    WHERE status = 'published'
    ORDER BY brief_date DESC,
             CASE edition WHEN 'weekly' THEN 0 ELSE 1 END
    LIMIT 1
  `) as Brief[];
  return rows[0] ?? null;
}

export async function getBriefByDate(
  briefDate: string,
  edition: "daily" | "weekly" = "daily"
): Promise<Brief | null> {
  const rows = (await sql`
    SELECT id::text, brief_date::text, edition, status, model_version,
           headline, dek, lede, sections, signals, silent, quotes,
           source_release_ids::text[] AS source_release_ids,
           cited_release_ids::text[] AS cited_release_ids,
           generated_at, published_at
    FROM briefs
    WHERE brief_date = ${briefDate}::date
      AND status = 'published'
      AND edition = ${edition}
    LIMIT 1
  `) as Brief[];
  return rows[0] ?? null;
}

export async function getRecentBriefs(limit = 14): Promise<Brief[]> {
  return (await sql`
    SELECT id::text, brief_date::text, edition, status, model_version,
           headline, dek, lede, sections, signals, silent, quotes,
           source_release_ids::text[] AS source_release_ids,
           cited_release_ids::text[] AS cited_release_ids,
           generated_at, published_at
    FROM briefs
    WHERE status = 'published'
    ORDER BY brief_date DESC,
             CASE edition WHEN 'weekly' THEN 0 ELSE 1 END
    LIMIT ${limit}
  `) as Brief[];
}

export async function getAllBriefs(
  edition?: "daily" | "weekly"
): Promise<Brief[]> {
  if (edition) {
    return (await sql`
      SELECT id::text, brief_date::text, edition, status, model_version,
             headline, dek, lede, sections, signals, silent, quotes,
             source_release_ids::text[] AS source_release_ids,
             cited_release_ids::text[] AS cited_release_ids,
             generated_at, published_at
      FROM briefs
      WHERE status = 'published' AND edition = ${edition}
      ORDER BY brief_date DESC
    `) as Brief[];
  }
  return (await sql`
    SELECT id::text, brief_date::text, edition, status, model_version,
           headline, dek, lede, sections, signals, silent, quotes,
           source_release_ids::text[] AS source_release_ids,
           cited_release_ids::text[] AS cited_release_ids,
           generated_at, published_at
    FROM briefs
    WHERE status = 'published'
    ORDER BY brief_date DESC,
             CASE edition WHEN 'weekly' THEN 0 ELSE 1 END
  `) as Brief[];
}

// 30-day daily release counts matching any of the given keywords against
// the press_releases.fts tsvector. Returns array length = days, oldest first.
// Used to draw a per-theme sparkline alongside each brief section.
export async function getThemeSparkline({
  keywords,
  endDate,
  days = 30,
}: {
  keywords: string[];
  endDate: string; // YYYY-MM-DD (ET, the brief_date)
  days?: number;
}): Promise<{ date: string; count: number }[]> {
  if (!keywords || keywords.length === 0) return [];
  const tsquery = keywords
    .map((k) => k.trim().toLowerCase())
    .filter(Boolean)
    .map((k) =>
      k
        .split(/\s+/)
        .map((w) => w.replace(/[^a-z0-9]/g, ""))
        .filter(Boolean)
        .join(" & ")
    )
    .filter(Boolean)
    .map((q) => `(${q})`)
    .join(" | ");
  if (!tsquery) return [];

  const rows = (await sql`
    WITH window_days AS (
      SELECT generate_series(0, ${days - 1})::int AS offset_days
    ),
    day_table AS (
      SELECT (${endDate}::date - offset_days) AS d FROM window_days
    ),
    counts AS (
      SELECT (pr.published_at AT TIME ZONE 'America/New_York')::date AS d,
             count(*)::int AS c
      FROM official_site_items pr
      JOIN officials s ON s.id = pr.official_id
      WHERE pr.published_at >= (${endDate}::date - ${days}::int)
        AND pr.published_at < (${endDate}::date + 1)
        AND pr.deleted_at IS NULL
        AND s.status = 'active' AND s.chamber = 'senate' AND s.jurisdiction = 'us'
        AND pr.fts @@ to_tsquery('english', ${tsquery})
      GROUP BY 1
    )
    SELECT to_char(day_table.d, 'YYYY-MM-DD') AS date,
           COALESCE(counts.c, 0) AS count
    FROM day_table
    LEFT JOIN counts ON counts.d = day_table.d
    ORDER BY day_table.d ASC
  `) as { date: string; count: number }[];
  return rows;
}

// Resolve cited release UUIDs into card-ready records for the brief route.
export async function getBriefCitations(
  ids: string[]
): Promise<Map<string, BriefCitation>> {
  if (ids.length === 0) return new Map();
  const rows = (await sql`
    SELECT pr.id::text AS id, pr.title, pr.source_url, pr.published_at,
           s.full_name AS senator_name, s.party, s.state
    FROM official_site_items pr
    JOIN officials s ON s.id = pr.official_id
    WHERE pr.id = ANY(${ids}::uuid[])
  `) as BriefCitation[];
  const map = new Map<string, BriefCitation>();
  for (const r of rows) map.set(r.id, r);
  return map;
}


// --- Social posts (Bluesky) ---------------------------------------------
//
// Read from `social_posts`. Default surface excludes replies — feed shows
// senator-authored top-level posts only, mirroring the press_releases
// "primary surface" rule. Replies are still in the database and queryable.

export type SocialFeedFilters = {
  page?: number;
  perPage?: number;
  party?: string;
  state?: string;
  officialId?: string;
  includeReplies?: boolean;
};

export async function getSocialFeed(
  f: SocialFeedFilters = {}
): Promise<{ items: SocialFeedItem[]; total: number }> {
  const page = f.page ?? 1;
  const perPage = f.perPage ?? 50;
  const offset = (page - 1) * perPage;

  // Social feed scopes to verified US senators. The 44 Bluesky handles
  // we collect against today are all US-Senate offices; House handles
  // are not yet verified, and state Bluesky is out of scope. Pin
  // chamber + jurisdiction to avoid future state/exec drift.
  const preds: string[] = [
    "sp.deleted_at IS NULL",
    "s.chamber = 'senate'",
    "s.jurisdiction = 'us'",
  ];
  const params: unknown[] = [];
  if (!f.includeReplies) preds.push("sp.is_reply = FALSE");
  if (f.party) {
    params.push(f.party);
    preds.push(`s.party = $${params.length}`);
  }
  if (f.state) {
    params.push(f.state);
    preds.push(`s.state = $${params.length}`);
  }
  if (f.officialId) {
    params.push(f.officialId);
    preds.push(`sp.official_id = $${params.length}`);
  }

  const where = preds.join(" AND ");
  params.push(perPage);
  const limitIdx = `$${params.length}`;
  params.push(offset);
  const offsetIdx = `$${params.length}`;

  const cols = `
    sp.id, sp.official_id, sp.source, sp.platform_post_id, sp.did, sp.handle,
    sp.text, sp.created_at, sp.is_reply, sp.reply_parent_uri,
    sp.embed_kind, sp.embed_summary,
    s.full_name AS senator_name, s.party, s.state
  `;
  const countText = `SELECT count(*)::int AS total FROM social_posts sp JOIN officials s ON s.id = sp.official_id WHERE ${where}`;
  const itemsText = `SELECT ${cols} FROM social_posts sp JOIN officials s ON s.id = sp.official_id WHERE ${where} ORDER BY sp.created_at DESC LIMIT ${limitIdx} OFFSET ${offsetIdx}`;
  const countParams = params.slice(0, params.length - 2);
  const [countResult, items] = await Promise.all([
    sql.query(countText, countParams),
    sql.query(itemsText, params),
  ]);
  return {
    items: items as SocialFeedItem[],
    total: Number((countResult as { total: number }[])[0].total),
  };
}

export type SocialStats = {
  total: number;
  senators_active: number;
  earliest: string | null;
  latest: string | null;
  party: { D: number; R: number; I: number };
};

export async function getSocialStats(
  f: SocialFeedFilters = {}
): Promise<SocialStats> {
  // Stats reflect the same filters as the feed they're describing — when
  // the user narrows to ?party=R, the summary should match what's below.
  // Party breakdown intentionally ignores `f.party` so the D/R/I split
  // stays useful even when one party is selected.
  const preds: string[] = ["sp.deleted_at IS NULL"];
  const params: unknown[] = [];
  if (!f.includeReplies) preds.push("sp.is_reply = FALSE");
  if (f.state) {
    params.push(f.state);
    preds.push(`s.state = $${params.length}`);
  }
  if (f.officialId) {
    params.push(f.officialId);
    preds.push(`sp.official_id = $${params.length}`);
  }
  const partyPreds = preds.slice();
  const partyParams = params.slice();
  if (f.party) {
    params.push(f.party);
    preds.push(`s.party = $${params.length}`);
  }

  const where = preds.join(" AND ");
  const partyWhere = partyPreds.join(" AND ");
  const overallText = `
    SELECT count(*)::int                              AS total,
           count(DISTINCT sp.official_id)::int         AS senators_active,
           min(sp.created_at)::text                   AS earliest,
           max(sp.created_at)::text                   AS latest
      FROM social_posts sp
      JOIN officials s ON s.id = sp.official_id
      WHERE ${where}
  `;
  const partyText = `
    SELECT s.party AS party, count(*)::int AS count
      FROM social_posts sp
      JOIN officials s ON s.id = sp.official_id
      WHERE ${partyWhere}
      GROUP BY s.party
  `;

  const [overall, byParty] = await Promise.all([
    sql.query(overallText, params),
    sql.query(partyText, partyParams),
  ]);
  const r = (overall as { total: number; senators_active: number; earliest: string | null; latest: string | null }[])[0];
  const party = { D: 0, R: 0, I: 0 };
  for (const row of byParty as { party: string; count: number }[]) {
    if (row.party === "D" || row.party === "R" || row.party === "I") {
      party[row.party] = row.count;
    }
  }
  return {
    total: r.total,
    senators_active: r.senators_active,
    earliest: r.earliest,
    latest: r.latest,
    party,
  };
}

export async function getSocialActiveSenators(): Promise<
  { official_id: string; full_name: string; party: "D" | "R" | "I"; state: string; post_count: number; latest: string }[]
> {
  return (await sql`
    SELECT sp.official_id,
           s.full_name,
           s.party,
           s.state,
           count(*)::int AS post_count,
           max(sp.created_at)::text AS latest
      FROM social_posts sp
      JOIN officials s ON s.id = sp.official_id
      WHERE sp.deleted_at IS NULL AND sp.is_reply = FALSE
      GROUP BY sp.official_id, s.full_name, s.party, s.state
      ORDER BY post_count DESC
  `) as { official_id: string; full_name: string; party: "D" | "R" | "I"; state: string; post_count: number; latest: string }[];
}

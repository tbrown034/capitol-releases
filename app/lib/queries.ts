import { sql } from "./db";
import type { FeedItem, SenatorWithCount, PressRelease, Senator } from "./db";

export async function getFeed({
  page = 1,
  perPage = 25,
  party,
  state,
  senator,
  search,
}: {
  page?: number;
  perPage?: number;
  party?: string;
  state?: string;
  senator?: string;
  search?: string;
} = {}): Promise<{ items: FeedItem[]; total: number }> {
  const offset = (page - 1) * perPage;

  // Use different queries based on filter combinations to stay with tagged templates
  if (search) {
    if (party && state) {
      const countResult = await sql`SELECT count(*) as total FROM press_releases pr JOIN senators s ON s.id = pr.senator_id WHERE pr.fts @@ plainto_tsquery('english', ${search}) AND s.party = ${party} AND s.state = ${state}`;
      const items = await sql`SELECT pr.id, pr.senator_id, pr.title, pr.published_at, pr.body_text, pr.source_url, pr.scraped_at, s.full_name as senator_name, s.party, s.state FROM press_releases pr JOIN senators s ON s.id = pr.senator_id WHERE pr.fts @@ plainto_tsquery('english', ${search}) AND s.party = ${party} AND s.state = ${state} ORDER BY pr.published_at DESC NULLS LAST LIMIT ${perPage} OFFSET ${offset}`;
      return { items: items as FeedItem[], total: Number(countResult[0].total) };
    }
    if (party) {
      const countResult = await sql`SELECT count(*) as total FROM press_releases pr JOIN senators s ON s.id = pr.senator_id WHERE pr.fts @@ plainto_tsquery('english', ${search}) AND s.party = ${party}`;
      const items = await sql`SELECT pr.id, pr.senator_id, pr.title, pr.published_at, pr.body_text, pr.source_url, pr.scraped_at, s.full_name as senator_name, s.party, s.state FROM press_releases pr JOIN senators s ON s.id = pr.senator_id WHERE pr.fts @@ plainto_tsquery('english', ${search}) AND s.party = ${party} ORDER BY pr.published_at DESC NULLS LAST LIMIT ${perPage} OFFSET ${offset}`;
      return { items: items as FeedItem[], total: Number(countResult[0].total) };
    }
    if (state) {
      const countResult = await sql`SELECT count(*) as total FROM press_releases pr JOIN senators s ON s.id = pr.senator_id WHERE pr.fts @@ plainto_tsquery('english', ${search}) AND s.state = ${state}`;
      const items = await sql`SELECT pr.id, pr.senator_id, pr.title, pr.published_at, pr.body_text, pr.source_url, pr.scraped_at, s.full_name as senator_name, s.party, s.state FROM press_releases pr JOIN senators s ON s.id = pr.senator_id WHERE pr.fts @@ plainto_tsquery('english', ${search}) AND s.state = ${state} ORDER BY pr.published_at DESC NULLS LAST LIMIT ${perPage} OFFSET ${offset}`;
      return { items: items as FeedItem[], total: Number(countResult[0].total) };
    }
    const countResult = await sql`SELECT count(*) as total FROM press_releases pr WHERE pr.fts @@ plainto_tsquery('english', ${search})`;
    const items = await sql`SELECT pr.id, pr.senator_id, pr.title, pr.published_at, pr.body_text, pr.source_url, pr.scraped_at, s.full_name as senator_name, s.party, s.state FROM press_releases pr JOIN senators s ON s.id = pr.senator_id WHERE pr.fts @@ plainto_tsquery('english', ${search}) ORDER BY pr.published_at DESC NULLS LAST LIMIT ${perPage} OFFSET ${offset}`;
    return { items: items as FeedItem[], total: Number(countResult[0].total) };
  }

  if (senator) {
    const countResult = await sql`SELECT count(*) as total FROM press_releases WHERE senator_id = ${senator}`;
    const items = await sql`SELECT pr.id, pr.senator_id, pr.title, pr.published_at, pr.body_text, pr.source_url, pr.scraped_at, s.full_name as senator_name, s.party, s.state FROM press_releases pr JOIN senators s ON s.id = pr.senator_id WHERE pr.senator_id = ${senator} ORDER BY pr.published_at DESC NULLS LAST LIMIT ${perPage} OFFSET ${offset}`;
    return { items: items as FeedItem[], total: Number(countResult[0].total) };
  }

  if (party && state) {
    const countResult = await sql`SELECT count(*) as total FROM press_releases pr JOIN senators s ON s.id = pr.senator_id WHERE s.party = ${party} AND s.state = ${state}`;
    const items = await sql`SELECT pr.id, pr.senator_id, pr.title, pr.published_at, pr.body_text, pr.source_url, pr.scraped_at, s.full_name as senator_name, s.party, s.state FROM press_releases pr JOIN senators s ON s.id = pr.senator_id WHERE s.party = ${party} AND s.state = ${state} ORDER BY pr.published_at DESC NULLS LAST LIMIT ${perPage} OFFSET ${offset}`;
    return { items: items as FeedItem[], total: Number(countResult[0].total) };
  }

  if (party) {
    const countResult = await sql`SELECT count(*) as total FROM press_releases pr JOIN senators s ON s.id = pr.senator_id WHERE s.party = ${party}`;
    const items = await sql`SELECT pr.id, pr.senator_id, pr.title, pr.published_at, pr.body_text, pr.source_url, pr.scraped_at, s.full_name as senator_name, s.party, s.state FROM press_releases pr JOIN senators s ON s.id = pr.senator_id WHERE s.party = ${party} ORDER BY pr.published_at DESC NULLS LAST LIMIT ${perPage} OFFSET ${offset}`;
    return { items: items as FeedItem[], total: Number(countResult[0].total) };
  }

  if (state) {
    const countResult = await sql`SELECT count(*) as total FROM press_releases pr JOIN senators s ON s.id = pr.senator_id WHERE s.state = ${state}`;
    const items = await sql`SELECT pr.id, pr.senator_id, pr.title, pr.published_at, pr.body_text, pr.source_url, pr.scraped_at, s.full_name as senator_name, s.party, s.state FROM press_releases pr JOIN senators s ON s.id = pr.senator_id WHERE s.state = ${state} ORDER BY pr.published_at DESC NULLS LAST LIMIT ${perPage} OFFSET ${offset}`;
    return { items: items as FeedItem[], total: Number(countResult[0].total) };
  }

  // No filters
  const countResult = await sql`SELECT count(*) as total FROM press_releases`;
  const items = await sql`SELECT pr.id, pr.senator_id, pr.title, pr.published_at, pr.body_text, pr.source_url, pr.scraped_at, s.full_name as senator_name, s.party, s.state FROM press_releases pr JOIN senators s ON s.id = pr.senator_id ORDER BY pr.published_at DESC NULLS LAST LIMIT ${perPage} OFFSET ${offset}`;
  return { items: items as FeedItem[], total: Number(countResult[0].total) };
}

export async function getSenators(): Promise<SenatorWithCount[]> {
  return (await sql`
    SELECT s.*,
           count(pr.id)::int as release_count,
           max(pr.published_at) as latest_release
    FROM senators s
    LEFT JOIN press_releases pr ON pr.senator_id = s.id
    GROUP BY s.id
    ORDER BY s.state, s.full_name
  `) as SenatorWithCount[];
}

export async function getSenator(id: string): Promise<Senator | null> {
  const rows = await sql`SELECT * FROM senators WHERE id = ${id}`;
  return (rows[0] as Senator) ?? null;
}

export async function getSenatorReleases(
  senatorId: string,
  page = 1,
  perPage = 25
): Promise<{ items: PressRelease[]; total: number }> {
  const offset = (page - 1) * perPage;
  const countResult = await sql`SELECT count(*) as total FROM press_releases WHERE senator_id = ${senatorId}`;
  const total = Number(countResult[0].total);

  const items = (await sql`
    SELECT * FROM press_releases WHERE senator_id = ${senatorId}
    ORDER BY published_at DESC NULLS LAST
    LIMIT ${perPage} OFFSET ${offset}
  `) as PressRelease[];

  return { items, total };
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
    LEFT JOIN press_releases pr ON pr.senator_id = s.id
  `;
  return result[0];
}

export async function getPartyBreakdown() {
  return sql`
    SELECT s.party, count(pr.id)::int as count
    FROM press_releases pr
    JOIN senators s ON s.id = pr.senator_id
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
    GROUP BY s.id, s.full_name, s.party, s.state
    ORDER BY count DESC
    LIMIT ${limit}
  `;
}

export function getStates(): string[] {
  return [
    "AL","AK","AZ","AR","CA","CO","CT","DE","FL","GA",
    "HI","ID","IL","IN","IA","KS","KY","LA","ME","MD",
    "MA","MI","MN","MS","MO","MT","NE","NV","NH","NJ",
    "NM","NY","NC","ND","OH","OK","OR","PA","RI","SC",
    "SD","TN","TX","UT","VT","VA","WA","WV","WI","WY",
  ];
}

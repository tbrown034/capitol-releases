import { NextRequest, NextResponse } from "next/server";
import { sql } from "../../../lib/db";

const MAX_TERM_LEN = 40;
const ALLTIME_CUTOFF = "2025-01-01";

function sanitize(term: string): string {
  return term.trim().replace(/[^a-zA-Z0-9 \-']/g, "").slice(0, MAX_TERM_LEN);
}

export async function GET(request: NextRequest) {
  const scopeParam = request.nextUrl.searchParams.get("scope") ?? "recent";
  const scope = scopeParam === "alltime" ? "alltime" : "recent";
  const term = sanitize(request.nextUrl.searchParams.get("q") ?? "");

  let rows: { id: string; count: number }[];

  if (scope === "recent" && term) {
    rows = (await sql`
      SELECT s.id, count(pr.id)::int as count
      FROM senators s
      LEFT JOIN press_releases pr
        ON pr.senator_id = s.id
        AND pr.deleted_at IS NULL
        AND pr.content_type != 'photo_release'
        AND pr.published_at IS NOT NULL
        AND pr.published_at >= NOW() - INTERVAL '30 days'
        AND pr.fts @@ websearch_to_tsquery('english', ${term})
      WHERE s.status = 'active' AND s.chamber = 'senate'
      GROUP BY s.id
    `) as { id: string; count: number }[];
  } else if (scope === "recent") {
    rows = (await sql`
      SELECT s.id, count(pr.id)::int as count
      FROM senators s
      LEFT JOIN press_releases pr
        ON pr.senator_id = s.id
        AND pr.deleted_at IS NULL
        AND pr.content_type != 'photo_release'
        AND pr.published_at IS NOT NULL
        AND pr.published_at >= NOW() - INTERVAL '30 days'
      WHERE s.status = 'active' AND s.chamber = 'senate'
      GROUP BY s.id
    `) as { id: string; count: number }[];
  } else if (term) {
    rows = (await sql`
      SELECT s.id, count(pr.id)::int as count
      FROM senators s
      LEFT JOIN press_releases pr
        ON pr.senator_id = s.id
        AND pr.deleted_at IS NULL
        AND pr.content_type != 'photo_release'
        AND pr.published_at IS NOT NULL
        AND pr.published_at >= ${ALLTIME_CUTOFF}::date
        AND pr.fts @@ websearch_to_tsquery('english', ${term})
      WHERE s.status = 'active' AND s.chamber = 'senate'
      GROUP BY s.id
    `) as { id: string; count: number }[];
  } else {
    rows = (await sql`
      SELECT s.id, count(pr.id)::int as count
      FROM senators s
      LEFT JOIN press_releases pr
        ON pr.senator_id = s.id
        AND pr.deleted_at IS NULL
        AND pr.content_type != 'photo_release'
        AND pr.published_at IS NOT NULL
        AND pr.published_at >= ${ALLTIME_CUTOFF}::date
      WHERE s.status = 'active' AND s.chamber = 'senate'
      GROUP BY s.id
    `) as { id: string; count: number }[];
  }

  const counts: Record<string, number> = {};
  for (const r of rows) counts[r.id] = r.count;

  return NextResponse.json(
    { scope, term, counts },
    { headers: { "Cache-Control": "public, max-age=600, s-maxage=600" } }
  );
}

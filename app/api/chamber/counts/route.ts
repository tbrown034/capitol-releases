import { NextRequest, NextResponse } from "next/server";
import { sql } from "../../../lib/db";

const MAX_TERM_LEN = 40;
const ALLTIME_CUTOFF = "2025-01-01";

function sanitize(term: string): string {
  return term.trim().replace(/[^a-zA-Z0-9 \-']/g, "").slice(0, MAX_TERM_LEN);
}

function buildChamberCountsQuery(
  scope: "recent" | "alltime",
  term: string
): { text: string; params: unknown[] } {
  const dateClause =
    scope === "recent"
      ? "pr.published_at >= NOW() - INTERVAL '30 days'"
      : "pr.published_at >= $1::date";
  const params: unknown[] = scope === "recent" ? [] : [ALLTIME_CUTOFF];

  const joinPreds = [
    "pr.deleted_at IS NULL",
    "pr.content_type != 'photo_release'",
    "pr.published_at IS NOT NULL",
    dateClause,
  ];
  if (term) {
    params.push(term);
    joinPreds.push(`pr.fts @@ websearch_to_tsquery('english', $${params.length})`);
  }

  const text = `
    SELECT s.id, count(pr.id)::int as count
    FROM senators s
    LEFT JOIN press_releases pr
      ON pr.senator_id = s.id
      AND ${joinPreds.join(" AND ")}
    WHERE s.status = 'active' AND s.chamber = 'senate'
    GROUP BY s.id
  `;

  return { text, params };
}

export async function GET(request: NextRequest) {
  const scopeParam = request.nextUrl.searchParams.get("scope") ?? "recent";
  const scope = scopeParam === "alltime" ? "alltime" : "recent";
  const term = sanitize(request.nextUrl.searchParams.get("q") ?? "");

  const { text, params } = buildChamberCountsQuery(scope, term);
  const rows = (await sql.query(text, params)) as { id: string; count: number }[];

  const counts: Record<string, number> = {};
  for (const r of rows) counts[r.id] = r.count;

  return NextResponse.json(
    { scope, term, counts },
    { headers: { "Cache-Control": "public, max-age=600, s-maxage=600" } }
  );
}

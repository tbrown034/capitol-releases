import { NextRequest, NextResponse } from "next/server";
import { sql } from "../../../lib/db";

const MAX_TERMS = 8;
const MAX_TERM_LEN = 40;

function sanitize(term: string): string {
  return term.trim().replace(/[^a-zA-Z0-9 \-']/g, "").slice(0, MAX_TERM_LEN);
}

export async function GET(request: NextRequest) {
  const raw = request.nextUrl.searchParams.get("q") ?? "";
  const terms = Array.from(
    new Set(
      raw
        .split(",")
        .map(sanitize)
        .filter((t) => t.length > 0)
    )
  ).slice(0, MAX_TERMS);

  if (terms.length === 0) {
    return NextResponse.json({ terms: [], series: {} });
  }

  const results = await Promise.all(
    terms.map(
      (term) => sql`
        SELECT to_char(date_trunc('week', published_at), 'YYYY-MM-DD') as week,
               count(*)::int as count
        FROM press_releases
        WHERE published_at >= '2025-01-01'
          AND published_at IS NOT NULL
          AND deleted_at IS NULL
          AND content_type != 'photo_release'
          AND fts @@ websearch_to_tsquery('english', ${term})
        GROUP BY week
        ORDER BY week
      `
    )
  );

  const series: Record<string, { week: string; count: number }[]> = {};
  terms.forEach((term, i) => {
    series[term] = results[i] as { week: string; count: number }[];
  });

  return NextResponse.json(
    { terms, series },
    { headers: { "Cache-Control": "public, max-age=600, s-maxage=600" } }
  );
}

import { NextRequest, NextResponse } from "next/server";
import { sql } from "../../../lib/db";

function rangeToDays(range: string): number | null {
  switch (range) {
    case "week":
      return 7;
    case "month":
      return 30;
    case "year":
      return 365;
    case "ytd": {
      const now = new Date();
      const start = new Date(now.getFullYear(), 0, 1);
      return Math.ceil(
        (now.getTime() - start.getTime()) / (1000 * 60 * 60 * 24)
      );
    }
    default:
      return null; // all-time
  }
}

export async function GET(request: NextRequest) {
  const range = request.nextUrl.searchParams.get("range") ?? "all";
  const limit = 10;
  const days = rangeToDays(range);

  let top;
  let bottom;

  if (days === null) {
    // All-time
    top = await sql`
      SELECT s.full_name, s.party, s.state, s.id,
             count(pr.id)::int as count
      FROM press_releases pr
      JOIN senators s ON s.id = pr.senator_id
      WHERE pr.deleted_at IS NULL
        AND (s.status IS NULL OR s.status = 'current')
      GROUP BY s.id, s.full_name, s.party, s.state
      ORDER BY count DESC
      LIMIT ${limit}
    `;
    bottom = await sql`
      SELECT s.full_name, s.party, s.state, s.id,
             count(pr.id)::int as count
      FROM senators s
      LEFT JOIN press_releases pr ON s.id = pr.senator_id AND pr.deleted_at IS NULL
      WHERE s.collection_method IS NOT NULL
        AND (s.status IS NULL OR s.status = 'current')
      GROUP BY s.id, s.full_name, s.party, s.state
      ORDER BY count ASC
      LIMIT ${limit}
    `;
  } else {
    top = await sql`
      SELECT s.full_name, s.party, s.state, s.id,
             count(pr.id)::int as count
      FROM press_releases pr
      JOIN senators s ON s.id = pr.senator_id
      WHERE pr.deleted_at IS NULL
        AND pr.published_at >= NOW() - make_interval(days => ${days})
      GROUP BY s.id, s.full_name, s.party, s.state
      ORDER BY count DESC
      LIMIT ${limit}
    `;
    bottom = await sql`
      SELECT s.full_name, s.party, s.state, s.id,
             count(pr.id)::int as count
      FROM senators s
      LEFT JOIN press_releases pr ON s.id = pr.senator_id
        AND pr.deleted_at IS NULL
        AND pr.published_at >= NOW() - make_interval(days => ${days})
      WHERE s.collection_method IS NOT NULL
        AND (s.status IS NULL OR s.status = 'current')
      GROUP BY s.id, s.full_name, s.party, s.state
      ORDER BY count ASC
      LIMIT ${limit}
    `;
  }

  return NextResponse.json({ top, bottom });
}

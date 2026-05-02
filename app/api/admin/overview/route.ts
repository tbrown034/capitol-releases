import { NextResponse } from "next/server";
import { headers } from "next/headers";
import { auth, isAdmin } from "@/app/lib/auth";
import { sql } from "@/app/lib/db";

export const dynamic = "force-dynamic";

type RunRow = {
  id: string;
  run_type: string;
  started_at: string;
  finished_at: string | null;
  stats: Record<string, unknown> | null;
};

type AlertRow = {
  id: string;
  created_at: string;
  alert_type: string;
  official_id: string | null;
  severity: string;
  message: string;
  acknowledged: boolean;
};

type CountRow = { count: string | number };

export async function GET() {
  const session = await auth.api.getSession({ headers: await headers() });
  if (!session?.user?.email || !isAdmin(session.user.email)) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const [totalRow] = (await sql`
    SELECT COUNT(*)::int AS count
    FROM press_releases
    WHERE deleted_at IS NULL
  `) as CountRow[];

  const [last24Row] = (await sql`
    SELECT COUNT(*)::int AS count
    FROM press_releases
    WHERE deleted_at IS NULL
      AND scraped_at > NOW() - INTERVAL '24 hours'
  `) as CountRow[];

  const [senatorRow] = (await sql`
    SELECT COUNT(*)::int AS count
    FROM senators
    WHERE status = 'active'
  `) as CountRow[];

  const [userRow] = (await sql`SELECT COUNT(*)::int AS count FROM "user"`) as CountRow[];

  const recentRuns = (await sql`
    SELECT id, run_type, started_at, finished_at, stats
    FROM scrape_runs
    ORDER BY started_at DESC
    LIMIT 10
  `) as RunRow[];

  const recentAlerts = (await sql`
    SELECT id, created_at, alert_type, official_id, severity, message, acknowledged
    FROM alerts
    ORDER BY created_at DESC
    LIMIT 10
  `) as AlertRow[];

  return NextResponse.json({
    totals: {
      releases: Number(totalRow?.count ?? 0),
      releases_last_24h: Number(last24Row?.count ?? 0),
      active_senators: Number(senatorRow?.count ?? 0),
      users: Number(userRow?.count ?? 0),
    },
    recent_runs: recentRuns,
    recent_alerts: recentAlerts,
  });
}

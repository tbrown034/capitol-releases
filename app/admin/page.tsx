import { headers } from "next/headers";
import { auth, isAdmin } from "@/app/lib/auth";
import { sql } from "@/app/lib/db";
import { SignInButton, SignOutButton } from "./admin-auth-buttons";

type Overview = {
  totals: {
    releases: number;
    releases_last_24h: number;
    active_senators: number;
    users: number;
  };
  recent_runs: Array<{
    id: string;
    run_type: string;
    started_at: string;
    finished_at: string | null;
    stats: Record<string, unknown> | null;
  }>;
  recent_alerts: Array<{
    id: string;
    created_at: string;
    alert_type: string;
    official_id: string | null;
    severity: string;
    message: string;
    acknowledged: boolean;
  }>;
  ask: {
    status_counts: Array<{ status: string; count: number }>;
    total_7d: number;
    cost_7d_usd: number;
    recent: Array<{
      created_at: string;
      official_id: string;
      question: string;
      status: string;
      latency_ms: number | null;
    }>;
  };
};

type CountRow = { count: string | number };

export const dynamic = "force-dynamic";

function formatTime(iso: string | null): string {
  if (!iso) return "-";
  const d = new Date(iso);
  return d.toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function severityColor(s: string): string {
  if (s === "critical" || s === "error") return "text-red-700 bg-red-50";
  if (s === "warning") return "text-amber-700 bg-amber-50";
  return "text-neutral-600 bg-neutral-50";
}

const ASK_FAILURE_STATUSES = new Set([
  "validation_failed",
  "protocol_error",
  "api_error",
  "retrieval_error",
  "refused",
]);

function askStatusColor(s: string): string {
  if (ASK_FAILURE_STATUSES.has(s)) return "text-red-700 bg-red-50";
  if (s === "declined") return "text-amber-700 bg-amber-50";
  if (s === "answered" || s === "related_only") return "text-emerald-700 bg-emerald-50";
  return "text-neutral-600 bg-neutral-50";
}

async function getAdminOverview(): Promise<Overview> {
  const [
    totalRows,
    last24Rows,
    senatorRows,
    userRows,
    recentRuns,
    recentAlerts,
  ] = (await Promise.all([
    sql`
      SELECT COUNT(*)::int AS count
      FROM official_site_items
      WHERE deleted_at IS NULL
    `,
    sql`
      SELECT COUNT(*)::int AS count
      FROM official_site_items
      WHERE deleted_at IS NULL
        AND scraped_at > NOW() - INTERVAL '24 hours'
    `,
    sql`
      SELECT COUNT(*)::int AS count
      FROM officials
      WHERE status = 'active'
    `,
    sql`SELECT COUNT(*)::int AS count FROM "user"`,
    sql`
      SELECT id, run_type, started_at, finished_at, stats
      FROM scrape_runs
      ORDER BY started_at DESC
      LIMIT 10
    `,
    // Open conditions only. Alert storage now touches created_at when a
    // condition recurs, so acknowledged rows are resolved history, not news
    // -- without this filter an acknowledged backlog crowds out live alerts.
    sql`
      SELECT id, created_at, alert_type, official_id, severity, message, acknowledged
      FROM alerts
      WHERE NOT acknowledged
      ORDER BY created_at DESC
      LIMIT 10
    `,
  ])) as [
    CountRow[],
    CountRow[],
    CountRow[],
    CountRow[],
    Overview["recent_runs"],
    Overview["recent_alerts"],
  ];

  // Ask-the-record notebook. Own try/catch: a missing ask_log table on a
  // fresh environment must not blank the whole dashboard.
  let ask: Overview["ask"] = {
    status_counts: [],
    total_7d: 0,
    cost_7d_usd: 0,
    recent: [],
  };
  try {
    const [statusRows, costRows, recentAsks] = (await Promise.all([
      sql`
        SELECT status, COUNT(*)::int AS count
        FROM ask_log
        WHERE created_at > NOW() - INTERVAL '7 days'
        GROUP BY status
        ORDER BY count DESC
      `,
      // Haiku 4.5: $1/M input, $5/M output. Estimate, for spend awareness.
      sql`
        SELECT COALESCE(SUM(input_tokens), 0)::float / 1e6 * 1.0
             + COALESCE(SUM(output_tokens), 0)::float / 1e6 * 5.0 AS usd
        FROM ask_log
        WHERE created_at > NOW() - INTERVAL '7 days'
      `,
      sql`
        SELECT created_at, official_id, question, status, latency_ms
        FROM ask_log
        ORDER BY created_at DESC
        LIMIT 10
      `,
    ])) as [
      Overview["ask"]["status_counts"],
      Array<{ usd: number }>,
      Overview["ask"]["recent"],
    ];
    ask = {
      status_counts: statusRows,
      total_7d: statusRows.reduce((s, r) => s + Number(r.count), 0),
      cost_7d_usd: Number(costRows[0]?.usd ?? 0),
      recent: recentAsks,
    };
  } catch (err) {
    console.error("[admin] ask_log queries failed", err);
  }

  return {
    totals: {
      releases: Number(totalRows[0]?.count ?? 0),
      releases_last_24h: Number(last24Rows[0]?.count ?? 0),
      active_senators: Number(senatorRows[0]?.count ?? 0),
      users: Number(userRows[0]?.count ?? 0),
    },
    recent_runs: recentRuns,
    recent_alerts: recentAlerts,
    ask,
  };
}

export default async function AdminPage() {
  // Never let an auth-subsystem failure render a raw 500 on a public URL.
  // A misconfigured environment (missing BETTER_AUTH_SECRET, unreachable
  // auth tables) makes getSession throw, and an unhandled throw here served
  // the Next.js error shell to every visitor who clicked the footer link.
  // Fail closed instead: no verified session means the signed-out view.
  let session: Awaited<ReturnType<typeof auth.api.getSession>> = null;
  try {
    session = await auth.api.getSession({ headers: await headers() });
  } catch (err) {
    console.error("[admin] getSession failed; rendering signed-out view", err);
    session = null;
  }

  if (!session) {
    return (
      <main className="mx-auto max-w-md px-4 py-16">
        <h1 className="text-2xl font-medium text-neutral-900 mb-2">Admin</h1>
        <p className="text-sm text-neutral-600 mb-8">
          Sign in to access the dashboard.
        </p>
        <SignInButton />
      </main>
    );
  }

  const email = session.user?.email ?? "";

  if (!isAdmin(email)) {
    return (
      <main className="mx-auto max-w-md px-4 py-16">
        <h1 className="text-2xl font-medium text-neutral-900 mb-2">Not authorized</h1>
        <p className="text-sm text-neutral-600 mb-6">
          {email} is signed in but not on the admin allowlist.
        </p>
        <SignOutButton redirectTo="/admin" />
      </main>
    );
  }

  const overview = await getAdminOverview();

  return (
    <main className="mx-auto max-w-5xl px-4 py-10">
      <div className="flex items-start justify-between mb-8">
        <div>
          <h1 className="text-2xl font-medium text-neutral-900">Admin</h1>
          <p className="text-sm text-neutral-500 mt-1">Signed in as {email}</p>
        </div>
        <SignOutButton />
      </div>

      <div className="space-y-10">
        <section>
          <h2 className="text-xs uppercase tracking-wide text-neutral-500 mb-3">
            Totals
          </h2>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <Stat label="Releases" value={overview.totals.releases} />
            <Stat label="Last 24h" value={overview.totals.releases_last_24h} />
            <Stat label="Active senators" value={overview.totals.active_senators} />
            <Stat label="Users" value={overview.totals.users} />
          </div>
        </section>

        <section>
          <h2 className="text-xs uppercase tracking-wide text-neutral-500 mb-3">
            Recent scrape runs
          </h2>
          <div className="border border-neutral-200 rounded-md overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-neutral-50 text-xs text-neutral-500">
                <tr>
                  <th className="text-left px-3 py-2 font-medium">Run</th>
                  <th className="text-left px-3 py-2 font-medium">Type</th>
                  <th className="text-left px-3 py-2 font-medium">Started</th>
                  <th className="text-left px-3 py-2 font-medium">Finished</th>
                </tr>
              </thead>
              <tbody>
                {overview.recent_runs.map((r) => (
                  <tr key={r.id} className="border-t border-neutral-100">
                    <td className="px-3 py-2 font-mono text-xs text-neutral-700">{r.id}</td>
                    <td className="px-3 py-2 text-neutral-600">{r.run_type}</td>
                    <td className="px-3 py-2 text-neutral-600">{formatTime(r.started_at)}</td>
                    <td className="px-3 py-2 text-neutral-600">{formatTime(r.finished_at)}</td>
                  </tr>
                ))}
                {overview.recent_runs.length === 0 && (
                  <tr>
                    <td colSpan={4} className="px-3 py-6 text-center text-neutral-400 text-sm">
                      No runs recorded.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </section>

        <section>
          <h2 className="text-xs uppercase tracking-wide text-neutral-500 mb-3">
            Recent alerts
          </h2>
          <div className="border border-neutral-200 rounded-md overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-neutral-50 text-xs text-neutral-500">
                <tr>
                  <th className="text-left px-3 py-2 font-medium">When</th>
                  <th className="text-left px-3 py-2 font-medium">Severity</th>
                  <th className="text-left px-3 py-2 font-medium">Type</th>
                  <th className="text-left px-3 py-2 font-medium">Senator</th>
                  <th className="text-left px-3 py-2 font-medium">Message</th>
                </tr>
              </thead>
              <tbody>
                {overview.recent_alerts.map((a) => (
                  <tr key={a.id} className="border-t border-neutral-100">
                    <td className="px-3 py-2 text-neutral-600">{formatTime(a.created_at)}</td>
                    <td className="px-3 py-2">
                      <span className={`inline-block px-1.5 py-0.5 rounded text-xs ${severityColor(a.severity)}`}>
                        {a.severity}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-neutral-600">{a.alert_type}</td>
                    <td className="px-3 py-2 text-neutral-600">{a.official_id ?? "-"}</td>
                    <td className="px-3 py-2 text-neutral-700">{a.message}</td>
                  </tr>
                ))}
                {overview.recent_alerts.length === 0 && (
                  <tr>
                    <td colSpan={5} className="px-3 py-6 text-center text-neutral-400 text-sm">
                      No alerts.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </section>

        <section>
          <h2 className="text-xs uppercase tracking-wide text-neutral-500 mb-3">
            Ask the record (7 days)
          </h2>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-3">
            <Stat label="Questions" value={overview.ask.total_7d} />
            <div className="border border-neutral-200 rounded-md p-3">
              <div className="text-xs text-neutral-500">Est. cost</div>
              <div className="text-2xl font-medium text-neutral-900 mt-1 tabular-nums">
                ${overview.ask.cost_7d_usd.toFixed(2)}
              </div>
            </div>
          </div>
          {overview.ask.status_counts.length > 0 && (
            <div className="flex flex-wrap gap-2 mb-3">
              {overview.ask.status_counts.map((s) => (
                <span
                  key={s.status}
                  className={`inline-block px-2 py-0.5 rounded text-xs ${askStatusColor(s.status)}`}
                >
                  {s.status}: {s.count}
                </span>
              ))}
            </div>
          )}
          <div className="border border-neutral-200 rounded-md overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-neutral-50 text-xs text-neutral-500">
                <tr>
                  <th className="text-left px-3 py-2 font-medium">When</th>
                  <th className="text-left px-3 py-2 font-medium">Member</th>
                  <th className="text-left px-3 py-2 font-medium">Question</th>
                  <th className="text-left px-3 py-2 font-medium">Status</th>
                  <th className="text-right px-3 py-2 font-medium">Latency</th>
                </tr>
              </thead>
              <tbody>
                {overview.ask.recent.map((q, i) => (
                  <tr key={i} className="border-t border-neutral-100">
                    <td className="px-3 py-2 text-neutral-600 whitespace-nowrap">
                      {formatTime(q.created_at)}
                    </td>
                    <td className="px-3 py-2 text-neutral-600">{q.official_id}</td>
                    <td className="px-3 py-2 text-neutral-700 max-w-xs truncate">
                      {q.question}
                    </td>
                    <td className="px-3 py-2">
                      <span className={`inline-block px-1.5 py-0.5 rounded text-xs ${askStatusColor(q.status)}`}>
                        {q.status}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-right text-neutral-600 tabular-nums">
                      {q.latency_ms != null ? `${(q.latency_ms / 1000).toFixed(1)}s` : "-"}
                    </td>
                  </tr>
                ))}
                {overview.ask.recent.length === 0 && (
                  <tr>
                    <td colSpan={5} className="px-3 py-6 text-center text-neutral-400 text-sm">
                      No questions logged.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </main>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="border border-neutral-200 rounded-md p-3">
      <div className="text-xs text-neutral-500">{label}</div>
      <div className="text-2xl font-medium text-neutral-900 mt-1 tabular-nums">
        {value.toLocaleString()}
      </div>
    </div>
  );
}

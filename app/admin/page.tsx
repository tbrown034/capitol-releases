"use client";

import { useEffect, useState } from "react";
import { useSession, signIn, signOut } from "@/app/lib/auth-client";

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
    senator_id: string | null;
    severity: string;
    message: string;
    acknowledged: boolean;
  }>;
};

function formatTime(iso: string | null): string {
  if (!iso) return "—";
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

export default function AdminPage() {
  const { data: session, isPending } = useSession();
  const [overview, setOverview] = useState<Overview | null>(null);
  const [overviewError, setOverviewError] = useState<string | null>(null);
  const [overviewLoading, setOverviewLoading] = useState(false);

  useEffect(() => {
    if (!session?.user?.email) return;
    setOverviewLoading(true);
    fetch("/api/admin/overview")
      .then(async (r) => {
        if (r.status === 401) {
          setOverviewError("unauthorized");
          return null;
        }
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((data) => {
        if (data) setOverview(data);
      })
      .catch((e) => setOverviewError(String(e)))
      .finally(() => setOverviewLoading(false));
  }, [session?.user?.email]);

  if (isPending) {
    return (
      <main className="mx-auto max-w-3xl px-4 py-16">
        <p className="text-sm text-neutral-500">Loading…</p>
      </main>
    );
  }

  if (!session) {
    return (
      <main className="mx-auto max-w-md px-4 py-16">
        <h1 className="text-2xl font-medium text-neutral-900 mb-2">Admin</h1>
        <p className="text-sm text-neutral-600 mb-8">
          Sign in to access the dashboard.
        </p>
        <button
          onClick={async () => {
            const res = await signIn.social({
              provider: "google",
              callbackURL: "/admin",
            });
            if (res?.data?.url) window.location.href = res.data.url;
          }}
          className="w-full rounded-md border border-neutral-300 bg-white px-4 py-2.5 text-sm font-medium text-neutral-900 hover:bg-neutral-50 transition-colors cursor-pointer"
        >
          Sign in with Google
        </button>
      </main>
    );
  }

  const email = session.user?.email ?? "";

  if (overviewError === "unauthorized") {
    return (
      <main className="mx-auto max-w-md px-4 py-16">
        <h1 className="text-2xl font-medium text-neutral-900 mb-2">Not authorized</h1>
        <p className="text-sm text-neutral-600 mb-6">
          {email} is signed in but not on the admin allowlist.
        </p>
        <button
          onClick={async () => {
            await signOut();
            window.location.reload();
          }}
          className="text-sm text-neutral-600 hover:text-neutral-900 underline cursor-pointer"
        >
          Sign out
        </button>
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-5xl px-4 py-10">
      <div className="flex items-start justify-between mb-8">
        <div>
          <h1 className="text-2xl font-medium text-neutral-900">Admin</h1>
          <p className="text-sm text-neutral-500 mt-1">Signed in as {email}</p>
        </div>
        <button
          onClick={async () => {
            await signOut();
            window.location.href = "/";
          }}
          className="text-sm text-neutral-600 hover:text-neutral-900 underline cursor-pointer"
        >
          Sign out
        </button>
      </div>

      {overviewLoading && !overview && (
        <p className="text-sm text-neutral-500">Loading overview…</p>
      )}

      {overview && (
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
                      <td className="px-3 py-2 text-neutral-600">{a.senator_id ?? "—"}</td>
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
        </div>
      )}
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

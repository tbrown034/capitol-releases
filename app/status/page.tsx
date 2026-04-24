import Link from "next/link";
import { getRecentRuns } from "../lib/queries";

export const metadata = {
  title: "Run history — Capitol Releases",
  description:
    "Daily pipeline runs, inserts, and errors for the Capitol Releases scraper.",
};

export const dynamic = "force-dynamic";

function fmtDate(iso: string): string {
  return new Date(iso).toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
    timeZone: "America/New_York",
    timeZoneName: "short",
  });
}

function fmtDuration(startIso: string, endIso: string | null): string {
  if (!endIso) return "—";
  const ms = new Date(endIso).getTime() - new Date(startIso).getTime();
  if (ms < 1000) return "<1s";
  const s = Math.round(ms / 1000);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  const rem = s % 60;
  return rem ? `${m}m ${rem}s` : `${m}m`;
}

export default async function StatusPage() {
  const runs = await getRecentRuns(50);

  return (
    <div className="mx-auto max-w-4xl px-4">
      <section className="pt-10 pb-8 md:pt-16 md:pb-12">
        <h1 className="font-serif text-4xl sm:text-5xl leading-[1.05] text-neutral-900 mb-4">
          Run history
        </h1>
        <p className="text-sm md:text-base text-neutral-500 max-w-2xl leading-relaxed">
          The daily pipeline runs at 9:00 AM ET on GitHub Actions. Each row is
          one invocation. Failures show as red and trigger an alert email.
        </p>
        <p className="text-xs text-neutral-400 mt-3">
          Full logs, including per-senator output, live in{" "}
          <a
            href="https://github.com/tbrown034/capitol-releases/actions"
            className="underline hover:text-neutral-900"
            target="_blank"
            rel="noopener noreferrer"
          >
            GitHub Actions
          </a>
          .
        </p>
      </section>

      <div className="overflow-x-auto border-t border-neutral-200">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-neutral-200 text-xs uppercase tracking-wide text-neutral-500">
              <th className="py-2 pr-4 text-left font-medium">Finished</th>
              <th className="py-2 pr-4 text-right font-medium">Duration</th>
              <th className="py-2 pr-4 text-right font-medium">Processed</th>
              <th className="py-2 pr-4 text-right font-medium">With new</th>
              <th className="py-2 pr-4 text-right font-medium">Inserted</th>
              <th className="py-2 pr-4 text-right font-medium">Errors</th>
            </tr>
          </thead>
          <tbody className="font-mono tabular-nums">
            {runs.map((r) => (
              <tr key={r.id} className="border-b border-neutral-100">
                <td className="py-2 pr-4 text-neutral-900">
                  {r.finished_at ? fmtDate(r.finished_at) : (
                    <span className="text-neutral-400">running</span>
                  )}
                </td>
                <td className="py-2 pr-4 text-right text-neutral-500">
                  {fmtDuration(r.started_at, r.finished_at)}
                </td>
                <td className="py-2 pr-4 text-right">{r.senators_processed}</td>
                <td className="py-2 pr-4 text-right">{r.senators_with_new}</td>
                <td className="py-2 pr-4 text-right text-neutral-900">
                  {r.inserted.toLocaleString()}
                </td>
                <td
                  className={`py-2 pr-4 text-right ${
                    r.errors > 0 ? "text-red-600" : "text-neutral-400"
                  }`}
                >
                  {r.errors}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p className="mt-8 mb-16 text-xs text-neutral-400">
        Showing the last {runs.length} daily runs.{" "}
        <Link href="/" className="underline hover:text-neutral-900">
          Back to home
        </Link>
        .
      </p>
    </div>
  );
}

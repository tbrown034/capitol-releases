import Link from "next/link";
import { getAllBriefs } from "../../lib/queries";
import type { Brief } from "../../lib/db";

export const metadata = {
  title: "Brief Archive — Capitol Releases",
  description:
    "Every published Capitol Releases brief, daily and weekly, organized by month.",
};

const FILTERS: { label: string; value: "all" | "daily" | "weekly" }[] = [
  { label: "All", value: "all" },
  { label: "Daily", value: "daily" },
  { label: "Weekly", value: "weekly" },
];

function fmtDate(d: string): string {
  return new Date(`${d}T12:00:00Z`).toLocaleDateString("en-US", {
    weekday: "short",
    month: "short",
    day: "numeric",
  });
}

function fmtMonth(d: string): string {
  return new Date(`${d}T12:00:00Z`).toLocaleDateString("en-US", {
    month: "long",
    year: "numeric",
  });
}

function groupByMonth(briefs: Brief[]): { month: string; items: Brief[] }[] {
  const groups: Record<string, Brief[]> = {};
  for (const b of briefs) {
    const key = b.brief_date.slice(0, 7);
    (groups[key] ??= []).push(b);
  }
  return Object.keys(groups)
    .sort((a, b) => (a < b ? 1 : -1))
    .map((key) => ({
      month: fmtMonth(`${key}-15`),
      items: groups[key],
    }));
}

export default async function BriefArchivePage({
  searchParams,
}: {
  searchParams: Promise<{ edition?: string }>;
}) {
  const params = await searchParams;
  const editionParam =
    params.edition === "daily" || params.edition === "weekly"
      ? params.edition
      : "all";

  const briefs = await getAllBriefs(
    editionParam === "all" ? undefined : editionParam
  );
  const groups = groupByMonth(briefs);

  return (
    <div className="mx-auto max-w-3xl px-4 py-12">
      <div className="mb-3 flex items-center gap-2 text-[0.7rem] font-[family-name:var(--font-dm-mono)] uppercase tracking-[0.18em] text-neutral-500">
        <Link href="/brief" className="text-neutral-900 hover:text-neutral-700">
          Capitol Brief
        </Link>
        <span aria-hidden className="text-neutral-300">
          /
        </span>
        <span>Archive</span>
      </div>

      <h1 className="font-[family-name:var(--font-source-serif)] text-4xl text-neutral-900 mb-2">
        Brief archive
      </h1>
      <p className="text-sm text-neutral-600 leading-relaxed mb-6 max-w-2xl">
        Every published brief, daily and weekly. Daily briefs run Tuesday
        through Saturday evenings. Weekly briefs publish Thursday night,
        covering the seven-day Senate work cycle (Friday previous through
        Thursday this week).
      </p>

      <div className="mb-8 flex items-center gap-1 text-sm">
        {FILTERS.map((f) => {
          const active = editionParam === f.value;
          const href = f.value === "all" ? "/brief/archive" : `/brief/archive?edition=${f.value}`;
          return (
            <Link
              key={f.value}
              href={href}
              className={`rounded border px-3 py-1.5 transition-colors ${
                active
                  ? "border-neutral-900 bg-neutral-900 text-white"
                  : "border-neutral-200 bg-white text-neutral-700 hover:border-neutral-400"
              }`}
            >
              {f.label}
            </Link>
          );
        })}
        <span className="ml-auto font-[family-name:var(--font-dm-mono)] tabular-nums text-xs text-neutral-500">
          {briefs.length} {briefs.length === 1 ? "brief" : "briefs"}
        </span>
      </div>

      {groups.length === 0 ? (
        <p className="text-neutral-600">No briefs yet.</p>
      ) : (
        groups.map((g) => (
          <section key={g.month} className="mb-10">
            <h2 className="font-[family-name:var(--font-source-serif)] text-lg text-neutral-900 mb-3 border-b border-neutral-200 pb-2">
              {g.month}
            </h2>
            <ul className="space-y-3">
              {g.items.map((b) => (
                <li key={b.id}>
                  <Link
                    href={`/brief/${b.brief_date}${b.edition === "weekly" ? "?edition=weekly" : ""}`}
                    className="group block"
                  >
                    <div className="flex items-baseline gap-3">
                      <span className="font-[family-name:var(--font-dm-mono)] tabular-nums text-xs text-neutral-500 shrink-0 w-20">
                        {fmtDate(b.brief_date)}
                      </span>
                      <span
                        className={`shrink-0 inline-block rounded px-1.5 py-0.5 font-[family-name:var(--font-dm-mono)] text-[0.6rem] uppercase tracking-wide ${
                          b.edition === "weekly"
                            ? "bg-amber-900 text-amber-50"
                            : "bg-neutral-200 text-neutral-700"
                        }`}
                      >
                        {b.edition}
                      </span>
                      <span className="text-neutral-900 group-hover:underline leading-snug">
                        {b.headline}
                      </span>
                    </div>
                    {b.dek && (
                      <p className="ml-[5.75rem] mt-1 text-xs text-neutral-500 leading-snug">
                        {b.dek}
                      </p>
                    )}
                  </Link>
                </li>
              ))}
            </ul>
          </section>
        ))
      )}
    </div>
  );
}

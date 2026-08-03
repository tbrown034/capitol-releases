import Link from "next/link";
import { notFound } from "next/navigation";
import {
  getBriefByDate,
  getRecentBriefs,
  getBriefCitations,
  getThemeSparkline,
} from "../../lib/queries";
import { BriefBody, type ThemeSeries } from "../../components/brief-body";

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

function fmtDate(d: string): string {
  return new Date(`${d}T12:00:00Z`).toLocaleDateString("en-US", {
    weekday: "long",
    month: "long",
    day: "numeric",
    year: "numeric",
  });
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ date: string }>;
}) {
  const { date } = await params;
  if (!DATE_RE.test(date)) return { title: "Daily Brief — Capitol Releases" };
  const brief = await getBriefByDate(date);
  if (!brief) return { title: "Daily Brief — Capitol Releases" };
  return {
    title: `${brief.headline} — Capitol Brief, ${fmtDate(date)}`,
    description: brief.dek ?? undefined,
  };
}

export default async function BriefDatePage({
  params,
  searchParams,
}: {
  params: Promise<{ date: string }>;
  searchParams: Promise<{ edition?: string }>;
}) {
  const [{ date }, { edition: editionParam }] = await Promise.all([
    params,
    searchParams,
  ]);
  if (!DATE_RE.test(date)) notFound();

  const edition: "daily" | "weekly" =
    editionParam === "weekly" ? "weekly" : "daily";
  const brief = await getBriefByDate(date, edition);
  if (!brief) notFound();

  const [recent, citations, sparklines] = await Promise.all([
    getRecentBriefs(14),
    getBriefCitations(brief.cited_release_ids ?? []),
    Promise.all(
      brief.sections.map<Promise<ThemeSeries>>((sec) =>
        sec.keywords && sec.keywords.length > 0
          ? getThemeSparkline({
              keywords: sec.keywords,
              endDate: brief.brief_date,
              days: 30,
            })
          : Promise.resolve([])
      )
    ),
  ]);

  return (
    <div className="mx-auto max-w-3xl px-4 py-12">
      <div className="mb-3 flex items-center gap-2 text-[0.7rem] font-[family-name:var(--font-dm-mono)] uppercase tracking-[0.18em] text-neutral-500">
        <Link
          href="/brief"
          className="text-neutral-900 hover:text-neutral-700"
        >
          Capitol Brief
        </Link>
        <span aria-hidden className="text-neutral-300">
          /
        </span>
        <span
          className={`rounded px-1.5 py-0.5 ${
            brief.edition === "weekly"
              ? "bg-amber-900 text-amber-50"
              : "bg-neutral-200 text-neutral-700"
          }`}
        >
          {brief.edition}
        </span>
        <span aria-hidden className="text-neutral-300">
          /
        </span>
        <span>{fmtDate(brief.brief_date)}</span>
        <Link
          href="/brief/archive"
          className="ml-auto rounded border border-neutral-200 px-2 py-0.5 text-neutral-700 hover:border-neutral-400 hover:text-neutral-900"
        >
          Archive
        </Link>
      </div>

      <h1 className="font-[family-name:var(--font-source-serif)] text-[2.5rem] leading-[1.15] text-neutral-900 mb-6">
        {brief.headline}
      </h1>

      <BriefBody brief={brief} citations={citations} sparklines={sparklines} />

      {recent.length > 1 && (
        <section className="mt-12 border-t border-neutral-200 pt-6">
          <h2 className="font-[family-name:var(--font-source-serif)] text-xl text-neutral-900 mb-4">
            Other briefs
          </h2>
          <ul className="space-y-2 text-sm">
            {recent.flatMap((r) =>
              r.brief_date === brief.brief_date && r.edition === brief.edition
                ? []
                : [
                <li key={r.id}>
                  <Link
                    href={`/brief/${r.brief_date}${r.edition === "weekly" ? "?edition=weekly" : ""}`}
                    className="group flex items-baseline gap-3 text-neutral-700 hover:text-neutral-900"
                  >
                    <span className="font-[family-name:var(--font-dm-mono)] tabular-nums text-xs text-neutral-500 shrink-0 w-20">
                      {r.brief_date}
                    </span>
                    <span
                      className={`shrink-0 inline-block rounded px-1.5 py-0.5 font-[family-name:var(--font-dm-mono)] text-[0.6rem] uppercase tracking-wide ${
                        r.edition === "weekly"
                          ? "bg-amber-900 text-amber-50"
                          : "bg-neutral-200 text-neutral-700"
                      }`}
                    >
                      {r.edition}
                    </span>
                    <span className="group-hover:underline">{r.headline}</span>
                  </Link>
                </li>,
              ]
            )}
          </ul>
          <Link
            href="/brief/archive"
            className="mt-4 inline-block text-xs text-neutral-500 hover:text-neutral-900 hover:underline"
          >
            View full archive →
          </Link>
        </section>
      )}
    </div>
  );
}

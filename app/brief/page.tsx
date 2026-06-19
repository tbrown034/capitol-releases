import Link from "next/link";
import {
  getLatestBrief,
  getRecentBriefs,
  getBriefCitations,
  getThemeSparkline,
} from "../lib/queries";
import { BriefBody, type ThemeSeries } from "../components/brief-body";
import { BriefSignup } from "../components/brief-signup";

export const metadata = {
  title: "Daily Brief, Capitol Releases",
  description:
    "An AI-generated daily brief summarizing every U.S. senator's official communications, with every claim grounded in source records.",
};

// Without this, the index is statically generated at build time and pins to
// whatever brief was latest at deploy — it sat 3 weeks stale on May 29 while
// the cron kept publishing. 10-min ISR matches the homepage and keeps it live.
export const revalidate = 600;

function fmtDate(d: string): string {
  return new Date(`${d}T12:00:00Z`).toLocaleDateString("en-US", {
    weekday: "long",
    month: "long",
    day: "numeric",
    year: "numeric",
  });
}

export default async function BriefIndexPage() {
  const brief = await getLatestBrief();
  if (!brief) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-16">
        <h1 className="font-[family-name:var(--font-source-serif)] text-3xl text-neutral-900 mb-3">
          The brief is on the way.
        </h1>
        <p className="text-neutral-700 leading-relaxed mb-6">
          We haven&apos;t published the first daily brief yet. The pipeline
          generates one each evening (Tuesday through Saturday), summarizing
          that day&apos;s senate.gov releases.
        </p>
        <BriefSignup source="brief-empty" />
      </div>
    );
  }

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
        <span className="text-neutral-900">Capitol Brief</span>
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

      <p className="mb-6 max-w-xl border-l-2 border-neutral-200 pl-3 text-[0.82rem] leading-relaxed text-neutral-600">
        An AI-synthesized digest of every U.S. senator&apos;s official
        communications from the past {brief.edition === "weekly" ? "week" : "day"}, every claim cites its source record.{" "}
        <Link
          href="/methodology"
          className="text-neutral-500 underline decoration-neutral-300 underline-offset-2 hover:text-neutral-900 hover:decoration-neutral-500"
        >
          How this is made
        </Link>
        .
      </p>

      <h1 className="font-[family-name:var(--font-source-serif)] text-[2.5rem] leading-[1.15] text-neutral-900 mb-6">
        {brief.headline}
      </h1>

      <BriefBody brief={brief} citations={citations} sparklines={sparklines} />

      <div className="mt-12">
        <BriefSignup />
      </div>

      {recent.length > 1 && (
        <section className="mt-12 border-t border-neutral-200 pt-6">
          <h2 className="font-[family-name:var(--font-source-serif)] text-xl text-neutral-900 mb-4">
            Earlier briefs
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

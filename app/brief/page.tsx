import Link from "next/link";
import { notFound } from "next/navigation";
import {
  getLatestBrief,
  getRecentBriefs,
  getBriefCitations,
  getThemeSparkline,
} from "../lib/queries";
import { BriefBody, type ThemeSeries } from "../components/brief-body";
import { BriefSignup } from "../components/brief-signup";

export const metadata = {
  title: "Daily Brief — Capitol Releases",
  description:
    "An AI-generated daily brief summarizing every U.S. senator's official communications, with every claim grounded in source records.",
};

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
        <span>{fmtDate(brief.brief_date)}</span>
      </div>

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
            {recent
              .filter((r) => r.brief_date !== brief.brief_date)
              .map((r) => (
                <li key={r.id}>
                  <Link
                    href={`/brief/${r.brief_date}`}
                    className="group flex items-baseline gap-3 text-neutral-700 hover:text-neutral-900"
                  >
                    <span className="font-[family-name:var(--font-dm-mono)] tabular-nums text-xs text-neutral-500 shrink-0 w-20">
                      {r.brief_date}
                    </span>
                    <span className="group-hover:underline">{r.headline}</span>
                  </Link>
                </li>
              ))}
          </ul>
        </section>
      )}
    </div>
  );
}

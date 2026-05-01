import Link from "next/link";
import { notFound } from "next/navigation";
import {
  getLatestBrief,
  getRecentBriefs,
  getBriefCitations,
} from "../lib/queries";
import { BriefBody } from "../components/brief-body";

export const metadata = {
  title: "Daily Brief — Capitol Releases",
  description:
    "An AI-generated daily brief summarizing every U.S. senator's official communications.",
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
  if (!brief) notFound();

  const [recent, citations] = await Promise.all([
    getRecentBriefs(14),
    getBriefCitations(brief.cited_release_ids ?? []),
  ]);

  return (
    <div className="mx-auto max-w-3xl px-4 py-12">
      <div className="mb-2 flex items-center gap-2 text-xs font-[family-name:var(--font-dm-mono)] uppercase tracking-wide text-neutral-500">
        <span>Daily brief</span>
        <span aria-hidden>·</span>
        <span>{fmtDate(brief.brief_date)}</span>
      </div>

      <h1 className="font-[family-name:var(--font-source-serif)] text-4xl leading-tight text-neutral-900 mb-4">
        {brief.headline}
      </h1>

      <div className="mb-8 rounded border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900">
        <strong>AI-generated.</strong> This brief is synthesized by Claude
        Sonnet 4.6 from the day's collected releases. Every claim links to a
        source record. The canonical archive lives at{" "}
        <Link href="/feed" className="underline">
          /feed
        </Link>
        .
      </div>

      <BriefBody brief={brief} citations={citations} />

      {recent.length > 1 && (
        <section className="mt-12 border-t border-neutral-200 pt-6">
          <h2 className="font-[family-name:var(--font-source-serif)] text-lg text-neutral-900 mb-3">
            Earlier briefs
          </h2>
          <ul className="space-y-1 text-sm">
            {recent
              .filter((r) => r.brief_date !== brief.brief_date)
              .map((r) => (
                <li key={r.id}>
                  <Link
                    href={`/brief/${r.brief_date}`}
                    className="text-neutral-700 hover:text-neutral-900 hover:underline"
                  >
                    <span className="font-[family-name:var(--font-dm-mono)] tabular-nums text-neutral-500 mr-3">
                      {r.brief_date}
                    </span>
                    {r.headline}
                  </Link>
                </li>
              ))}
          </ul>
        </section>
      )}
    </div>
  );
}

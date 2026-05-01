import Link from "next/link";
import type { Brief, BriefCitation } from "../lib/db";
import { ThemeSparkline } from "./theme-sparkline";

export type ThemeSeries = { date: string; count: number }[];

function paragraphs(text: string): string[] {
  return text
    .split(/\n\n+/)
    .map((p) => p.trim())
    .filter(Boolean);
}

const PARTY_DOT: Record<string, string> = {
  D: "bg-sky-500",
  R: "bg-rose-500",
  I: "bg-amber-500",
};

function CitationCards({
  ids,
  citations,
}: {
  ids: string[];
  citations: Map<string, BriefCitation>;
}) {
  const resolved = ids
    .map((id) => citations.get(id))
    .filter((c): c is BriefCitation => Boolean(c));
  if (resolved.length === 0) return null;
  return (
    <div className="mt-4 grid gap-1.5">
      {resolved.map((c) => (
        <Link
          key={c.id}
          href={`/releases/${c.id}`}
          className="group flex items-start gap-2.5 rounded border border-neutral-200 bg-white px-3 py-2 text-xs leading-snug transition-colors hover:border-neutral-400"
        >
          <span
            aria-hidden
            className={`mt-1 h-2 w-2 shrink-0 rounded-full ${PARTY_DOT[c.party] ?? "bg-neutral-400"}`}
          />
          <span className="flex-1">
            <span className="font-medium text-neutral-900">
              {c.senator_name}
            </span>
            <span className="text-neutral-500">
              {" "}
              · {c.party}-{c.state}
            </span>
            <span className="block text-neutral-700 group-hover:text-neutral-900">
              {c.title}
            </span>
          </span>
        </Link>
      ))}
    </div>
  );
}

export function BriefBody({
  brief,
  citations,
  sparklines,
}: {
  brief: Brief;
  citations: Map<string, BriefCitation>;
  sparklines?: ThemeSeries[];
}) {
  const sourceCount = brief.source_release_ids?.length ?? 0;
  const themeCount = brief.sections?.length ?? 0;
  const sectionsWithReleases = brief.sections.flatMap((s) => s.release_ids);
  const senatorsCount = new Set(
    sectionsWithReleases
      .map((id) => citations.get(id)?.senator_name)
      .filter(Boolean)
  ).size;

  return (
    <article className="text-neutral-900">
      {brief.dek && (
        <p className="text-lg text-neutral-700 leading-relaxed mb-6 font-[family-name:var(--font-source-serif)]">
          {brief.dek}
        </p>
      )}

      <div className="mb-10 grid grid-cols-3 gap-4 rounded border border-neutral-200 bg-neutral-50 px-4 py-3 text-center">
        <div>
          <div className="font-[family-name:var(--font-dm-mono)] tabular-nums text-xl text-neutral-900">
            {sourceCount}
          </div>
          <div className="text-[0.65rem] uppercase tracking-wide text-neutral-500">
            releases
          </div>
        </div>
        <div className="border-x border-neutral-200">
          <div className="font-[family-name:var(--font-dm-mono)] tabular-nums text-xl text-neutral-900">
            {senatorsCount}
          </div>
          <div className="text-[0.65rem] uppercase tracking-wide text-neutral-500">
            senators cited
          </div>
        </div>
        <div>
          <div className="font-[family-name:var(--font-dm-mono)] tabular-nums text-xl text-neutral-900">
            {themeCount}
          </div>
          <div className="text-[0.65rem] uppercase tracking-wide text-neutral-500">
            themes
          </div>
        </div>
      </div>

      <div className="mb-12">
        {paragraphs(brief.lede).map((p, i) => (
          <p
            key={i}
            className={`leading-[1.7] mb-4 text-neutral-900 ${i === 0 ? "text-[1.1rem]" : "text-[1.05rem]"}`}
          >
            {p}
          </p>
        ))}
      </div>

      {brief.sections.map((sec, i) => {
        const series = sparklines?.[i];
        const hasSeries = series && series.length > 0;
        return (
          <section
            key={i}
            className="border-t border-neutral-200 pt-7 mb-9"
          >
            <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
              <h2 className="font-[family-name:var(--font-source-serif)] text-2xl leading-tight text-neutral-900">
                {sec.theme}
              </h2>
              {hasSeries && (
                <ThemeSparkline
                  data={series}
                  highlightDate={brief.brief_date}
                />
              )}
            </div>
            {paragraphs(sec.body).map((p, j) => (
              <p
                key={j}
                className="leading-[1.7] mb-3 text-neutral-800"
              >
                {p}
              </p>
            ))}
            <CitationCards ids={sec.release_ids} citations={citations} />
          </section>
        );
      })}

      {brief.signals.length > 0 && (
        <section className="border-t border-neutral-200 pt-7 mb-9">
          <h2 className="font-[family-name:var(--font-source-serif)] text-2xl text-neutral-900 mb-4">
            Signals
          </h2>
          <ul className="space-y-3">
            {brief.signals.map((s, i) => (
              <li
                key={i}
                className="flex gap-3 rounded border border-neutral-200 bg-neutral-50 px-3 py-2 text-sm leading-relaxed"
              >
                <span className="mt-0.5 inline-block shrink-0 rounded bg-neutral-900 px-1.5 py-0.5 font-[family-name:var(--font-dm-mono)] text-[0.6rem] uppercase tracking-wide text-white">
                  {s.kind.replace(/_/g, " ")}
                </span>
                <span className="text-neutral-800">{s.note}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {brief.quotes && brief.quotes.length > 0 && (
        <section className="border-t border-neutral-200 pt-7 mb-9">
          <h2 className="font-[family-name:var(--font-source-serif)] text-2xl text-neutral-900 mb-4">
            Five quotes that defined the week
          </h2>
          <ul className="space-y-5">
            {brief.quotes.map((q, i) => {
              const cite = q.release_id ? citations.get(q.release_id) : null;
              return (
                <li key={i} className="border-l-2 border-neutral-900 pl-4">
                  <p className="font-[family-name:var(--font-source-serif)] text-lg italic leading-snug text-neutral-900">
                    &ldquo;{q.text}&rdquo;
                  </p>
                  <p className="mt-2 text-sm text-neutral-700">
                    — {q.speaker}
                    {q.context && (
                      <span className="text-neutral-500"> · {q.context}</span>
                    )}
                  </p>
                  {cite && (
                    <Link
                      href={`/releases/${cite.id}`}
                      className="mt-1 inline-block text-xs text-neutral-500 hover:text-neutral-900 hover:underline"
                    >
                      Source: {cite.title}
                    </Link>
                  )}
                </li>
              );
            })}
          </ul>
        </section>
      )}

      {brief.silent.length > 0 && (
        <section className="border-t border-neutral-200 pt-7 mb-9">
          <h2 className="font-[family-name:var(--font-source-serif)] text-2xl text-neutral-900 mb-2">
            {brief.edition === "weekly" ? "Quiet weeks" : "Quiet desks"}
          </h2>
          <p className="text-xs text-neutral-500 mb-4">
            {brief.edition === "weekly"
              ? "Senators with zero releases in this seven-day window."
              : "Senators with no release in two weeks or more."}
          </p>
          <ul className="grid gap-1 text-sm text-neutral-700 sm:grid-cols-2">
            {brief.silent.map((s, i) => {
              type SilentLike = {
                senator: string;
                days_quiet?: number;
                days_quiet_in_window?: number;
              };
              const sl = s as SilentLike;
              const days = sl.days_quiet_in_window ?? sl.days_quiet ?? 0;
              return (
                <li
                  key={i}
                  className="flex items-baseline justify-between gap-3 border-b border-neutral-100 py-1"
                >
                  <span>{sl.senator}</span>
                  <span className="font-[family-name:var(--font-dm-mono)] tabular-nums text-xs text-neutral-500">
                    {days >= 999 ? "—" : `${days}d`}
                  </span>
                </li>
              );
            })}
          </ul>
        </section>
      )}

      <footer className="mt-12 border-t border-neutral-200 pt-6 text-xs leading-relaxed text-neutral-500">
        <p className="mb-1">
          <span className="font-medium text-neutral-700">How this is made.</span>{" "}
          Every {brief.brief_date} brief is synthesized by Anthropic&apos;s
          Claude Sonnet 4.6 from the day&apos;s collected senate.gov releases.
          The model can only cite releases in our archive, and every section
          links to the source records used. The canonical archive lives at{" "}
          <Link href="/feed" className="underline hover:text-neutral-900">
            /feed
          </Link>
          .
        </p>
      </footer>
    </article>
  );
}

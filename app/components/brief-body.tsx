import Link from "next/link";
import type { Brief, BriefCitation } from "../lib/db";

function paragraphs(text: string): string[] {
  return text
    .split(/\n\n+/)
    .map((p) => p.trim())
    .filter(Boolean);
}

function CitationList({
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
    <ul className="mt-3 space-y-1 text-xs text-neutral-500">
      {resolved.map((c) => (
        <li key={c.id} className="leading-snug">
          <Link
            href={`/releases/${c.id}`}
            className="text-neutral-700 hover:text-neutral-900 hover:underline"
          >
            {c.senator_name} ({c.party}-{c.state}) — {c.title}
          </Link>
        </li>
      ))}
    </ul>
  );
}

export function BriefBody({
  brief,
  citations,
}: {
  brief: Brief;
  citations: Map<string, BriefCitation>;
}) {
  return (
    <article className="text-neutral-900">
      {brief.dek && (
        <p className="text-base text-neutral-600 leading-relaxed mb-8">
          {brief.dek}
        </p>
      )}

      <div className="prose prose-neutral max-w-none mb-10">
        {paragraphs(brief.lede).map((p, i) => (
          <p key={i} className="leading-relaxed mb-4 text-[1.05rem]">
            {p}
          </p>
        ))}
      </div>

      {brief.sections.map((sec, i) => (
        <section
          key={i}
          className="border-t border-neutral-200 pt-6 mb-8"
        >
          <h2 className="font-[family-name:var(--font-source-serif)] text-xl text-neutral-900 mb-3">
            {sec.theme}
          </h2>
          {paragraphs(sec.body).map((p, j) => (
            <p
              key={j}
              className="leading-relaxed mb-3 text-[0.98rem] text-neutral-800"
            >
              {p}
            </p>
          ))}
          <CitationList ids={sec.release_ids} citations={citations} />
        </section>
      ))}

      {brief.signals.length > 0 && (
        <section className="border-t border-neutral-200 pt-6 mb-8">
          <h2 className="font-[family-name:var(--font-source-serif)] text-xl text-neutral-900 mb-3">
            Signals
          </h2>
          <ul className="space-y-2">
            {brief.signals.map((s, i) => (
              <li key={i} className="text-sm leading-relaxed text-neutral-700">
                <span className="font-[family-name:var(--font-dm-mono)] text-xs uppercase tracking-wide text-neutral-500 mr-2">
                  {s.kind.replace(/_/g, " ")}
                </span>
                {s.note}
              </li>
            ))}
          </ul>
        </section>
      )}

      {brief.silent.length > 0 && (
        <section className="border-t border-neutral-200 pt-6 mb-8">
          <h2 className="font-[family-name:var(--font-source-serif)] text-xl text-neutral-900 mb-3">
            Quiet desks
          </h2>
          <ul className="space-y-1 text-sm text-neutral-700">
            {brief.silent.map((s, i) => (
              <li key={i}>
                {s.senator}{" "}
                <span className="text-neutral-500">
                  — {s.days_quiet} days without a release
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </article>
  );
}

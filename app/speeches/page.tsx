import Link from "next/link";
import { getFloorSpeeches } from "../lib/queries";
import { Pagination } from "../components/pagination";
import { EmptyState } from "../components/empty-state";

export const metadata = {
  title: "Speeches — Capitol Releases",
  description:
    "U.S. Senate floor speeches from the Congressional Record, since January 1, 2025. House coverage in Phase 2.",
};

export const revalidate = 600;

const CHAMBER_VALUES = ["all", "senate", "house"] as const;
type ChamberFilter = (typeof CHAMBER_VALUES)[number];

function normalizeChamber(s: string | undefined): ChamberFilter {
  return s === "senate" || s === "house" ? s : "all";
}

function formatDate(d: string): string {
  const dt = new Date(d);
  return dt.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    timeZone: "UTC",
  });
}

function partyColor(p: string): string {
  if (p === "D") return "text-blue-700";
  if (p === "R") return "text-red-700";
  return "text-neutral-600";
}

export default async function SpeechesPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | undefined>>;
}) {
  const sp = await searchParams;
  const chamber = normalizeChamber(sp.chamber);
  const page = Number(sp.page ?? "1");
  const perPage = 25;
  const party = sp.party;
  const state = sp.state;

  const { items, total, chamberAvailable } = await getFloorSpeeches({
    chamber,
    page,
    perPage,
    party,
    state,
  });

  const buildHref = (overrides: Record<string, string | null | undefined>) => {
    const u = new URLSearchParams();
    if (chamber !== "all") u.set("chamber", chamber);
    if (party) u.set("party", party);
    if (state) u.set("state", state);
    for (const [k, v] of Object.entries(overrides)) {
      if (v === null || v === undefined) u.delete(k);
      else u.set(k, v);
    }
    u.delete("page");
    const s = u.toString();
    return s ? `/speeches?${s}` : "/speeches";
  };

  return (
    <div className="mx-auto max-w-3xl px-4 py-12">
      <h1 className="font-[family-name:var(--font-source-serif)] text-4xl text-neutral-900 mb-3">
        Floor speeches
      </h1>
      <p className="text-sm text-neutral-600 leading-relaxed mb-2 max-w-2xl">
        Senate floor remarks from the Congressional Record, parsed into
        per-speaker turns. Pulled daily from{" "}
        <a
          href="https://www.congress.gov/congressional-record"
          className="underline hover:text-neutral-900"
          target="_blank"
          rel="noopener"
        >
          congress.gov
        </a>
        . House coverage is Phase 2 — the GPO bulkdata path differs and the
        parser isn&rsquo;t built yet.
      </p>
      <p className="text-xs text-neutral-500 leading-relaxed mb-6 max-w-2xl">
        <span className="font-[family-name:var(--font-dm-mono)] tabular-nums text-neutral-900 font-semibold">
          {total.toLocaleString()}
        </span>{" "}
        Senate floor speeches with body text since January 1, 2025.
      </p>

      <div className="flex flex-wrap gap-1 mb-6">
        {CHAMBER_VALUES.map((c) => (
          <Link
            key={c}
            href={buildHref({ chamber: c === "all" ? null : c })}
            className={`px-3 py-1 text-xs border ${
              chamber === c
                ? "border-neutral-900 bg-neutral-900 text-white"
                : "border-neutral-200 text-neutral-600 hover:border-neutral-400"
            }`}
          >
            {c === "all" ? "All Congress" : c === "senate" ? "Senate" : "House"}
          </Link>
        ))}
      </div>

      {chamber === "house" ? (
        <EmptyState
          message="House floor speeches are coming in Phase 2. The Congressional Record exposes the House sections via a different GPO bulkdata path; the parser hasn't been built yet."
          suggestions={[
            { label: "Browse Senate floor speeches", href: "/speeches?chamber=senate" },
            { label: "Browse press releases", href: "/feed" },
          ]}
        />
      ) : items.length === 0 ? (
        <EmptyState
          message="No speeches match these filters."
          clearHref="/speeches"
        />
      ) : (
        <>
          <ul className="divide-y divide-neutral-200 border-t border-neutral-200">
            {items.map((sp) => {
              const previewBody = sp.body_text
                ? sp.body_text.replace(/\s+/g, " ").trim().slice(0, 280)
                : "";
              return (
                <li key={sp.id} className="py-4">
                  <div className="flex flex-col gap-1">
                    <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5 text-xs text-neutral-500 font-[family-name:var(--font-dm-mono)] tabular-nums">
                      <time dateTime={sp.speech_date}>
                        {formatDate(sp.speech_date)}
                      </time>
                      <span>·</span>
                      <Link
                        href={`/senators/${sp.official_id}`}
                        className="text-neutral-900 hover:underline font-sans"
                      >
                        {sp.senator_name}
                      </Link>
                      <span className={`font-sans ${partyColor(sp.party)}`}>
                        ({sp.party}-{sp.state})
                      </span>
                      <span>·</span>
                      <span>{sp.word_count.toLocaleString()} words</span>
                    </div>
                    <h2 className="text-base text-neutral-900 leading-snug">
                      {sp.title}
                    </h2>
                    {previewBody && (
                      <p className="text-sm text-neutral-600 leading-snug line-clamp-2">
                        {previewBody}…
                      </p>
                    )}
                    {sp.detail_url && (
                      <a
                        href={sp.detail_url}
                        className="text-xs text-neutral-500 hover:text-neutral-900 underline self-start"
                        target="_blank"
                        rel="noopener"
                      >
                        Read on congress.gov →
                      </a>
                    )}
                  </div>
                </li>
              );
            })}
          </ul>
          <Pagination
            currentPage={page}
            perPage={perPage}
            total={total}
            basePath="/speeches"
          />
        </>
      )}
    </div>
  );
}

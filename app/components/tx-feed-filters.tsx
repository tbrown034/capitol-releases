"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { CONTENT_TYPE_LABEL } from "../lib/content-types";
import type { ContentType } from "../lib/db";

// Filter row for /texas/feed and /texas/search. Drops the state selector
// (TX is implied) and adds a senator selector. Content types in the
// dropdown are restricted to ones present in the TX corpus — showing
// "Presidential action" or "Floor statement" as filter options is
// confusing when no record matches them.
const TX_TYPES: ContentType[] = ["press_release", "other"];

export function TxFeedFilters({
  basePath,
  senators,
}: {
  basePath: string;
  senators: { id: string; full_name: string; district: number }[];
}) {
  const router = useRouter();
  const searchParams = useSearchParams();

  function update(key: string, value: string) {
    const params = new URLSearchParams(searchParams.toString());
    if (value) params.set(key, value);
    else params.delete(key);
    params.delete("page");
    const qs = params.toString();
    router.push(qs ? `${basePath}?${qs}` : basePath);
  }

  const party = searchParams.get("party") ?? "";
  const senator = searchParams.get("senator") ?? "";
  const type = searchParams.get("type") ?? "";

  const sortedSenators = [...senators].sort((a, b) => a.district - b.district);

  return (
    <div className="flex flex-wrap items-center gap-2 text-xs">
      <span className="uppercase tracking-wider text-neutral-500 mr-1">
        Filter
      </span>
      <select
        value={type}
        onChange={(e) => update("type", e.target.value)}
        aria-label="Filter by content type"
        className="border border-neutral-200 bg-white px-3 py-1.5 text-sm text-neutral-700 hover:border-neutral-400 transition-colors focus:border-neutral-900 focus:outline-none"
      >
        <option value="">All types</option>
        {TX_TYPES.map((t) => (
          <option key={t} value={t}>
            {t === "other" ? "Video / other" : CONTENT_TYPE_LABEL[t]}
          </option>
        ))}
      </select>
      <select
        value={party}
        onChange={(e) => update("party", e.target.value)}
        aria-label="Filter by party"
        className="border border-neutral-200 bg-white px-3 py-1.5 text-sm text-neutral-700 hover:border-neutral-400 transition-colors focus:border-neutral-900 focus:outline-none"
      >
        <option value="">All parties</option>
        <option value="D">Democrats</option>
        <option value="R">Republicans</option>
      </select>
      <select
        value={senator}
        onChange={(e) => update("senator", e.target.value)}
        aria-label="Filter by senator"
        className="border border-neutral-200 bg-white px-3 py-1.5 text-sm text-neutral-700 hover:border-neutral-400 transition-colors focus:border-neutral-900 focus:outline-none"
      >
        <option value="">All senators</option>
        {sortedSenators.map((s) => (
          <option key={s.id} value={s.id}>
            D{String(s.district).padStart(2, "0")} — {s.full_name}
          </option>
        ))}
      </select>
      {(party || senator || type) && (
        <button
          onClick={() => router.push(basePath)}
          className="text-sm text-neutral-500 underline hover:text-neutral-900 transition-colors ml-1"
        >
          Clear
        </button>
      )}
    </div>
  );
}

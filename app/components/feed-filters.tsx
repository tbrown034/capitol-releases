"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { getStates } from "../lib/states";
import { CONTENT_TYPE_ORDER, CONTENT_TYPE_LABEL } from "../lib/queries";

export function FeedFilters({ basePath = "/feed" }: { basePath?: string }) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const states = getStates();

  function update(key: string, value: string) {
    const params = new URLSearchParams(searchParams.toString());
    if (value) {
      params.set(key, value);
    } else {
      params.delete(key);
    }
    params.delete("page");
    router.push(`${basePath}?${params.toString()}`);
  }

  const party = searchParams.get("party") ?? "";
  const state = searchParams.get("state") ?? "";
  const type = searchParams.get("type") ?? "";

  return (
    <div className="flex flex-wrap items-center gap-2 text-xs">
      <span className="uppercase tracking-wider text-neutral-400 mr-1">
        Filter
      </span>
      <select
        value={type}
        onChange={(e) => update("type", e.target.value)}
        className="border border-neutral-200 bg-white px-3 py-1.5 text-sm text-neutral-700 hover:border-neutral-400 transition-colors focus:border-neutral-900 focus:outline-none"
      >
        <option value="">All types</option>
        {CONTENT_TYPE_ORDER.map((t) => (
          <option key={t} value={t}>
            {CONTENT_TYPE_LABEL[t]}
          </option>
        ))}
      </select>
      <select
        value={party}
        onChange={(e) => update("party", e.target.value)}
        className="border border-neutral-200 bg-white px-3 py-1.5 text-sm text-neutral-700 hover:border-neutral-400 transition-colors focus:border-neutral-900 focus:outline-none"
      >
        <option value="">All parties</option>
        <option value="D">Democrats</option>
        <option value="R">Republicans</option>
        <option value="I">Independents</option>
      </select>

      <select
        value={state}
        onChange={(e) => update("state", e.target.value)}
        className="border border-neutral-200 bg-white px-3 py-1.5 text-sm text-neutral-700 hover:border-neutral-400 transition-colors focus:border-neutral-900 focus:outline-none"
      >
        <option value="">All states</option>
        {states.map((s) => (
          <option key={s} value={s}>
            {s}
          </option>
        ))}
      </select>

      {(party || state || type) && (
        <button
          onClick={() => {
            router.push(basePath);
          }}
          className="text-sm text-neutral-500 underline hover:text-neutral-900 transition-colors ml-1"
        >
          Clear
        </button>
      )}
    </div>
  );
}

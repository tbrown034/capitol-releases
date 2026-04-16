"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { getStates } from "../lib/queries";

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

  return (
    <div className="flex flex-wrap items-center gap-3">
      <select
        value={party}
        onChange={(e) => update("party", e.target.value)}
        className="rounded border border-gray-300 bg-white px-3 py-1.5 text-sm"
      >
        <option value="">All parties</option>
        <option value="D">Democrat</option>
        <option value="R">Republican</option>
        <option value="I">Independent</option>
      </select>

      <select
        value={state}
        onChange={(e) => update("state", e.target.value)}
        className="rounded border border-gray-300 bg-white px-3 py-1.5 text-sm"
      >
        <option value="">All states</option>
        {states.map((s) => (
          <option key={s} value={s}>
            {s}
          </option>
        ))}
      </select>

      {(party || state) && (
        <button
          onClick={() => {
            router.push(basePath);
          }}
          className="text-sm text-gray-500 underline hover:text-gray-800"
        >
          Clear filters
        </button>
      )}
    </div>
  );
}

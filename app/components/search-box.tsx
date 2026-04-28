"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";

export function SearchBox({
  basePath = "/search",
  placeholder = "Search release text...",
}: {
  basePath?: string;
  placeholder?: string;
}) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [query, setQuery] = useState(searchParams.get("q") ?? "");

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!query.trim()) return;
    const params = new URLSearchParams();
    params.set("q", query.trim());
    for (const key of ["party", "state", "type"]) {
      const v = searchParams.get(key);
      if (v) params.set(key, v);
    }
    router.push(`${basePath}?${params.toString()}`);
  }

  return (
    <form onSubmit={handleSubmit} className="flex gap-3 items-end">
      <input
        type="text"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder={placeholder}
        className="flex-1 border-b border-neutral-300 bg-transparent px-1 py-2 text-sm text-neutral-900 focus:border-neutral-900 focus:outline-none transition-colors placeholder:text-neutral-400"
      />
      <button
        type="submit"
        className="border border-neutral-900 bg-neutral-900 px-4 py-1.5 text-sm text-white hover:bg-white hover:text-neutral-900 transition-colors"
      >
        Search
      </button>
    </form>
  );
}

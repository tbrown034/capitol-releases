"use client";

import { useMemo, useState } from "react";
import posthog from "posthog-js";
import { AskRecord } from "./ask-record";

// Front-page entry to "Ask the record": pick any member, then ask.
// Reuses the member-page AskRecord component wholesale — same statuses,
// citations, disclosure, and rate limits.

export type AskableMember = {
  id: string;
  full_name: string;
  party: string;
  state: string;
  chamber: string | null;
};

function chamberLabel(m: AskableMember): string {
  if (m.chamber === "senate") return "Sen.";
  if (m.chamber === "house") return "Rep.";
  return "";
}

export function AskAnyMember({ members }: { members: AskableMember[] }) {
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<AskableMember | null>(null);

  const matches = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (q.length < 2) return [];
    return members
      .filter(
        (m) =>
          m.full_name.toLowerCase().includes(q) ||
          m.state.toLowerCase() === q,
      )
      .slice(0, 8);
  }, [query, members]);

  if (selected) {
    return (
      <div>
        <div className="mb-3 flex items-center gap-2 text-sm">
          <span className="text-neutral-800 font-medium">
            {chamberLabel(selected)} {selected.full_name} ({selected.party}-
            {selected.state})
          </span>
          <button
            onClick={() => {
              setSelected(null);
              setQuery("");
            }}
            className="text-xs text-neutral-500 underline hover:text-neutral-900"
          >
            change member
          </button>
        </div>
        <AskRecord officialId={selected.id} memberName={selected.full_name} />
      </div>
    );
  }

  return (
    <div className="relative">
      <input
        type="text"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="Find your senator or representative..."
        aria-label="Search for a member of Congress to ask about"
        className="w-full border border-neutral-200 bg-white px-3 py-2 text-sm text-neutral-800 placeholder:text-neutral-400 focus:border-neutral-900 focus:outline-none transition-colors"
      />
      {matches.length > 0 && (
        <ul className="absolute z-10 mt-1 w-full border border-neutral-200 bg-white shadow-sm max-h-72 overflow-y-auto">
          {matches.map((m) => (
            <li key={m.id}>
              <button
                onClick={() => {
                  setSelected(m);
                  posthog.capture("ask_member_selected", { official_id: m.id });
                }}
                className="w-full px-3 py-2 text-left text-sm text-neutral-800 hover:bg-neutral-50 flex items-baseline justify-between"
              >
                <span>
                  {chamberLabel(m)} {m.full_name}
                </span>
                <span className="text-xs text-neutral-400">
                  {m.party}-{m.state}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
      <p className="mt-2 text-xs text-neutral-400">
        Ask about any member&apos;s record. Answers come only from their
        archived releases, with citations.
      </p>
    </div>
  );
}

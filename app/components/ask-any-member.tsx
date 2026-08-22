"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import posthog from "posthog-js";
import { AskRecord } from "./ask-record";

// Front-page "Ask the record": two boxes — pick a member (type-to-filter,
// dropdown, or one-click chips), then ask. A full question typed straight
// into the question box still works: we detect the member name inside it
// and fire in one Enter. Lesson learned live on launch morning: users type
// questions into the first box they see.

export type AskableMember = {
  id: string;
  full_name: string;
  party: string;
  state: string;
  chamber: string | null;
  passages?: number;
};

function chamberLabel(m: AskableMember): string {
  if (m.chamber === "senate") return "Sen.";
  if (m.chamber === "house") return "Rep.";
  return "";
}

function memberPath(m: AskableMember): string {
  return m.chamber === "house" ? `/house/${m.id}` : `/senators/${m.id}`;
}

// Words that appear in questions but are never the member's name.
const STOPWORDS = new Set([
  "sen", "senator", "rep", "representative", "congressman", "congresswoman",
  "what", "when", "where", "who", "why", "how", "did", "does", "has", "have",
  "had", "say", "said", "says", "about", "the", "and", "for", "recently",
  "their", "his", "her", "she", "him", "they", "think", "thinks", "stance",
  "position", "vote", "voted", "record",
]);

function detectMembers(
  text: string,
  members: AskableMember[],
): AskableMember[] {
  const tokens = (text.toLowerCase().match(/[a-z]{3,}/g) ?? []).filter(
    (t) => !STOPWORDS.has(t),
  );
  if (tokens.length === 0) return [];
  return members
    .filter((m) => {
      const name = m.full_name.toLowerCase();
      return tokens.some((t) => name.includes(t));
    })
    .slice(0, 8);
}

export function AskAnyMember({ members }: { members: AskableMember[] }) {
  const [query, setQuery] = useState("");
  const [pendingQuestion, setPendingQuestion] = useState("");
  const [selected, setSelected] = useState<AskableMember | null>(null);
  const [handoffQuestion, setHandoffQuestion] = useState<string>("");
  const [hint, setHint] = useState<string>("");

  // Clickable starters: deepest senate archives, balanced 3 D + 3 R and
  // interleaved — a nonpartisan archive doesn't lead with one party.
  const featured = useMemo(() => {
    const ranked = [...members].sort(
      (a, b) => (b.passages ?? 0) - (a.passages ?? 0),
    );
    const dems = ranked
      .filter((m) => m.party === "D" && m.chamber === "senate")
      .slice(0, 3);
    const reps = ranked
      .filter((m) => m.party === "R" && m.chamber === "senate")
      .slice(0, 3);
    const out: AskableMember[] = [];
    for (let i = 0; i < 3; i++) {
      if (dems[i]) out.push(dems[i]);
      if (reps[i]) out.push(reps[i]);
    }
    return out;
  }, [members]);

  const matches = useMemo(
    () => (query.trim().length >= 2 ? detectMembers(query, members) : []),
    [query, members],
  );

  function choose(m: AskableMember, question?: string) {
    setSelected(m);
    setHandoffQuestion((question ?? pendingQuestion).trim());
    setHint("");
    setQuery("");
    posthog.capture("ask_member_selected", { official_id: m.id });
  }

  // Fallback: a full question with no member selected — find the name in it.
  function onQuestionSubmit(e: React.FormEvent) {
    e.preventDefault();
    const cands = detectMembers(pendingQuestion, members);
    if (cands.length === 1) {
      choose(cands[0], pendingQuestion);
    } else if (cands.length > 1) {
      setQuery(pendingQuestion);
      setHint("A few members match that name — pick one on the left.");
    } else {
      setHint(
        "Pick a member on the left, or include their name in the question.",
      );
    }
  }

  if (selected) {
    return (
      <div>
        <div className="mb-3 flex items-center gap-2 text-sm">
          <Link
            href={memberPath(selected)}
            className="text-neutral-800 font-medium underline decoration-neutral-300 hover:decoration-neutral-900"
          >
            {chamberLabel(selected)} {selected.full_name} ({selected.party}-
            {selected.state})
          </Link>
          <button
            onClick={() => {
              setSelected(null);
              setHandoffQuestion("");
              setPendingQuestion("");
              setQuery("");
            }}
            className="text-xs text-neutral-500 underline hover:text-neutral-900"
          >
            change member
          </button>
        </div>
        <AskRecord
          officialId={selected.id}
          memberName={selected.full_name}
          initialQuestion={handoffQuestion || undefined}
        />
      </div>
    );
  }

  return (
    <div className="grid gap-3 md:grid-cols-[280px_1fr]">
      {/* Member box: suggestion chips first, then type-to-filter input */}
      <div className="relative">
        {featured.length > 0 && (
          <>
            <div className="mb-1.5 text-[10px] uppercase tracking-wider text-neutral-400">
              Suggestions
            </div>
            <div className="mb-2 flex flex-wrap gap-1.5">
              {featured.map((m) => (
                <button
                  key={m.id}
                  onClick={() => choose(m)}
                  className="rounded-full border border-neutral-200 bg-white px-2.5 py-1 text-xs text-neutral-600 hover:border-neutral-400 hover:text-neutral-900 transition-colors"
                >
                  {chamberLabel(m)} {m.full_name.split(" ").slice(-1)[0]} (
                  {m.party}-{m.state})
                </button>
              ))}
            </div>
          </>
        )}
        <select
          value=""
          onChange={(e) => {
            const m = members.find((x) => x.id === e.target.value);
            if (m) choose(m);
          }}
          aria-label="Choose a member from an alphabetical list"
          className="mb-2 w-full border border-neutral-200 bg-white px-2.5 py-2.5 text-sm text-neutral-700 focus:border-neutral-900 focus:outline-none transition-colors"
        >
          <option value="">Choose from the full list (A to Z)...</option>
          {members.map((m) => (
            <option key={m.id} value={m.id}>
              {m.full_name} ({m.party}-{m.state})
            </option>
          ))}
        </select>
        <input
          type="text"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setHint("");
          }}
          placeholder="Or type in your senator or rep..."
          aria-label="Type the name of a senator or representative"
          className="w-full border border-neutral-200 bg-white px-3 py-2.5 text-sm text-neutral-800 placeholder:text-neutral-400 focus:border-neutral-900 focus:outline-none transition-colors"
        />
        {matches.length > 0 && (
          <ul className="absolute z-10 mt-1 w-full border border-neutral-200 bg-white shadow-sm max-h-72 overflow-y-auto">
            {matches.map((m) => (
              <li key={m.id}>
                <button
                  onClick={() => choose(m)}
                  className="w-full px-3 py-2 text-left text-sm text-neutral-800 hover:bg-neutral-50 flex items-baseline justify-between gap-2"
                >
                  <span>
                    {chamberLabel(m)} {m.full_name}
                  </span>
                  <span className="text-xs text-neutral-400 shrink-0">
                    {m.party}-{m.state}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* Question box: works immediately if the question names the member */}
      <div>
        <form onSubmit={onQuestionSubmit}>
          <input
            type="text"
            value={pendingQuestion}
            onChange={(e) => {
              setPendingQuestion(e.target.value);
              setHint("");
            }}
            maxLength={300}
            placeholder="What have they said about...?"
            aria-label="Your question about the member's record"
            className="w-full border border-neutral-200 bg-white px-3 py-2.5 text-sm text-neutral-800 placeholder:text-neutral-400 focus:border-neutral-900 focus:outline-none transition-colors"
          />
        </form>
        <p className="mt-2 text-xs text-neutral-400">
          Answers come only from the selected member&apos;s archived releases,
          one member at a time, with citations. When the record can&apos;t
          answer, it says so.
        </p>
        {hint && <p className="mt-1 text-xs text-amber-700">{hint}</p>}
      </div>
    </div>
  );
}

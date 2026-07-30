"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import posthog from "posthog-js";
import { AskRecord } from "./ask-record";

// Front-page "Ask the record": question-first. Users type a full question
// ("what did warren say about trump recently"); we detect the member name
// inside it, select that member, and fire the question in one Enter press.
// Typing just a name still works as a plain picker. Lesson learned live on
// launch morning: users type questions into the first box they see.

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

export function AskAnyMember({ members }: { members: AskableMember[] }) {
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<AskableMember | null>(null);
  const [handoffQuestion, setHandoffQuestion] = useState<string>("");
  const [hint, setHint] = useState<string>("");

  // Match members by any meaningful word in the query, so a full question
  // containing "warren" finds Warren even though the whole string doesn't.
  const matches = useMemo(() => {
    const tokens = (query.toLowerCase().match(/[a-z]{3,}/g) ?? []).filter(
      (t) => !STOPWORDS.has(t),
    );
    if (tokens.length === 0) return [];
    const hits = members.filter((m) => {
      const name = m.full_name.toLowerCase();
      return tokens.some((t) => name.includes(t));
    });
    return hits.slice(0, 8);
  }, [query, members]);

  // A query with 4+ words (or a question mark) is a question to carry over,
  // not just a name lookup.
  function questionPart(q: string): string {
    const words = q.trim().split(/\s+/);
    return words.length >= 4 || q.includes("?") ? q.trim() : "";
  }

  function choose(m: AskableMember) {
    setSelected(m);
    setHandoffQuestion(questionPart(query));
    setHint("");
    posthog.capture("ask_member_selected", { official_id: m.id });
  }

  function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (matches.length === 1) {
      choose(matches[0]);
    } else if (matches.length > 1) {
      setHint("A few members match — pick who you mean below.");
    } else {
      setHint(
        "Include a member's name, like: What did Warren say about housing?",
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
    <div className="relative">
      <form onSubmit={onSubmit}>
        <input
          type="text"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setHint("");
          }}
          placeholder="Ask about any member of Congress..."
          aria-label="Ask a question about any member of Congress"
          className="w-full border border-neutral-200 bg-white px-3 py-2.5 text-sm text-neutral-800 placeholder:text-neutral-400 focus:border-neutral-900 focus:outline-none transition-colors"
        />
      </form>
      <p className="mt-2 text-xs text-neutral-400">
        All of Congress — include the member&apos;s name in your question.
        Answers come only from their archived releases, with citations.
      </p>
      {hint && <p className="mt-1 text-xs text-amber-700">{hint}</p>}
      {matches.length > 0 && (
        <ul className="absolute z-10 mt-1 w-full border border-neutral-200 bg-white shadow-sm max-h-72 overflow-y-auto">
          {matches.map((m) => (
            <li key={m.id}>
              <button
                onClick={() => choose(m)}
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
    </div>
  );
}

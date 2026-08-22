"use client";

import { useEffect, useState } from "react";
import posthog from "posthog-js";

// "Ask the record" — the reader-facing surface of the RAG pipeline.
// Renders validated answers with per-passage citation superscripts, honest
// boundary states (related_only / not_in_record / no_sources / declined),
// and an AI disclosure footer on every response.

type Source = {
  n: number;
  title: string;
  source_url: string;
  published_at: string | null;
};

type Segment = { text: string; refs: number[] };

type AskResponse = {
  status: string;
  segments?: Segment[];
  sources?: Source[];
  message?: string;
  disclosure?: string;
  error?: string;
};

type AskState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "result"; data: AskResponse }
  | { kind: "error"; message: string };

function formatDate(iso: string | null): string {
  if (!iso) return "";
  return new Date(iso).toLocaleDateString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

const BOUNDARY_NOTE: Record<string, string> = {
  related_only:
    "The record can't fully answer this as asked. Here's what it does contain.",
  not_in_record: "Not in the record.",
  no_sources: "No matching releases.",
  declined: "Question declined.",
};

export function AskRecord({
  officialId,
  memberName,
  initialQuestion,
}: {
  officialId: string;
  memberName: string;
  // When the front-page box hands off a full question ("what did warren say
  // about trump"), it arrives here and fires immediately — the user already
  // pressed Enter once and should not have to press it again.
  initialQuestion?: string;
}) {
  const [question, setQuestion] = useState(initialQuestion ?? "");
  const [state, setState] = useState<AskState>({ kind: "idle" });

  useEffect(() => {
    if (initialQuestion && initialQuestion.trim().length >= 3) {
      void runAsk(initialQuestion);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function submit(e: React.FormEvent) {
    e.preventDefault();
    void runAsk(question);
  }

  async function runAsk(raw: string) {
    const q = raw.trim();
    if (q.length < 3 || state.kind === "loading") return;

    setState({ kind: "loading" });
    posthog.capture("ask_submitted", { official_id: officialId });

    try {
      const res = await fetch(`/api/officials/${officialId}/ask`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: q }),
      });
      const data: AskResponse = await res.json();
      if (!res.ok) {
        posthog.capture("ask_failed", { official_id: officialId, http: res.status });
        setState({
          kind: "error",
          message: data.error ?? "Something went wrong. Try again.",
        });
        return;
      }
      posthog.capture("ask_result", {
        official_id: officialId,
        status: data.status,
        sources: data.sources?.length ?? 0,
      });
      setState({ kind: "result", data });
    } catch {
      setState({ kind: "error", message: "Network error. Try again." });
    }
  }

  return (
    <div>
      <form onSubmit={submit} className="flex gap-2">
        <input
          type="text"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          maxLength={300}
          placeholder={`What has ${memberName} said about...`}
          aria-label={`Ask about ${memberName}'s record`}
          className="flex-1 border border-neutral-200 bg-white px-3 py-2 text-sm text-neutral-800 placeholder:text-neutral-400 focus:border-neutral-900 focus:outline-none transition-colors"
        />
        <button
          type="submit"
          disabled={state.kind === "loading" || question.trim().length < 3}
          className="border border-neutral-900 bg-neutral-900 px-4 py-2 text-sm text-white hover:bg-neutral-700 disabled:border-neutral-200 disabled:bg-neutral-200 disabled:text-neutral-400 transition-colors"
        >
          {state.kind === "loading" ? "Searching..." : "Ask"}
        </button>
      </form>

      <p className="mt-2 text-xs text-neutral-400">
        Answers draw only on {memberName}&apos;s collected releases, one member
        at a time, with citations. When the record can&apos;t answer, it says so.
      </p>

      {state.kind === "loading" && (
        <p className="mt-4 text-sm text-neutral-500">
          Searching {memberName}&apos;s record and drafting a cited answer...
        </p>
      )}

      {state.kind === "error" && (
        <p className="mt-4 text-sm text-red-700 border-l-2 border-red-300 pl-3">
          {state.message}
        </p>
      )}

      {state.kind === "result" && <Result data={state.data} />}
    </div>
  );
}

function Result({ data }: { data: AskResponse }) {
  const boundary = BOUNDARY_NOTE[data.status];

  return (
    <div className="mt-4">
      {boundary && (
        <p className="mb-3 inline-block border border-amber-300 bg-amber-50 px-2.5 py-1 text-xs text-amber-800">
          {boundary}
        </p>
      )}

      {data.message && (
        <p className="text-sm text-neutral-700 leading-relaxed">{data.message}</p>
      )}

      {data.segments && data.segments.length > 0 && (
        <p className="text-sm text-neutral-800 leading-relaxed whitespace-pre-line">
          {data.segments.map((seg, i) => (
            <span key={i}>
              {seg.text}
              {seg.refs.map((n) => {
                const src = data.sources?.find((s) => s.n === n);
                return (
                  <a
                    key={n}
                    href={src?.source_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    title={src?.title}
                    className="align-super text-[10px] text-neutral-500 hover:text-neutral-900 ml-0.5"
                  >
                    [{n}]
                  </a>
                );
              })}
            </span>
          ))}
        </p>
      )}

      {data.sources && data.sources.length > 0 && (
        <div className="mt-4">
          <h3 className="text-xs uppercase tracking-wider text-neutral-500 mb-2">
            Sources
          </h3>
          <ul className="space-y-1.5">
            {data.sources.map((s) => (
              <li key={s.n} className="text-sm">
                <span className="text-neutral-400 mr-1.5">[{s.n}]</span>
                <a
                  href={s.source_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-neutral-800 underline decoration-neutral-300 hover:decoration-neutral-900"
                >
                  {s.title}
                </a>
                {s.published_at && (
                  <span className="text-neutral-400 ml-1.5 text-xs">
                    {formatDate(s.published_at)}
                  </span>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

      {data.disclosure && (
        <p className="mt-4 border-t border-neutral-100 pt-2 text-xs text-neutral-400">
          {data.disclosure}{" "}
          <a
            href="mailto:trevorbrown.web@gmail.com?subject=Capitol%20Releases%20answer%20correction"
            className="underline hover:text-neutral-600"
          >
            Report a problem
          </a>
        </p>
      )}
    </div>
  );
}

"use client";

import { useState } from "react";
import posthog from "posthog-js";

type State =
  | { kind: "idle" }
  | { kind: "submitting" }
  | { kind: "success" }
  | { kind: "error"; message: string };

export function BriefSignup({ source = "brief-page" }: { source?: string }) {
  const [email, setEmail] = useState("");
  const [state, setState] = useState<State>({ kind: "idle" });

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (state.kind === "submitting") return;
    setState({ kind: "submitting" });
    try {
      const res = await fetch("/api/newsletter/subscribe", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ email, source }),
      });
      if (!res.ok) {
        const data = (await res.json().catch(() => ({}))) as {
          error?: string;
        };
        const message = data.error ?? "Something went wrong.";
        setState({ kind: "error", message });
        posthog.capture("newsletter_subscribe_error", { source, error: message });
        return;
      }
      posthog.identify(email, { email });
      posthog.capture("newsletter_subscribed", { source });
      setState({ kind: "success" });
    } catch {
      const message = "Network error. Try again.";
      setState({ kind: "error", message });
      posthog.capture("newsletter_subscribe_error", { source, error: message });
    }
  }

  if (state.kind === "success") {
    return (
      <div className="rounded border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-900">
        <strong>Subscribed.</strong> The next brief will land in your inbox at
        6:30 a.m. ET. Unsubscribe with one click from any email.
      </div>
    );
  }

  return (
    <form
      onSubmit={onSubmit}
      className="rounded border border-neutral-200 bg-neutral-50 p-4"
    >
      <label
        htmlFor="brief-email"
        className="block text-sm font-medium text-neutral-900 mb-1"
      >
        Get the brief in your inbox
      </label>
      <p className="text-xs text-neutral-600 mb-3 leading-relaxed">
        One email per weekday morning, 6:30 a.m. ET. Tuesday-Saturday&rsquo;s Senate
        activity, sent the next morning. No tracking, no marketing, no resale.
      </p>
      <div className="flex gap-2">
        <input
          id="brief-email"
          type="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="you@example.com"
          autoComplete="email"
          className="flex-1 rounded border border-neutral-300 bg-white px-3 py-2 text-sm focus:border-neutral-500 focus:outline-none"
          disabled={state.kind === "submitting"}
        />
        <button
          type="submit"
          disabled={state.kind === "submitting"}
          className="rounded bg-neutral-900 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-neutral-700 disabled:cursor-not-allowed disabled:bg-neutral-400"
        >
          {state.kind === "submitting" ? "Subscribing..." : "Subscribe"}
        </button>
      </div>
      {state.kind === "error" && (
        <p className="mt-2 text-xs text-red-700">{state.message}</p>
      )}
    </form>
  );
}

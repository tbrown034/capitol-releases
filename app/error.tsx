"use client";

import Link from "next/link";
import { useEffect } from "react";

// Catches any uncaught render-path error from a route segment. Most common
// trigger is a Neon cold-start fetch failure that survives the retry in
// db.ts. We show a calm, journalism-grade fallback instead of the default
// Next overlay or a stack trace.
export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    if (typeof window !== "undefined") {
      console.error("[Capitol Releases] Page error:", error);
    }
  }, [error]);

  const isNetwork = /fetch failed|database|ECONN|ETIMEDOUT|ENOTFOUND/i.test(
    error?.message ?? ""
  );

  return (
    <div className="mx-auto max-w-2xl px-4 py-16">
      <h1 className="font-[family-name:var(--font-source-serif)] text-3xl text-neutral-900 mb-3">
        Something went sideways.
      </h1>
      <p className="text-sm text-neutral-600 leading-relaxed mb-3">
        {isNetwork
          ? "We couldn't reach the database just now. This usually clears in a few seconds — the connection pool warms up after a quiet period."
          : "An unexpected error rendered this page."}
      </p>
      <div className="flex flex-wrap gap-3 mt-6">
        <button
          onClick={reset}
          className="rounded-full border border-neutral-900 bg-neutral-900 text-white px-4 py-1.5 text-sm hover:bg-neutral-700 transition-colors cursor-pointer"
        >
          Try again
        </button>
        <Link
          href="/"
          className="rounded-full border border-neutral-300 px-4 py-1.5 text-sm text-neutral-700 hover:border-neutral-500 transition-colors"
        >
          Back to home
        </Link>
      </div>
      {error?.digest && (
        <p className="mt-8 text-[11px] text-neutral-400 font-mono">
          Reference: {error.digest}
        </p>
      )}
    </div>
  );
}

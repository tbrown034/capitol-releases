"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useState, FormEvent } from "react";

export function Pagination({
  total,
  perPage,
  basePath,
  currentPage: currentPageProp,
}: {
  total: number;
  perPage: number;
  basePath: string;
  currentPage?: number;
}) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const currentPage =
    currentPageProp ?? Number(searchParams.get("page") ?? "1");
  const totalPages = Math.max(1, Math.ceil(total / perPage));
  const [jumpValue, setJumpValue] = useState("");

  if (totalPages <= 1) return null;

  function hrefFor(page: number) {
    const params = new URLSearchParams(searchParams.toString());
    params.set("page", String(page));
    return `${basePath}?${params.toString()}`;
  }

  function goTo(page: number) {
    const clamped = Math.min(Math.max(1, page), totalPages);
    router.push(hrefFor(clamped));
  }

  function onJump(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const n = Number(jumpValue);
    if (!Number.isFinite(n) || n < 1) return;
    goTo(n);
    setJumpValue("");
  }

  const pages = buildPageList(currentPage, totalPages);
  const firstResult = (currentPage - 1) * perPage + 1;
  const lastResult = Math.min(currentPage * perPage, total);

  return (
    <nav className="mt-6 flex flex-col gap-3 border-t border-neutral-200 pt-4 sm:flex-row sm:items-center sm:justify-between">
      <p className="text-xs text-neutral-500 font-[family-name:var(--font-dm-mono)] tabular-nums">
        {firstResult.toLocaleString()}–{lastResult.toLocaleString()} of{" "}
        {total.toLocaleString()}
      </p>

      <div className="flex flex-wrap items-center gap-1.5">
        <PageButton
          disabled={currentPage <= 1}
          onClick={() => goTo(1)}
          title="First page"
        >
          «
        </PageButton>
        <PageButton
          disabled={currentPage <= 1}
          onClick={() => goTo(currentPage - 1)}
          title="Previous page"
        >
          ‹ Prev
        </PageButton>

        {pages.map((p, i) =>
          p === "…" ? (
            <span
              key={`ellipsis-${i}`}
              className="px-1 text-xs text-neutral-400"
            >
              …
            </span>
          ) : (
            <PageButton
              key={p}
              active={p === currentPage}
              onClick={() => goTo(p)}
            >
              {p}
            </PageButton>
          )
        )}

        <PageButton
          disabled={currentPage >= totalPages}
          onClick={() => goTo(currentPage + 1)}
          title="Next page"
        >
          Next ›
        </PageButton>
        <PageButton
          disabled={currentPage >= totalPages}
          onClick={() => goTo(totalPages)}
          title="Last page"
        >
          »
        </PageButton>

        <form onSubmit={onJump} className="ml-2 flex items-center gap-1">
          <label
            htmlFor="page-jump"
            className="text-xs text-neutral-400"
          >
            Go to
          </label>
          <input
            id="page-jump"
            type="number"
            min={1}
            max={totalPages}
            value={jumpValue}
            onChange={(e) => setJumpValue(e.target.value)}
            placeholder={String(currentPage)}
            className="w-14 rounded border border-neutral-300 px-1.5 py-0.5 text-xs font-[family-name:var(--font-dm-mono)] tabular-nums focus:border-neutral-900 focus:outline-none"
          />
        </form>
      </div>
    </nav>
  );
}

function PageButton({
  children,
  onClick,
  active,
  disabled,
  title,
}: {
  children: React.ReactNode;
  onClick: () => void;
  active?: boolean;
  disabled?: boolean;
  title?: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      title={title}
      className={`min-w-[28px] rounded border px-2 py-0.5 text-xs font-[family-name:var(--font-dm-mono)] tabular-nums transition-colors disabled:cursor-not-allowed disabled:opacity-30 ${
        active
          ? "border-neutral-900 bg-neutral-900 text-white"
          : "border-neutral-200 text-neutral-600 hover:border-neutral-400 hover:text-neutral-900"
      }`}
    >
      {children}
    </button>
  );
}

function buildPageList(current: number, total: number): (number | "…")[] {
  // Always show: 1, last, current, current±1, plus ellipses to bridge gaps.
  const set = new Set<number>([1, total, current, current - 1, current + 1]);
  if (current <= 3) {
    set.add(2);
    set.add(3);
    set.add(4);
  }
  if (current >= total - 2) {
    set.add(total - 1);
    set.add(total - 2);
    set.add(total - 3);
  }
  const ordered = Array.from(set)
    .filter((p) => p >= 1 && p <= total)
    .sort((a, b) => a - b);

  const out: (number | "…")[] = [];
  let prev = 0;
  for (const p of ordered) {
    if (prev && p - prev > 1) out.push("…");
    out.push(p);
    prev = p;
  }
  return out;
}

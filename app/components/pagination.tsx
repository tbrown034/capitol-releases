"use client";

import { useRouter, useSearchParams } from "next/navigation";

export function Pagination({
  total,
  perPage,
  basePath,
}: {
  total: number;
  perPage: number;
  basePath: string;
}) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const currentPage = Number(searchParams.get("page") ?? "1");
  const totalPages = Math.ceil(total / perPage);

  if (totalPages <= 1) return null;

  function goTo(page: number) {
    const params = new URLSearchParams(searchParams.toString());
    params.set("page", String(page));
    router.push(`${basePath}?${params.toString()}`);
  }

  return (
    <nav className="flex items-center justify-between border-t border-gray-200 pt-4 mt-6">
      <p className="text-sm text-gray-600">
        Page {currentPage} of {totalPages} ({total.toLocaleString()} results)
      </p>
      <div className="flex gap-2">
        <button
          onClick={() => goTo(currentPage - 1)}
          disabled={currentPage <= 1}
          className="rounded border border-gray-300 px-3 py-1.5 text-sm disabled:opacity-40 hover:bg-gray-50"
        >
          Previous
        </button>
        <button
          onClick={() => goTo(currentPage + 1)}
          disabled={currentPage >= totalPages}
          className="rounded border border-gray-300 px-3 py-1.5 text-sm disabled:opacity-40 hover:bg-gray-50"
        >
          Next
        </button>
      </div>
    </nav>
  );
}

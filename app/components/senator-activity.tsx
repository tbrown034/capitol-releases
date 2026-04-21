"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { getSenatorPhotoUrl, getInitials } from "../lib/photos";

type SenatorRow = {
  id: string;
  full_name: string;
  party: string;
  state: string;
  count: number;
};

type Range = "all" | "ytd" | "year" | "month" | "week";

const RANGE_LABELS: { value: Range; label: string }[] = [
  { value: "all", label: "All" },
  { value: "ytd", label: "YTD" },
  { value: "year", label: "Year" },
  { value: "month", label: "Month" },
  { value: "week", label: "Week" },
];

function SenatorList({
  rows,
  startIndex = 1,
}: {
  rows: SenatorRow[];
  startIndex?: number;
}) {
  return (
    <div className="space-y-0.5">
      {rows.map((row, i) => {
        const photoUrl = getSenatorPhotoUrl(row.full_name, row.id);
        return (
          <Link
            key={row.id}
            href={`/senators/${row.id}`}
            className="flex items-center justify-between py-1.5 text-sm hover:bg-neutral-50 transition-colors -mx-2 px-2"
          >
            <span className="flex items-center gap-2">
              <span className="font-mono text-xs text-neutral-300 w-4 text-right tabular-nums">
                {startIndex + i}
              </span>
              {photoUrl ? (
                <img
                  src={photoUrl}
                  alt=""
                  width={20}
                  height={20}
                  className="h-5 w-5 rounded-full object-cover"
                />
              ) : (
                <span className="flex h-5 w-5 items-center justify-center rounded-full bg-neutral-100 text-[8px] font-medium text-neutral-400">
                  {getInitials(row.full_name)}
                </span>
              )}
              <span className="text-neutral-900">{row.full_name}</span>
              <span className="text-neutral-400 hidden sm:inline">
                ({row.party}-{row.state})
              </span>
            </span>
            <span className="font-mono text-neutral-500 tabular-nums">
              {row.count.toLocaleString()}
            </span>
          </Link>
        );
      })}
    </div>
  );
}

export function SenatorActivity({
  initialTop,
  initialBottom,
}: {
  initialTop: SenatorRow[];
  initialBottom: SenatorRow[];
}) {
  const [range, setRange] = useState<Range>("all");
  const [top, setTop] = useState(initialTop);
  const [bottom, setBottom] = useState(initialBottom);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (range === "all") {
      setTop(initialTop);
      setBottom(initialBottom);
      return;
    }

    let cancelled = false;
    setLoading(true);

    fetch(`/api/senators/activity?range=${range}`)
      .then((r) => r.json())
      .then((data) => {
        if (cancelled) return;
        setTop(data.top);
        setBottom(data.bottom);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [range, initialTop, initialBottom]);

  return (
    <aside className={loading ? "opacity-60 transition-opacity" : ""}>
      {/* Range filter */}
      <div className="flex items-center gap-1 mb-4 border-b border-neutral-900 pb-2">
        {RANGE_LABELS.map((r) => (
          <button
            key={r.value}
            onClick={() => setRange(r.value)}
            className={`px-2 py-0.5 text-xs rounded transition-colors ${
              range === r.value
                ? "bg-neutral-900 text-white"
                : "text-neutral-400 hover:text-neutral-900"
            }`}
          >
            {r.label}
          </button>
        ))}
      </div>

      {/* Most Active */}
      <h2 className="text-xs uppercase tracking-wider text-neutral-500 mb-3">
        Most Active
      </h2>
      <SenatorList rows={top} />

      {/* Least Active */}
      <h2 className="text-xs uppercase tracking-wider text-neutral-500 mt-6 mb-3 border-t border-neutral-200 pt-4">
        Least Active
      </h2>
      <SenatorList rows={bottom} />
    </aside>
  );
}

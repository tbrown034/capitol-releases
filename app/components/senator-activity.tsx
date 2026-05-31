"use client";

import { useState } from "react";
import Link from "next/link";
import Image from "next/image";
import { getMemberPhotoUrl, getMemberHref, getInitials } from "../lib/photos";

type SenatorRow = {
  id: string;
  full_name: string;
  party: string;
  state: string;
  count: number;
  chamber?: string | null;
  district?: string | null;
  bioguide_id?: string | null;
};

type Range = "all" | "ytd" | "year" | "month" | "week";

const RANGE_LABELS: { value: Range; label: string }[] = [
  { value: "all", label: "All" },
  { value: "ytd", label: "YTD" },
  { value: "year", label: "Year" },
  { value: "month", label: "Month" },
  { value: "week", label: "Week" },
];

const PARTY_TINT: Record<string, string> = {
  D: "rgba(59,130,246,0.10)",
  R: "rgba(239,68,68,0.10)",
  I: "rgba(245,158,11,0.10)",
};

function SenatorList({
  rows,
  startIndex = 1,
  emphasizeTop = false,
}: {
  rows: SenatorRow[];
  startIndex?: number;
  emphasizeTop?: boolean;
}) {
  const max = rows.reduce((m, r) => Math.max(m, r.count), 0);
  return (
    <div className="space-y-0.5">
      {rows.map((row, i) => {
        const photoUrl = getMemberPhotoUrl(row.full_name, row.id, row.chamber, row.bioguide_id);
        const isTopThree = emphasizeTop && i < 3;
        const pct = max > 0 ? Math.max(2, (row.count / max) * 100) : 0;
        const tint = PARTY_TINT[row.party] ?? "rgba(115,115,115,0.10)";
        return (
          <Link
            key={row.id}
            href={getMemberHref(row.id, row.chamber)}
            className="relative flex items-center justify-between py-1.5 text-sm hover:bg-neutral-50 transition-colors -mx-2 px-2 overflow-hidden"
          >
            {/* Magnitude bar — sits behind row content, party-tinted. */}
            {row.count > 0 && (
              <span
                aria-hidden="true"
                className="absolute inset-y-0 left-0 -z-0"
                style={{ width: `${pct}%`, background: tint }}
              />
            )}
            <span className="relative z-10 flex items-center gap-2 min-w-0">
              <span className="font-mono text-xs text-neutral-300 w-4 text-right tabular-nums">
                {startIndex + i}
              </span>
              {photoUrl ? (
                <Image
                  src={photoUrl}
                  alt={`${row.full_name} (${row.party}-${row.state})`}
                  width={20}
                  height={20}
                  className="size-5 rounded-full object-cover"
                  unoptimized
                />
              ) : (
                <span className="flex size-5 items-center justify-center rounded-full bg-neutral-100 text-[8px] font-medium text-neutral-400">
                  {getInitials(row.full_name)}
                </span>
              )}
              <span
                className={`truncate ${
                  isTopThree
                    ? "text-neutral-900 font-semibold"
                    : "text-neutral-900"
                }`}
              >
                {row.full_name}
              </span>
              <span className="text-neutral-400 hidden sm:inline shrink-0">
                ({row.party}-{row.state})
              </span>
            </span>
            <span
              className={`relative z-10 font-mono tabular-nums shrink-0 ml-2 ${
                isTopThree ? "text-neutral-900 font-semibold" : "text-neutral-500"
              }`}
            >
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

  async function selectRange(nextRange: Range) {
    setRange(nextRange);
    if (nextRange === "all") {
      setTop(initialTop);
      setBottom(initialBottom);
      return;
    }

    setLoading(true);
    try {
      const response = await fetch(`/api/senators/activity?range=${nextRange}`);
      const data = await response.json();
      setTop(data.top);
      setBottom(data.bottom);
    } finally {
      setLoading(false);
    }
  }

  return (
    <aside className={loading ? "opacity-60 transition-opacity" : ""}>
      {/* Range filter */}
      <address aria-label="Time range" className="flex items-center gap-1 mb-4 border-b border-neutral-900 pb-2 not-italic">
        {RANGE_LABELS.map((r) => (
          <button
            key={r.value}
            type="button"
            aria-pressed={range === r.value}
            onClick={() => {
              void selectRange(r.value);
            }}
            className={`px-2 py-0.5 text-xs rounded transition-colors ${
              range === r.value
                ? "bg-neutral-900 text-white"
                : "text-neutral-500 hover:text-neutral-900"
            }`}
          >
            {r.label}
          </button>
        ))}
      </address>

      {/* Most Active */}
      <h2 className="text-xs uppercase tracking-wider text-neutral-500 mb-3">
        Most Active
      </h2>
      <SenatorList rows={top} emphasizeTop />

      {/* Least Active */}
      <h2 className="text-xs uppercase tracking-wider text-neutral-500 mt-6 mb-3 border-t border-neutral-200 pt-4">
        Least Active
      </h2>
      <SenatorList rows={bottom} />
    </aside>
  );
}

"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

type Member = {
  id: string;
  full_name: string;
  party: "D" | "R" | "I";
  state: string;
  count: number;
};

const PARTY_COLOR = {
  D: "#3b82f6",
  R: "#ef4444",
  I: "#f59e0b",
} as const;

// House visualization: a 5-row semicircle (matches the Senate visual
// language) with seats sized down to fit ~437 members. The Senate uses
// rows of [12, 16, 20, 24, 28] = 100; we use proportionally larger rows
// that sum to 437.
const ROWS = [55, 71, 87, 103, 121]; // sum = 437
const CX = 460;
const CY = 460;
const INNER_R = 130;
const ROW_STEP = 50;
const SEAT_R = 5.5;
const VIEW_W = 920;
const VIEW_H = 500;

const round = (n: number) => Math.round(n * 1000) / 1000;

type Seat = { row: number; idx: number; angle: number; x: number; y: number };

const SEATS: Seat[] = (() => {
  const seats: Seat[] = [];
  for (let row = 0; row < ROWS.length; row++) {
    const n = ROWS[row];
    const radius = INNER_R + row * ROW_STEP;
    for (let k = 0; k < n; k++) {
      const angle = ((k + 0.5) * Math.PI) / n;
      const x = round(CX - radius * Math.cos(angle));
      const y = round(CY - radius * Math.sin(angle));
      seats.push({ row, idx: k, angle, x, y });
    }
  }
  return seats.sort((a, b) => a.angle - b.angle);
})();

function intensity(count: number, max: number): number {
  if (count <= 0 || max <= 0) return 0;
  return Math.log(count + 1) / Math.log(max + 1);
}

function fillFor(party: "D" | "R" | "I", count: number, max: number) {
  if (count === 0) return { fill: "#f5f5f4", stroke: "#d6d3d1", opacity: 1 };
  const t = Math.max(0.25, Math.min(1, intensity(count, max)));
  const opacity = Math.round(t * 1000) / 1000;
  return { fill: PARTY_COLOR[party], stroke: PARTY_COLOR[party], opacity };
}

export function HouseChamber({ members }: { members: Member[] }) {
  const sorted = useMemo(() => {
    // Sort by party (D, I, R) then state — visually groups Ds on the left
    // and Rs on the right, matching how the chamber is actually arranged.
    const PARTY_RANK = { D: 0, I: 1, R: 2 } as const;
    return [...members].sort((a, b) => {
      const p = PARTY_RANK[a.party] - PARTY_RANK[b.party];
      if (p !== 0) return p;
      return a.state.localeCompare(b.state);
    });
  }, [members]);

  const seated = useMemo(() => {
    // Pad/truncate to seat count. Some House rows may be empty (vacancy)
    // — we render those as un-filled gray seats.
    const cap = SEATS.length;
    return sorted.slice(0, cap);
  }, [sorted]);

  const max = useMemo(() => {
    return seated.reduce((m, s) => (s.count > m ? s.count : m), 0);
  }, [seated]);

  const [hover, setHover] = useState<{ member: Member; x: number; y: number } | null>(null);

  const totals = useMemo(() => {
    const t = { D: 0, R: 0, I: 0, total: members.length };
    for (const m of members) t[m.party]++;
    return t;
  }, [members]);

  const totalActivity = useMemo(
    () => members.reduce((sum, m) => sum + m.count, 0),
    [members]
  );

  return (
    <div className="relative">
      <div className="text-xs text-neutral-500 mb-3 flex flex-wrap items-center gap-x-4 gap-y-1">
        <span>
          <span className="font-[family-name:var(--font-dm-mono)] tabular-nums text-neutral-900 font-semibold">
            {totalActivity.toLocaleString()}
          </span>{" "}
          releases from{" "}
          <span className="font-[family-name:var(--font-dm-mono)] tabular-nums text-neutral-900 font-semibold">
            {totals.total}
          </span>{" "}
          U.S. House members in the last 30 days
        </span>
        <span className="text-neutral-400">·</span>
        <span className="text-blue-700">{totals.D} D</span>
        <span className="text-red-700">{totals.R} R</span>
        {totals.I > 0 && <span className="text-amber-700">{totals.I} I</span>}
      </div>
      <svg
        viewBox={`0 0 ${VIEW_W} ${VIEW_H}`}
        className="w-full max-w-3xl mx-auto"
        role="img"
        aria-label="U.S. House chamber visualization"
      >
        {SEATS.map((seat, i) => {
          const m = seated[i];
          if (!m) {
            return (
              <circle
                key={i}
                cx={seat.x}
                cy={seat.y}
                r={SEAT_R}
                fill="#f5f5f4"
                stroke="#e7e5e4"
                strokeWidth={0.5}
              />
            );
          }
          const { fill, stroke, opacity } = fillFor(m.party, m.count, max);
          return (
            <Link key={m.id} href={`/house/${m.id}`}>
              <circle
                cx={seat.x}
                cy={seat.y}
                r={SEAT_R}
                fill={fill}
                fillOpacity={opacity}
                stroke={stroke}
                strokeOpacity={1}
                strokeWidth={0.5}
                className="cursor-pointer transition-all hover:r-7"
                onMouseEnter={() => setHover({ member: m, x: seat.x, y: seat.y })}
                onMouseLeave={() => setHover(null)}
              />
            </Link>
          );
        })}
      </svg>
      {hover && (
        <div
          className="pointer-events-none absolute z-10 bg-neutral-900 text-white text-xs px-2 py-1 rounded shadow-lg"
          style={{
            left: `${(hover.x / VIEW_W) * 100}%`,
            top: `${(hover.y / VIEW_H) * 100}%`,
            transform: "translate(-50%, -130%)",
          }}
        >
          <div className="font-medium">{hover.member.full_name}</div>
          <div className="text-neutral-300">
            {hover.member.party}-{hover.member.state}
            {" · "}
            {hover.member.count} release{hover.member.count !== 1 ? "s" : ""}
          </div>
        </div>
      )}
      <p className="text-[11px] text-neutral-400 text-center mt-2">
        Each dot is one of the 437 active House members. Color = party, opacity =
        release activity (last 30 days). Click for archive page.
      </p>
    </div>
  );
}

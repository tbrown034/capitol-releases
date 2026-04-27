import Link from "next/link";
import { familyName } from "../lib/names";

type Senator = {
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

const PARTY_RANK = { D: 0, I: 1, R: 2 } as const;

const ROWS = [12, 16, 20, 24, 28];
const CX = 340;
const CY = 340;
const INNER_R = 110;
const ROW_STEP = 44;
const SEAT_R = 10;
const VIEW_W = 680;
const VIEW_H = 380;

type Seat = { row: number; idx: number; angle: number; x: number; y: number };

// Pure-deterministic; depends only on module-level constants. Computed once at
// module load to avoid recomputing 100 (x, y) pairs on every render.
const SEATS: Seat[] = (() => {
  const seats: Seat[] = [];
  for (let row = 0; row < ROWS.length; row++) {
    const n = ROWS[row];
    const radius = INNER_R + row * ROW_STEP;
    for (let k = 0; k < n; k++) {
      const angle = ((k + 0.5) * Math.PI) / n;
      const x = CX - radius * Math.cos(angle);
      const y = CY - radius * Math.sin(angle);
      seats.push({ row, idx: k, angle, x, y });
    }
  }
  return seats.sort((a, b) => a.angle - b.angle);
})();

function fillFor(party: "D" | "R" | "I", count: number, max: number) {
  if (count === 0) return { fill: "#f5f5f4", stroke: "#d6d3d1" };
  const t = Math.max(0.25, Math.min(1, count / Math.max(max, 1)));
  return { fill: PARTY_COLOR[party], stroke: PARTY_COLOR[party], opacity: t };
}

export function SenateChamber({
  senators,
  days = 7,
}: {
  senators: Senator[];
  days?: number;
}) {
  const sorted = [...senators].sort((a, b) => {
    const r = PARTY_RANK[a.party] - PARTY_RANK[b.party];
    if (r !== 0) return r;
    if (a.state !== b.state) return a.state.localeCompare(b.state);
    return a.full_name.localeCompare(b.full_name);
  });

  const seats = SEATS;
  const max = sorted.reduce((m, s) => Math.max(m, s.count), 0);
  const active = sorted.filter((s) => s.count > 0).length;
  const top = sorted.reduce<Senator | null>(
    (best, s) => (best === null || s.count > best.count ? s : best),
    null
  );

  const counts = { D: 0, I: 0, R: 0 } as Record<"D" | "I" | "R", number>;
  for (const s of sorted) counts[s.party]++;

  return (
    <div>
      <p className="text-base text-neutral-700 mb-1">
        <span className="font-semibold text-neutral-900">{active}</span> of 100
        senators issued at least one release in the last {days} days.
        {top && top.count > 0 && (
          <>
            {" "}
            Most active:{" "}
            <Link
              href={`/senators/${top.id}`}
              className="font-medium text-neutral-900 underline decoration-neutral-300 underline-offset-2 hover:decoration-neutral-900"
            >
              {familyName(top.full_name)} ({top.party}-{top.state})
            </Link>{" "}
            with {top.count}.
          </>
        )}
      </p>
      <p className="text-xs text-neutral-400 mb-4">
        Each seat = one senator. Color intensity = press releases in the last{" "}
        {days} days. Democrats left, Independents center, Republicans right.
      </p>

      <div className="overflow-x-auto -mx-4 px-4 sm:mx-0 sm:px-0">
      <svg
        role="img"
        aria-label={`Senate chamber showing press release activity over the last ${days} days for all 100 senators`}
        viewBox={`0 0 ${VIEW_W} ${VIEW_H}`}
        preserveAspectRatio="xMidYMid meet"
        className="h-auto max-h-[460px]"
        style={{ width: "100%", minWidth: 560 }}
      >
        <title>{`Senate chamber — press release activity, last ${days} days`}</title>

        {/* Floor curve */}
        <path
          d={`M ${CX - (INNER_R - 24)} ${CY} A ${INNER_R - 24} ${
            INNER_R - 24
          } 0 0 1 ${CX + (INNER_R - 24)} ${CY} L ${CX + (INNER_R - 24)} ${
            CY + 1
          } L ${CX - (INNER_R - 24)} ${CY + 1} Z`}
          fill="#fafaf9"
          stroke="#e7e5e4"
        />
        <line
          x1={CX - (INNER_R + ROW_STEP * (ROWS.length - 1) + SEAT_R + 8)}
          x2={CX + (INNER_R + ROW_STEP * (ROWS.length - 1) + SEAT_R + 8)}
          y1={CY + 1}
          y2={CY + 1}
          stroke="#e7e5e4"
        />

        {seats.map((seat, i) => {
          const senator = sorted[i];
          if (!senator) return null;
          const { fill, stroke, opacity } = fillFor(
            senator.party,
            senator.count,
            max
          );
          return (
            // Plain <a> instead of next/link: valid in SVG, no client-side
            // prefetcher attached to each of 100 hover targets.
            <a
              key={senator.id}
              href={`/senators/${senator.id}`}
              aria-label={`${senator.full_name} (${senator.party}-${senator.state}), ${senator.count} releases`}
              className="outline-none focus-visible:[outline:2px_solid_#0a0a0a] focus-visible:[outline-offset:2px]"
            >
              <circle
                cx={seat.x}
                cy={seat.y}
                r={SEAT_R}
                fill={fill}
                fillOpacity={opacity ?? 1}
                stroke={stroke}
                strokeWidth={1}
                className="motion-safe:transition-[r,fill-opacity] motion-safe:duration-150 hover:[r:11] hover:fill-opacity-100"
              >
                <title>{`${senator.full_name} (${senator.party}-${senator.state}) — ${senator.count} release${senator.count === 1 ? "" : "s"}`}</title>
              </circle>
            </a>
          );
        })}
      </svg>
      </div>

      <div className="mt-3 flex flex-wrap items-center justify-between gap-x-6 gap-y-2 text-xs text-neutral-500">
        <div className="flex items-center gap-x-4 gap-y-1 flex-wrap">
          <span className="flex items-center gap-1.5">
            <span
              className="inline-block h-2.5 w-2.5 rounded-full"
              style={{ background: PARTY_COLOR.D }}
            />
            Democrats <span className="tabular-nums">{counts.D}</span>
          </span>
          <span className="flex items-center gap-1.5">
            <span
              className="inline-block h-2.5 w-2.5 rounded-full"
              style={{ background: PARTY_COLOR.I }}
            />
            Independents <span className="tabular-nums">{counts.I}</span>
          </span>
          <span className="flex items-center gap-1.5">
            <span
              className="inline-block h-2.5 w-2.5 rounded-full"
              style={{ background: PARTY_COLOR.R }}
            />
            Republicans <span className="tabular-nums">{counts.R}</span>
          </span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-neutral-400">Less</span>
          <span className="flex items-center gap-0.5">
            {[0.25, 0.45, 0.65, 0.85, 1].map((o) => (
              <span
                key={o}
                className="inline-block h-2.5 w-3 rounded-sm"
                style={{ background: "#737373", opacity: o }}
              />
            ))}
          </span>
          <span className="text-neutral-400">
            More {max > 0 && `(max ${max})`}
          </span>
        </div>
      </div>
    </div>
  );
}

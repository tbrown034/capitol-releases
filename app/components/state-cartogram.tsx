import Link from "next/link";

type StateInfo = {
  code: string;
  parties: ("D" | "R" | "I")[];
  releaseCount: number;
};

const TILES: Record<string, [number, number]> = {
  AK: [1, 1],  ME: [1, 11],
  VT: [2, 10], NH: [2, 11],
  WA: [3, 2], ID: [3, 3], MT: [3, 4], ND: [3, 5], MN: [3, 6], WI: [3, 8], MI: [3, 9], NY: [3, 10], MA: [3, 11],
  OR: [4, 2], NV: [4, 3], WY: [4, 4], SD: [4, 5], IA: [4, 6], IL: [4, 7], IN: [4, 8], OH: [4, 9], PA: [4, 10], RI: [4, 11],
  CA: [5, 2], UT: [5, 3], CO: [5, 4], NE: [5, 5], MO: [5, 6], KY: [5, 7], WV: [5, 8], VA: [5, 9], NJ: [5, 10], CT: [5, 11],
  AZ: [6, 3], NM: [6, 4], KS: [6, 5], AR: [6, 6], TN: [6, 7], NC: [6, 8], MD: [6, 9], DE: [6, 10],
  OK: [7, 5], LA: [7, 6], MS: [7, 7], AL: [7, 8], SC: [7, 9],
  HI: [8, 1], TX: [8, 5], GA: [8, 9], FL: [8, 10],
};

function tileColor(parties: ("D" | "R" | "I")[]): "blue" | "red" | "purple" | "gray" {
  if (parties.length === 0) return "gray";
  const hasR = parties.includes("R");
  const hasDemAligned = parties.some((p) => p === "D" || p === "I");
  if (hasR && hasDemAligned) return "purple";
  if (hasR) return "red";
  return "blue";
}

const COLOR_CLASS: Record<"blue" | "red" | "purple" | "gray", string> = {
  blue: "bg-blue-100 text-blue-900 hover:bg-blue-200 border-blue-200",
  red: "bg-red-100 text-red-900 hover:bg-red-200 border-red-200",
  purple: "bg-purple-100 text-purple-900 hover:bg-purple-200 border-purple-200",
  gray: "bg-neutral-100 text-neutral-500 hover:bg-neutral-200 border-neutral-200",
};

const ACTIVE_CLASS: Record<"blue" | "red" | "purple" | "gray", string> = {
  blue: "bg-blue-600 text-white border-blue-700 hover:bg-blue-700",
  red: "bg-red-600 text-white border-red-700 hover:bg-red-700",
  purple: "bg-purple-600 text-white border-purple-700 hover:bg-purple-700",
  gray: "bg-neutral-600 text-white border-neutral-700 hover:bg-neutral-700",
};

export function StateCartogram({
  states,
  activeState,
  buildHref,
}: {
  states: StateInfo[];
  activeState?: string;
  buildHref: (stateCode: string | null) => string;
}) {
  const byCode = new Map(states.map((s) => [s.code, s]));

  return (
    <div className="mb-8">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-xs uppercase tracking-wider text-neutral-500">
          Browse by State
        </h2>
        {activeState && (
          <Link
            href={buildHref(null)}
            className="text-xs text-neutral-500 hover:text-neutral-900 underline"
          >
            Clear filter
          </Link>
        )}
      </div>

      <div
        className="grid gap-1 max-w-2xl"
        style={{
          gridTemplateColumns: "repeat(11, minmax(0, 1fr))",
          gridTemplateRows: "repeat(8, minmax(0, 1fr))",
          aspectRatio: "11 / 8",
        }}
      >
        {Object.entries(TILES).map(([code, [row, col]]) => {
          const info = byCode.get(code);
          const parties = info?.parties ?? [];
          const color = tileColor(parties);
          const isActive = activeState === code;
          const classes = isActive ? ACTIVE_CLASS[color] : COLOR_CLASS[color];
          const count = info?.releaseCount ?? 0;
          const partyDesc =
            parties.length === 0
              ? "no senators"
              : parties.sort().join(", ");
          return (
            <Link
              key={code}
              href={buildHref(code)}
              title={`${code} — ${partyDesc} — ${count.toLocaleString()} releases`}
              style={{ gridColumn: col, gridRow: row }}
              className={`flex items-center justify-center border text-[10px] font-[family-name:var(--font-dm-mono)] font-medium tabular-nums transition-colors aspect-square ${classes}`}
            >
              {code}
            </Link>
          );
        })}
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-neutral-500">
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-3 w-3 bg-blue-100 border border-blue-200" />
          Both Democrat
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-3 w-3 bg-red-100 border border-red-200" />
          Both Republican
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-3 w-3 bg-purple-100 border border-purple-200" />
          Split
        </span>
      </div>
    </div>
  );
}

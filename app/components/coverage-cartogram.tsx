import Link from "next/link";

type StateCoverage = {
  code: string;
  name: string;
  href: string;
  members: number;
  releases: number;
  status: "live" | "in_progress";
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

export function CoverageCartogram({
  coverage,
}: {
  coverage: StateCoverage[];
}) {
  const byCode = new Map(coverage.map((c) => [c.code, c]));
  const liveCount = coverage.filter((c) => c.status === "live").length;
  const inProgressCount = coverage.filter((c) => c.status === "in_progress").length;

  return (
    <div className="mb-8">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-xs uppercase tracking-wider text-neutral-500">
          Coverage Map
        </h2>
        <span className="text-xs text-neutral-500">
          <span className="text-neutral-900 font-medium">{liveCount}</span> live
          {inProgressCount > 0 && (
            <>
              <span className="text-neutral-300"> · </span>
              <span className="text-neutral-900 font-medium">{inProgressCount}</span> in progress
            </>
          )}
          <span className="text-neutral-300"> · </span>
          <span>{50 - liveCount - inProgressCount} planned</span>
        </span>
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
          const status = info?.status;

          if (status === "live" && info) {
            return (
              <Link
                key={code}
                href={info.href}
                title={`${info.name} — ${info.members} senators · ${info.releases.toLocaleString()} releases`}
                style={{ gridColumn: col, gridRow: row }}
                className="flex items-center justify-center border text-[10px] font-[family-name:var(--font-dm-mono)] font-medium tabular-nums transition-colors aspect-square bg-emerald-100 text-emerald-900 hover:bg-emerald-200 border-emerald-300"
              >
                {code}
              </Link>
            );
          }

          if (status === "in_progress" && info) {
            return (
              <Link
                key={code}
                href={info.href}
                title={`${info.name} — backfill in progress`}
                style={{ gridColumn: col, gridRow: row }}
                className="flex items-center justify-center border text-[10px] font-[family-name:var(--font-dm-mono)] font-medium tabular-nums transition-colors aspect-square bg-amber-50 text-amber-900 hover:bg-amber-100 border-amber-200"
              >
                {code}
              </Link>
            );
          }

          return (
            <div
              key={code}
              title={`${code} — planned`}
              style={{ gridColumn: col, gridRow: row }}
              className="flex items-center justify-center border text-[10px] font-[family-name:var(--font-dm-mono)] font-medium tabular-nums aspect-square bg-neutral-50 text-neutral-300 border-neutral-200 cursor-not-allowed"
            >
              {code}
            </div>
          );
        })}
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-neutral-500">
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-3 w-3 bg-emerald-100 border border-emerald-300" />
          Live
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-3 w-3 bg-amber-50 border border-amber-200" />
          Backfill in progress
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-3 w-3 bg-neutral-50 border border-neutral-200" />
          Planned
        </span>
      </div>
    </div>
  );
}

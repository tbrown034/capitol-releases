// Server-rendered SVG sparkline. No client JS, no hydration cost.
// Shows the daily volume of releases matching a theme's keywords across
// the past 30 days, with the brief day highlighted as a filled dot.

type Point = { date: string; count: number };

const SPARKLINE_PADDING = { top: 4, right: 4, bottom: 4, left: 4 };

export function ThemeSparkline({
  data,
  width = 220,
  height = 36,
  highlightDate,
}: {
  data: Point[];
  width?: number;
  height?: number;
  highlightDate?: string;
}) {
  if (!data || data.length === 0) return null;

  const innerW = width - SPARKLINE_PADDING.left - SPARKLINE_PADDING.right;
  const innerH = height - SPARKLINE_PADDING.top - SPARKLINE_PADDING.bottom;
  const maxCount = Math.max(1, ...data.map((d) => d.count));

  const x = (i: number) => SPARKLINE_PADDING.left + (i / Math.max(1, data.length - 1)) * innerW;
  const y = (c: number) => SPARKLINE_PADDING.top + innerH - (c / maxCount) * innerH;

  const linePath = data
    .map((d, i) => `${i === 0 ? "M" : "L"} ${x(i).toFixed(2)} ${y(d.count).toFixed(2)}`)
    .join(" ");

  const areaPath =
    `M ${x(0).toFixed(2)} ${(SPARKLINE_PADDING.top + innerH).toFixed(2)} ` +
    data.map((d, i) => `L ${x(i).toFixed(2)} ${y(d.count).toFixed(2)}`).join(" ") +
    ` L ${x(data.length - 1).toFixed(2)} ${(SPARKLINE_PADDING.top + innerH).toFixed(2)} Z`;

  const total = data.reduce((s, d) => s + d.count, 0);
  const todayIdx = highlightDate
    ? data.findIndex((d) => d.date === highlightDate)
    : data.length - 1;
  const todayPoint = todayIdx >= 0 ? data[todayIdx] : data[data.length - 1];

  return (
    <div className="flex items-center gap-3 text-xs text-neutral-500">
      <svg
        width={width}
        height={height}
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label={`30-day release volume for this theme. Today: ${todayPoint.count}.`}
        className="shrink-0"
      >
        <path d={areaPath} fill="#171717" fillOpacity="0.06" />
        <path
          d={linePath}
          fill="none"
          stroke="#171717"
          strokeWidth="1.25"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        {todayIdx >= 0 && (
          <circle
            cx={x(todayIdx)}
            cy={y(todayPoint.count)}
            r={2.75}
            fill="#171717"
            stroke="#ffffff"
            strokeWidth="1"
          />
        )}
      </svg>
      <div className="flex flex-col leading-tight">
        <span className="font-[family-name:var(--font-dm-mono)] tabular-nums text-[0.7rem] text-neutral-900">
          {todayPoint.count} today
        </span>
        <span className="text-[0.65rem] uppercase tracking-wide">
          {total} in 30 days
        </span>
      </div>
    </div>
  );
}

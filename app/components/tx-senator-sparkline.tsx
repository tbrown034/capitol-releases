"use client";

import * as d3 from "d3";

type Bar = { week: string; count: number };

const SPARKLINE_WIDTH = 520;
const SPARKLINE_HEIGHT = 80;
const SPARKLINE_MARGIN = { top: 6, right: 4, bottom: 16, left: 4 };

export function TxSenatorSparkline({ data }: { data: Bar[] }) {
  if (data.length === 0) return null;

  const innerW = SPARKLINE_WIDTH - SPARKLINE_MARGIN.left - SPARKLINE_MARGIN.right;
  const innerH = SPARKLINE_HEIGHT - SPARKLINE_MARGIN.top - SPARKLINE_MARGIN.bottom;
  const bandwidth = innerW / data.length;
  const barWidth = Math.max(1, bandwidth * 0.8);
  const maxCount = data.reduce((max, point) => Math.max(max, point.count), 1);
  const seenLabels = new Set<string>();

  return (
    <svg
      role="img"
      aria-label="Weekly press release volume since January 2025"
      width="100%"
      height={SPARKLINE_HEIGHT}
      viewBox={`0 0 ${SPARKLINE_WIDTH} ${SPARKLINE_HEIGHT}`}
      preserveAspectRatio="xMinYMin meet"
      className="block w-full h-auto"
    >
      <g transform={`translate(${SPARKLINE_MARGIN.left},${SPARKLINE_MARGIN.top})`}>
        {data.map((point, index) => {
          const barHeight = Math.max(1, (point.count / maxCount) * innerH);
          return (
            <rect
              key={point.week}
              x={index * bandwidth + (bandwidth - barWidth) / 2}
              y={innerH - barHeight}
              width={barWidth}
              height={barHeight}
              fill="#525252"
            />
          );
        })}
        {data.flatMap((point, index) => {
          const date = new Date(point.week);
          const month = date.getUTCMonth();
          const year = date.getUTCFullYear();
          if (month % 3 !== 0) return [];
          const key = `${year}-${month}`;
          if (seenLabels.has(key)) return [];
          seenLabels.add(key);
          const label = month === 0 ? `'${String(year).slice(2)}` : d3.timeFormat("%b")(date);
          return [
            <text
              key={key}
              x={index * bandwidth + bandwidth / 2}
              y={innerH + 12}
              textAnchor="start"
              fontSize="9"
              fill="#a3a3a3"
            >
              {label}
            </text>,
          ];
        })}
      </g>
    </svg>
  );
}

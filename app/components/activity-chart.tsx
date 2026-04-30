"use client";

import { useRef, useEffect, useState } from "react";
import * as d3 from "d3";
import { drawYGrid, drawTimeAxis } from "./chart-axes";

type DataPoint = { day: string; count: number };

type Hover = { date: Date; count: number; cx: number } | null;

export function ActivityChart({ data }: { data: DataPoint[] }) {
  const svgRef = useRef<SVGSVGElement>(null);
  const wrapperRef = useRef<HTMLDivElement>(null);
  const [hover, setHover] = useState<Hover>(null);

  useEffect(() => {
    if (!svgRef.current || data.length === 0) return;

    const margin = { top: 12, right: 12, bottom: 28, left: 32 };
    const width = 800;
    const height = 180;
    const innerW = width - margin.left - margin.right;
    const innerH = height - margin.top - margin.bottom;

    const parsed = data.map((d) => ({
      date: new Date(d.day),
      count: d.count,
    }));

    const svg = d3.select(svgRef.current);
    svg.selectAll("*").remove();

    const x = d3
      .scaleTime()
      .domain(d3.extent(parsed, (d) => d.date) as [Date, Date])
      .range([0, innerW]);

    const maxCount = d3.max(parsed, (d) => d.count) ?? 1;
    const y = d3
      .scaleLinear()
      .domain([0, maxCount])
      .nice()
      .range([innerH, 0]);

    const g = svg
      .append("g")
      .attr("transform", `translate(${margin.left},${margin.top})`);

    drawYGrid(g, y, innerW);

    // Monochrome opacity ramp matches the chamber: low values fade, peak
    // values hit full saturation. Avoids the chart screaming "danger" for
    // a normal high-volume day.
    const opacity = d3
      .scaleLinear()
      .domain([0, maxCount])
      .range([0.28, 1])
      .clamp(true);

    const barWidth = Math.max(2, (innerW / parsed.length) * 0.62);

    const bars = g
      .selectAll("rect.bar")
      .data(parsed)
      .join("rect")
      .attr("class", "bar")
      .attr("x", (d) => x(d.date) - barWidth / 2)
      .attr("width", barWidth)
      .attr("y", (d) => y(d.count))
      .attr("height", (d) => innerH - y(d.count))
      .attr("fill", "#171717")
      .attr("fill-opacity", (d) => opacity(d.count))
      .attr("rx", 1);

    // Invisible per-day hover targets, wider than the visible bar so the
    // pointer doesn't have to be pixel-perfect.
    const hitWidth = innerW / parsed.length;
    g.append("g")
      .selectAll("rect.hit")
      .data(parsed)
      .join("rect")
      .attr("class", "hit")
      .attr("x", (d) => x(d.date) - hitWidth / 2)
      .attr("width", hitWidth)
      .attr("y", 0)
      .attr("height", innerH)
      .attr("fill", "transparent")
      .style("cursor", "crosshair")
      .on("mouseenter", function (_event, d) {
        bars
          .filter((b) => b === d)
          .attr("fill", "#dc2626")
          .attr("fill-opacity", 1);
        setHover({
          date: d.date,
          count: d.count,
          cx: margin.left + x(d.date),
        });
      })
      .on("mouseleave", function (_event, d) {
        bars
          .filter((b) => b === d)
          .attr("fill", "#171717")
          .attr("fill-opacity", opacity(d.count));
        setHover(null);
      });

    drawTimeAxis(g, x, innerH, "%b %d");
  }, [data]);

  const fmt = d3.timeFormat("%b %-d, %Y");

  return (
    <div ref={wrapperRef} className="relative">
      <svg
        ref={svgRef}
        width="100%"
        height={180}
        viewBox="0 0 800 180"
        preserveAspectRatio="xMidYMid meet"
        aria-label="Daily press release volume over the past 90 days"
      />
      {hover && wrapperRef.current && (
        <div
          className="pointer-events-none absolute -translate-x-1/2 rounded-md border border-neutral-200 bg-white px-2 py-1 shadow-sm"
          style={{
            left: `${(hover.cx / 800) * 100}%`,
            top: 0,
          }}
        >
          <div className="text-[10px] uppercase tracking-wider text-neutral-500 font-mono tabular-nums">
            {fmt(hover.date)}
          </div>
          <div className="text-sm font-semibold text-neutral-900 tabular-nums">
            {hover.count.toLocaleString()}{" "}
            <span className="text-xs text-neutral-500 font-normal">
              {hover.count === 1 ? "release" : "releases"}
            </span>
          </div>
        </div>
      )}
    </div>
  );
}

"use client";

import { useRef, useEffect } from "react";
import * as d3 from "d3";
import { familyName } from "../lib/names";

type SenatorRow = {
  id: string;
  full_name: string;
  party: "D" | "R" | "I";
  state: string;
  weeks: { week: string; count: number }[];
};

const partyColor = {
  D: "#3b82f6",
  R: "#ef4444",
  I: "#f59e0b",
} as const;

export function SwimLane({ data }: { data: SenatorRow[] }) {
  const svgRef = useRef<SVGSVGElement>(null);

  useEffect(() => {
    if (!svgRef.current || data.length === 0) return;

    const width = svgWidth;
    const height = svgHeight;
    const innerW = width - margin.left - margin.right;

    // Collect all weeks
    const allWeeks = new Set<string>();
    for (const senator of data) {
      for (const w of senator.weeks) {
        allWeeks.add(w.week);
      }
    }
    const weekDates = Array.from(allWeeks)
      .map((w) => new Date(w))
      .sort((a, b) => a.getTime() - b.getTime());

    const svg = d3.select(svgRef.current);
    svg.selectAll("*").remove();
    svg.attr("viewBox", `0 0 ${width} ${height}`);

    const g = svg
      .append("g")
      .attr("transform", `translate(${margin.left},${margin.top})`);

    const x = d3
      .scaleTime()
      .domain(d3.extent(weekDates) as [Date, Date])
      .range([0, innerW]);

    const maxCount = d3.max(data, (s) =>
      d3.max(s.weeks, (w) => w.count)
    ) ?? 1;
    const r = d3.scaleSqrt().domain([0, maxCount]).range([0, 7]);

    // Grid lines
    g.selectAll("line.grid")
      .data(data)
      .join("line")
      .attr("class", "grid")
      .attr("x1", 0)
      .attr("x2", innerW)
      .attr("y1", (_, i) => i * rowHeight + rowHeight / 2)
      .attr("y2", (_, i) => i * rowHeight + rowHeight / 2)
      .attr("stroke", "#d6d3d1")
      .attr("stroke-width", 1);

    // Senator labels
    g.selectAll("text.label")
      .data(data)
      .join("text")
      .attr("class", "label")
      .attr("x", -6)
      .attr("y", (_, i) => i * rowHeight + rowHeight / 2)
      .attr("text-anchor", "end")
      .attr("dominant-baseline", "middle")
      .attr("font-size", 10)
      .attr("fill", "#44403c")
      .text((d) => `${familyName(d.full_name)} (${d.party}-${d.state})`);

    // Dots
    for (let i = 0; i < data.length; i++) {
      const senator = data[i];
      const cy = i * rowHeight + rowHeight / 2;

      g.selectAll(`circle.s-${i}`)
        .data(senator.weeks)
        .join("circle")
        .attr("cx", (d) => x(new Date(d.week)))
        .attr("cy", cy)
        .attr("r", (d) => r(d.count))
        .attr("fill", partyColor[senator.party])
        .attr("opacity", 0.85);
    }

    // X axis
    g.append("g")
      .attr("transform", `translate(0,${data.length * rowHeight + 4})`)
      .call(
        d3
          .axisBottom(x)
          .ticks(8)
          .tickFormat((d) => d3.timeFormat("%b")(d as Date))
      )
      .call((g) => g.select(".domain").remove())
      .call((g) => g.selectAll(".tick line").remove())
      .call((g) =>
        g.selectAll(".tick text").attr("fill", "#9ca3af").attr("font-size", 10)
      );
  }, [data]);

  const rowHeight = 20;
  const margin = { top: 20, right: 20, bottom: 30, left: 140 };
  const svgWidth = 800;
  const svgHeight = margin.top + data.length * rowHeight + margin.bottom;

  return (
    <div className="overflow-x-auto">
      <svg
        ref={svgRef}
        width="100%"
        height={svgHeight}
        viewBox={`0 0 ${svgWidth} ${svgHeight}`}
        preserveAspectRatio="xMinYMin meet"
      />
    </div>
  );
}

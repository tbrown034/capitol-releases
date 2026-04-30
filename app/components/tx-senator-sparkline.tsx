"use client";

import * as d3 from "d3";
import { useEffect, useRef } from "react";

type Bar = { week: string; count: number };

// Compact weekly-volume sparkline for an individual TX senator. Used on the
// per-senator page. The bar shape (not line) makes single-week spikes
// readable when total volume is small (most TX senators have <30 records).
export function TxSenatorSparkline({ data }: { data: Bar[] }) {
  const svgRef = useRef<SVGSVGElement>(null);

  const w = 520;
  const h = 80;
  const margin = { top: 6, right: 4, bottom: 16, left: 4 };

  useEffect(() => {
    if (!svgRef.current || data.length === 0) return;
    const innerW = w - margin.left - margin.right;
    const innerH = h - margin.top - margin.bottom;

    const x = d3.scaleBand<string>().domain(data.map((d) => d.week)).range([0, innerW]).padding(0.2);
    const y = d3.scaleLinear().domain([0, d3.max(data, (d) => d.count) ?? 1]).range([innerH, 0]);

    const svg = d3.select(svgRef.current);
    svg.selectAll("*").remove();
    svg.attr("viewBox", `0 0 ${w} ${h}`);
    const g = svg.append("g").attr("transform", `translate(${margin.left},${margin.top})`);

    // Bars
    g.selectAll("rect")
      .data(data)
      .enter()
      .append("rect")
      .attr("x", (d) => x(d.week) ?? 0)
      .attr("y", (d) => y(d.count))
      .attr("width", x.bandwidth())
      .attr("height", (d) => Math.max(1, innerH - y(d.count)))
      .attr("fill", "#525252");

    // Quarter labels along bottom
    const seen = new Set<string>();
    data.forEach((d) => {
      const date = new Date(d.week);
      const month = date.getUTCMonth();
      const year = date.getUTCFullYear();
      if (month % 3 !== 0) return;
      const key = `${year}-${month}`;
      if (seen.has(key)) return;
      seen.add(key);
      const label = month === 0 ? `'${String(year).slice(2)}` : d3.timeFormat("%b")(date);
      g.append("text")
        .attr("x", (x(d.week) ?? 0) + x.bandwidth() / 2)
        .attr("y", innerH + 12)
        .attr("text-anchor", "start")
        .attr("font-size", 9)
        .attr("fill", "#a3a3a3")
        .text(label);
    });
  }, [data]);

  return (
    <svg
      ref={svgRef}
      role="img"
      aria-label="Weekly press release volume since January 2025"
      width="100%"
      height={h}
      viewBox={`0 0 ${w} ${h}`}
      preserveAspectRatio="xMinYMin meet"
      className="block w-full h-auto"
    />
  );
}

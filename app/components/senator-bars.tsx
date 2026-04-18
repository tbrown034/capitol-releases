"use client";

import { useRef, useEffect } from "react";
import * as d3 from "d3";
import Link from "next/link";

type SenatorRow = {
  id: string;
  full_name: string;
  party: "D" | "R" | "I";
  state: string;
  weeks: { week: string; count: number }[];
  total: number;
};

const partyColor = {
  D: "#3b82f6",
  R: "#ef4444",
  I: "#f59e0b",
} as const;

export function SenatorBars({ data }: { data: SenatorRow[] }) {
  const svgRef = useRef<SVGSVGElement>(null);

  const rowHeight = 28;
  const margin = { top: 4, right: 40, bottom: 4, left: 150 };
  const svgWidth = 800;
  const svgHeight = margin.top + data.length * rowHeight + margin.bottom;

  useEffect(() => {
    if (!svgRef.current || data.length === 0) return;

    const innerW = svgWidth - margin.left - margin.right;

    const svg = d3.select(svgRef.current);
    svg.selectAll("*").remove();
    svg.attr("viewBox", `0 0 ${svgWidth} ${svgHeight}`);

    const g = svg
      .append("g")
      .attr("transform", `translate(${margin.left},${margin.top})`);

    const maxTotal = d3.max(data, (d) => d.total) ?? 1;

    const x = d3.scaleLinear().domain([0, maxTotal]).range([0, innerW]);

    // Rows
    for (let i = 0; i < data.length; i++) {
      const senator = data[i];
      const y = i * rowHeight;

      // Alternating background
      if (i % 2 === 0) {
        g.append("rect")
          .attr("x", -margin.left)
          .attr("y", y)
          .attr("width", svgWidth)
          .attr("height", rowHeight)
          .attr("fill", "#fafaf9");
      }

      // Senator label
      g.append("text")
        .attr("x", -8)
        .attr("y", y + rowHeight / 2)
        .attr("text-anchor", "end")
        .attr("dominant-baseline", "middle")
        .attr("font-size", 11)
        .attr("fill", "#44403c")
        .text(
          `${senator.full_name.split(" ").pop()} (${senator.party}-${senator.state})`
        );

      // Party dot
      g.append("circle")
        .attr("cx", -margin.left + 8)
        .attr("cy", y + rowHeight / 2)
        .attr("r", 3.5)
        .attr("fill", partyColor[senator.party]);

      // Bar
      g.append("rect")
        .attr("x", 0)
        .attr("y", y + 6)
        .attr("width", x(senator.total))
        .attr("height", rowHeight - 12)
        .attr("rx", 2)
        .attr("fill", partyColor[senator.party])
        .attr("opacity", 0.75);

      // Count label
      g.append("text")
        .attr("x", x(senator.total) + 6)
        .attr("y", y + rowHeight / 2)
        .attr("dominant-baseline", "middle")
        .attr("font-size", 10)
        .attr("font-family", "monospace")
        .attr("fill", "#a3a3a3")
        .text(senator.total);
    }
  }, [data, svgHeight]);

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

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
  total: number;
};

const partyColor = {
  D: "#3b82f6",
  R: "#ef4444",
  I: "#f59e0b",
} as const;

export function SenatorBars({ data }: { data: SenatorRow[] }) {
  const svgRef = useRef<SVGSVGElement>(null);

  const rowHeight = 24;
  const labelWidth = 150;
  const totalWidth = 50;
  const margin = { top: 24, right: 8, bottom: 4, left: labelWidth + 16 };
  const svgWidth = 800;
  const svgHeight = margin.top + data.length * rowHeight + margin.bottom;

  useEffect(() => {
    if (!svgRef.current || data.length === 0) return;

    const innerW = svgWidth - margin.left - margin.right - totalWidth;

    const svg = d3.select(svgRef.current);
    svg.selectAll("*").remove();
    svg.attr("viewBox", `0 0 ${svgWidth} ${svgHeight}`);

    // Collect all unique weeks across all senators
    const allWeeks = new Set<string>();
    for (const s of data) {
      for (const w of s.weeks) allWeeks.add(w.week);
    }
    const sortedWeeks = Array.from(allWeeks).sort();

    const g = svg
      .append("g")
      .attr("transform", `translate(${margin.left},${margin.top})`);

    // X scale: weeks
    const x = d3
      .scaleBand()
      .domain(sortedWeeks)
      .range([0, innerW])
      .padding(0.08);

    // Color intensity scale per senator (relative to their own max)
    const globalMax = d3.max(data, (s) =>
      d3.max(s.weeks, (w) => w.count)
    ) ?? 1;

    // Month-start labels along top. Key on year+month so the same month label
    // across years (Jan 2025 / Jan 2026) doesn't collide and drop the second.
    // Show year only on January (or the first label) to keep it readable.
    const seenMonths = new Set<string>();
    let firstLabel = true;
    for (const week of sortedWeeks) {
      const d = new Date(week);
      const key = `${d.getUTCFullYear()}-${d.getUTCMonth()}`;
      if (seenMonths.has(key)) continue;
      seenMonths.add(key);
      const monthAbbr = d3.timeFormat("%b")(d);
      const showYear = firstLabel || d.getUTCMonth() === 0;
      const label = showYear ? `${monthAbbr} '${String(d.getUTCFullYear()).slice(2)}` : monthAbbr;
      firstLabel = false;
      g.append("text")
        .attr("x", x(week)! + x.bandwidth() / 2)
        .attr("y", -8)
        .attr("text-anchor", "start")
        .attr("font-size", 9)
        .attr("fill", "#a3a3a3")
        .text(label);
    }

    // Rows — each row wrapped in an <a> so the entire band is a click target
    // to the senator page.
    for (let i = 0; i < data.length; i++) {
      const senator = data[i];
      const yPos = i * rowHeight;
      const weekMap = new Map(senator.weeks.map((w) => [w.week, w.count]));
      const baseColor = partyColor[senator.party];
      const isTopThree = i < 3;

      const rowLink = g
        .append("a")
        .attr("href", `/senators/${senator.id}`)
        .attr("aria-label", `${senator.full_name} — ${senator.total} releases`)
        .style("cursor", "pointer");

      // Alternating background + hover band (a single rect; transitions on
      // mouseover lift the row out of the alt stripe).
      const bgRow = rowLink
        .append("rect")
        .attr("x", -margin.left)
        .attr("y", yPos)
        .attr("width", svgWidth)
        .attr("height", rowHeight)
        .attr("fill", i % 2 === 0 ? "#fafaf9" : "transparent")
        .style("transition", "fill 120ms");
      rowLink
        .on("mouseenter", () => bgRow.attr("fill", "#f5f5f4"))
        .on("mouseleave", () =>
          bgRow.attr("fill", i % 2 === 0 ? "#fafaf9" : "transparent")
        );

      // Senator label — bolder for top three.
      rowLink
        .append("text")
        .attr("x", -8)
        .attr("y", yPos + rowHeight / 2)
        .attr("text-anchor", "end")
        .attr("dominant-baseline", "middle")
        .attr("font-size", 11)
        .attr("font-weight", isTopThree ? 600 : 400)
        .attr("fill", isTopThree ? "#171717" : "#44403c")
        .text(
          `${familyName(senator.full_name)} (${senator.party}-${senator.state})`
        );

      // Party dot
      rowLink
        .append("circle")
        .attr("cx", -margin.left + 8)
        .attr("cy", yPos + rowHeight / 2)
        .attr("r", 3.5)
        .attr("fill", baseColor);

      // Swim lane cells
      const colorScale = d3
        .scaleLinear<string>()
        .domain([0, 1, globalMax])
        .range([
          "transparent",
          d3.color(baseColor)!.copy({ opacity: 0.2 }).formatRgb(),
          baseColor,
        ])
        .clamp(true);

      for (const week of sortedWeeks) {
        const count = weekMap.get(week) ?? 0;
        if (count === 0) continue;
        rowLink
          .append("rect")
          .attr("x", x(week)!)
          .attr("y", yPos + 3)
          .attr("width", x.bandwidth())
          .attr("height", rowHeight - 6)
          .attr("rx", 2)
          .attr("fill", colorScale(count))
          .attr("opacity", 0.9);
      }

      // Total label — heavier weight, darker; tabular-aligned.
      rowLink
        .append("text")
        .attr("x", innerW + totalWidth - 4)
        .attr("y", yPos + rowHeight / 2)
        .attr("text-anchor", "end")
        .attr("dominant-baseline", "middle")
        .attr("font-size", 11)
        .attr("font-weight", isTopThree ? 600 : 500)
        .attr("font-family", "monospace")
        .attr("fill", isTopThree ? "#171717" : "#525252")
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

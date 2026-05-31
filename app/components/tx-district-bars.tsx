"use client";

import * as d3 from "d3";
import Link from "next/link";
import { useEffect, useRef } from "react";

type Row = {
  id: string;
  full_name: string;
  party: "D" | "R" | "I";
  district: number;
  release_count: number;
};

const PARTY_COLOR = { D: "#3b82f6", R: "#ef4444", I: "#f59e0b" } as const;
const ROW_HEIGHT = 22;
const LABEL_WIDTH = 168;
const VALUE_WIDTH = 36;
const MARGIN = { top: 4, right: 8, bottom: 22, left: LABEL_WIDTH + 8 } as const;
const SVG_WIDTH = 720;

function familyName(full: string): string {
  // "Juan \"Chuy\" Hinojosa" -> "Hinojosa"; "José Menéndez" -> "Menéndez"
  return full.replace(/"[^"]+"/g, "").trim().split(/\s+/).at(-1) ?? full;
}

export function TxDistrictBars({ rows }: { rows: Row[] }) {
  const svgRef = useRef<SVGSVGElement>(null);

  // Sort highest-volume first; zero-record senators stack at the bottom in
  // district order so the "silent caucus" reads as a contiguous block.
  const sorted = rows.toSorted((a, b) => {
    if (b.release_count !== a.release_count) return b.release_count - a.release_count;
    return a.district - b.district;
  });

  const max = Math.max(1, ...sorted.map((r) => r.release_count));
  const svgH = MARGIN.top + sorted.length * ROW_HEIGHT + MARGIN.bottom;
  const total = sorted.reduce((s, r) => s + r.release_count, 0);
  const silentCount = sorted.filter((r) => r.release_count === 0).length;

  useEffect(() => {
    if (!svgRef.current) return;
    const innerW = SVG_WIDTH - MARGIN.left - MARGIN.right - VALUE_WIDTH;
    const x = d3.scaleLinear().domain([0, max]).range([0, innerW]);

    const svg = d3.select(svgRef.current);
    svg.selectAll("*").remove();
    svg.attr("viewBox", `0 0 ${SVG_WIDTH} ${svgH}`);
    const g = svg.append("g").attr("transform", `translate(${MARGIN.left},${MARGIN.top})`);

    sorted.forEach((r, i) => {
      const y = i * ROW_HEIGHT;
      const baseColor = PARTY_COLOR[r.party];
      const isZero = r.release_count === 0;

      const link = g
        .append("a")
        .attr("href", `/texas/${r.id}`)
        .attr("aria-label", `${r.full_name} (${r.party}, District ${r.district}), ${r.release_count} releases`)
        .style("cursor", "pointer");

      // Hover band
      const band = link
        .append("rect")
        .attr("x", -MARGIN.left)
        .attr("y", y)
        .attr("width", SVG_WIDTH)
        .attr("height", ROW_HEIGHT)
        .attr("fill", i % 2 === 1 ? "#fafaf9" : "transparent")
        .style("transition", "fill 120ms");
      link
        .on("mouseenter", () => band.attr("fill", "#f5f5f4"))
        .on("mouseleave", () => band.attr("fill", i % 2 === 1 ? "#fafaf9" : "transparent"));

      // District badge
      link
        .append("text")
        .attr("x", -MARGIN.left + 6)
        .attr("y", y + ROW_HEIGHT / 2)
        .attr("dominant-baseline", "middle")
        .attr("font-size", 10)
        .attr("font-family", "ui-monospace,SFMono-Regular,Menlo,monospace")
        .attr("fill", "#a3a3a3")
        .text(`D${String(r.district).padStart(2, "0")}`);

      // Senator label
      link
        .append("text")
        .attr("x", -8)
        .attr("y", y + ROW_HEIGHT / 2)
        .attr("text-anchor", "end")
        .attr("dominant-baseline", "middle")
        .attr("font-size", 11)
        .attr("font-weight", isZero ? 400 : 500)
        .attr("fill", isZero ? "#a3a3a3" : "#171717")
        .text(`${familyName(r.full_name)} (${r.party})`);

      // Bar — for zero rows, render a thin gray rule so the row is visible.
      if (isZero) {
        link
          .append("line")
          .attr("x1", 0)
          .attr("x2", 28)
          .attr("y1", y + ROW_HEIGHT / 2)
          .attr("y2", y + ROW_HEIGHT / 2)
          .attr("stroke", "#d6d3d1")
          .attr("stroke-width", 1.5)
          .attr("stroke-dasharray", "2,2");
      } else {
        link
          .append("rect")
          .attr("x", 0)
          .attr("y", y + 4)
          .attr("width", x(r.release_count))
          .attr("height", ROW_HEIGHT - 8)
          .attr("rx", 2)
          .attr("fill", baseColor)
          .attr("opacity", 0.85);
      }

      // Count
      link
        .append("text")
        .attr("x", innerW + VALUE_WIDTH - 4)
        .attr("y", y + ROW_HEIGHT / 2)
        .attr("text-anchor", "end")
        .attr("dominant-baseline", "middle")
        .attr("font-size", 11)
        .attr("font-family", "ui-monospace,SFMono-Regular,Menlo,monospace")
        .attr("font-weight", isZero ? 400 : 600)
        .attr("fill", isZero ? "#a3a3a3" : "#171717")
        .text(isZero ? "—" : r.release_count.toString());
    });

    // Source credit baked into the SVG bottom — survives a screenshot crop.
    const creditY = sorted.length * ROW_HEIGHT + 14;
    g.append("text")
      .attr("x", -MARGIN.left + 4)
      .attr("y", creditY)
      .attr("font-size", 10)
      .attr("fill", "#a3a3a3")
      .attr("font-family", "system-ui, -apple-system, sans-serif")
      .text(`${silentCount} of ${sorted.length} senators have published nothing · n=${total} releases`);
    g.append("text")
      .attr("x", innerW + VALUE_WIDTH - 4)
      .attr("y", creditY)
      .attr("text-anchor", "end")
      .attr("font-size", 10)
      .attr("fill", "#a3a3a3")
      .attr("font-family", "system-ui, -apple-system, sans-serif")
      .text("Capitol Releases · capitolreleases.com/texas");

    return () => {
      svg.selectAll("*")
        .on("mouseenter", null)
        .on("mouseleave", null)
        .on("mousemove", null)
        .remove();
    };
  }, [sorted, max, svgH, total, silentCount]);

  return (
    <div className="overflow-x-auto">
      <svg
        ref={svgRef}
        role="img"
        aria-label={`Press release volume per Texas state senator since Jan 2025. ${sorted.filter((r) => r.release_count === 0).length} senators have published nothing.`}
        width="100%"
        height={svgH}
        viewBox={`0 0 ${SVG_WIDTH} ${svgH}`}
        preserveAspectRatio="xMinYMin meet"
        className="block w-full h-auto"
      />
      {/* Hidden link list for keyboard users — d3-rendered <a> elements
          aren't always tab-reachable in browsers. */}
      <ul className="sr-only">
        {sorted.map((r) => (
          <li key={r.id}>
            <Link href={`/texas/${r.id}`}>
              {r.full_name} (D{r.district}, {r.party}): {r.release_count} releases
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}

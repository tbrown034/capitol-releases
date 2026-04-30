"use client";

import * as d3 from "d3";
import { useEffect, useRef } from "react";

type Bar = { month: string; count: number };

// Vertical-bar monthly-volume chart with annotated session windows.
// The Texas Legislature meets in regular session January-May of
// odd-numbered years; the chart highlights the 2025 regular session and
// any subsequent special sessions to explain the publishing pulse.
export function TxMonthlyVolume({ data }: { data: Bar[] }) {
  const svgRef = useRef<SVGSVGElement>(null);

  const w = 720;
  const h = 220;
  // Bottom margin reserves space for both the X-axis month labels and an
  // in-SVG source credit so the chart survives screenshot crops.
  const margin = { top: 18, right: 12, bottom: 48, left: 32 };

  useEffect(() => {
    if (!svgRef.current || data.length === 0) return;

    const innerW = w - margin.left - margin.right;
    const innerH = h - margin.top - margin.bottom;

    const months = data.map((d) => d.month);
    const x = d3.scaleBand<string>().domain(months).range([0, innerW]).padding(0.18);
    const y = d3
      .scaleLinear()
      .domain([0, d3.max(data, (d) => d.count) ?? 1])
      .nice()
      .range([innerH, 0]);

    const svg = d3.select(svgRef.current);
    svg.selectAll("*").remove();
    svg.attr("viewBox", `0 0 ${w} ${h}`);
    const g = svg.append("g").attr("transform", `translate(${margin.left},${margin.top})`);

    // Session band: 2025 regular session, Jan 14 -- June 2 (rendered as
    // shaded background spanning the months that fall in that window).
    const sessionBand = months.filter(
      (m) => m >= "2025-01-01" && m <= "2025-06-01"
    );
    if (sessionBand.length > 0) {
      const start = x(sessionBand[0]) ?? 0;
      const end = (x(sessionBand[sessionBand.length - 1]) ?? 0) + x.bandwidth();
      g.append("rect")
        .attr("x", start - 4)
        .attr("y", -8)
        .attr("width", end - start + 8)
        .attr("height", innerH + 8)
        .attr("fill", "#fef3c7")
        .attr("opacity", 0.45);
      g.append("text")
        .attr("x", start)
        .attr("y", -6)
        .attr("font-size", 9)
        .attr("font-family", "ui-monospace,SFMono-Regular,Menlo,monospace")
        .attr("fill", "#92400e")
        .text("2025 SESSION");
    }

    // Bars
    g.selectAll("rect.bar")
      .data(data)
      .enter()
      .append("rect")
      .attr("class", "bar")
      .attr("x", (d) => x(d.month) ?? 0)
      .attr("y", (d) => y(d.count))
      .attr("width", x.bandwidth())
      .attr("height", (d) => innerH - y(d.count))
      .attr("fill", "#525252");

    // X axis: show "Jan", "Apr", "Jul", "Oct" + year labels
    months.forEach((m) => {
      const date = new Date(m);
      const month = date.getUTCMonth();
      if (month % 3 !== 0) return;
      const isYearStart = month === 0;
      const label = isYearStart
        ? `Jan ${String(date.getUTCFullYear()).slice(2)}`
        : d3.timeFormat("%b")(date);
      g.append("text")
        .attr("x", (x(m) ?? 0) + x.bandwidth() / 2)
        .attr("y", innerH + 14)
        .attr("text-anchor", "middle")
        .attr("font-size", 10)
        .attr("fill", "#737373")
        .text(label);
    });

    // Y axis ticks: 0 + max
    const yTicks = y.ticks(3);
    yTicks.forEach((t) => {
      g.append("line")
        .attr("x1", -4)
        .attr("x2", innerW)
        .attr("y1", y(t))
        .attr("y2", y(t))
        .attr("stroke", "#e7e5e4")
        .attr("stroke-dasharray", t === 0 ? "0" : "2,3");
      g.append("text")
        .attr("x", -8)
        .attr("y", y(t))
        .attr("text-anchor", "end")
        .attr("dominant-baseline", "middle")
        .attr("font-size", 10)
        .attr("font-family", "ui-monospace,SFMono-Regular,Menlo,monospace")
        .attr("fill", "#a3a3a3")
        .text(t);
    });

    // Source credit baked into the SVG so the chart survives screenshot
    // crops on social/Reddit.
    const total = data.reduce((s, d) => s + d.count, 0);
    const creditY = innerH + 36;
    g.append("text")
      .attr("x", 0)
      .attr("y", creditY)
      .attr("font-size", 10)
      .attr("fill", "#a3a3a3")
      .attr("font-family", "system-ui, -apple-system, sans-serif")
      .text(`Texas Senate press releases · n=${total} since Jan 2025`);
    g.append("text")
      .attr("x", innerW)
      .attr("y", creditY)
      .attr("text-anchor", "end")
      .attr("font-size", 10)
      .attr("fill", "#a3a3a3")
      .attr("font-family", "system-ui, -apple-system, sans-serif")
      .text("Capitol Releases · capitolreleases.com/texas");
  }, [data]);

  return (
    <svg
      ref={svgRef}
      role="img"
      aria-label="Monthly press release volume from the Texas Senate, January 2025 through present, with the 2025 regular legislative session highlighted."
      width="100%"
      height={h}
      viewBox={`0 0 ${w} ${h}`}
      preserveAspectRatio="xMinYMin meet"
      className="block w-full h-auto"
    />
  );
}

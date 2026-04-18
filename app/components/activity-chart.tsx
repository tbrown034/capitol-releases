"use client";

import { useRef, useEffect } from "react";
import * as d3 from "d3";

type DataPoint = { day: string; count: number };

export function ActivityChart({ data }: { data: DataPoint[] }) {
  const svgRef = useRef<SVGSVGElement>(null);

  useEffect(() => {
    if (!svgRef.current || data.length === 0) return;

    const margin = { top: 8, right: 12, bottom: 28, left: 32 };
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

    const y = d3
      .scaleLinear()
      .domain([0, d3.max(parsed, (d) => d.count) ?? 1])
      .nice()
      .range([innerH, 0]);

    const g = svg
      .append("g")
      .attr("transform", `translate(${margin.left},${margin.top})`);

    // Y grid lines
    g.append("g")
      .call(d3.axisLeft(y).ticks(4).tickSize(-innerW))
      .call((sel) => sel.select(".domain").remove())
      .call((sel) =>
        sel
          .selectAll(".tick line")
          .attr("stroke", "#e5e5e5")
          .attr("stroke-dasharray", "2,2")
      )
      .call((sel) =>
        sel
          .selectAll(".tick text")
          .attr("fill", "#a3a3a3")
          .attr("font-size", 10)
      );

    // Color scale: low volume -> muted blue, high volume -> vivid coral
    const maxCount = d3.max(parsed, (d) => d.count) ?? 1;
    const colorScale = d3
      .scaleLinear<string>()
      .domain([0, maxCount * 0.5, maxCount])
      .range(["#93c5fd", "#6366f1", "#f43f5e"])
      .clamp(true);

    // Bars
    const barWidth = Math.max(2, (innerW / parsed.length) * 0.55);

    g.selectAll("rect")
      .data(parsed)
      .join("rect")
      .attr("x", (d) => x(d.date) - barWidth / 2)
      .attr("width", barWidth)
      .attr("y", (d) => y(d.count))
      .attr("height", (d) => innerH - y(d.count))
      .attr("fill", (d) => colorScale(d.count))
      .attr("rx", 1);

    // X axis
    g.append("g")
      .attr("transform", `translate(0,${innerH})`)
      .call(
        d3
          .axisBottom(x)
          .ticks(6)
          .tickFormat((d) => d3.timeFormat("%b %d")(d as Date))
      )
      .call((sel) => sel.select(".domain").remove())
      .call((sel) => sel.selectAll(".tick line").remove())
      .call((sel) =>
        sel
          .selectAll(".tick text")
          .attr("fill", "#a3a3a3")
          .attr("font-size", 10)
      );
  }, [data]);

  return (
    <svg
      ref={svgRef}
      width="100%"
      height={180}
      viewBox="0 0 800 180"
      preserveAspectRatio="xMidYMid meet"
    />
  );
}

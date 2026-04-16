"use client";

import { useRef, useEffect } from "react";
import * as d3 from "d3";

type DataPoint = { day: string; count: number };

export function ActivityChart({ data }: { data: DataPoint[] }) {
  const svgRef = useRef<SVGSVGElement>(null);

  useEffect(() => {
    if (!svgRef.current || data.length === 0) return;

    const margin = { top: 8, right: 12, bottom: 28, left: 32 };
    const width = svgRef.current.clientWidth;
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

    // Area
    const area = d3
      .area<{ date: Date; count: number }>()
      .x((d) => x(d.date))
      .y0(innerH)
      .y1((d) => y(d.count))
      .curve(d3.curveMonotoneX);

    g.append("path")
      .datum(parsed)
      .attr("fill", "#e5e7eb")
      .attr("d", area);

    // Line
    const line = d3
      .line<{ date: Date; count: number }>()
      .x((d) => x(d.date))
      .y((d) => y(d.count))
      .curve(d3.curveMonotoneX);

    g.append("path")
      .datum(parsed)
      .attr("fill", "none")
      .attr("stroke", "#374151")
      .attr("stroke-width", 1.5)
      .attr("d", line);

    // X axis
    g.append("g")
      .attr("transform", `translate(0,${innerH})`)
      .call(
        d3
          .axisBottom(x)
          .ticks(6)
          .tickFormat((d) => d3.timeFormat("%b %d")(d as Date))
      )
      .call((g) => g.select(".domain").remove())
      .call((g) => g.selectAll(".tick line").attr("stroke", "#e5e7eb"))
      .call((g) =>
        g.selectAll(".tick text").attr("fill", "#9ca3af").attr("font-size", 10)
      );

    // Y axis
    g.append("g")
      .call(d3.axisLeft(y).ticks(4).tickSize(-innerW))
      .call((g) => g.select(".domain").remove())
      .call((g) =>
        g
          .selectAll(".tick line")
          .attr("stroke", "#f3f4f6")
          .attr("stroke-dasharray", "2,2")
      )
      .call((g) =>
        g.selectAll(".tick text").attr("fill", "#9ca3af").attr("font-size", 10)
      );
  }, [data]);

  return (
    <svg
      ref={svgRef}
      width="100%"
      height={180}
      viewBox="0 0 600 180"
      preserveAspectRatio="xMidYMid meet"
    />
  );
}

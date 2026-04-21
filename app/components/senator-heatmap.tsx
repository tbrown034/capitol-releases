"use client";

import { useRef, useEffect } from "react";
import * as d3 from "d3";

type DayRow = { day: string; count: number };

const partyColor = {
  D: "#3b82f6",
  R: "#ef4444",
  I: "#f59e0b",
} as const;

const CELL = 11;
const GAP = 2;
const DAY_ROW = CELL + GAP;
const WEEK_COL = CELL + GAP;
const LEFT_PAD = 24;
const TOP_PAD = 16;
const BOTTOM_PAD = 18;

export function SenatorHeatmap({
  data,
  party,
}: {
  data: DayRow[];
  party: "D" | "R" | "I";
}) {
  const svgRef = useRef<SVGSVGElement>(null);

  useEffect(() => {
    if (!svgRef.current) return;

    const svg = d3.select(svgRef.current);
    svg.selectAll("*").remove();

    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const start = new Date("2025-01-01T00:00:00");
    const end = today;

    // All days from 2025-01-01 → today, indexed by ISO date
    const days = d3.timeDay.range(start, d3.timeDay.offset(end, 1));
    const counts = new Map(data.map((d) => [d.day, d.count]));
    const fmt = d3.timeFormat("%Y-%m-%d");

    // Columns: weeks starting Sunday. Column index = weeks since first Sunday on or before start.
    const firstSunday = d3.timeSunday.floor(start);
    const lastSunday = d3.timeSunday.floor(end);
    const totalWeeks =
      Math.round((+lastSunday - +firstSunday) / (7 * 24 * 3600 * 1000)) + 1;

    const width = LEFT_PAD + totalWeeks * WEEK_COL + 8;
    const height = TOP_PAD + 7 * DAY_ROW + BOTTOM_PAD;

    svg.attr("viewBox", `0 0 ${width} ${height}`);

    const maxCount = d3.max(data, (d) => d.count) ?? 1;

    const base = partyColor[party];
    // 5-step scale: empty → base (quantized for github-like banding)
    const fillFor = (count: number) => {
      if (count <= 0) return "#f5f5f4";
      if (maxCount <= 1) return d3.color(base)!.copy({ opacity: 0.9 }).formatRgb();
      const t = count / maxCount;
      if (t < 0.25) return d3.color(base)!.copy({ opacity: 0.2 }).formatRgb();
      if (t < 0.5) return d3.color(base)!.copy({ opacity: 0.4 }).formatRgb();
      if (t < 0.75) return d3.color(base)!.copy({ opacity: 0.65 }).formatRgb();
      return d3.color(base)!.copy({ opacity: 0.9 }).formatRgb();
    };

    const g = svg.append("g").attr("transform", `translate(${LEFT_PAD},${TOP_PAD})`);

    // Day labels (Mon, Wed, Fri)
    const dayLabels = [
      { idx: 1, text: "Mon" },
      { idx: 3, text: "Wed" },
      { idx: 5, text: "Fri" },
    ];
    for (const d of dayLabels) {
      g.append("text")
        .attr("x", -4)
        .attr("y", d.idx * DAY_ROW + CELL - 2)
        .attr("text-anchor", "end")
        .attr("font-size", 9)
        .attr("fill", "#a3a3a3")
        .text(d.text);
    }

    // Cells
    for (const day of days) {
      const weekIdx = Math.round(
        (+d3.timeSunday.floor(day) - +firstSunday) / (7 * 24 * 3600 * 1000)
      );
      const dow = day.getDay(); // 0=Sun..6=Sat
      const count = counts.get(fmt(day)) ?? 0;

      g.append("rect")
        .attr("x", weekIdx * WEEK_COL)
        .attr("y", dow * DAY_ROW)
        .attr("width", CELL)
        .attr("height", CELL)
        .attr("rx", 2)
        .attr("fill", fillFor(count))
        .append("title")
        .text(
          `${d3.timeFormat("%b %-d, %Y")(day)} — ${count} release${count !== 1 ? "s" : ""}`
        );
    }

    // Month labels along top. Skip months before our data window
    // (the heatmap grid begins on the Sunday on/before Jan 1, which can
    // land in the prior December). Include the year on every January.
    const months = d3.timeMonth.range(
      d3.timeMonth.floor(start),
      d3.timeMonth.offset(end, 1)
    );
    for (const monthStart of months) {
      if (monthStart < start) continue;
      const weekIdx = Math.round(
        (+d3.timeSunday.floor(monthStart) - +firstSunday) / (7 * 24 * 3600 * 1000)
      );
      const isJan = monthStart.getMonth() === 0;
      const label = isJan
        ? d3.timeFormat("%b %Y")(monthStart)
        : d3.timeFormat("%b")(monthStart);
      g.append("text")
        .attr("x", weekIdx * WEEK_COL)
        .attr("y", -4)
        .attr("font-size", 9)
        .attr("font-weight", isJan ? 600 : 400)
        .attr("fill", isJan ? "#525252" : "#a3a3a3")
        .text(label);
    }

    // Legend in bottom-right
    const legendX = totalWeeks * WEEK_COL - 110;
    const legendY = 7 * DAY_ROW + 6;
    const legendG = g
      .append("g")
      .attr("transform", `translate(${legendX},${legendY})`);
    legendG
      .append("text")
      .attr("x", 0)
      .attr("y", CELL - 2)
      .attr("font-size", 9)
      .attr("fill", "#a3a3a3")
      .text("Less");
    const levels = [0, 0.2, 0.45, 0.7, 1];
    levels.forEach((t, i) => {
      const sample =
        t === 0
          ? "#f5f5f4"
          : d3
              .color(base)!
              .copy({ opacity: [0.2, 0.4, 0.65, 0.9][i - 1] ?? 0.9 })
              .formatRgb();
      legendG
        .append("rect")
        .attr("x", 26 + i * (CELL + 2))
        .attr("y", 0)
        .attr("width", CELL)
        .attr("height", CELL)
        .attr("rx", 2)
        .attr("fill", sample);
    });
    legendG
      .append("text")
      .attr("x", 26 + levels.length * (CELL + 2) + 2)
      .attr("y", CELL - 2)
      .attr("font-size", 9)
      .attr("fill", "#a3a3a3")
      .text("More");
  }, [data, party]);

  return (
    <svg
      ref={svgRef}
      width="100%"
      preserveAspectRatio="xMinYMin meet"
    />
  );
}

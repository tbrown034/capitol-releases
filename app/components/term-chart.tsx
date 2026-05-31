"use client";

import { useEffect, useMemo, useReducer, useRef } from "react";
import * as d3 from "d3";
import { formatReleaseDate } from "../lib/dates";
import { drawYGrid, drawTimeAxis } from "./chart-axes";

const MAX_TERMS = 6;
const PALETTE = [
  "#2563eb", // blue
  "#dc2626", // red
  "#ea580c", // orange
  "#16a34a", // green
  "#9333ea", // purple
  "#0891b2", // cyan
];

type Series = Record<string, { week: string; count: number }[]>;
type ChartState = {
  terms: string[];
  series: Series;
  input: string;
  loading: boolean;
  hover: { week: string } | null;
};
type ChartAction =
  | { type: "input"; input: string }
  | { type: "hover"; hover: { week: string } | null }
  | { type: "remove"; term: string }
  | { type: "loading"; terms: string[] }
  | { type: "loaded"; series: Series };

function chartReducer(state: ChartState, action: ChartAction): ChartState {
  switch (action.type) {
    case "input":
      return { ...state, input: action.input };
    case "hover":
      return { ...state, hover: action.hover };
    case "remove": {
      const nextSeries = { ...state.series };
      delete nextSeries[action.term];
      return {
        ...state,
        terms: state.terms.filter((term) => term !== action.term),
        series: nextSeries,
      };
    }
    case "loading":
      return { ...state, terms: action.terms, input: "", loading: true };
    case "loaded":
      return { ...state, series: action.series, loading: false };
  }
}

export function TermChart({
  initialTerms,
  initialSeries,
}: {
  initialTerms: string[];
  initialSeries: Series;
}) {
  const [{ terms, series, input, loading, hover }, dispatch] = useReducer(
    chartReducer,
    {
      terms: initialTerms,
      series: initialSeries,
      input: "",
      loading: false,
      hover: null,
    }
  );
  const svgRef = useRef<SVGSVGElement>(null);

  const colorFor = useMemo(() => {
    const m = new Map<string, string>();
    terms.forEach((t, i) => m.set(t, PALETTE[i % PALETTE.length]));
    return (t: string) => m.get(t) ?? "#737373";
  }, [terms]);

  const allWeeks = useMemo(() => {
    const set = new Set<string>();
    Object.values(series).forEach((rows) => rows.forEach((r) => set.add(r.week)));
    return Array.from(set).sort();
  }, [series]);

  const matrix = useMemo(() => {
    const m = new Map<string, Record<string, number>>();
    for (const w of allWeeks) m.set(w, {});
    for (const [term, rows] of Object.entries(series)) {
      for (const r of rows) {
        const cell = m.get(r.week);
        if (cell) cell[term] = r.count;
      }
    }
    return m;
  }, [series, allWeeks]);

  useEffect(() => {
    if (!svgRef.current) return;
    const svg = d3.select(svgRef.current);
    svg.selectAll("*").remove();
    if (allWeeks.length === 0 || terms.length === 0) return;

    // Right margin widened so per-line end labels don't clip.
    const margin = { top: 12, right: 64, bottom: 28, left: 36 };
    const width = 800;
    const height = 260;
    const innerW = width - margin.left - margin.right;
    const innerH = height - margin.top - margin.bottom;

    const dates = allWeeks.map((w) => new Date(w));
    const maxCount =
      d3.max(terms.map((t) => d3.max((series[t] ?? []).map((r) => r.count)) ?? 0)) ?? 1;

    const x = d3
      .scaleTime()
      .domain(d3.extent(dates) as [Date, Date])
      .range([0, innerW]);

    const y = d3
      .scaleLinear()
      .domain([0, Math.max(maxCount, 1)])
      .nice()
      .range([innerH, 0]);

    const g = svg
      .append("g")
      .attr("transform", `translate(${margin.left},${margin.top})`);

    drawYGrid(g, y, innerW);
    drawTimeAxis(g, x, innerH);

    const line = d3
      .line<{ date: Date; count: number }>()
      .x((d) => x(d.date))
      .y((d) => y(d.count))
      .curve(d3.curveMonotoneX);

    // Render lines + collect end-of-line labels. Label y positions are
    // de-overlapped greedily so two terms ending at the same value don't
    // stomp each other.
    const endLabels: { term: string; y: number; color: string; lastValue: number }[] = [];
    for (const term of terms) {
      const rows = (series[term] ?? []).map((r) => ({
        date: new Date(r.week),
        count: r.count,
      }));
      if (rows.length === 0) continue;
      g.append("path")
        .datum(rows)
        .attr("fill", "none")
        .attr("stroke", colorFor(term))
        .attr("stroke-width", 1.75)
        .attr("stroke-linejoin", "round")
        .attr("stroke-linecap", "round")
        .attr("d", line);

      const last = rows[rows.length - 1];
      endLabels.push({
        term,
        y: y(last.count),
        color: colorFor(term),
        lastValue: last.count,
      });
    }

    // De-overlap: sort by y, push down anything within 12px of the previous.
    endLabels.sort((a, b) => a.y - b.y);
    for (let i = 1; i < endLabels.length; i++) {
      if (endLabels[i].y - endLabels[i - 1].y < 12) {
        endLabels[i].y = endLabels[i - 1].y + 12;
      }
    }

    const labelG = g
      .append("g")
      .attr("transform", `translate(${innerW + 6}, 0)`);
    labelG
      .selectAll("text.end-label")
      .data(endLabels)
      .join("text")
      .attr("class", "end-label")
      .attr("x", 0)
      .attr("y", (d) => d.y)
      .attr("dy", "0.32em")
      .attr("font-size", 10)
      .attr("font-weight", 500)
      .attr("fill", (d) => d.color)
      .text((d) => d.term);

    // Focus crosshair + per-line dots at hovered week.
    const focus = g.append("g").style("display", "none");
    focus
      .append("line")
      .attr("y1", 0)
      .attr("y2", innerH)
      .attr("stroke", "#525252")
      .attr("stroke-width", 1)
      .attr("stroke-dasharray", "2,2");

    const focusDots = focus
      .append("g")
      .selectAll("circle")
      .data(terms)
      .join("circle")
      .attr("r", 3.5)
      .attr("fill", "#fff")
      .attr("stroke-width", 2)
      .attr("stroke", (t) => colorFor(t));

    const overlay = g
      .append("rect")
      .attr("width", innerW)
      .attr("height", innerH)
      .attr("fill", "transparent")
      .style("pointer-events", "all");

    const bisect = d3.bisector((d: Date) => d).left;

    overlay
      .on("mouseenter", () => focus.style("display", null))
      .on("mouseleave", () => {
        focus.style("display", "none");
        dispatch({ type: "hover", hover: null });
      })
      .on("mousemove", (event) => {
        const [mx] = d3.pointer(event);
        const date = x.invert(mx);
        const idx = bisect(dates, date);
        const candidates = [dates[idx - 1], dates[idx]].filter(Boolean) as Date[];
        const nearest = candidates.reduce<Date | null>((best, d) => {
          if (!best) return d;
          return Math.abs(d.getTime() - date.getTime()) <
            Math.abs(best.getTime() - date.getTime())
            ? d
            : best;
        }, null);
        if (!nearest) return;
        const nearestWeek = allWeeks[dates.indexOf(nearest)];
        focus.select("line").attr("transform", `translate(${x(nearest)},0)`);
        focusDots
          .attr("cx", x(nearest))
          .attr("cy", (t) => {
            const row = (series[t] ?? []).find((r) => r.week === nearestWeek);
            return row ? y(row.count) : -100;
          });
        dispatch({ type: "hover", hover: { week: nearestWeek } });
      });

    return () => {
      svg.selectAll("*")
        .on("mouseenter", null)
        .on("mouseleave", null)
        .on("mousemove", null)
        .remove();
    };
  }, [series, terms, colorFor, allWeeks]);

  const removeTerm = (t: string) => {
    dispatch({ type: "remove", term: t });
  };
  const addTerm = async (raw: string) => {
    const cleaned = raw.trim().replace(/[^a-zA-Z0-9 \-']/g, "").slice(0, 40);
    if (!cleaned || terms.length >= MAX_TERMS) return;
    if (terms.some((t) => t.toLowerCase() === cleaned.toLowerCase())) return;
    const nextTerms = [...terms, cleaned];
    dispatch({ type: "loading", terms: nextTerms });
    try {
      const response = await fetch(
        `/api/trending/series?q=${encodeURIComponent(nextTerms.join(","))}`
      );
      const data = await response.json();
      dispatch({ type: "loaded", series: data.series ?? {} });
    } catch {
      dispatch({ type: "loaded", series });
    }
  };

  const hoverRow = hover ? matrix.get(hover.week) : null;
  const hoverDate = hover ? new Date(hover.week) : null;

  return (
    <div>
      <div className="flex flex-wrap items-center gap-2 mb-3">
        {terms.map((t) => (
          <span
            key={t}
            className="inline-flex items-center gap-1.5 rounded-full border bg-white px-2.5 py-0.5 text-xs"
            style={{ borderColor: colorFor(t), color: colorFor(t) }}
          >
            <span
              className="inline-block size-2 rounded-full"
              style={{ background: colorFor(t) }}
            />
            <span className="font-medium">{t}</span>
            <button
              type="button"
              onClick={() => removeTerm(t)}
              className="ml-0.5 text-neutral-400 hover:text-neutral-700 cursor-pointer"
              aria-label={`Remove ${t}`}
            >
              ×
            </button>
          </span>
        ))}
        {terms.length < MAX_TERMS && (
          <div className="inline-flex">
            <input
              type="text"
              value={input}
              onChange={(e) => dispatch({ type: "input", input: e.target.value })}
              onKeyDown={async (e) => {
                if (e.key !== "Enter") return;
                await addTerm(input);
              }}
              aria-label="Add comparison term"
              placeholder="Add term…"
              maxLength={40}
              className="w-28 rounded-full border border-dashed border-neutral-300 bg-white px-2.5 py-0.5 text-xs text-neutral-700 placeholder:text-neutral-400 focus:outline-none focus:border-neutral-500"
            />
          </div>
        )}
      </div>

      <div className="relative overflow-x-auto -mx-4 px-4 sm:mx-0 sm:px-0">
        <svg
          ref={svgRef}
          width="100%"
          height={260}
          viewBox="0 0 800 260"
          preserveAspectRatio="xMidYMid meet"
          aria-label="Weekly mention frequency by term"
        />
        {loading && (
          <div className="absolute inset-0 flex items-center justify-center text-xs text-neutral-500 bg-white/60">
            Loading…
          </div>
        )}
        {!loading && allWeeks.length === 0 && terms.length > 0 && (
          <div className="absolute inset-0 flex items-center justify-center text-xs text-neutral-500">
            No matches.
          </div>
        )}
      </div>

      {hoverRow && hoverDate && (
        <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-neutral-600">
          <span className="font-mono tabular-nums text-neutral-500">
            Week of {formatReleaseDate(hoverDate)}
          </span>
          {terms.map((t) => (
            <span key={t} className="inline-flex items-center gap-1">
              <span
                className="inline-block size-2 rounded-full"
                style={{ background: colorFor(t) }}
              />
              <span className="text-neutral-700">{t}</span>
              <span className="font-mono tabular-nums font-semibold text-neutral-900">
                {hoverRow[t] ?? 0}
              </span>
            </span>
          ))}
        </div>
      )}

      <p className="mt-3 text-xs text-neutral-500">
        Weekly mentions in release titles + bodies, since Jan 2025. Stemming
        included, e.g. <em>Iran</em> matches <em>Iranian</em>.
      </p>
    </div>
  );
}

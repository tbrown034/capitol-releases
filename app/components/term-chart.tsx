"use client";

import { useEffect, useMemo, useRef, useState } from "react";
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

export function TermChart({ initialTerms }: { initialTerms: string[] }) {
  const [terms, setTerms] = useState<string[]>(initialTerms);
  const [series, setSeries] = useState<Series>({});
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(true);
  const [hover, setHover] = useState<{ week: string } | null>(null);
  const svgRef = useRef<SVGSVGElement>(null);

  useEffect(() => {
    let cancelled = false;
    if (terms.length === 0) {
      setSeries({});
      setLoading(false);
      return;
    }
    setLoading(true);
    fetch(`/api/trending/series?q=${encodeURIComponent(terms.join(","))}`)
      .then((r) => r.json())
      .then((data) => {
        if (cancelled) return;
        setSeries(data.series ?? {});
        setLoading(false);
      })
      .catch(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [terms]);

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
        setHover(null);
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
        setHover({ week: nearestWeek });
      });
  }, [series, terms, colorFor, allWeeks]);

  const removeTerm = (t: string) => setTerms((cur) => cur.filter((x) => x !== t));
  const addTerm = (raw: string) => {
    const cleaned = raw.trim().replace(/[^a-zA-Z0-9 \-']/g, "").slice(0, 40);
    if (!cleaned || terms.length >= MAX_TERMS) return;
    if (terms.some((t) => t.toLowerCase() === cleaned.toLowerCase())) return;
    setTerms((cur) => [...cur, cleaned]);
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
              className="inline-block h-2 w-2 rounded-full"
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
          <form
            onSubmit={(e) => {
              e.preventDefault();
              addTerm(input);
              setInput("");
            }}
            className="inline-flex"
          >
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Add term…"
              maxLength={40}
              className="rounded-full border border-dashed border-neutral-300 bg-white px-2.5 py-0.5 text-xs text-neutral-700 placeholder:text-neutral-400 focus:outline-none focus:border-neutral-500 w-28"
            />
          </form>
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
                className="inline-block h-2 w-2 rounded-full"
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
        included — e.g. <em>Iran</em> matches <em>Iranian</em>.
      </p>
    </div>
  );
}

"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import * as d3 from "d3";
import Link from "next/link";
import { normalizeTitle } from "../lib/titles";
import { formatReleaseDate } from "../lib/dates";

type Headline = {
  week: string;
  title: string;
  source_url: string;
  published_at: string;
  senator_name: string;
  party: "D" | "R" | "I";
  state: string;
  senator_id: string;
};

type TimelineData = {
  weekly: { week: string; count: number }[];
  spikeHeadlines: Headline[];
  term: string;
};

const PRESETS = ["Trump", "Iran", "Ukraine", "fentanyl", "Medicaid", "abortion"];

export function TopicTimeline({ initialTerm }: { initialTerm: string }) {
  const [term, setTerm] = useState(initialTerm);
  const [data, setData] = useState<TimelineData | null>(null);
  const [loading, setLoading] = useState(true);
  const [input, setInput] = useState("");
  const svgRef = useRef<SVGSVGElement>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetch(`/api/trending/timeline?term=${encodeURIComponent(term)}`)
      .then((r) => r.json())
      .then((d: TimelineData) => {
        if (!cancelled) {
          setData(d);
          setLoading(false);
        }
      })
      .catch(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [term]);

  const spikeWeeks = useMemo(
    () => new Set(data?.spikeHeadlines.map((h) => h.week) ?? []),
    [data]
  );

  useEffect(() => {
    if (!svgRef.current || !data) return;
    const svg = d3.select(svgRef.current);
    svg.selectAll("*").remove();
    if (data.weekly.length === 0) return;

    const margin = { top: 12, right: 16, bottom: 28, left: 36 };
    const width = 800;
    const height = 220;
    const innerW = width - margin.left - margin.right;
    const innerH = height - margin.top - margin.bottom;

    const parsed = data.weekly.map((w) => ({
      date: new Date(w.week),
      week: w.week,
      count: w.count,
    }));

    const x = d3
      .scaleTime()
      .domain(d3.extent(parsed, (d) => d.date) as [Date, Date])
      .range([0, innerW]);

    const maxCount = d3.max(parsed, (d) => d.count) ?? 1;
    const y = d3
      .scaleLinear()
      .domain([0, maxCount])
      .nice()
      .range([innerH, 0]);

    const g = svg
      .append("g")
      .attr("transform", `translate(${margin.left},${margin.top})`);

    g.append("g")
      .call(d3.axisLeft(y).ticks(4).tickSize(-innerW))
      .call((sel) => sel.select(".domain").remove())
      .call((sel) =>
        sel.selectAll(".tick line").attr("stroke", "#e5e5e5").attr("stroke-dasharray", "2,2")
      )
      .call((sel) =>
        sel.selectAll(".tick text").attr("fill", "#a3a3a3").attr("font-size", 10)
      );

    g.append("g")
      .attr("transform", `translate(0,${innerH})`)
      .call(
        d3
          .axisBottom(x)
          .ticks(6)
          .tickFormat((d) => d3.timeFormat("%b %Y")(d as Date))
      )
      .call((sel) => sel.select(".domain").remove())
      .call((sel) => sel.selectAll(".tick line").remove())
      .call((sel) =>
        sel.selectAll(".tick text").attr("fill", "#a3a3a3").attr("font-size", 10)
      );

    const barW = Math.max(2, (innerW / parsed.length) * 0.6);
    g.selectAll("rect.bar")
      .data(parsed)
      .join("rect")
      .attr("class", "bar")
      .attr("x", (d) => x(d.date) - barW / 2)
      .attr("width", barW)
      .attr("y", (d) => y(d.count))
      .attr("height", (d) => innerH - y(d.count))
      .attr("fill", (d) => (spikeWeeks.has(d.week) ? "#dc2626" : "#9ca3af"))
      .attr("rx", 1);
  }, [data, spikeWeeks]);

  const submitTerm = (raw: string) => {
    const cleaned = raw.trim().replace(/[^a-zA-Z0-9 \-']/g, "").slice(0, 40);
    if (!cleaned) return;
    setTerm(cleaned);
  };

  return (
    <div>
      <div className="flex flex-wrap items-center gap-2 mb-3">
        <span className="text-[10px] uppercase tracking-wider text-neutral-500 mr-1">
          Term:
        </span>
        {PRESETS.map((t) => {
          const selected = t.toLowerCase() === term.toLowerCase();
          return (
            <button
              key={t}
              type="button"
              onClick={() => submitTerm(t)}
              className={`text-xs rounded-full border px-2.5 py-0.5 transition-colors ${
                selected
                  ? "border-neutral-900 bg-neutral-900 text-white"
                  : "border-neutral-300 text-neutral-600 hover:border-neutral-500"
              }`}
            >
              {t}
            </button>
          );
        })}
        <form
          onSubmit={(e) => {
            e.preventDefault();
            submitTerm(input);
            setInput("");
          }}
          className="inline-flex"
        >
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Custom term…"
            maxLength={40}
            className="rounded-full border border-dashed border-neutral-300 bg-white px-2.5 py-0.5 text-xs text-neutral-700 placeholder:text-neutral-400 focus:outline-none focus:border-neutral-500 w-32"
          />
        </form>
      </div>

      <div className="relative overflow-x-auto -mx-4 px-4 sm:mx-0 sm:px-0">
        <svg
          ref={svgRef}
          width="100%"
          height={220}
          viewBox="0 0 800 220"
          preserveAspectRatio="xMidYMid meet"
          aria-label={`Weekly volume of releases mentioning ${term}`}
        />
        {loading && (
          <div className="absolute inset-0 flex items-center justify-center text-xs text-neutral-400 bg-white/60">
            Loading…
          </div>
        )}
        {!loading && data && data.weekly.length === 0 && (
          <div className="absolute inset-0 flex items-center justify-center text-xs text-neutral-400">
            No matches for &ldquo;{term}&rdquo;.
          </div>
        )}
      </div>

      {data && data.spikeHeadlines.length > 0 && (
        <div className="mt-5">
          <h3 className="text-[10px] uppercase tracking-wider text-neutral-500 mb-3">
            Top headlines from spike weeks
          </h3>
          <ol className="space-y-3">
            {data.spikeHeadlines
              .slice()
              .sort((a, b) => b.week.localeCompare(a.week))
              .map((h) => (
                <li
                  key={h.source_url}
                  className="border-l-2 border-red-200 pl-3"
                >
                  <div className="text-[11px] text-neutral-500 font-mono tabular-nums mb-0.5">
                    Week of {formatReleaseDate(h.week)}
                    {" · "}
                    <Link
                      href={`/senators/${h.senator_id}`}
                      className="text-neutral-700 hover:underline"
                    >
                      {h.senator_name}
                    </Link>{" "}
                    ({h.party}-{h.state})
                  </div>
                  <a
                    href={h.source_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-sm text-neutral-900 hover:underline leading-snug"
                  >
                    {normalizeTitle(h.title)}
                  </a>
                </li>
              ))}
          </ol>
        </div>
      )}
    </div>
  );
}

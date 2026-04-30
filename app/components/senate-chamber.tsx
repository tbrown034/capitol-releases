"use client";

import Link from "next/link";
import Image from "next/image";
import { useEffect, useMemo, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { familyName } from "../lib/names";
import { getSenatorPhotoUrl, getInitials } from "../lib/photos";

type Senator = {
  id: string;
  full_name: string;
  party: "D" | "R" | "I";
  state: string;
  count: number;
};

const PARTY_COLOR = {
  D: "#3b82f6",
  R: "#ef4444",
  I: "#f59e0b",
} as const;

const PARTY_RANK = { D: 0, I: 1, R: 2 } as const;

const ROWS = [12, 16, 20, 24, 28];
const CX = 340;
const CY = 340;
const INNER_R = 110;
const ROW_STEP = 44;
const SEAT_R = 10;
const VIEW_W = 680;
const VIEW_H = 380;

const DEFAULT_TERM = "Trump";
// Display-cased; FTS is case-insensitive so "Fentanyl" matches lowercase
// occurrences. "Supreme Court" works via websearch_to_tsquery as a phrase
// match. Mix of domestic + foreign policy + judicial to give the chamber
// distinct heatmaps when toggled.
const DEFAULT_TERMS = [
  DEFAULT_TERM,
  "Tariffs",
  "Iran",
  "Ukraine",
  "Israel",
  "Medicaid",
  "Supreme Court",
];
const MAX_TERM_LEN = 40;

type Seat = { row: number; idx: number; angle: number; x: number; y: number };

// Rounded to 3 decimals so server and client serialize the same string.
// Without this, Number→string conversion differs between Node and the browser
// at the 14th+ digit, breaking React hydration.
const round = (n: number) => Math.round(n * 1000) / 1000;

const SEATS: Seat[] = (() => {
  const seats: Seat[] = [];
  for (let row = 0; row < ROWS.length; row++) {
    const n = ROWS[row];
    const radius = INNER_R + row * ROW_STEP;
    for (let k = 0; k < n; k++) {
      const angle = ((k + 0.5) * Math.PI) / n;
      const x = round(CX - radius * Math.cos(angle));
      const y = round(CY - radius * Math.sin(angle));
      seats.push({ row, idx: k, angle, x, y });
    }
  }
  return seats.sort((a, b) => a.angle - b.angle);
})();

// Log-compressed intensity. Linear count/max gets crushed when one outlier
// (e.g. Warren at 43 mentions of "Trump") sits far above the median (~5);
// every other senator collapses to the floor opacity and the chamber reads
// as "one bright dot, ninety-nine pale dots". log(count+1)/log(max+1)
// spreads the middle of the distribution into visible bands while still
// reserving full saturation for the leader.
function intensity(count: number, max: number): number {
  if (count <= 0 || max <= 0) return 0;
  return Math.log(count + 1) / Math.log(max + 1);
}

function fillFor(party: "D" | "R" | "I", count: number, max: number) {
  if (count === 0) return { fill: "#f5f5f4", stroke: "#d6d3d1" };
  const t = Math.max(0.25, Math.min(1, intensity(count, max)));
  // Round to 3 decimals so server and client serialize the float identically (avoids hydration mismatch).
  const opacity = Math.round(t * 1000) / 1000;
  return { fill: PARTY_COLOR[party], stroke: PARTY_COLOR[party], opacity };
}

type HoverState = { senator: Senator; x: number; y: number } | null;

type TimeScope = "recent" | "alltime" | "ytd";
type Mode = { scope: TimeScope; term: string | null; loading: boolean };

// Single source of truth for the time-window dropdown. Each option carries
// its own prepositional phrase so the headline reads grammatically when the
// dropdown is the entire trailing fragment ("...in their press releases
// year-to-date.").
const WINDOW_OPTIONS = [
  { key: "7d", label: "in the last 7 days", short: "last 7d", scope: "recent" as TimeScope, days: 7 },
  { key: "30d", label: "in the last 30 days", short: "last 30d", scope: "recent" as TimeScope, days: 30 },
  { key: "90d", label: "in the last 90 days", short: "last 90d", scope: "recent" as TimeScope, days: 90 },
  { key: "ytd", label: "year-to-date", short: "YTD", scope: "ytd" as TimeScope, days: 0 },
  { key: "all", label: "since Jan 2025", short: "since Jan 2025", scope: "alltime" as TimeScope, days: 0 },
] as const;
type WindowKey = (typeof WINDOW_OPTIONS)[number]["key"];
const DEFAULT_WINDOW: WindowKey = "30d";

export function SenateChamber({
  senators,
  days = 30,
}: {
  senators: Senator[];
  days?: number;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const initialTerm = (() => {
    const qParam = searchParams.get("q");
    if (qParam === null) return DEFAULT_TERM;
    const raw = qParam
      .trim()
      .replace(/[^a-zA-Z0-9 \-']/g, "")
      .slice(0, MAX_TERM_LEN);
    return raw || null;
  })();

  const initialWindow: WindowKey = (() => {
    const raw = searchParams.get("window") ?? DEFAULT_WINDOW;
    return (WINDOW_OPTIONS.find((w) => w.key === raw)?.key ?? DEFAULT_WINDOW) as WindowKey;
  })();

  const [hover, setHover] = useState<HoverState>(null);
  const [windowKey, setWindowKey] = useState<WindowKey>(initialWindow);
  const currentWindow = WINDOW_OPTIONS.find((w) => w.key === windowKey)!;
  const [mode, setMode] = useState<Mode>({
    scope: currentWindow.scope,
    term: initialTerm,
    loading: false,
  });
  const [overrideCounts, setOverrideCounts] = useState<Record<string, number> | null>(null);
  const [input, setInput] = useState("");
  const [isTouch, setIsTouch] = useState(false);

  // Keep mode.scope in sync with the active window option.
  useEffect(() => {
    setMode((m) =>
      m.scope === currentWindow.scope ? m : { ...m, scope: currentWindow.scope }
    );
  }, [currentWindow.scope]);

  // Reflect mode → URL. Use `replace` so we don't pollute browser history on
  // every chip click; default state strips params entirely.
  useEffect(() => {
    const params = new URLSearchParams();
    if (windowKey !== DEFAULT_WINDOW) params.set("window", windowKey);
    // Only write q to URL when the user has changed it from the default.
    // mode.term === null means "all press releases" (must be reflected with q=);
    // mode.term === DEFAULT_TERM is the landing state and stays implicit.
    if (mode.term === null) params.set("q", "");
    else if (mode.term !== DEFAULT_TERM) params.set("q", mode.term);
    const qs = params.toString();
    const url = qs ? `${pathname}?${qs}` : pathname;
    if (typeof window !== "undefined") {
      const current = window.location.pathname + window.location.search;
      if (current !== url) router.replace(url, { scroll: false });
    }
  }, [windowKey, mode.term, pathname, router]);

  useEffect(() => {
    setIsTouch(
      typeof window !== "undefined" &&
        ("ontouchstart" in window || navigator.maxTouchPoints > 0)
    );
  }, []);

  // On touch devices: first tap on a seat shows the preview card; second tap
  // on the same seat navigates. Tapping outside closes the card.
  useEffect(() => {
    if (!isTouch || !hover) return;
    const handler = (e: MouseEvent) => {
      const target = e.target as HTMLElement | null;
      if (!target) return;
      if (target.closest('a[href^="/senators/"]')) return;
      if (target.closest('[role="tooltip"]')) return;
      setHover(null);
    };
    window.addEventListener("click", handler);
    return () => window.removeEventListener("click", handler);
  }, [isTouch, hover]);

  // Default state = the server-rendered counts (recent / 30d / no term).
  // Anything else needs a client-side fetch from /api/chamber/counts.
  const isDefault = windowKey === DEFAULT_WINDOW && mode.term === null;

  useEffect(() => {
    if (isDefault) {
      setOverrideCounts(null);
      return;
    }
    let cancelled = false;
    setMode((m) => ({ ...m, loading: true }));
    const params = new URLSearchParams({ scope: currentWindow.scope });
    if (currentWindow.scope === "recent") {
      params.set("days", String(currentWindow.days));
    }
    if (mode.term) params.set("q", mode.term);
    fetch(`/api/chamber/counts?${params.toString()}`)
      .then((r) => r.json())
      .then((data) => {
        if (cancelled) return;
        setOverrideCounts(data.counts ?? {});
        setMode((m) => ({ ...m, loading: false }));
      })
      .catch(() => {
        if (!cancelled) setMode((m) => ({ ...m, loading: false }));
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [windowKey, mode.term]);

  const sanitize = (s: string) =>
    s.trim().replace(/[^a-zA-Z0-9 \-']/g, "").slice(0, MAX_TERM_LEN);

  const setTerm = (raw: string | null) => {
    if (raw === null) {
      setMode((m) => ({ ...m, term: null }));
    } else {
      const t = sanitize(raw);
      if (!t) return;
      setMode((m) => ({ ...m, term: t }));
    }
    setHover(null);
  };

  const senatorsWithCounts = useMemo<Senator[]>(() => {
    if (overrideCounts === null) return senators;
    return senators.map((s) => ({ ...s, count: overrideCounts[s.id] ?? 0 }));
  }, [senators, overrideCounts]);

  const sorted = useMemo(
    () =>
      [...senatorsWithCounts].sort((a, b) => {
        const r = PARTY_RANK[a.party] - PARTY_RANK[b.party];
        if (r !== 0) return r;
        if (a.state !== b.state) return a.state.localeCompare(b.state);
        return a.full_name.localeCompare(b.full_name);
      }),
    [senatorsWithCounts]
  );

  const seats = SEATS;
  const max = sorted.reduce((m, s) => Math.max(m, s.count), 0);
  const active = sorted.filter((s) => s.count > 0).length;
  const top = sorted.reduce<Senator | null>(
    (best, s) => (best === null || s.count > best.count ? s : best),
    null
  );
  const topN = useMemo(
    () =>
      [...senatorsWithCounts]
        .filter((s) => s.count > 0)
        .sort((a, b) => b.count - a.count)
        .slice(0, 10),
    [senatorsWithCounts]
  );

  const counts = { D: 0, I: 0, R: 0 } as Record<"D" | "I" | "R", number>;
  for (const s of sorted) counts[s.party]++;

  const showHover =
    (senator: Senator) => (e: React.SyntheticEvent<SVGCircleElement>) => {
      const rect = e.currentTarget.getBoundingClientRect();
      setHover({
        senator,
        x: rect.left + rect.width / 2,
        y: rect.top,
      });
    };
  const hideHover = () => setHover(null);

  // Touch: tap-to-preview, second-tap-to-open. If a different senator's card
  // is showing or none is, this tap previews instead of navigating.
  const handleSeatClick =
    (senator: Senator) => (e: React.MouseEvent<HTMLAnchorElement>) => {
      if (!isTouch) return;
      const sameOpen = hover && hover.senator.id === senator.id;
      if (sameOpen) return; // second tap → allow navigation
      e.preventDefault();
      const circle = e.currentTarget.querySelector("circle");
      const rect = (circle ?? e.currentTarget).getBoundingClientRect();
      setHover({
        senator,
        x: rect.left + rect.width / 2,
        y: rect.top,
      });
    };

  const isTerm = mode.term !== null;
  const isLoading = mode.loading;
  // "last 30d" / "YTD" / "since Jan 2025" — short label used in aria text and
  // the Top 10 subtitle.
  const scopePhrase = currentWindow.short;

  // Pill-styled dropdown so it reads as obviously clickable rather than
  // "underlined word in a sentence." Background fill, border, chevron, and
  // hover state all telegraph "this is a control."
  const WindowDropdown = (
    <span className="relative inline-flex items-center align-baseline">
      <select
        value={windowKey}
        onChange={(e) => setWindowKey(e.target.value as WindowKey)}
        aria-label="Time window"
        className="appearance-none cursor-pointer rounded-full border border-neutral-400 bg-neutral-100 hover:bg-neutral-200 hover:border-neutral-900 focus:outline-none focus-visible:border-neutral-900 focus-visible:ring-2 focus-visible:ring-neutral-900/20 transition-colors font-semibold text-neutral-900 pl-2.5 pr-8 py-0 text-[0.95em] leading-tight"
      >
        {WINDOW_OPTIONS.map((w) => (
          <option key={w.key} value={w.key}>{w.label}</option>
        ))}
      </select>
      <span
        aria-hidden="true"
        className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 text-neutral-900 text-lg leading-none font-bold"
      >
        ▾
      </span>
    </span>
  );

  return (
    <div className="relative">
      {/* Search term selector */}
      <div className="flex flex-wrap items-center gap-2 mb-3">
        <span className="hidden sm:inline-block text-[10px] uppercase tracking-wider text-neutral-500 mr-1 w-32 sm:w-36">
          Search term:
        </span>
        <button
          type="button"
          onClick={() => setTerm(null)}
          className={`text-xs rounded-full border px-2.5 py-0.5 transition-colors ${
            mode.term === null
              ? "border-neutral-900 bg-neutral-900 text-white"
              : "border-neutral-300 text-neutral-600 hover:border-neutral-500"
          }`}
        >
          None
        </button>
        {DEFAULT_TERMS.map((t) => {
          const selected =
            mode.term !== null && mode.term.toLowerCase() === t.toLowerCase();
          return (
            <button
              key={t}
              type="button"
              onClick={() => setTerm(t)}
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
            setTerm(input);
            setInput("");
          }}
          className="inline-flex"
        >
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Custom term…"
            maxLength={MAX_TERM_LEN}
            className="rounded-full border border-dashed border-neutral-300 bg-white px-2.5 py-0.5 text-xs text-neutral-700 placeholder:text-neutral-400 focus:outline-none focus:border-neutral-500 w-32"
          />
        </form>
      </div>
      <p className="text-[11px] text-neutral-500 mb-3 -mt-1">
        Searches the full text of every release (title + body), with stemming
        — e.g. &ldquo;Iran&rdquo; matches &ldquo;Iranian&rdquo;.
      </p>

      {/* Headline — "in the last [N days ▾]" is an inline dropdown. The
          phrasing names the source ("press releases") so a screenshot of the
          chamber alone reads as a complete claim. */}
      {isTerm ? (
        <p className="text-base text-neutral-700 mb-1">
          <span className="font-semibold text-neutral-900">{active}</span> of 100
          senators mentioned{" "}
          <span className="font-semibold text-neutral-900">
            &ldquo;{mode.term}&rdquo;
          </span>{" "}
          in their press releases {WindowDropdown}
          {top && top.count > 0 && (
            <>
              {" "}
              Most:{" "}
              <Link
                href={`/senators/${top.id}`}
                className="font-medium text-neutral-900 underline decoration-neutral-300 underline-offset-2 hover:decoration-neutral-900"
              >
                {familyName(top.full_name)} ({top.party}-{top.state})
              </Link>{" "}
              with {top.count}.
            </>
          )}
        </p>
      ) : (
        <p className="text-base text-neutral-700 mb-1">
          <span className="font-semibold text-neutral-900">{active}</span> of 100
          senators issued at least one press release {WindowDropdown}
          {top && top.count > 0 && (
            <>
              {" "}
              Most active:{" "}
              <Link
                href={`/senators/${top.id}`}
                className="font-medium text-neutral-900 underline decoration-neutral-300 underline-offset-2 hover:decoration-neutral-900"
              >
                {familyName(top.full_name)} ({top.party}-{top.state})
              </Link>{" "}
              with {top.count}.
            </>
          )}
        </p>
      )}
      <p className="text-[11px] text-neutral-500 mb-3">
        <span className="hidden sm:inline">Hover a seat for details, click to open.</span>
        <span className="sm:hidden">Tap a seat for details.</span>
      </p>

      <div>
        <svg
          role="img"
          aria-label={
            isTerm
              ? `Senate chamber colored by mentions of "${mode.term}" (${scopePhrase})`
              : `Senate chamber colored by press release activity (${scopePhrase})`
          }
          viewBox={`0 35 ${VIEW_W} ${VIEW_H - 30}`}
          preserveAspectRatio="xMidYMid meet"
          className={`block w-full h-auto max-h-[420px] transition-opacity ${isLoading ? "opacity-60" : "opacity-100"}`}
        >
          <title>
            {isTerm
              ? `Senate chamber — mentions of "${mode.term}", ${scopePhrase}`
              : `Senate chamber — press release activity, ${scopePhrase}`}
          </title>

          <path
            d={`M ${CX - (INNER_R - 24)} ${CY} A ${INNER_R - 24} ${
              INNER_R - 24
            } 0 0 1 ${CX + (INNER_R - 24)} ${CY} L ${CX + (INNER_R - 24)} ${
              CY + 1
            } L ${CX - (INNER_R - 24)} ${CY + 1} Z`}
            fill="#fafaf9"
            stroke="#e7e5e4"
          />
          <line
            x1={CX - (INNER_R + ROW_STEP * (ROWS.length - 1) + SEAT_R + 8)}
            x2={CX + (INNER_R + ROW_STEP * (ROWS.length - 1) + SEAT_R + 8)}
            y1={CY + 1}
            y2={CY + 1}
            stroke="#e7e5e4"
          />

          {seats.map((seat, i) => {
            const senator = sorted[i];
            if (!senator) return null;
            const { fill, stroke, opacity } = fillFor(
              senator.party,
              senator.count,
              max
            );
            return (
              <a
                key={senator.id}
                href={`/senators/${senator.id}`}
                onClick={handleSeatClick(senator)}
                aria-label={`${senator.full_name} (${senator.party}-${senator.state}), ${senator.count} ${isTerm ? `mentions of ${mode.term}` : "releases"}${" "}${scopePhrase}`}
                className="outline-none focus-visible:[outline:2px_solid_#0a0a0a] focus-visible:[outline-offset:2px]"
              >
                <circle
                  cx={seat.x}
                  cy={seat.y}
                  r={SEAT_R}
                  fill={fill}
                  fillOpacity={opacity ?? 1}
                  stroke={stroke}
                  strokeWidth={1}
                  onMouseEnter={showHover(senator)}
                  onMouseLeave={hideHover}
                  onFocus={showHover(senator)}
                  onBlur={hideHover}
                  className="motion-safe:transition-[r,fill-opacity] motion-safe:duration-150 hover:[r:11] hover:fill-opacity-100"
                />
              </a>
            );
          })}

          {/* Source attribution baked into the SVG so it survives a
              screenshot crop. r/dataisbeautiful mods remove charts where
              source isn't visible on the image. */}
          <text
            x={VIEW_W - 8}
            y={VIEW_H - 12}
            textAnchor="end"
            fontSize="11"
            fill="#a3a3a3"
            fontFamily="system-ui, -apple-system, sans-serif"
          >
            {isTerm
              ? `Mentions of "${mode.term}" · ${scopePhrase} · n=${max}`
              : `Press releases · ${scopePhrase} · n=${max}`}
          </text>
          <text
            x={8}
            y={VIEW_H - 12}
            textAnchor="start"
            fontSize="11"
            fill="#a3a3a3"
            fontFamily="system-ui, -apple-system, sans-serif"
          >
            Capitol Releases · capitolreleases.com
          </text>
        </svg>
      </div>

      {hover && <HoverCard hover={hover} mode={mode} scopeLabel={scopePhrase} />}

      <div className="mt-3 flex flex-wrap items-center justify-between gap-x-6 gap-y-2 text-xs text-neutral-500">
        <div className="flex items-center gap-x-4 gap-y-1 flex-wrap">
          <span className="flex items-center gap-1.5">
            <span
              className="inline-block h-2.5 w-2.5 rounded-full"
              style={{ background: PARTY_COLOR.D }}
            />
            Democrats <span className="tabular-nums">{counts.D}</span>
          </span>
          <span className="flex items-center gap-1.5">
            <span
              className="inline-block h-2.5 w-2.5 rounded-full"
              style={{ background: PARTY_COLOR.I }}
            />
            Independents <span className="tabular-nums">{counts.I}</span>
          </span>
          <span className="flex items-center gap-1.5">
            <span
              className="inline-block h-2.5 w-2.5 rounded-full"
              style={{ background: PARTY_COLOR.R }}
            />
            Republicans <span className="tabular-nums">{counts.R}</span>
          </span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-neutral-400">Less</span>
          <span className="flex items-center gap-0.5">
            {[0.25, 0.45, 0.65, 0.85, 1].map((o) => (
              <span
                key={`d-${o}`}
                className="inline-block h-2.5 w-3 rounded-sm"
                style={{ background: PARTY_COLOR.D, opacity: o }}
              />
            ))}
          </span>
          <span className="flex items-center gap-0.5">
            {[0.25, 0.45, 0.65, 0.85, 1].map((o) => (
              <span
                key={`r-${o}`}
                className="inline-block h-2.5 w-3 rounded-sm"
                style={{ background: PARTY_COLOR.R, opacity: o }}
              />
            ))}
          </span>
          <span className="text-neutral-400">
            More {max > 0 && `(max ${max})`}
          </span>
        </div>
      </div>

      {topN.length > 0 && (
        <div className="mt-6 pt-5 border-t border-neutral-200">
          <h3 className="text-[10px] uppercase tracking-wider text-neutral-500 mb-3">
            {isTerm
              ? `Top 10 by mentions of "${mode.term}"`
              : "Top 10 by release volume"}{" "}
            <span className="text-neutral-400">
              ({scopePhrase})
            </span>
          </h3>
          <ol className="grid grid-cols-1 sm:grid-cols-2 gap-x-6">
            {topN.map((s, i) => {
              const photo = getSenatorPhotoUrl(s.full_name, s.id);
              const ringColor =
                s.party === "D"
                  ? "ring-blue-500"
                  : s.party === "R"
                    ? "ring-red-500"
                    : "ring-amber-500";
              return (
                <li
                  key={s.id}
                  className="flex items-center gap-2.5 py-1.5 border-b border-neutral-100 last:border-b-0"
                >
                  <span className="w-5 text-right text-[11px] tabular-nums text-neutral-400 font-mono">
                    {i + 1}
                  </span>
                  {photo ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img
                      src={photo}
                      alt={`${s.full_name} (${s.party}-${s.state})`}
                      width={24}
                      height={24}
                      className={`h-6 w-6 rounded-full object-cover ring-1 ${ringColor}`}
                    />
                  ) : (
                    <span
                      className={`flex h-6 w-6 items-center justify-center rounded-full bg-neutral-100 text-[9px] font-medium text-neutral-500 ring-1 ${ringColor}`}
                    >
                      {getInitials(s.full_name)}
                    </span>
                  )}
                  <Link
                    href={`/senators/${s.id}`}
                    className="text-sm text-neutral-800 hover:text-neutral-900 hover:underline truncate flex-1 min-w-0"
                  >
                    {familyName(s.full_name)}{" "}
                    <span className="text-xs text-neutral-500">
                      ({s.party}-{s.state})
                    </span>
                  </Link>
                  <span className="text-sm font-mono tabular-nums text-neutral-900">
                    {s.count.toLocaleString()}
                  </span>
                </li>
              );
            })}
          </ol>
        </div>
      )}
    </div>
  );
}

function HoverCard({
  hover,
  mode,
  scopeLabel,
}: {
  hover: NonNullable<HoverState>;
  mode: Mode;
  scopeLabel: string;
}) {
  const { senator, x, y } = hover;
  const photo = getSenatorPhotoUrl(senator.full_name, senator.id);
  const partyName =
    senator.party === "D"
      ? "Democrat"
      : senator.party === "R"
        ? "Republican"
        : "Independent";

  const CARD_W = 240;
  const CARD_H = 96;
  const GAP = 12;

  const left = Math.max(8, Math.min(window.innerWidth - CARD_W - 8, x - CARD_W / 2));
  const top = Math.max(8, y - CARD_H - GAP);

  const isTerm = mode.term !== null;

  return (
    <div
      role="tooltip"
      aria-hidden="true"
      style={{
        position: "fixed",
        left,
        top,
        width: CARD_W,
        zIndex: 50,
        pointerEvents: "none",
      }}
      className="rounded-md border border-neutral-200 bg-white shadow-lg p-2.5 flex items-center gap-3"
    >
      <div className="shrink-0">
        {photo ? (
          <Image
            src={photo}
            alt={`${senator.full_name} (${senator.party}-${senator.state})`}
            width={56}
            height={70}
            className="rounded-sm object-cover bg-neutral-100"
          />
        ) : (
          <div className="w-[56px] h-[70px] rounded-sm bg-neutral-100 flex items-center justify-center text-sm font-medium text-neutral-500">
            {getInitials(senator.full_name)}
          </div>
        )}
      </div>
      <div className="min-w-0 flex-1">
        <div className="text-sm font-semibold text-neutral-900 truncate">
          {senator.full_name}
        </div>
        <div className="text-xs text-neutral-500">
          {partyName} · {senator.state}
        </div>
        <div className="text-xs text-neutral-700 mt-1 tabular-nums">
          {isTerm
            ? senator.count === 0
              ? `0 mentions of "${mode.term}" · ${scopeLabel}`
              : `${senator.count} mention${senator.count === 1 ? "" : "s"} of "${mode.term}" · ${scopeLabel}`
            : senator.count === 0
              ? `No releases · ${scopeLabel}`
              : `${senator.count} release${senator.count === 1 ? "" : "s"} · ${scopeLabel}`}
        </div>
      </div>
    </div>
  );
}

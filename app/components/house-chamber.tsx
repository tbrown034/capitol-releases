"use client";

import Link from "next/link";
import Image from "next/image";
import { Suspense, useEffect, useMemo, useReducer, useRef, useState } from "react";
import { usePathname, useSearchParams } from "next/navigation";
import { familyName } from "../lib/names";
import { getMemberPhotoUrl, getInitials } from "../lib/photos";

type Member = {
  id: string;
  full_name: string;
  party: "D" | "R" | "I";
  state: string;
  count: number;
  bioguide_id?: string | null;
};

const PARTY_COLOR = {
  D: "#3b82f6",
  R: "#ef4444",
  I: "#f59e0b",
} as const;

const PARTY_RANK = { D: 0, I: 1, R: 2 } as const;

// 5-row semicircle sized to seat all 437 House members. Rows sum to 437.
const ROWS = [55, 71, 87, 103, 121];
const TOTAL_SEATS = ROWS.reduce((a, b) => a + b, 0);
const CX = 460;
const CY = 460;
const INNER_R = 130;
const ROW_STEP = 50;
const SEAT_R = 5.5;
const VIEW_W = 920;
const VIEW_H = 500;

const DEFAULT_TERM = "Trump";
const DEFAULT_TERMS = [
  DEFAULT_TERM,
  "Tariffs",
  "Iran",
  "Gas prices",
  "Ukraine",
  "Israel",
  "Medicaid",
  "Supreme Court",
];
const MAX_TERM_LEN = 40;

function sanitizeTerm(s: string) {
  return s.trim().replace(/[^a-zA-Z0-9 \-']/g, "").slice(0, MAX_TERM_LEN);
}

type Seat = { row: number; idx: number; angle: number; x: number; y: number };

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

function intensity(count: number, max: number): number {
  if (count <= 0 || max <= 0) return 0;
  return Math.log(count + 1) / Math.log(max + 1);
}

function fillFor(party: "D" | "R" | "I", count: number, max: number) {
  if (count === 0) return { fill: "#f5f5f4", stroke: "#d6d3d1" };
  const t = Math.max(0.25, Math.min(1, intensity(count, max)));
  const opacity = Math.round(t * 1000) / 1000;
  return { fill: PARTY_COLOR[party], stroke: PARTY_COLOR[party], opacity };
}

type HoverState = { member: Member; x: number; y: number } | null;

type TimeScope = "recent" | "alltime" | "ytd";
type Mode = { term: string | null; loading: boolean };
function modeReducer(mode: Mode, patch: Partial<Mode>): Mode {
  return { ...mode, ...patch };
}

const WINDOW_OPTIONS = [
  { key: "7d", label: "in the last 7 days", short: "last 7d", scope: "recent" as TimeScope, days: 7 },
  { key: "30d", label: "in the last 30 days", short: "last 30d", scope: "recent" as TimeScope, days: 30 },
  { key: "90d", label: "in the last 90 days", short: "last 90d", scope: "recent" as TimeScope, days: 90 },
  { key: "ytd", label: "year-to-date", short: "YTD", scope: "ytd" as TimeScope, days: 0 },
  { key: "all", label: "since Jan 2025", short: "since Jan 2025", scope: "alltime" as TimeScope, days: 0 },
] as const;
type WindowKey = (typeof WINDOW_OPTIONS)[number]["key"];
const DEFAULT_WINDOW: WindowKey = "30d";

export function HouseChamber(props: { members: Member[] }) {
  return (
    <Suspense fallback={null}>
      <HouseChamberInner {...props} />
    </Suspense>
  );
}

function HouseChamberInner({ members }: { members: Member[] }) {
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const initialTerm = (() => {
    const qParam = searchParams.get("q");
    if (qParam === null) return DEFAULT_TERM;
    const raw = sanitizeTerm(qParam);
    return raw || null;
  })();

  const initialWindow: WindowKey = (() => {
    const raw = searchParams.get("window") ?? DEFAULT_WINDOW;
    return (WINDOW_OPTIONS.find((w) => w.key === raw)?.key ?? DEFAULT_WINDOW) as WindowKey;
  })();

  const [hover, setHover] = useState<HoverState>(null);
  const [windowKey, setWindowKey] = useState<WindowKey>(initialWindow);
  const currentWindow = WINDOW_OPTIONS.find((w) => w.key === windowKey)!;
  const [mode, setMode] = useReducer(modeReducer, {
    term: initialTerm,
    loading: false,
  });
  const [overrideCounts, setOverrideCounts] = useState<Record<string, number> | null>(null);
  const [input, setInput] = useState("");
  const isTouch =
    typeof window !== "undefined" &&
    ("ontouchstart" in window || navigator.maxTouchPoints > 0);
  // Tracks which member is currently "previewed" on touch. Ref (not state)
  // so the click handler reads it synchronously and isn't fooled by a stale
  // hover state that was just set by a synthetic mouseenter in the same tap.
  const previewedIdRef = useRef<string | null>(null);

  const syncUrl = (nextWindowKey: WindowKey, nextTerm: string | null) => {
    const params = new URLSearchParams();
    params.set("chamber", "house");
    if (nextWindowKey !== DEFAULT_WINDOW) params.set("window", nextWindowKey);
    if (nextTerm === null) params.set("q", "");
    else if (nextTerm !== DEFAULT_TERM) params.set("q", nextTerm);
    const qs = params.toString();
    const url = qs ? `${pathname}?${qs}` : pathname;
    if (typeof window !== "undefined") {
      const current = window.location.pathname + window.location.search;
      if (current !== url) window.history.replaceState(null, "", url);
    }
  };

  useEffect(() => {
    if (!isTouch || !hover) return;
    const handler = (e: MouseEvent) => {
      const target = e.target as HTMLElement | null;
      if (!target) return;
      if (target.closest('a[href^="/house/"]')) return;
      if (target.closest('[role="tooltip"]')) return;
      previewedIdRef.current = null;
      setHover(null);
    };
    window.addEventListener("click", handler);
    return () => window.removeEventListener("click", handler);
  }, [isTouch, hover]);

  const refreshCounts = async (nextWindowKey: WindowKey, nextTerm: string | null) => {
    const nextWindow = WINDOW_OPTIONS.find((w) => w.key === nextWindowKey)!;
    if (nextWindowKey === DEFAULT_WINDOW && nextTerm === null) {
      setOverrideCounts(null);
      return;
    }
    setMode({ loading: true });
    const params = new URLSearchParams({ scope: nextWindow.scope, chamber: "house" });
    if (nextWindow.scope === "recent") {
      params.set("days", String(nextWindow.days));
    }
    if (nextTerm) params.set("q", nextTerm);
    try {
      const response = await fetch(`/api/chamber/counts?${params.toString()}`);
      const data = await response.json();
      setOverrideCounts(data.counts ?? {});
    } finally {
      setMode({ loading: false });
    }
  };

  const setTerm = (raw: string | null) => {
    let nextTerm: string | null;
    if (raw === null) {
      nextTerm = null;
    } else {
      const t = sanitizeTerm(raw);
      if (!t) return;
      nextTerm = t;
    }
    setMode({ term: nextTerm });
    syncUrl(windowKey, nextTerm);
    void refreshCounts(windowKey, nextTerm);
    setHover(null);
  };

  const membersWithCounts = useMemo<Member[]>(() => {
    if (overrideCounts === null) return members;
    return members.map((s) => ({ ...s, count: overrideCounts[s.id] ?? 0 }));
  }, [members, overrideCounts]);

  const sorted = useMemo(
    () =>
      membersWithCounts.toSorted((a, b) => {
        const r = PARTY_RANK[a.party] - PARTY_RANK[b.party];
        if (r !== 0) return r;
        if (a.state !== b.state) return a.state.localeCompare(b.state);
        return a.full_name.localeCompare(b.full_name);
      }),
    [membersWithCounts]
  );

  const seated = useMemo(() => sorted.slice(0, TOTAL_SEATS), [sorted]);

  const seats = SEATS;
  const max = seated.reduce((m, s) => Math.max(m, s.count), 0);
  const totalMembers = members.length;
  const active = seated.filter((s) => s.count > 0).length;
  const top = seated.reduce<Member | null>(
    (best, s) => (best === null || s.count > best.count ? s : best),
    null
  );
  const topN = useMemo(
    () =>
      [...membersWithCounts]
        .filter((s) => s.count > 0)
        .sort((a, b) => b.count - a.count)
        .slice(0, 10),
    [membersWithCounts]
  );

  const counts = { D: 0, I: 0, R: 0 } as Record<"D" | "I" | "R", number>;
  for (const s of sorted) counts[s.party]++;

  const showHover =
    (member: Member) => (e: React.SyntheticEvent<SVGCircleElement>) => {
      // Touch devices fire synthetic mouseenter on tap. If we set the hover
      // card from that, the click handler can't tell first-tap from second-tap
      // and the link navigates immediately. On touch, the click handler owns
      // the preview.
      if (isTouch) return;
      const rect = e.currentTarget.getBoundingClientRect();
      setHover({
        member,
        x: rect.left + rect.width / 2,
        y: rect.top,
      });
    };
  const hideHover = () => {
    if (isTouch) return;
    setHover(null);
  };

  const handleSeatClick =
    (member: Member) => (e: React.MouseEvent<HTMLAnchorElement>) => {
      if (!isTouch) return;
      // Second tap on the same seat → clear the ref and allow the <a> to navigate.
      if (previewedIdRef.current === member.id) {
        previewedIdRef.current = null;
        return;
      }
      e.preventDefault();
      previewedIdRef.current = member.id;
      const circle = e.currentTarget.querySelector("circle");
      const rect = (circle ?? e.currentTarget).getBoundingClientRect();
      setHover({
        member,
        x: rect.left + rect.width / 2,
        y: rect.top,
      });
    };

  const isTerm = mode.term !== null;
  const isLoading = mode.loading;
  const scopePhrase = currentWindow.short;

  const WindowDropdown = (
    <span className="relative inline-flex items-center align-baseline">
      <select
        value={windowKey}
        onChange={(e) => {
          const nextWindowKey = e.target.value as WindowKey;
          setWindowKey(nextWindowKey);
          syncUrl(nextWindowKey, mode.term);
          void refreshCounts(nextWindowKey, mode.term);
        }}
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
        <div className="inline-flex gap-1">
          <input
            aria-label="Custom House search term"
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                setTerm(input);
                setInput("");
              }
            }}
            placeholder="Custom term…"
            maxLength={MAX_TERM_LEN}
            className="rounded-full border border-dashed border-neutral-300 bg-white px-2.5 py-0.5 text-xs text-neutral-700 placeholder:text-neutral-400 focus:outline-none focus:border-neutral-500 w-32"
          />
          <button
            type="button"
            onClick={() => {
              setTerm(input);
              setInput("");
            }}
            className="rounded-full border border-neutral-300 px-2.5 py-0.5 text-xs text-neutral-600 hover:border-neutral-500"
          >
            Search term
          </button>
        </div>
      </div>
      <p className="text-[11px] text-neutral-500 mb-3 -mt-1">
        Searches the full text of every release (title + body), with stemming
       , e.g. &ldquo;Iran&rdquo; matches &ldquo;Iranian&rdquo;.
      </p>

      {isTerm ? (
        <p className="text-base text-neutral-700 mb-1">
          <span className="font-semibold text-neutral-900">{active}</span> of {totalMembers} House
          members mentioned{" "}
          <span className="font-semibold text-neutral-900">
            &ldquo;{mode.term}&rdquo;
          </span>{" "}
          in their press releases {WindowDropdown}
          {top && top.count > 0 && (
            <>
              {" "}
              Most:{" "}
              <Link
                href={`/house/${top.id}`}
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
          <span className="font-semibold text-neutral-900">{active}</span> of {totalMembers} House
          members issued at least one press release {WindowDropdown}
          {top && top.count > 0 && (
            <>
              {" "}
              Most active:{" "}
              <Link
                href={`/house/${top.id}`}
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
              ? `House chamber colored by mentions of "${mode.term}" (${scopePhrase})`
              : `House chamber colored by press release activity (${scopePhrase})`
          }
          viewBox={`0 35 ${VIEW_W} ${VIEW_H - 30}`}
          preserveAspectRatio="xMidYMid meet"
          className={`block w-full h-auto max-h-[560px] transition-opacity ${isLoading ? "opacity-60" : "opacity-100"}`}
        >
          <title>
            {isTerm
              ? `House chamber, mentions of "${mode.term}", ${scopePhrase}`
              : `House chamber, press release activity, ${scopePhrase}`}
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
            const member = seated[i];
            if (!member) {
              return (
                <circle
                  key={i}
                  cx={seat.x}
                  cy={seat.y}
                  r={SEAT_R}
                  fill="#f5f5f4"
                  stroke="#e7e5e4"
                  strokeWidth={0.5}
                />
              );
            }
            const { fill, stroke, opacity } = fillFor(
              member.party,
              member.count,
              max
            );
            return (
              <a
                key={member.id}
                href={`/house/${member.id}`}
                onClick={handleSeatClick(member)}
                aria-label={`${member.full_name} (${member.party}-${member.state}), ${member.count} ${isTerm ? `mentions of ${mode.term}` : "releases"}${" "}${scopePhrase}`}
                className="outline-none focus-visible:[outline:2px_solid_#0a0a0a] focus-visible:[outline-offset:2px]"
              >
                <circle
                  cx={seat.x}
                  cy={seat.y}
                  r={SEAT_R}
                  fill={fill}
                  fillOpacity={opacity ?? 1}
                  stroke={stroke}
                  strokeWidth={0.5}
                  onMouseEnter={showHover(member)}
                  onMouseLeave={hideHover}
                  onFocus={showHover(member)}
                  onBlur={hideHover}
                  className="motion-safe:transition-[r,fill-opacity] motion-safe:duration-150 hover:[r:8] hover:fill-opacity-100"
                />
              </a>
            );
          })}

          {/* Right-side metric caption removed, redundant with headline. */}
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
              className="inline-block size-2.5 rounded-full"
              style={{ background: PARTY_COLOR.D }}
            />
            Democrats <span className="tabular-nums">{counts.D}</span>
          </span>
          {counts.I > 0 && (
            <span className="flex items-center gap-1.5">
              <span
                className="inline-block size-2.5 rounded-full"
                style={{ background: PARTY_COLOR.I }}
              />
              Independents <span className="tabular-nums">{counts.I}</span>
            </span>
          )}
          <span className="flex items-center gap-1.5">
            <span
              className="inline-block size-2.5 rounded-full"
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
              const photo = getMemberPhotoUrl(s.full_name, s.id, "house", s.bioguide_id ?? null);
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
                    <Image
                      src={photo}
                      alt={`${s.full_name} (${s.party}-${s.state})`}
                      width={24}
                      height={24}
                      className={`size-6 rounded-full object-cover ring-1 ${ringColor}`}
                      unoptimized
                    />
                  ) : (
                    <span
                      className={`flex size-6 items-center justify-center rounded-full bg-neutral-100 text-[9px] font-medium text-neutral-500 ring-1 ${ringColor}`}
                    >
                      {getInitials(s.full_name)}
                    </span>
                  )}
                  <Link
                    href={`/house/${s.id}`}
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
  const { member, x, y } = hover;
  const photo = getMemberPhotoUrl(member.full_name, member.id, "house", member.bioguide_id ?? null);
  const partyName =
    member.party === "D"
      ? "Democrat"
      : member.party === "R"
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
            alt={`${member.full_name} (${member.party}-${member.state})`}
            width={56}
            height={70}
            className="rounded-sm object-cover bg-neutral-100"
          />
        ) : (
          <div className="w-[56px] h-[70px] rounded-sm bg-neutral-100 flex items-center justify-center text-sm font-medium text-neutral-500">
            {getInitials(member.full_name)}
          </div>
        )}
      </div>
      <div className="min-w-0 flex-1">
        <div className="text-sm font-semibold text-neutral-900 truncate">
          {member.full_name}
        </div>
        <div className="text-xs text-neutral-500">
          {partyName} · {member.state}
        </div>
        <div className="text-xs text-neutral-700 mt-1 tabular-nums">
          {isTerm
            ? member.count === 0
              ? `0 mentions of "${mode.term}" · ${scopeLabel}`
              : `${member.count} mention${member.count === 1 ? "" : "s"} of "${mode.term}" · ${scopeLabel}`
            : member.count === 0
              ? `No releases · ${scopeLabel}`
              : `${member.count} release${member.count === 1 ? "" : "s"} · ${scopeLabel}`}
        </div>
      </div>
    </div>
  );
}

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

const DEFAULT_TERMS = ["Trump", "Iran", "Ukraine", "fentanyl", "Medicaid"];
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
  return { fill: PARTY_COLOR[party], stroke: PARTY_COLOR[party], opacity: t };
}

type HoverState = { senator: Senator; x: number; y: number } | null;

type TimeScope = "recent" | "alltime";
type Mode = { scope: TimeScope; term: string | null; loading: boolean };

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

  // Initialize from URL so views are shareable (?scope=alltime&q=Trump).
  // Default landing state is `q=Trump` -- the unscoped "press release count"
  // view is functionally just a senator productivity ranking; defaulting to
  // Trump frames the chamber as a topic-attention map, which is what the
  // viz is for.
  const initialScope: TimeScope =
    searchParams.get("scope") === "alltime" ? "alltime" : "recent";
  const initialTerm = (() => {
    const qParam = searchParams.get("q");
    if (qParam === null) return "Trump";
    const raw = qParam
      .trim()
      .replace(/[^a-zA-Z0-9 \-']/g, "")
      .slice(0, MAX_TERM_LEN);
    return raw || null;
  })();

  const [hover, setHover] = useState<HoverState>(null);
  const [mode, setMode] = useState<Mode>({
    scope: initialScope,
    term: initialTerm,
    loading: false,
  });
  const [overrideCounts, setOverrideCounts] = useState<Record<string, number> | null>(null);
  const [input, setInput] = useState("");
  const [isTouch, setIsTouch] = useState(false);

  // Reflect mode → URL. Use `replace` so we don't pollute browser history on
  // every chip click; default state strips params entirely.
  useEffect(() => {
    const params = new URLSearchParams();
    if (mode.scope !== "recent") params.set("scope", mode.scope);
    if (mode.term) params.set("q", mode.term);
    const qs = params.toString();
    const url = qs ? `${pathname}?${qs}` : pathname;
    if (typeof window !== "undefined") {
      const current = window.location.pathname + window.location.search;
      if (current !== url) router.replace(url, { scroll: false });
    }
  }, [mode.scope, mode.term, pathname, router]);

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

  const isDefault = mode.scope === "recent" && mode.term === null;

  useEffect(() => {
    if (isDefault) {
      setOverrideCounts(null);
      return;
    }
    let cancelled = false;
    setMode((m) => ({ ...m, loading: true }));
    const params = new URLSearchParams({ scope: mode.scope });
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
  }, [mode.scope, mode.term]);

  const sanitize = (s: string) =>
    s.trim().replace(/[^a-zA-Z0-9 \-']/g, "").slice(0, MAX_TERM_LEN);

  const setScope = (scope: TimeScope) => {
    setMode((m) => ({ ...m, scope }));
    setHover(null);
  };
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
  const scopePhrase =
    mode.scope === "recent" ? `the last ${days} days` : "Jan 2025";

  return (
    <div className="relative">
      {/* Time scope selector */}
      <div className="flex flex-wrap items-center gap-2 mb-2">
        <span className="hidden sm:inline-block text-[10px] uppercase tracking-wider text-neutral-500 mr-1 w-32 sm:w-36">
          Time scope:
        </span>
        <button
          type="button"
          onClick={() => setScope("recent")}
          className={`text-xs rounded-full border px-2.5 py-0.5 transition-colors ${
            mode.scope === "recent"
              ? "border-neutral-900 bg-neutral-900 text-white"
              : "border-neutral-300 text-neutral-600 hover:border-neutral-500"
          }`}
        >
          Recent ({days}d)
        </button>
        <button
          type="button"
          onClick={() => setScope("alltime")}
          className={`text-xs rounded-full border px-2.5 py-0.5 transition-colors ${
            mode.scope === "alltime"
              ? "border-neutral-900 bg-neutral-900 text-white"
              : "border-neutral-300 text-neutral-600 hover:border-neutral-500"
          }`}
        >
          Since Jan 1, 2025
        </button>
      </div>

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
      <p className="text-[11px] text-neutral-400 mb-3 -mt-1">
        Searches the full text of every release (title + body), with stemming
        — e.g. &ldquo;Iran&rdquo; matches &ldquo;Iranian&rdquo;.
      </p>

      {/* Headline */}
      {isTerm ? (
        <p className="text-base text-neutral-700 mb-1">
          <span className="font-semibold text-neutral-900">{active}</span> of 100
          senators have mentioned{" "}
          <span className="font-semibold text-neutral-900">
            &ldquo;{mode.term}&rdquo;
          </span>{" "}
          {mode.scope === "recent" ? `in ${scopePhrase}` : `since ${scopePhrase}`}.
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
          senators issued at least one release{" "}
          {mode.scope === "recent" ? `in ${scopePhrase}` : `since ${scopePhrase}`}.
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
      <p className="text-xs text-neutral-500 mb-4">
        Each seat = one senator.{" "}
        {isTerm
          ? `Color intensity = releases mentioning "${mode.term}" (title or body, with stemming) ${mode.scope === "recent" ? `in ${scopePhrase}` : `since ${scopePhrase}`}.`
          : `Color intensity = press releases ${mode.scope === "recent" ? `in ${scopePhrase}` : `since ${scopePhrase}`}.`}{" "}
        Democrats left, Independents center, Republicans right.{" "}
        <span className="text-neutral-400">
          <span className="hidden sm:inline">
            Hover a seat for the senator&rsquo;s name and count; click to open
            their page.
          </span>
          <span className="sm:hidden">
            Tap a seat to preview. Tap again to open the senator&rsquo;s
            page. Tap elsewhere to close.
          </span>
        </span>
      </p>

      <div>
        <svg
          role="img"
          aria-label={
            isTerm
              ? `Senate chamber colored by mentions of "${mode.term}" (${mode.scope === "recent" ? `last ${days} days` : "since Jan 2025"})`
              : `Senate chamber colored by press release activity (${mode.scope === "recent" ? `last ${days} days` : "since Jan 2025"})`
          }
          viewBox={`0 0 ${VIEW_W} ${VIEW_H}`}
          preserveAspectRatio="xMidYMid meet"
          className={`block w-full h-auto max-h-[460px] transition-opacity ${isLoading ? "opacity-60" : "opacity-100"}`}
        >
          <title>
            {isTerm
              ? `Senate chamber — mentions of "${mode.term}", ${mode.scope === "recent" ? `last ${days} days` : "since Jan 2025"}`
              : `Senate chamber — press release activity, ${mode.scope === "recent" ? `last ${days} days` : "since Jan 2025"}`}
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
                aria-label={`${senator.full_name} (${senator.party}-${senator.state}), ${senator.count} ${isTerm ? `mentions of ${mode.term}` : "releases"}${mode.scope === "recent" ? ` in last ${days} days` : " since Jan 2025"}`}
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
        </svg>
      </div>

      {hover && <HoverCard hover={hover} mode={mode} days={days} />}

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
              ({mode.scope === "recent" ? `last ${days}d` : "since Jan 2025"})
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
  days,
}: {
  hover: NonNullable<HoverState>;
  mode: Mode;
  days: number;
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
  const scopeLabel =
    mode.scope === "recent" ? `${days}d` : "since Jan 2025";

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

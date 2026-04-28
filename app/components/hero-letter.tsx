"use client";

import { useEffect, useState } from "react";
import { getSenatorPhotoUrl, getInitials } from "../lib/photos";
import { normalizeTitle } from "../lib/titles";
import { TypeIcon } from "./type-icon";
import { formatReleaseDate, formatTimestamp, formatTimestampShort } from "../lib/dates";
import type { ContentType } from "../lib/db";

type HeroItem = {
  id: string;
  title: string;
  senator_id: string;
  senator_name: string;
  party: "D" | "R" | "I";
  state: string;
  published_at: string | null;
  scraped_at?: string;
  content_type: ContentType;
  source_url: string;
};

const ROTATION_MS = 8000;

function formatDateTime(dateStr: string | null): string {
  if (!dateStr) return "";
  const d = new Date(dateStr);
  const hasTime = d.getUTCHours() !== 0 || d.getUTCMinutes() !== 0;
  if (!hasTime) return formatReleaseDate(dateStr);
  return formatTimestamp(d);
}

function formatCaptured(dateStr: string | undefined): string {
  return formatTimestampShort(dateStr);
}

export function HeroLetter({ items, asOf }: { items: HeroItem[]; asOf?: string | null }) {
  const [idx, setIdx] = useState(0);
  const [fade, setFade] = useState(true);
  const [paused, setPaused] = useState(false);

  const advance = (delta: number) => {
    setFade(false);
    setTimeout(() => {
      setIdx((i) => (i + delta + items.length) % items.length);
      setFade(true);
    }, 220);
  };

  useEffect(() => {
    if (items.length <= 1 || paused) return;
    const t = setInterval(() => advance(1), ROTATION_MS);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [items.length, paused]);

  if (items.length === 0) return null;
  const item = items[idx];
  const photo = getSenatorPhotoUrl(item.senator_name, item.senator_id);
  const partyName =
    item.party === "D" ? "Democrat" : item.party === "R" ? "Republican" : "Independent";
  const partyAccent =
    item.party === "D"
      ? "bg-blue-500"
      : item.party === "R"
        ? "bg-red-500"
        : "bg-amber-500";

  const dateLabel = formatDateTime(item.published_at);
  const captured = formatCaptured(item.scraped_at);
  const hasPublishedTime = (() => {
    if (!item.published_at) return false;
    const d = new Date(item.published_at);
    return d.getUTCHours() !== 0 || d.getUTCMinutes() !== 0;
  })();

  return (
    <div className="w-full max-w-sm md:max-w-[26rem]">
      <div className="flex items-end justify-between mb-2 gap-3">
        <div className="min-w-0">
          <h2 className="text-xs uppercase tracking-wider text-neutral-500">
            Latest releases
          </h2>
          {asOf && (
            <p className="text-[10px] text-neutral-400 mt-0.5">
              as of{" "}
              <time dateTime={asOf}>{formatTimestampShort(asOf)}</time>
            </p>
          )}
        </div>
        <div
          className="flex items-center gap-1"
          onMouseEnter={() => setPaused(true)}
          onMouseLeave={() => setPaused(false)}
        >
          <button
            type="button"
            onClick={() => advance(-1)}
            aria-label="Previous release"
            className="h-6 w-6 rounded border border-neutral-300 text-neutral-500 hover:text-neutral-900 hover:border-neutral-500 cursor-pointer flex items-center justify-center transition-colors"
          >
            <svg width="10" height="10" viewBox="0 0 10 10" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M6.5 2L3 5l3.5 3" />
            </svg>
          </button>
          <button
            type="button"
            onClick={() => advance(1)}
            aria-label="Next release"
            className="h-6 w-6 rounded border border-neutral-300 text-neutral-500 hover:text-neutral-900 hover:border-neutral-500 cursor-pointer flex items-center justify-center transition-colors"
          >
            <svg width="10" height="10" viewBox="0 0 10 10" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M3.5 2L7 5l-3.5 3" />
            </svg>
          </button>
        </div>
      </div>

      <div
        className="relative"
        onMouseEnter={() => setPaused(true)}
        onMouseLeave={() => setPaused(false)}
      >
        <div className="relative bg-white border border-neutral-200 shadow-sm rounded-sm overflow-hidden">
          <div className={`h-[3px] ${partyAccent}`} />
          <div
            className={`p-4 transition-opacity duration-200 ${fade ? "opacity-100" : "opacity-0"}`}
          >
            <div className="flex items-center justify-between text-[10px] uppercase tracking-wider text-neutral-400 mb-3">
              <span className="inline-flex items-center gap-1.5">
                <TypeIcon type={item.content_type} size={12} className="text-neutral-500" />
                <span>Press release</span>
              </span>
              {dateLabel && (
                <time
                  dateTime={item.published_at ?? undefined}
                  className="font-[family-name:var(--font-dm-mono)] tabular-nums normal-case tracking-normal text-[11px] text-neutral-500"
                >
                  {dateLabel}
                </time>
              )}
            </div>

            <div className="flex items-start gap-3 mb-3">
              {photo ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={photo}
                  alt={`${item.senator_name} (${item.party}-${item.state})`}
                  width={40}
                  height={40}
                  className="h-10 w-10 rounded-full object-cover ring-1 ring-neutral-200"
                />
              ) : (
                <span className="flex h-10 w-10 items-center justify-center rounded-full bg-neutral-100 text-xs font-medium text-neutral-500 ring-1 ring-neutral-200">
                  {getInitials(item.senator_name)}
                </span>
              )}
              <div className="min-w-0 flex-1 leading-tight">
                <div className="text-[10px] uppercase tracking-wider text-neutral-400">From</div>
                <div className="text-sm text-neutral-900 font-[family-name:var(--font-source-serif)] font-semibold truncate">
                  Sen. {item.senator_name}
                </div>
                <div className="text-[11px] text-neutral-500">
                  {partyName} · {item.state}
                </div>
              </div>
            </div>

            <div className="border-t border-neutral-100 pt-3">
              <div className="text-[10px] uppercase tracking-wider text-neutral-400 mb-1">Subject</div>
              <a
                href={item.source_url}
                target="_blank"
                rel="noopener noreferrer"
                className="block text-[15px] leading-snug text-neutral-900 font-[family-name:var(--font-source-serif)] hover:underline line-clamp-3"
              >
                {normalizeTitle(item.title)}
              </a>
            </div>

            <div className="mt-4 flex items-center justify-between text-[10px] text-neutral-400">
              <span>
                senate.gov
                {!hasPublishedTime && captured && (
                  <span className="ml-2 text-neutral-400">· captured {captured}</span>
                )}
              </span>
              <span className="font-mono tabular-nums">
                {idx + 1} / {items.length}
              </span>
            </div>
          </div>
        </div>

        <div className="absolute inset-0 pointer-events-none -z-10 translate-x-1.5 translate-y-1.5 bg-stone-100 border border-neutral-200 rounded-sm" />
        <div className="absolute inset-0 pointer-events-none -z-20 translate-x-3 translate-y-3 bg-stone-50 border border-neutral-200 rounded-sm" />
      </div>

      <div className="mt-2 flex gap-1">
        {items.map((_, i) => (
          <button
            key={i}
            type="button"
            onClick={() => {
              setFade(false);
              setTimeout(() => {
                setIdx(i);
                setFade(true);
              }, 220);
            }}
            aria-label={`Go to release ${i + 1}`}
            className={`h-1 flex-1 rounded-full transition-colors ${
              i === idx ? "bg-neutral-700" : "bg-neutral-200 hover:bg-neutral-400"
            }`}
          />
        ))}
      </div>
    </div>
  );
}

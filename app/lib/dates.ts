const ET = "America/New_York";

export function formatReleaseDate(input: string | Date | null | undefined): string {
  if (!input) return "";
  const d = typeof input === "string" ? new Date(input) : input;
  return d.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function ymdInET(d: Date): string {
  return d.toLocaleDateString("en-CA", { timeZone: ET });
}

// Feed-card date formatter. Shows "Today, 2:42 PM EDT" or "Yesterday" for
// recent items, full date otherwise. When the office-claimed date is in the
// future relative to when we captured the item, display falls back to the
// scrape timestamp so a typo in the upstream date doesn't push the row to
// the top of the visible feed in a confusing way.
export function formatFeedDate(
  publishedAt: string | Date | null | undefined,
  scrapedAt: string | Date | null | undefined
): string {
  if (!publishedAt && !scrapedAt) return "";
  const effective = effectiveDate(publishedAt, scrapedAt);
  if (!effective) return "";

  const todayYmd = ymdInET(new Date());
  const effYmd = ymdInET(effective);

  if (effYmd === todayYmd) {
    const time = effective.toLocaleString("en-US", {
      hour: "numeric",
      minute: "2-digit",
      timeZone: ET,
      timeZoneName: "short",
    });
    return `Today, ${time}`;
  }

  // Yesterday: shift today by one day in ET.
  const yesterday = new Date();
  yesterday.setUTCDate(yesterday.getUTCDate() - 1);
  if (effYmd === ymdInET(yesterday)) return "Yesterday";

  return effective.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    timeZone: ET,
  });
}

// Returns the date we should display to the reader. Prefers published_at,
// but if that's clearly future-dated relative to scrape time, falls back to
// the scrape date so the feed stays coherent.
export function effectiveDate(
  publishedAt: string | Date | null | undefined,
  scrapedAt: string | Date | null | undefined
): Date | null {
  const p = publishedAt
    ? typeof publishedAt === "string"
      ? new Date(publishedAt)
      : publishedAt
    : null;
  const s = scrapedAt
    ? typeof scrapedAt === "string"
      ? new Date(scrapedAt)
      : scrapedAt
    : null;
  if (p && s && p.getTime() - s.getTime() > 24 * 60 * 60 * 1000) return s;
  return p ?? s;
}

export function formatShortDate(input: string | Date | null | undefined): string {
  if (!input) return "";
  const d = typeof input === "string" ? new Date(input) : input;
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

export function formatMonthYear(input: string | Date | null | undefined): string {
  if (!input) return "";
  const d = typeof input === "string" ? new Date(input) : input;
  return d.toLocaleDateString("en-US", { month: "short", year: "numeric" });
}

export function formatLongMonthYear(input: string | Date | null | undefined): string {
  if (!input) return "";
  const d = typeof input === "string" ? new Date(input) : input;
  return d.toLocaleDateString("en-US", { month: "long", year: "numeric" });
}

export function formatTimestamp(input: string | Date | null | undefined): string {
  if (!input) return "";
  const d = typeof input === "string" ? new Date(input) : input;
  return d.toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
    timeZone: ET,
    timeZoneName: "short",
  });
}

// True when the published date is more than a day ahead of when we
// captured the release. Catches upstream typos (e.g. senator's office
// puts "May 04" on a release we scraped April 28). Never overwrite the
// source date in the DB; flag it on display.
export function isFutureDated(
  publishedAt: string | Date | null | undefined,
  scrapedAt: string | Date | null | undefined,
  toleranceMs: number = 24 * 60 * 60 * 1000
): boolean {
  if (!publishedAt || !scrapedAt) return false;
  const p = typeof publishedAt === "string" ? new Date(publishedAt) : publishedAt;
  const s = typeof scrapedAt === "string" ? new Date(scrapedAt) : scrapedAt;
  return p.getTime() - s.getTime() > toleranceMs;
}

export function formatTimestampShort(input: string | Date | null | undefined): string {
  if (!input) return "";
  const d = typeof input === "string" ? new Date(input) : input;
  return d.toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    timeZone: ET,
    timeZoneName: "short",
  });
}

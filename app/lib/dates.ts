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

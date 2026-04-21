import Link from "next/link";
import type { FeedItem } from "../lib/db";
import { getSenatorPhotoUrl, getInitials } from "../lib/photos";
import { TypeBadge } from "./type-badge";

function formatDate(dateStr: string | null): string {
  if (!dateStr) return "";
  return new Date(dateStr).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

const SMALL_WORDS = new Set([
  "a","an","the","and","but","or","for","nor","on","at","to","by","of","in","is","it","as",
]);

function normalizeTitle(title: string): string {
  const letters = title.replace(/[^a-zA-Z]/g, "");
  if (letters.length === 0) return title;
  const upperCount = letters.replace(/[^A-Z]/g, "").length;
  if (upperCount / letters.length < 0.7) return title;

  return title.replace(/\S+/g, (word, offset: number) => {
    const core = word.replace(/[^a-zA-Z]/g, "");
    // Keep likely acronyms (2-4 char all-caps, not a common word)
    if (/^[A-Z]{2,4}$/.test(core) && !SMALL_WORDS.has(core.toLowerCase()))
      return word;
    // Lowercase common small words except at start
    if (offset > 0 && SMALL_WORDS.has(core.toLowerCase()))
      return word.toLowerCase();
    // Title case
    return word.charAt(0).toUpperCase() + word.slice(1).toLowerCase();
  });
}

export function ReleaseCard({ item }: { item: FeedItem }) {
  const photoUrl = getSenatorPhotoUrl(item.senator_name, item.senator_id);
  const partyRing =
    item.party === "D"
      ? "ring-blue-500"
      : item.party === "R"
        ? "ring-red-500"
        : "ring-amber-500";

  return (
    <article className="border-b border-neutral-100 py-1.5">
      <div className="flex items-start gap-2.5">
        <Link
          href={`/senators/${item.senator_id}`}
          className="shrink-0 mt-0.5"
        >
          {photoUrl ? (
            <img
              src={photoUrl}
              alt={item.senator_name}
              width={28}
              height={28}
              className={`h-7 w-7 rounded-full object-cover ring-1.5 ${partyRing}`}
            />
          ) : (
            <span
              className={`flex h-7 w-7 items-center justify-center rounded-full bg-neutral-100 text-[10px] font-medium text-neutral-500 ring-1.5 ${partyRing}`}
            >
              {getInitials(item.senator_name)}
            </span>
          )}
        </Link>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-1.5 text-xs text-neutral-400">
            <Link
              href={`/senators/${item.senator_id}`}
              className="text-neutral-500 hover:text-neutral-900 transition-colors"
            >
              {item.senator_name}
            </Link>
            <span>·</span>
            <span>{item.party}-{item.state}</span>
            {item.published_at && (
              <>
                <span>·</span>
                <time
                  dateTime={item.published_at}
                  className="font-[family-name:var(--font-dm-mono)] tabular-nums"
                >
                  {formatDate(item.published_at)}
                </time>
              </>
            )}
            {item.content_type && item.content_type !== "press_release" && (
              <TypeBadge
                type={item.content_type}
                href={`/feed?type=${item.content_type}`}
                size="xs"
              />
            )}
          </div>
          <h3 className="text-sm text-neutral-900 leading-snug mt-0.5">
            <a
              href={item.source_url}
              target="_blank"
              rel="noopener noreferrer"
              className="hover:underline"
            >
              {normalizeTitle(item.title)}
            </a>
          </h3>
        </div>
      </div>
    </article>
  );
}

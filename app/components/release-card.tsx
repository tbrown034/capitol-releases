import Link from "next/link";
import type { FeedItem } from "../lib/db";
import { getSenatorPhotoUrl, getInitials } from "../lib/photos";
import { normalizeTitle } from "../lib/titles";
import { formatReleaseDate } from "../lib/dates";
import { TypeBadge } from "./type-badge";
import { TypeIcon } from "./type-icon";

function sourceHost(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return "senate.gov";
  }
}

export function ReleaseCard({ item }: { item: FeedItem }) {
  const photoUrl = getSenatorPhotoUrl(item.senator_name, item.senator_id);
  const partyRing =
    item.party === "D"
      ? "ring-blue-500"
      : item.party === "R"
        ? "ring-red-500"
        : "ring-amber-500";
  const partyAccent =
    item.party === "D"
      ? "border-l-blue-200"
      : item.party === "R"
        ? "border-l-red-200"
        : "border-l-amber-200";

  const type = item.content_type ?? "press_release";
  const host = sourceHost(item.source_url);

  return (
    <article
      className={`border-b border-neutral-100 border-l-2 ${partyAccent} pl-3 py-1.5 -ml-3`}
    >
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
            <span className="text-neutral-400 inline-flex items-center gap-1">
              <TypeIcon type={type} size={12} className="text-neutral-400" />
              <span className="text-[10px] uppercase tracking-wider text-neutral-400">From</span>
            </span>
            <Link
              href={`/senators/${item.senator_id}`}
              className="text-neutral-700 font-[family-name:var(--font-source-serif)] hover:text-neutral-900 transition-colors"
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
                  {formatReleaseDate(item.published_at)}
                </time>
              </>
            )}
            {type !== "press_release" && (
              <TypeBadge
                type={type}
                href={`/feed?type=${type}`}
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
          <div className="mt-0.5 text-[10px] text-neutral-400">
            <a
              href={item.source_url}
              target="_blank"
              rel="noopener noreferrer"
              className="hover:text-neutral-600 transition-colors"
            >
              {host}
            </a>
          </div>
        </div>
      </div>
    </article>
  );
}

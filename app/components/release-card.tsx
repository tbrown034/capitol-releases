import Link from "next/link";
import Image from "next/image";
import type { FeedItem } from "../lib/db";
import { getMemberPhotoUrl, getInitials, getMemberHref } from "../lib/photos";
import { normalizeTitle } from "../lib/titles";
import { formatFeedDate, formatReleaseDate, isFutureDated } from "../lib/dates";
import { TypeBadge } from "./type-badge";
import { TypeIcon } from "./type-icon";

function sourceHost(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return "senate.gov";
  }
}

// ts_headline output is server-trusted Postgres output that we explicitly
// asked to wrap matches in <mark>. We escape the rest, then re-inject mark
// tags. Anything else is rendered as text.
function escapeSnippetText(s: string) {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function Snippet({ text }: { text: string }) {
  // Split on our known mark tokens (we set StartSel/StopSel ourselves).
  const parts = text.split(/(<mark>|<\/mark>)/g);
  let inMark = false;
  const nodes: React.ReactNode[] = [];
  parts.forEach((p) => {
    if (p === "<mark>") {
      inMark = true;
      return;
    }
    if (p === "</mark>") {
      inMark = false;
      return;
    }
    if (!p) return;
    const safe = escapeSnippetText(p)
      .replace(/&amp;/g, "&")
      .replace(/&lt;/g, "<")
      .replace(/&gt;/g, ">");
    nodes.push(
      inMark ? (
        <mark key={`mark-${safe}-${nodes.length}`} className="bg-yellow-100 text-yellow-950 px-0.5 rounded-sm">
          {safe}
        </mark>
      ) : (
        <span key={`text-${safe}-${nodes.length}`}>{safe}</span>
      )
    );
  });
  return <>{nodes}</>;
}

export function ReleaseCard({
  item,
  snippet,
}: {
  item: FeedItem;
  snippet?: string | null;
}) {
  const photoUrl = getMemberPhotoUrl(
    item.senator_name,
    item.official_id,
    item.chamber,
    item.bioguide_id
  );
  const memberHref = getMemberHref(item.official_id, item.chamber);
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
          href={memberHref}
          className="shrink-0 mt-0.5"
        >
          {photoUrl ? (
            <Image
              src={photoUrl}
              alt={item.senator_name}
              width={28}
              height={28}
              className={`size-7 rounded-full object-cover ring-1.5 ${partyRing}`}
              unoptimized
            />
          ) : (
            <span
              className={`flex size-7 items-center justify-center rounded-full bg-neutral-100 text-[10px] font-medium text-neutral-500 ring-1.5 ${partyRing}`}
            >
              {getInitials(item.senator_name)}
            </span>
          )}
        </Link>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-1.5 text-xs text-neutral-500">
            <span className="text-neutral-400 inline-flex items-center gap-1">
              <TypeIcon type={type} size={12} className="text-neutral-400" />
              <span className="text-[10px] uppercase tracking-wider text-neutral-400">From</span>
            </span>
            <Link
              href={memberHref}
              className="text-neutral-700 font-[family-name:var(--font-source-serif)] hover:text-neutral-900 transition-colors"
            >
              {item.senator_name}
            </Link>
            <span>·</span>
            <span>{item.party}-{item.state}</span>
            {(item.published_at || item.scraped_at) && (
              <>
                <span>·</span>
                <time
                  dateTime={item.published_at ?? item.scraped_at}
                  className="font-[family-name:var(--font-dm-mono)] tabular-nums"
                >
                  {formatFeedDate(item.published_at, item.scraped_at)}
                </time>
                {isFutureDated(item.published_at, item.scraped_at) && (
                  <span
                    title={`Office-published date (${formatReleaseDate(item.published_at)}) is in the future; we captured this on ${formatReleaseDate(item.scraped_at)}.`}
                    className="text-amber-700 cursor-help"
                  >
                    *
                  </span>
                )}
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
            <Link
              href={`/releases/${item.id}`}
              className="hover:underline"
            >
              {normalizeTitle(item.title)}
            </Link>
          </h3>
          {snippet && snippet.trim().length > 0 && (
            <p className="mt-1 text-[12px] text-neutral-600 leading-relaxed line-clamp-3">
              <Snippet text={snippet} />
            </p>
          )}
          <div className="mt-0.5 text-[10px] text-neutral-400 flex items-center gap-2">
            <Link
              href={`/releases/${item.id}`}
              className="hover:text-neutral-600 transition-colors"
            >
              Read here
            </Link>
            <span className="text-neutral-300">·</span>
            <a
              href={item.source_url}
              target="_blank"
              rel="noopener noreferrer"
              className="hover:text-neutral-600 transition-colors"
            >
              {host}
              <span aria-hidden> ↗</span>
            </a>
          </div>
        </div>
      </div>
    </article>
  );
}

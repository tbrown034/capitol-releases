import Link from "next/link";
import { PartyDot } from "./party-badge";
import type { FeedItem } from "../lib/db";

function formatDate(dateStr: string | null): string {
  if (!dateStr) return "";
  const d = new Date(dateStr);
  return d.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function timeAgo(dateStr: string | null): string {
  if (!dateStr) return "";
  const now = new Date();
  const d = new Date(dateStr);
  const diffMs = now.getTime() - d.getTime();
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));
  if (diffDays === 0) return "Today";
  if (diffDays === 1) return "Yesterday";
  if (diffDays < 7) return `${diffDays}d ago`;
  if (diffDays < 30) return `${Math.floor(diffDays / 7)}w ago`;
  return formatDate(dateStr);
}

export function ReleaseCard({ item }: { item: FeedItem }) {
  const date = formatDate(item.published_at);
  const ago = timeAgo(item.published_at);

  return (
    <article className="group border-b border-stone-100 py-3.5 last:border-0">
      <div className="flex items-start gap-2.5">
        <div className="mt-1.5 shrink-0">
          <PartyDot party={item.party} />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1.5 text-xs text-stone-400">
            <Link
              href={`/senators/${item.senator_id}`}
              className="font-medium text-stone-600 hover:text-blue-600"
            >
              {item.senator_name}
            </Link>
            <span className="text-stone-300">/</span>
            <span>
              {item.party}-{item.state}
            </span>
            {date && (
              <>
                <span className="text-stone-300">/</span>
                <time
                  dateTime={item.published_at ?? undefined}
                  title={date}
                  className="tabular-nums"
                >
                  {ago}
                </time>
              </>
            )}
          </div>
          <h3 className="mt-0.5 text-[13px] font-medium leading-snug text-stone-800 group-hover:text-stone-950">
            <a
              href={item.source_url}
              target="_blank"
              rel="noopener noreferrer"
              className="hover:underline"
            >
              {item.title}
            </a>
          </h3>
          {item.body_text && (
            <p className="mt-1 text-xs leading-relaxed text-stone-400 line-clamp-1">
              {item.body_text.slice(0, 180)}
            </p>
          )}
        </div>
      </div>
    </article>
  );
}

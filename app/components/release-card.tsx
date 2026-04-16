import Link from "next/link";
import type { FeedItem } from "../lib/db";

function formatDate(dateStr: string | null): string {
  if (!dateStr) return "";
  return new Date(dateStr).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

export function ReleaseCard({ item }: { item: FeedItem }) {
  return (
    <article className="border-b border-neutral-100 py-2.5">
      <div className="flex items-start gap-2">
        <span className={`mt-1.5 inline-block h-1.5 w-1.5 rounded-full shrink-0 ${
          item.party === "D" ? "bg-blue-500" : item.party === "R" ? "bg-red-500" : "bg-amber-500"
        }`} />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1.5 text-xs text-neutral-400">
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
          </div>
          <h3 className="text-sm text-neutral-900 leading-snug mt-0.5">
            <a
              href={item.source_url}
              target="_blank"
              rel="noopener noreferrer"
              className="hover:underline"
            >
              {item.title}
            </a>
          </h3>
        </div>
      </div>
    </article>
  );
}

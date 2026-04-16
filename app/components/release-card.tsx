import Link from "next/link";
import { PartyDot } from "./party-badge";
import type { FeedItem } from "../lib/db";

function formatDate(dateStr: string | null): string {
  if (!dateStr) return "No date";
  const d = new Date(dateStr);
  return d.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

export function ReleaseCard({ item }: { item: FeedItem }) {
  return (
    <article className="border-b border-gray-100 py-4 last:border-0">
      <div className="flex items-start gap-3">
        <div className="mt-1.5">
          <PartyDot party={item.party} />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 text-xs text-gray-500">
            <Link
              href={`/senators/${item.senator_id}`}
              className="font-medium text-gray-700 hover:text-blue-600"
            >
              {item.senator_name}
            </Link>
            <span>({item.party}-{item.state})</span>
            <span>{formatDate(item.published_at)}</span>
          </div>
          <h3 className="mt-1 text-sm font-medium leading-snug text-gray-900">
            <a
              href={item.source_url}
              target="_blank"
              rel="noopener noreferrer"
              className="hover:text-blue-600"
            >
              {item.title}
            </a>
          </h3>
          {item.body_text && (
            <p className="mt-1 text-xs leading-relaxed text-gray-500 line-clamp-2">
              {item.body_text.slice(0, 200)}
            </p>
          )}
        </div>
      </div>
    </article>
  );
}

import Link from "next/link";
import type { ContentType } from "../lib/db";
import { CONTENT_TYPE_PLURAL } from "../lib/queries";
import { TypeIcon } from "./type-icon";

type MailbagRow = { content_type: ContentType; count: number };

const ORDER: ContentType[] = [
  "press_release",
  "statement",
  "letter",
  "op_ed",
  "floor_statement",
  "blog",
  "presidential_action",
  "other",
];

export function MailbagStrip({
  items,
  days = 7,
}: {
  items: MailbagRow[];
  days?: number;
}) {
  const map = new Map(items.map((r) => [r.content_type, r.count]));
  const total = items.reduce((s, r) => s + r.count, 0);
  const visible = ORDER.filter((t) => (map.get(t) ?? 0) > 0);

  if (visible.length === 0) return null;

  return (
    <section
      aria-label={`Mailbag, last ${days} days`}
      className="border border-neutral-200 bg-stone-50/60 rounded-sm px-4 py-3 mb-8 md:mb-12"
    >
      <div className="flex items-center justify-between gap-4 mb-2">
        <div className="text-[10px] uppercase tracking-wider text-neutral-500">
          Mailbag · last {days} days
        </div>
        <div className="text-xs text-neutral-500 tabular-nums">
          <span className="font-semibold text-neutral-900">{total.toLocaleString()}</span>{" "}
          {total === 1 ? "item" : "items"}
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-x-5 gap-y-2 text-sm">
        {visible.map((type) => {
          const count = map.get(type) ?? 0;
          return (
            <Link
              key={type}
              href={`/feed?type=${type}`}
              className="inline-flex items-center gap-1.5 text-neutral-700 hover:text-neutral-900 transition-colors group"
            >
              <TypeIcon type={type} size={14} className="text-neutral-500 group-hover:text-neutral-900 transition-colors" />
              <span className="font-mono tabular-nums font-semibold text-neutral-900">
                {count.toLocaleString()}
              </span>
              <span className="text-neutral-500 group-hover:text-neutral-700 transition-colors">
                {CONTENT_TYPE_PLURAL[type] ?? type}
              </span>
            </Link>
          );
        })}
      </div>
      <p className="mt-3 pt-3 border-t border-neutral-200 text-[11px] text-neutral-500 leading-relaxed">
        Office-published only. Campaign sites, third-party clippings, and
        &ldquo;In the News&rdquo; aggregations are not included.{" "}
        <Link href="/about" className="underline hover:text-neutral-900">
          Methodology
        </Link>
      </p>
    </section>
  );
}

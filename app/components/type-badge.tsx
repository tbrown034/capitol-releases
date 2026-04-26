import Link from "next/link";
import type { ContentType } from "../lib/db";
import { CONTENT_TYPE_LABEL_SHORT, CONTENT_TYPE_LABEL } from "../lib/queries";

// photo_release is intentionally absent -- it's excluded from every UI surface
// via queries.ts, so this component never receives it.
const STYLES: Partial<Record<ContentType, string>> = {
  press_release: "border-neutral-200 text-neutral-500",
  statement: "border-sky-200 bg-sky-50 text-sky-700",
  op_ed: "border-purple-200 bg-purple-50 text-purple-700",
  blog: "border-rose-200 bg-rose-50 text-rose-700",
  letter: "border-amber-200 bg-amber-50 text-amber-700",
  floor_statement: "border-indigo-200 bg-indigo-50 text-indigo-700",
  presidential_action: "border-emerald-200 bg-emerald-50 text-emerald-700",
  other: "border-neutral-200 bg-neutral-50 text-neutral-500",
};
const FALLBACK_STYLE = "border-neutral-200 bg-neutral-50 text-neutral-500";

export function TypeBadge({
  type,
  href,
  size = "sm",
}: {
  type: ContentType;
  href?: string;
  size?: "sm" | "xs";
}) {
  const label = CONTENT_TYPE_LABEL_SHORT[type] ?? type;
  const full = CONTENT_TYPE_LABEL[type] ?? type;
  const px = size === "xs" ? "px-1.5 py-0" : "px-1.5 py-0.5";
  const text = size === "xs" ? "text-[10px]" : "text-[11px]";
  const cls = `inline-flex items-center ${px} ${text} border ${STYLES[type] ?? FALLBACK_STYLE} tracking-wide`;

  if (href) {
    return (
      <Link href={href} title={full} className={`${cls} hover:border-neutral-400 transition-colors`}>
        {label}
      </Link>
    );
  }
  return (
    <span title={full} className={cls}>
      {label}
    </span>
  );
}

import Link from "next/link";

type Suggestion = {
  label: string;
  href: string;
};

export function EmptyState({
  message,
  clearHref,
  suggestions = [],
}: {
  message: string;
  clearHref?: string;
  suggestions?: Suggestion[];
}) {
  const links: Suggestion[] = [];
  if (clearHref) links.push({ label: "Clear filters", href: clearHref });
  for (const s of suggestions) links.push(s);
  if (!links.some((l) => l.href === "/trending")) {
    links.push({ label: "See what's trending", href: "/trending" });
  }

  return (
    <div className="py-12 text-center">
      <p className="text-sm text-neutral-500">{message}</p>
      <div className="mt-4 flex flex-wrap justify-center gap-x-4 gap-y-2 text-sm">
        {links.map((l, i) => (
          <Link
            key={`${l.href}-${i}`}
            href={l.href}
            className="text-neutral-700 underline underline-offset-2 hover:text-neutral-900"
          >
            {l.label}
          </Link>
        ))}
      </div>
    </div>
  );
}

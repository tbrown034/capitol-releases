import Link from "next/link";

const links = [
  { href: "/feed", label: "Feed" },
  { href: "/senators", label: "Senators" },
  { href: "/search", label: "Search" },
  { href: "/about", label: "Methodology" },
];

export function Nav() {
  return (
    <header className="border-b border-stone-200 bg-white">
      <div className="mx-auto flex max-w-5xl items-center justify-between px-4 py-3">
        <Link href="/" className="flex items-center gap-2">
          <span className="flex h-7 w-7 items-center justify-center rounded bg-stone-900 text-xs font-bold text-white">
            CR
          </span>
          <span className="text-base font-bold tracking-tight text-stone-900">
            Capitol Releases
          </span>
        </Link>
        <nav className="flex items-center gap-1">
          {links.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              className="rounded-md px-3 py-1.5 text-sm text-stone-500 transition-colors hover:bg-stone-100 hover:text-stone-900"
            >
              {link.label}
            </Link>
          ))}
        </nav>
      </div>
    </header>
  );
}

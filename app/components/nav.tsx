import Link from "next/link";

const links = [
  { href: "/feed", label: "Feed" },
  { href: "/senators", label: "Directory" },
  { href: "/search", label: "Search" },
  { href: "/about", label: "Methodology" },
];

export function Nav() {
  return (
    <header className="border-b border-neutral-200">
      <nav className="mx-auto max-w-5xl px-4 py-4 flex items-center justify-between">
        <Link
          href="/"
          className="text-sm font-medium text-neutral-900 hover:text-neutral-600 transition-colors"
        >
          Capitol Releases
        </Link>
        <div className="flex items-center gap-6">
          {links.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              className="text-sm text-neutral-500 hover:text-neutral-900 transition-colors"
            >
              {link.label}
            </Link>
          ))}
        </div>
      </nav>
    </header>
  );
}

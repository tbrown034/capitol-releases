import Link from "next/link";

export function Nav() {
  return (
    <header className="border-b border-gray-200 bg-white">
      <div className="mx-auto flex max-w-5xl items-center justify-between px-4 py-3">
        <Link href="/" className="text-lg font-bold tracking-tight text-gray-900">
          Capitol Releases
        </Link>
        <nav className="flex items-center gap-6 text-sm">
          <Link href="/feed" className="text-gray-600 hover:text-gray-900">
            Feed
          </Link>
          <Link href="/senators" className="text-gray-600 hover:text-gray-900">
            Senators
          </Link>
          <Link href="/search" className="text-gray-600 hover:text-gray-900">
            Search
          </Link>
          <Link href="/about" className="text-gray-600 hover:text-gray-900">
            About
          </Link>
        </nav>
      </div>
    </header>
  );
}

import Link from "next/link";

export function Footer() {
  return (
    <footer className="border-t border-neutral-200 bg-stone-50">
      <div className="mx-auto max-w-5xl px-4 py-10">
        <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-8">
          <div className="flex items-center gap-3">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src="/logo.svg"
              alt="Capitol Releases"
              className="h-6 opacity-60"
            />
            <p className="text-xs text-neutral-400">
              Senate press release archive
            </p>
          </div>

          <nav className="flex flex-wrap gap-x-6 gap-y-2 text-xs text-neutral-500">
            <Link href="/feed" className="hover:text-neutral-900 transition-colors">Feed</Link>
            <Link href="/senators" className="hover:text-neutral-900 transition-colors">Directory</Link>
            <Link href="/search" className="hover:text-neutral-900 transition-colors">Search</Link>
            <Link href="/about" className="hover:text-neutral-900 transition-colors">Methodology</Link>
            <Link href="/status" className="hover:text-neutral-900 transition-colors">Run history</Link>
          </nav>
        </div>

        <div className="mt-8 pt-6 border-t border-neutral-200 text-[11px] text-neutral-400 leading-relaxed space-y-3">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
            <p>
              Data scraped daily from official{" "}
              <a
                href="https://www.senate.gov/senators/"
                className="underline hover:text-neutral-600"
                target="_blank"
                rel="noopener noreferrer"
              >
                senate.gov
              </a>{" "}
              press pages. For journalism and public-records purposes. Not affiliated with the U.S. government.
            </p>
            <p className="whitespace-nowrap">
              Built by{" "}
              <a
                href="https://trevorthewebdeveloper.com"
                className="underline hover:text-neutral-600"
                target="_blank"
                rel="noopener noreferrer"
              >
                Trevor Brown
              </a>
            </p>
          </div>
          <div className="flex flex-wrap gap-x-4 gap-y-1">
            <a
              href="https://github.com/tbrown034/capitol-releases"
              className="underline hover:text-neutral-600"
              target="_blank"
              rel="noopener noreferrer"
            >
              Source code
            </a>
            <a
              href="https://github.com/tbrown034/capitol-releases/issues"
              className="underline hover:text-neutral-600"
              target="_blank"
              rel="noopener noreferrer"
            >
              Report a bug
            </a>
            <a
              href="mailto:trevorbrown.web@gmail.com"
              className="underline hover:text-neutral-600"
            >
              Contact
            </a>
          </div>
        </div>
      </div>
    </footer>
  );
}

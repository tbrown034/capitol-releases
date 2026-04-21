"use client";

import { useState } from "react";
import Link from "next/link";

const links = [
  { href: "/feed", label: "Feed" },
  { href: "/senators", label: "Directory" },
  { href: "/search", label: "Search" },
  { href: "/about", label: "Methodology" },
];

export function Nav() {
  const [open, setOpen] = useState(false);

  return (
    <header className="border-b border-neutral-200">
      <nav className="mx-auto max-w-5xl px-4 py-4 flex items-center justify-between">
        <Link
          href="/"
          className="text-neutral-900 hover:text-neutral-600 transition-colors font-[family-name:var(--font-source-serif)] font-semibold text-[15px] sm:text-base tracking-[0.08em] leading-[1.05]"
          aria-label="Capitol Releases home"
        >
          <span className="hidden min-[480px]:inline">CAPITOL RELEASES</span>
          <span className="min-[480px]:hidden block">
            CAPITOL
            <br />
            RELEASES
          </span>
        </Link>

        {/* Desktop links */}
        <div className="hidden md:flex items-center gap-6">
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

        {/* Mobile toggle */}
        <button
          onClick={() => setOpen(!open)}
          className="md:hidden p-1 text-neutral-600"
          aria-label="Toggle menu"
        >
          <svg
            width="20"
            height="20"
            viewBox="0 0 20 20"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinecap="round"
          >
            {open ? (
              <>
                <line x1="4" y1="4" x2="16" y2="16" />
                <line x1="16" y1="4" x2="4" y2="16" />
              </>
            ) : (
              <>
                <line x1="3" y1="6" x2="17" y2="6" />
                <line x1="3" y1="10" x2="17" y2="10" />
                <line x1="3" y1="14" x2="17" y2="14" />
              </>
            )}
          </svg>
        </button>
      </nav>

      {/* Mobile menu */}
      {open && (
        <div className="md:hidden border-t border-neutral-100 px-4 py-3 space-y-2">
          {links.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              onClick={() => setOpen(false)}
              className="block text-sm text-neutral-500 hover:text-neutral-900 transition-colors py-1"
            >
              {link.label}
            </Link>
          ))}
        </div>
      )}
    </header>
  );
}

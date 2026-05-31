"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import Image from "next/image";
import { usePathname } from "next/navigation";

type NavItem = { href: string; label: string };

// Order: Members ▾ · Feed · Brief · About · 🔍
const afterMembers: NavItem[] = [
  { href: "/feed", label: "Feed" },
  { href: "/brief", label: "Brief" },
];

const memberLinks: NavItem[] = [
  { href: "/members/senate", label: "Senate" },
  { href: "/members/house", label: "House" },
];

const trailing: NavItem[] = [
  { href: "/about", label: "About" },
];

function linkClass(active: boolean) {
  return `transition-colors ${active ? "text-neutral-900" : "hover:text-neutral-900"}`;
}

export function Nav() {
  const [open, setOpen] = useState(false);
  const [membersOpen, setMembersOpen] = useState(false);
  const pathname = usePathname();
  const membersRef = useRef<HTMLDivElement>(null);

  const inMembers = pathname.startsWith("/members") || pathname.startsWith("/senators") || pathname.startsWith("/house");

  useEffect(() => {
    function onDocClick(e: MouseEvent) {
      if (membersRef.current && !membersRef.current.contains(e.target as Node)) {
        setMembersOpen(false);
      }
    }
    if (membersOpen) document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, [membersOpen]);

  return (
    <header className="border-b border-neutral-200 relative">
      <nav className="mx-auto max-w-5xl p-4 flex items-center justify-between">
        <Link href="/" aria-label="Capitol Releases home">
          <Image src="/logo.svg" alt="Capitol Releases" width={192} height={32} className="h-8 w-auto" />
        </Link>

        <div className="hidden md:flex items-center gap-5 text-sm text-neutral-500">
          <div
            className="relative flex items-center gap-1"
            ref={membersRef}
            onMouseEnter={() => setMembersOpen(true)}
          >
            <Link href="/members" className={linkClass(inMembers)}>
              Members
            </Link>
            <button
              type="button"
              onClick={() => setMembersOpen((v) => !v)}
              className={`p-0.5 -m-0.5 ${linkClass(inMembers)}`}
              aria-haspopup="menu"
              aria-expanded={membersOpen}
              aria-label="Members menu"
            >
              <svg width="10" height="10" viewBox="0 0 10 10" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
                <path d="M2 4l3 3 3-3" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </button>

            {membersOpen && (
              <div
                className="absolute left-0 top-full mt-2 min-w-[160px] rounded-md border border-neutral-200 bg-white py-1 shadow-sm z-40"
                onMouseLeave={() => setMembersOpen(false)}
                role="menu"
                tabIndex={-1}
              >
                <Link
                  href="/members"
                  onClick={() => setMembersOpen(false)}
                  className="block px-3 py-1.5 text-sm text-neutral-700 hover:bg-neutral-50 hover:text-neutral-900"
                >
                  All members
                </Link>
                <div className="my-1 border-t border-neutral-100" />
                {memberLinks.map((link) => (
                  <Link
                    key={link.href}
                    href={link.href}
                    onClick={() => setMembersOpen(false)}
                    className="block px-3 py-1.5 text-sm text-neutral-700 hover:bg-neutral-50 hover:text-neutral-900"
                  >
                    {link.label}
                  </Link>
                ))}
              </div>
            )}
          </div>

          {afterMembers.map((link) => (
            <Link key={link.href} href={link.href} className={linkClass(pathname === link.href)}>
              {link.label}
            </Link>
          ))}

          {trailing.map((link) => (
            <Link key={link.href} href={link.href} className={linkClass(pathname === link.href)}>
              {link.label}
            </Link>
          ))}

          <Link
            href="/search"
            aria-label="Search"
            className={`p-1 -m-1 ${linkClass(pathname === "/search")}`}
          >
            <svg width="18" height="18" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
              <circle cx="9" cy="9" r="6" />
              <line x1="13.5" y1="13.5" x2="17" y2="17" strokeLinecap="round" />
            </svg>
          </Link>
        </div>

        <div className="flex md:hidden items-center">
          <button
            type="button"
            onClick={() => setOpen(!open)}
            className="p-1.5 -mr-1.5 cursor-pointer"
            aria-label={open ? "Close menu" : "Open menu"}
          >
            <svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" className="text-neutral-700">
              {open ? (
                <>
                  <line x1="4" y1="4" x2="16" y2="16" />
                  <line x1="16" y1="4" x2="4" y2="16" />
                </>
              ) : (
                <>
                  <line x1="3" y1="5" x2="17" y2="5" />
                  <line x1="3" y1="10" x2="17" y2="10" />
                  <line x1="3" y1="15" x2="17" y2="15" />
                </>
              )}
            </svg>
          </button>
        </div>
      </nav>

      {open && (
        <div className="md:hidden fixed inset-0 z-50 bg-white">
          <button
            type="button"
            className="absolute inset-0 cursor-default"
            onClick={() => setOpen(false)}
            aria-label="Close mobile menu"
          />
          <div className="relative border-b border-neutral-200 bg-white">
            <div className="mx-auto max-w-5xl p-4 flex items-center justify-between">
              <Link href="/" aria-label="Capitol Releases home" onClick={() => setOpen(false)}>
                <Image src="/logo.svg" alt="Capitol Releases" width={192} height={32} className="h-8 w-auto" />
              </Link>
              <button
                type="button"
                onClick={() => setOpen(false)}
                className="p-1.5 -mr-1.5 cursor-pointer"
                aria-label="Close menu"
              >
                <svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" className="text-neutral-700">
                  <line x1="4" y1="4" x2="16" y2="16" />
                  <line x1="16" y1="4" x2="4" y2="16" />
                </svg>
              </button>
            </div>
          </div>
          <div className="relative mx-auto max-w-5xl px-4 py-6 flex flex-col gap-1 bg-white">
            <div className="py-3 border-b border-neutral-100">
              <p className="text-[11px] uppercase tracking-wider text-neutral-400 mb-2">Members</p>
              <Link
                href="/members"
                onClick={() => setOpen(false)}
                className="block py-1.5 text-base text-neutral-700 hover:text-neutral-900"
              >
                All members
              </Link>
              <Link
                href="/members/senate"
                onClick={() => setOpen(false)}
                className="block py-1.5 text-base text-neutral-700 hover:text-neutral-900"
              >
                Senate
              </Link>
              <Link
                href="/members/house"
                onClick={() => setOpen(false)}
                className="block py-1.5 text-base text-neutral-700 hover:text-neutral-900"
              >
                House
              </Link>
            </div>
            <MobileLink href="/feed" label="Feed" pathname={pathname} onClick={() => setOpen(false)} />
            <MobileLink href="/brief" label="Brief" pathname={pathname} onClick={() => setOpen(false)} />
            <MobileLink href="/about" label="About" pathname={pathname} onClick={() => setOpen(false)} />
            <MobileLink href="/search" label="Search" pathname={pathname} onClick={() => setOpen(false)} />
          </div>
        </div>
      )}
    </header>
  );
}

function MobileLink({
  href,
  label,
  pathname,
  onClick,
}: {
  href: string;
  label: string;
  pathname: string;
  onClick: () => void;
}) {
  const active = pathname === href;
  return (
    <Link
      href={href}
      onClick={onClick}
      className={`text-base py-3 border-b border-neutral-100 transition-colors ${
        active ? "text-neutral-900 font-medium" : "text-neutral-700 hover:text-neutral-900"
      }`}
    >
      {label}
    </Link>
  );
}

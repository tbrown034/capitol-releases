import type { Metadata } from "next";
import { DM_Sans, DM_Mono, Source_Serif_4 } from "next/font/google";
import { Nav } from "./components/nav";
import "./globals.css";

const dmSans = DM_Sans({
  variable: "--font-dm-sans",
  subsets: ["latin"],
});

const dmMono = DM_Mono({
  variable: "--font-dm-mono",
  weight: ["400", "500"],
  subsets: ["latin"],
});

const sourceSerif = Source_Serif_4({
  variable: "--font-source-serif",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Capitol Releases",
  description:
    "A searchable archive of official press releases from all 100 U.S. senators. Normalized, indexed, updated daily.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${dmSans.variable} ${dmMono.variable} ${sourceSerif.variable} antialiased`}
    >
      <body className="bg-white text-neutral-900 font-[family-name:var(--font-dm-sans)]">
        <div className="h-[3px] bg-neutral-800 w-full" />
        <Nav />
        <main>{children}</main>
        <footer className="border-t border-neutral-200 bg-stone-50">
          <div className="mx-auto max-w-5xl px-4 py-10">
            <div className="flex items-start justify-between">
              <div className="max-w-sm">
                <p className="text-sm font-medium text-neutral-900">
                  Capitol Releases
                </p>
                <p className="mt-2 text-[11px] text-neutral-400 leading-relaxed">
                  A journalism and public-records project. All data sourced from
                  official senate.gov websites. Not affiliated with the U.S.
                  government. Built by Trevor Brown.
                </p>
              </div>
              <div className="flex gap-8 text-[11px] text-neutral-400">
                <div className="space-y-1.5">
                  <a href="/feed" className="block hover:text-neutral-600 transition-colors">Feed</a>
                  <a href="/senators" className="block hover:text-neutral-600 transition-colors">Directory</a>
                  <a href="/search" className="block hover:text-neutral-600 transition-colors">Search</a>
                </div>
                <div className="space-y-1.5">
                  <a href="/about" className="block hover:text-neutral-600 transition-colors">Methodology</a>
                  <a
                    href="https://github.com/tbrown034/capitol-releases"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="block hover:text-neutral-600 transition-colors"
                  >
                    Source Code
                  </a>
                </div>
              </div>
            </div>
            <p className="mt-8 text-[11px] text-neutral-400">
              Data collected from public records under the First Amendment.
              Photos from the Congressional Bioguide (public domain).
            </p>
          </div>
        </footer>
      </body>
    </html>
  );
}

import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { Nav } from "./components/nav";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
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
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col bg-[#fafaf9] text-stone-900">
        <Nav />
        <main className="flex-1">{children}</main>
        <footer className="border-t border-stone-200 bg-white">
          <div className="mx-auto max-w-5xl px-4 py-8">
            <div className="flex items-start justify-between">
              <div>
                <div className="flex items-center gap-2">
                  <span className="flex h-6 w-6 items-center justify-center rounded bg-stone-900 text-[10px] font-bold text-white">
                    CR
                  </span>
                  <span className="text-sm font-bold text-stone-900">
                    Capitol Releases
                  </span>
                </div>
                <p className="mt-2 max-w-sm text-xs text-stone-400 leading-relaxed">
                  A journalism and public-records project. All data sourced from
                  official senate.gov websites. Not affiliated with the U.S.
                  Senate or any government agency.
                </p>
              </div>
              <div className="flex gap-8 text-xs text-stone-400">
                <div className="space-y-1.5">
                  <p className="font-medium text-stone-600">Navigate</p>
                  <a href="/feed" className="block hover:text-stone-600">Feed</a>
                  <a href="/senators" className="block hover:text-stone-600">Senators</a>
                  <a href="/search" className="block hover:text-stone-600">Search</a>
                </div>
                <div className="space-y-1.5">
                  <p className="font-medium text-stone-600">Project</p>
                  <a href="/about" className="block hover:text-stone-600">Methodology</a>
                  <a
                    href="https://github.com/tbrown034/capitol-releases"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="block hover:text-stone-600"
                  >
                    GitHub
                  </a>
                </div>
              </div>
            </div>
            <p className="mt-6 text-[10px] text-stone-300">
              Built by Trevor Brown. Data collected from public records under
              the First Amendment.
            </p>
          </div>
        </footer>
      </body>
    </html>
  );
}

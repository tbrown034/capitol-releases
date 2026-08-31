import type { Metadata } from "next";
import { DM_Sans, DM_Mono, Source_Serif_4 } from "next/font/google";
import { Analytics } from "@vercel/analytics/next";
import { Nav } from "./components/nav";
import { Footer } from "./components/footer";
import { SITE_URL } from "./lib/site";
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
  metadataBase: new URL(SITE_URL),
  title: "Capitol Releases",
  description:
    "A searchable archive of official press releases from all 100 U.S. senators, all 437 U.S. House members, and the Texas State Senate. Normalized, indexed, updated four times daily.",
};

const websiteJsonLd = {
  "@context": "https://schema.org",
  "@type": "WebSite",
  name: "Capitol Releases",
  url: SITE_URL,
  description:
    "Searchable archive of official press releases from U.S. senators, House members, and the Texas State Senate. Updated multiple times daily.",
  potentialAction: {
    "@type": "SearchAction",
    target: `${SITE_URL}/search?q={search_term_string}`,
    "query-input": "required name=search_term_string",
  },
  publisher: {
    "@type": "Person",
    name: "Trevor Brown",
    url: "https://trevorthewebdeveloper.com",
    sameAs: [
      "https://github.com/tbrown034",
      "https://www.linkedin.com/in/trevorabrown",
    ],
  },
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
        <a
          href="#main"
          className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-50 focus:px-3 focus:py-2 focus:bg-neutral-900 focus:text-white focus:text-sm focus:rounded"
        >
          Skip to content
        </a>
        <div className="h-[3px] bg-neutral-800 w-full" />
        <Nav />
        <main id="main">{children}</main>
        <Footer />
        <Analytics />
        <script type="application/ld+json">{JSON.stringify(websiteJsonLd)}</script>
      </body>
    </html>
  );
}

import type { MetadataRoute } from "next";
import { SITE_URL } from "./lib/site";

// Crawlers we want reading content pages: they drive AI-search citations.
const AI_CRAWLERS = [
  "GPTBot",
  "OAI-SearchBot",
  "ChatGPT-User",
  "ClaudeBot",
  "Claude-SearchBot",
  "Claude-User",
  "PerplexityBot",
  "Perplexity-User",
  "Google-Extended",
  "Applebot-Extended",
  "Meta-ExternalAgent",
  "Amazonbot",
  "DuckAssistBot",
  "MistralAI-User",
  "cohere-ai",
];

// High-volume scrapers with no citation upside (TikTok, Common Crawl).
const BLOCKED_CRAWLERS = ["Bytespider", "CCBot"];

// Search-results pages are uncacheable DB hits with unbounded query
// permutations; content stays discoverable through the sitemap.
const DISALLOWED_PATHS = ["/api/", "/search", "/texas/search"];

export default function robots(): MetadataRoute.Robots {
  return {
    rules: [
      {
        userAgent: "*",
        allow: "/",
        disallow: DISALLOWED_PATHS,
      },
      {
        userAgent: AI_CRAWLERS,
        allow: "/",
        disallow: DISALLOWED_PATHS,
      },
      {
        userAgent: BLOCKED_CRAWLERS,
        disallow: "/",
      },
    ],
    // Sharded via generateSitemaps() in app/sitemap.ts — /sitemap.xml no
    // longer exists. Keep this list in sync with RELEASE_SHARDS there.
    sitemap: [0, 1, 2, 3, 4].map((id) => `${SITE_URL}/sitemap/${id}.xml`),
    host: SITE_URL,
  };
}

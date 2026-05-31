import { getRecentBriefs } from "../../lib/queries";
import { SITE_URL } from "../../lib/site";

const TITLE = "Capitol Brief — Capitol Releases";
const DESCRIPTION =
  "Daily AI-generated brief of every U.S. senator's official communications, with every claim grounded in source records.";

function escapeXml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&apos;");
}

function rfc822(d: string | null): string {
  const date = d ? new Date(d) : new Date();
  return date.toUTCString();
}

function paragraphs(text: string): string[] {
  return text.split(/\n\n+/).flatMap((p) => {
    const trimmed = p.trim();
    return trimmed ? [trimmed] : [];
  });
}

export async function GET() {
  const briefs = await getRecentBriefs(30);
  const lastBuildDate = briefs[0]?.published_at ?? new Date().toISOString();

  const items = briefs
    .map((b) => {
      const url = `${SITE_URL}/brief/${b.brief_date}`;
      const lede = paragraphs(b.lede)
        .slice(0, 2)
        .map((p) => `<p>${escapeXml(p)}</p>`)
        .join("");
      const sectionsHtml = b.sections
        .map(
          (s) =>
            `<h3>${escapeXml(s.theme)}</h3>` +
            paragraphs(s.body)
              .map((p) => `<p>${escapeXml(p)}</p>`)
              .join("")
        )
        .join("");
      const description = `${b.dek ? `<p><em>${escapeXml(b.dek)}</em></p>` : ""}${lede}${sectionsHtml}`;
      return `
    <item>
      <title>${escapeXml(b.headline)}</title>
      <link>${escapeXml(url)}</link>
      <guid isPermaLink="true">${escapeXml(url)}</guid>
      <pubDate>${rfc822(b.published_at)}</pubDate>
      <description>${escapeXml(description)}</description>
    </item>`;
    })
    .join("");

  const xml = `<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>${escapeXml(TITLE)}</title>
    <link>${escapeXml(`${SITE_URL}/brief`)}</link>
    <atom:link href="${escapeXml(`${SITE_URL}/brief/rss.xml`)}" rel="self" type="application/rss+xml"/>
    <description>${escapeXml(DESCRIPTION)}</description>
    <language>en-us</language>
    <lastBuildDate>${rfc822(lastBuildDate)}</lastBuildDate>${items}
  </channel>
</rss>`;

  return new Response(xml, {
    status: 200,
    headers: {
      "content-type": "application/rss+xml; charset=utf-8",
      "cache-control": "public, max-age=600",
    },
  });
}

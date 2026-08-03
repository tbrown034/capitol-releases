import { neon } from "@neondatabase/serverless";
import { readFileSync } from "node:fs";

for (const envFile of [".env.local", ".env"]) {
  try {
    const content = readFileSync(envFile, "utf8");
    for (const line of content.split("\n")) {
      const m = line.match(/^([A-Z_]+)=(.*)$/);
      if (m && !process.env[m[1]]) process.env[m[1]] = m[2].replace(/^["']|["']$/g, "");
    }
  } catch {}
}

const sql = neon(process.env.DATABASE_URL);

async function main() {
  console.log("=== current server time ===");
  const now = await sql`SELECT NOW() as now, CURRENT_DATE as today`;
  console.log(now[0]);

  console.log("\n=== Durbin May release ===");
  const rows = await sql`
    SELECT id, title, published_at, scraped_at, updated_at, source_url, date_source, date_confidence
    FROM press_releases
    WHERE id = '1387de7d-3d9c-4873-b050-e34b899029a6'
  `;
  for (const r of rows) {
    console.log("  id:", r.id);
    console.log("  title:", r.title.slice(0, 80));
    console.log("  published_at:", r.published_at);
    console.log("  scraped_at:  ", r.scraped_at);
    console.log("  updated_at:  ", r.updated_at);
    console.log("  source_url:  ", r.source_url);
    console.log("  date_source: ", r.date_source);
    console.log("  date_confidence:", r.date_confidence);
  }

  console.log("\n=== ALL future-dated releases (published_at > NOW()) ===");
  const future = await sql`
    SELECT senator_id, title, published_at, scraped_at, source_url, date_source
    FROM press_releases
    WHERE published_at > NOW() AND deleted_at IS NULL
    ORDER BY published_at DESC LIMIT 50
  `;
  console.log(`  ${future.length} records found`);
  for (const r of future) {
    const days = Math.round((new Date(r.published_at).getTime() - Date.now()) / 86400000);
    console.log(`  +${days}d ${r.published_at?.toISOString?.().slice(0, 16)} ${r.senator_id} ${r.date_source}: ${r.title.slice(0, 60)}`);
  }

  console.log("\n=== future-dated by senator ===");
  const bySenator = await sql`
    SELECT senator_id, count(*)::int as n, min(published_at) as earliest_future, max(published_at) as latest_future
    FROM press_releases
    WHERE published_at > NOW() AND deleted_at IS NULL
    GROUP BY senator_id ORDER BY n DESC
  `;
  for (const r of bySenator) {
    console.log(`  ${r.senator_id}: ${r.n} (${r.earliest_future?.toISOString?.().slice(0,10)} to ${r.latest_future?.toISOString?.().slice(0,10)})`);
  }

  console.log("\n=== probe Durbin source URL ===");
  const url = rows[0]?.source_url;
  if (url) {
    try {
      const res = await fetch(url, {
        headers: {
          "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
        },
      });
      const html = await res.text();
      // Try to extract date-related microdata/meta
      const datePublished = html.match(/datePublished["']?\s*[:=]\s*["']([^"']+)/i);
      const ogPublishedTime = html.match(/property=["']article:published_time["'][^>]+content=["']([^"']+)/i);
      const timeTag = html.match(/<time[^>]+datetime=["']([^"']+)/i);
      const visibleDate = html.match(/<p[^>]*class=["'][^"']*date[^"']*["'][^>]*>([^<]+)<\/p>/i);
      const mayMatch = html.match(/(May\s+0?[1-9]|May\s+[12]\d|May\s+3[01])\s*,?\s*2026/i);
      console.log(`  HTTP ${res.status}`);
      console.log(`  datePublished microdata:`, datePublished?.[1]);
      console.log(`  og:article:published_time:`, ogPublishedTime?.[1]);
      console.log(`  <time datetime>:`, timeTag?.[1]);
      console.log(`  .date <p>:`, visibleDate?.[1]?.trim());
      console.log(`  May 2026 mention in HTML:`, mayMatch?.[0]);
    } catch (e) {
      console.log("  fetch failed:", e.message);
    }
  }
}

main().catch((e) => { console.error(e); process.exit(1); });

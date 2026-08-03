// Pull every record currently failing the data-quality tests so we can see
// exactly what the cleanup target looks like.
import { neon } from "@neondatabase/serverless";
import { readFileSync } from "node:fs";

for (const envFile of [".env.local", ".env"]) {
  try {
    const c = readFileSync(envFile, "utf8");
    for (const line of c.split("\n")) {
      const m = line.match(/^([A-Z_]+)=(.*)$/);
      if (m && !process.env[m[1]]) process.env[m[1]] = m[2].replace(/^["']|["']$/g, "");
    }
  } catch {}
}

const sql = neon(process.env.DATABASE_URL);

async function main() {
  console.log("=== A. test_dates_in_valid_range (pre-2010 or > +60d) ===");
  const a = await sql`
    SELECT id, senator_id, title, source_url, published_at, scraped_at, date_source, date_confidence
    FROM press_releases
    WHERE deleted_at IS NULL
      AND published_at IS NOT NULL
      AND (published_at < '2010-01-01' OR published_at > NOW() + INTERVAL '60 days')
    ORDER BY published_at
  `;
  console.log(`  ${a.length} records`);
  for (const r of a) {
    console.log(`  ${r.id} ${r.senator_id} ${r.published_at?.toISOString?.().slice(0,10)} src=${r.date_source} conf=${r.date_confidence}`);
    console.log(`    title: ${(r.title ?? "").slice(0, 90)}`);
    console.log(`    url:   ${r.source_url}`);
  }

  console.log("\n=== B. test_all_urls_are_government (non-.gov) ===");
  const b = await sql`
    SELECT id, senator_id, title, source_url
    FROM press_releases
    WHERE deleted_at IS NULL AND source_url NOT LIKE '%.gov%'
    ORDER BY senator_id, source_url
  `;
  console.log(`  ${b.length} records`);
  for (const r of b) {
    console.log(`  ${r.id} ${r.senator_id}  ${r.source_url}`);
    console.log(`    title: ${(r.title ?? "").slice(0, 90)}`);
  }

  console.log("\n=== C. test_no_listing_page_urls ===");
  // Listing pages typically contain ?page= or end in /press-releases or /news
  const c = await sql`
    SELECT id, senator_id, title, source_url
    FROM press_releases
    WHERE deleted_at IS NULL AND (
      source_url ~* '(\\?|&)page=\\d+'
      OR source_url ~* '/press-releases/?$'
      OR source_url ~* '/news/?$'
      OR source_url ~* '/newsroom/?$'
      OR source_url ~* '/media/?$'
      OR source_url ~* '/page/\\d+/?$'
    )
    ORDER BY senator_id
  `;
  console.log(`  ${c.length} records`);
  for (const r of c) {
    console.log(`  ${r.id} ${r.senator_id}  ${r.source_url}`);
    console.log(`    title: ${(r.title ?? "").slice(0, 90)}`);
  }

  console.log("\n=== D. test_no_navigation_urls (heuristics) ===");
  const d = await sql`
    SELECT id, senator_id, title, source_url
    FROM press_releases
    WHERE deleted_at IS NULL AND (
      source_url ~* '/(contact|about|biography|services?|issues?|committees?|legislation|video|gallery|signup|subscribe|home)(/|$)'
      OR source_url ~* '/(facebook|twitter|youtube|instagram|tiktok|threads)\\.com'
    )
    ORDER BY senator_id
  `;
  console.log(`  ${d.length} records`);
  for (const r of d) {
    console.log(`  ${r.id} ${r.senator_id}  ${r.source_url}`);
    console.log(`    title: ${(r.title ?? "").slice(0, 90)}`);
  }
}

main().catch((e) => { console.error(e); process.exit(1); });

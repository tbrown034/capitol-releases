import { neon } from "@neondatabase/serverless";
import { readFileSync } from "node:fs";
for (const f of [".env.local", ".env"]) { try { for (const l of readFileSync(`/Users/home/Desktop/dev/active/capitol-releases/${f}`, "utf8").split("\n")) { const m = l.match(/^([A-Z_]+)=(.*)$/); if (m && !process.env[m[1]]) process.env[m[1]] = m[2].replace(/^["']|["']$/g, ""); } } catch {} }
const sql = neon(process.env.DATABASE_URL);

console.log("=== listing-page URLs (exact test pattern) ===");
const c = await sql`
  SELECT id, senator_id, title, source_url, scraped_at, content_type
  FROM press_releases
  WHERE deleted_at IS NULL
    AND (source_url ~ '/press-releases/?$' OR source_url ~ '/news-releases/?$' OR source_url ~ '/newsroom/?$' OR source_url ~ '/news/?$')
  ORDER BY senator_id
`;
console.log(`  ${c.length} records`);
for (const r of c) {
  console.log(`  ${r.id} ${r.senator_id} ${r.content_type}  ${r.source_url}`);
  console.log(`    title: ${(r.title ?? "").slice(0, 90)}`);
}

console.log("\n=== nav URLs (exact test pattern) ===");
const d = await sql`
  SELECT id, senator_id, title, source_url, content_type
  FROM press_releases
  WHERE deleted_at IS NULL
    AND (source_url ~ '/(about|contact|services|issues)(/?(\\?.*)?$)'
       OR source_url LIKE '%facebook.com%'
       OR source_url LIKE '%twitter.com%'
       OR source_url LIKE '%bsky.app%')
`;
console.log(`  ${d.length} records`);
for (const r of d) {
  console.log(`  ${r.id} ${r.senator_id} ${r.content_type}  ${r.source_url}`);
  console.log(`    title: ${(r.title ?? "").slice(0, 90)}`);
}

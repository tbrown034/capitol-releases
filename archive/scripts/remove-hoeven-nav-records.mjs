// Hard-removes 3 Hoeven records that are nav/contact pages, not press releases.
// They were collected by mistake and are the only remaining tombstones after
// the deletion-detector cleanup. Hard delete is appropriate because they were
// never legitimate press releases -- there's no archival value to preserving
// them.

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

const NAV_PAGE_URLS = [
  "https://www.hoeven.senate.gov/contact/e-newsletter-signup",
  "https://www.hoeven.senate.gov/postal-concerns",
  "https://www.hoeven.senate.gov/serving-you/finding-our-pow/mias",
];

async function main() {
  const before = await sql`
    SELECT id, title, source_url FROM press_releases WHERE source_url = ANY(${NAV_PAGE_URLS}::text[])
  `;
  console.log(`Found ${before.length} matching records:`);
  for (const r of before) console.log(`  ${r.id} ${r.source_url}  (title: "${r.title}")`);

  if (before.length === 0) {
    console.log("Nothing to delete.");
    return;
  }

  const ids = before.map((r) => r.id);
  // Drop any version history first (FK constraint safety).
  const cv = await sql`DELETE FROM content_versions WHERE press_release_id = ANY(${ids}::uuid[]) RETURNING id`;
  if (cv.length > 0) console.log(`removed ${cv.length} content_versions rows`);

  await sql`DELETE FROM press_releases WHERE id = ANY(${ids}::uuid[])`;
  console.log(`Deleted ${ids.length} press_releases rows.`);

  const left = await sql`SELECT count(*)::int as n FROM press_releases WHERE deleted_at IS NOT NULL`;
  console.log(`tombstoned remaining: ${left[0].n}`);
}

main().catch((e) => { console.error(e); process.exit(1); });

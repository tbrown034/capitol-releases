// Restore all currently-tombstoned releases EXCEPT those whose URL returns
// a confirmed 404 or 410 from a real-browser User-Agent right now. The bulk
// of the 1,286 original tombstones turned out to be detector false positives
// (98.3% returned 200). The remaining 370 are Akamai 403s -- unverifiable,
// but produced by the same broken detector run, so default to restoring.

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

// IDs that returned a 404 or 410 on a Safari-UA fetch in two consecutive
// re-verification runs. These four are kept tombstoned; the rest are restored.
const CONFIRMED_DELETED_URLS = [
  "https://www.hoeven.senate.gov/contact/e-newsletter-signup",
  "https://www.hoeven.senate.gov/postal-concerns",
  "https://www.hoeven.senate.gov/serving-you/finding-our-pow/mias",
  "https://www.wyden.senate.gov/news/press-releases/wyden-joins-colleagues-in-calling-for-immediate-cease-fire-in-gaza-as-cease-fire-in-lebanon-takes-effect",
];

async function main() {
  const before = await sql`SELECT count(*)::int as n FROM press_releases WHERE deleted_at IS NOT NULL`;
  console.log("currently tombstoned:", before[0].n);

  const result = await sql`
    UPDATE press_releases
    SET deleted_at = NULL,
        updated_at = NOW()
    WHERE deleted_at IS NOT NULL
      AND source_url <> ALL(${CONFIRMED_DELETED_URLS}::text[])
    RETURNING id
  `;
  console.log("restored:", result.length);

  const after = await sql`SELECT count(*)::int as n FROM press_releases WHERE deleted_at IS NOT NULL`;
  console.log("remaining tombstoned:", after[0].n);

  const remaining = await sql`
    SELECT senator_id, source_url FROM press_releases WHERE deleted_at IS NOT NULL
  `;
  for (const r of remaining) console.log(`  ${r.senator_id}: ${r.source_url}`);
}

main().catch((e) => { console.error(e); process.exit(1); });

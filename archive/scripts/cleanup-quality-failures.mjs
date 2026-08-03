// Hard-delete the 10 records currently failing data-quality tests:
//   - 1 Whitehouse 2007 release (out of corpus scope: Jan 2025+)
//   - 4 Hoeven social-media URLs (facebook/twitter/instagram/youtube; never
//     legitimate press releases, collector misfire)
//   - 5 listing-page URLs (the /press-releases or /news index pages
//     themselves got captured as releases on Cantwell/Graham/Hoeven/
//     Klobuchar/Thune; collector misfire)
// Hard delete (not tombstone) is correct because these were never
// legitimate releases — same logic as the 3 Hoeven nav pages removed earlier.

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

async function findAndDelete(label, predicateClause, params = []) {
  const findSql = `SELECT id, senator_id, source_url, title FROM press_releases WHERE deleted_at IS NULL AND ${predicateClause}`;
  const found = await sql.query(findSql, params);
  console.log(`\n${label}: ${found.length} matches`);
  for (const r of found) console.log(`  ${r.senator_id}  ${r.source_url}  (${(r.title ?? "").slice(0, 60)})`);
  if (found.length === 0) return 0;
  const ids = found.map((r) => r.id);
  await sql`DELETE FROM content_versions WHERE press_release_id = ANY(${ids}::uuid[])`;
  const delSql = `DELETE FROM press_releases WHERE id = ANY($1::uuid[])`;
  await sql.query(delSql, [ids]);
  return ids.length;
}

let total = 0;

total += await findAndDelete(
  "A. Implausible dates (pre-2010 or > +60d)",
  "published_at IS NOT NULL AND (published_at < '2010-01-01' OR published_at > NOW() + INTERVAL '60 days')"
);

total += await findAndDelete(
  "B. Non-.gov URLs",
  "source_url NOT LIKE '%.gov%'"
);

total += await findAndDelete(
  "C. Listing-page URLs",
  "(source_url ~ '/press-releases/?$' OR source_url ~ '/news-releases/?$' OR source_url ~ '/newsroom/?$' OR source_url ~ '/news/?$')"
);

total += await findAndDelete(
  "D. Navigation URLs (regex match)",
  `(source_url ~ '/(about|contact|services|issues)(/?(\\?.*)?$)' OR source_url LIKE '%facebook.com%' OR source_url LIKE '%twitter.com%' OR source_url LIKE '%bsky.app%')`
);

console.log(`\nTotal hard-deleted: ${total}`);

// Verify
console.log(`\n=== verify all four predicates now return 0 ===`);
for (const [label, sql_] of [
  ["A", `SELECT count(*)::int as n FROM press_releases WHERE deleted_at IS NULL AND published_at IS NOT NULL AND (published_at < '2010-01-01' OR published_at > NOW() + INTERVAL '60 days')`],
  ["B", `SELECT count(*)::int as n FROM press_releases WHERE deleted_at IS NULL AND source_url NOT LIKE '%.gov%'`],
  ["C", `SELECT count(*)::int as n FROM press_releases WHERE deleted_at IS NULL AND (source_url ~ '/press-releases/?$' OR source_url ~ '/news-releases/?$' OR source_url ~ '/newsroom/?$' OR source_url ~ '/news/?$')`],
  ["D", `SELECT count(*)::int as n FROM press_releases WHERE deleted_at IS NULL AND (source_url ~ '/(about|contact|services|issues)(/?(\\?.*)?$)' OR source_url LIKE '%facebook.com%' OR source_url LIKE '%twitter.com%' OR source_url LIKE '%bsky.app%')`],
]) {
  const r = await sql.query(sql_);
  console.log(`  ${label}: ${r[0].n}`);
}

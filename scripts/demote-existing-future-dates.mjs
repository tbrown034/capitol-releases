// One-shot: apply the new future-date demotion to records already in DB.
// Going forward, the collectors do this at ingest.

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

const before = await sql`
  SELECT id, senator_id, title, published_at, scraped_at, date_source, date_confidence
  FROM press_releases
  WHERE deleted_at IS NULL AND published_at > NOW() + INTERVAL '1 day'
`;
console.log(`${before.length} records currently future-dated:`);
for (const r of before) console.log(`  ${r.senator_id}  ${r.published_at?.toISOString?.().slice(0,10)}  ${r.date_source} (conf ${r.date_confidence})  ${r.title.slice(0,70)}`);

if (before.length === 0) process.exit(0);

await sql`
  UPDATE press_releases
  SET date_source = CASE
        WHEN date_source IS NULL OR date_source = '' THEN 'future_typo'
        WHEN date_source LIKE '%_future_typo' THEN date_source
        ELSE date_source || '_future_typo'
      END,
      date_confidence = LEAST(COALESCE(date_confidence, 0), 0.2),
      updated_at = NOW()
  WHERE deleted_at IS NULL AND published_at > NOW() + INTERVAL '1 day'
`;

const after = await sql`
  SELECT id, senator_id, date_source, date_confidence
  FROM press_releases
  WHERE deleted_at IS NULL AND published_at > NOW() + INTERVAL '1 day'
`;
console.log(`\nAfter:`);
for (const r of after) console.log(`  ${r.senator_id}  date_source=${r.date_source}  date_confidence=${r.date_confidence}`);

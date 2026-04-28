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

const UA =
  "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15";

const DRY_RUN = process.argv.includes("--dry-run");
const CONCURRENCY = 4;
const PAUSE_MS = 250;

async function probe(url) {
  const controller = new AbortController();
  const t = setTimeout(() => controller.abort(), 12000);
  try {
    const res = await fetch(url, {
      method: "GET",
      redirect: "follow",
      headers: {
        "User-Agent": UA,
        Accept: "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
      },
      signal: controller.signal,
    });
    clearTimeout(t);
    return res.status;
  } catch (e) {
    clearTimeout(t);
    return 0;
  }
}

async function main() {
  console.log(`Mode: ${DRY_RUN ? "DRY RUN" : "LIVE"}`);
  const rows = await sql`
    SELECT id, senator_id, source_url
    FROM press_releases WHERE deleted_at IS NOT NULL
    ORDER BY senator_id, source_url
  `;
  console.log(`Re-verifying ${rows.length} tombstoned releases with browser UA...`);

  const live = [];
  const stillGone = [];
  const errored = [];

  // simple chunked concurrency with politeness pause
  for (let i = 0; i < rows.length; i += CONCURRENCY) {
    const batch = rows.slice(i, i + CONCURRENCY);
    const results = await Promise.all(
      batch.map(async (r) => ({ row: r, status: await probe(r.source_url) }))
    );
    for (const { row, status } of results) {
      if (status === 200) live.push(row);
      else if (status === 404 || status === 410) stillGone.push({ row, status });
      else errored.push({ row, status });
    }
    if ((i + CONCURRENCY) % 120 === 0 || i + CONCURRENCY >= rows.length) {
      console.log(
        `  ${Math.min(i + CONCURRENCY, rows.length)}/${rows.length}  live=${live.length} 404/410=${stillGone.length} other=${errored.length}`
      );
    }
    await new Promise((r) => setTimeout(r, PAUSE_MS));
  }

  console.log("\n=== summary ===");
  console.log(`  live (false positives):    ${live.length}`);
  console.log(`  still 404/410 (genuine):   ${stillGone.length}`);
  console.log(`  other status / errors:     ${errored.length}`);

  if (errored.length > 0) {
    const byStatus = {};
    for (const e of errored) byStatus[e.status] = (byStatus[e.status] ?? 0) + 1;
    console.log(`  other status breakdown:`, byStatus);
  }

  if (stillGone.length > 0) {
    console.log("\n=== sample of genuine 404/410s ===");
    for (const { row, status } of stillGone.slice(0, 10)) {
      console.log(`  ${status} ${row.senator_id}: ${row.source_url.slice(0, 80)}`);
    }
    console.log("\n=== senators with confirmed deletions ===");
    const byS = {};
    for (const { row } of stillGone) byS[row.senator_id] = (byS[row.senator_id] ?? 0) + 1;
    for (const [sid, n] of Object.entries(byS).sort((a, b) => b[1] - a[1])) {
      console.log(`  ${sid}: ${n}`);
    }
  }

  if (DRY_RUN) {
    console.log("\nDRY RUN -- no DB changes made.");
    return;
  }

  if (live.length > 0) {
    const ids = live.map((r) => r.id);
    // restore in batches to avoid huge IN lists
    const BATCH = 500;
    for (let i = 0; i < ids.length; i += BATCH) {
      const slice = ids.slice(i, i + BATCH);
      await sql`
        UPDATE press_releases
        SET deleted_at = NULL,
            last_seen_live = NOW(),
            updated_at = NOW()
        WHERE id = ANY(${slice}::uuid[])
      `;
    }
    console.log(`\nRestored ${ids.length} false-positive tombstones.`);
  }

  if (errored.length > 0) {
    console.log(
      `\nLeft ${errored.length} non-404/non-200 records as-is for manual triage.`
    );
  }
}

main().catch((e) => { console.error(e); process.exit(1); });

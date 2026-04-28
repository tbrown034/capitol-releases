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
  const [{ total_releases }] = await sql`SELECT count(*)::int as total_releases FROM press_releases WHERE deleted_at IS NULL`;
  const [{ total_versions }] = await sql`SELECT count(*)::int as total_versions FROM content_versions`;
  const [{ releases_with_versions }] = await sql`SELECT count(DISTINCT press_release_id)::int as releases_with_versions FROM content_versions`;
  const [{ deleted_count }] = await sql`SELECT count(*)::int as deleted_count FROM press_releases WHERE deleted_at IS NOT NULL`;

  console.log("=== overall ===");
  console.log("total non-deleted releases:", total_releases.toLocaleString());
  console.log("total content_versions rows:", total_versions.toLocaleString());
  console.log("releases with at least 1 prior version:", releases_with_versions.toLocaleString());
  console.log("releases tombstoned (deleted_at IS NOT NULL):", deleted_count.toLocaleString());
  console.log("edit rate:", `${((releases_with_versions / total_releases) * 100).toFixed(2)}%`);

  console.log("\n=== version distribution ===");
  const dist = await sql`
    SELECT version_count, count(*)::int as releases
    FROM (
      SELECT press_release_id, count(*) AS version_count
      FROM content_versions GROUP BY press_release_id
    ) sub
    GROUP BY version_count ORDER BY version_count
  `;
  for (const r of dist) console.log(`  ${r.version_count} prior version(s): ${r.releases.toLocaleString()} releases`);

  console.log("\n=== top 10 most-edited releases ===");
  const top = await sql`
    SELECT pr.id, pr.title, pr.senator_id, count(cv.id)::int as versions, max(cv.captured_at) as latest_edit
    FROM content_versions cv
    JOIN press_releases pr ON pr.id = cv.press_release_id
    GROUP BY pr.id, pr.title, pr.senator_id
    ORDER BY versions DESC, latest_edit DESC
    LIMIT 10
  `;
  for (const r of top) console.log(`  ${r.versions}x  ${r.senator_id}  ${r.title.slice(0, 80)}`);

  console.log("\n=== edits over time (by month) ===");
  const monthly = await sql`
    SELECT date_trunc('month', captured_at)::date as month, count(*)::int as edits, count(DISTINCT press_release_id)::int as releases_edited
    FROM content_versions
    GROUP BY 1 ORDER BY 1 DESC LIMIT 12
  `;
  for (const r of monthly) console.log(`  ${r.month.toISOString().slice(0,10)}: ${r.edits} edits across ${r.releases_edited} releases`);

  console.log("\n=== edit timing relative to publication ===");
  const timing = await sql`
    SELECT
      sum(CASE WHEN cv.captured_at - pr.published_at < INTERVAL '1 hour' THEN 1 ELSE 0 END)::int as within_1h,
      sum(CASE WHEN cv.captured_at - pr.published_at BETWEEN INTERVAL '1 hour' AND INTERVAL '24 hours' THEN 1 ELSE 0 END)::int as within_24h,
      sum(CASE WHEN cv.captured_at - pr.published_at BETWEEN INTERVAL '24 hours' AND INTERVAL '7 days' THEN 1 ELSE 0 END)::int as within_week,
      sum(CASE WHEN cv.captured_at - pr.published_at > INTERVAL '7 days' THEN 1 ELSE 0 END)::int as after_week
    FROM content_versions cv
    JOIN press_releases pr ON pr.id = cv.press_release_id
    WHERE pr.published_at IS NOT NULL
  `;
  console.log(`  within 1 hour of publish: ${timing[0].within_1h}`);
  console.log(`  1h - 24h after publish:   ${timing[0].within_24h}`);
  console.log(`  1d - 7d after publish:    ${timing[0].within_week}`);
  console.log(`  more than a week later:   ${timing[0].after_week}`);

  console.log("\n=== deletions over time (last 12 months) ===");
  const delMonthly = await sql`
    SELECT date_trunc('month', deleted_at)::date as month, count(*)::int as deletions
    FROM press_releases WHERE deleted_at IS NOT NULL
    GROUP BY 1 ORDER BY 1 DESC LIMIT 12
  `;
  for (const r of delMonthly) console.log(`  ${r.month.toISOString().slice(0,10)}: ${r.deletions} deletions`);

  console.log("\n=== senators with most deletions ===");
  const delBySenator = await sql`
    SELECT senator_id, count(*)::int as deletions FROM press_releases WHERE deleted_at IS NOT NULL
    GROUP BY senator_id ORDER BY deletions DESC LIMIT 10
  `;
  for (const r of delBySenator) console.log(`  ${r.senator_id}: ${r.deletions}`);
}

main().catch((e) => { console.error(e); process.exit(1); });

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

async function fetchStatus(url) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 10000);
  try {
    const res = await fetch(url, {
      method: "GET",
      redirect: "manual",
      headers: {
        "User-Agent":
          "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
        Accept: "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
      },
      signal: controller.signal,
    });
    clearTimeout(timer);
    const status = res.status;
    const location = res.headers.get("location");
    let bodyHint = "";
    if (status >= 200 && status < 300) {
      const text = await res.text();
      // Look for canonical/og:url that may point elsewhere
      const canonical = text.match(/<link[^>]+rel=["']canonical["'][^>]+href=["']([^"']+)["']/i);
      const ogUrl = text.match(/property=["']og:url["'][^>]+content=["']([^"']+)["']/i);
      const titleM = text.match(/<title[^>]*>([^<]*)<\/title>/i);
      bodyHint = ` title="${(titleM?.[1] ?? "").trim().slice(0, 60)}"`;
      if (canonical) bodyHint += ` canonical=${canonical[1].slice(0, 80)}`;
      if (ogUrl) bodyHint += ` ogurl=${ogUrl[1].slice(0, 80)}`;
    }
    return { status, location, bodyHint };
  } catch (e) {
    clearTimeout(timer);
    return { status: 0, location: null, bodyHint: ` ERR ${e.message ?? e}` };
  }
}

async function main() {
  console.log("=== sampling 15 King deletions ===");
  const sample = await sql`
    SELECT id, title, source_url, published_at, deleted_at
    FROM press_releases
    WHERE senator_id = 'king-angus' AND deleted_at IS NOT NULL
    ORDER BY random() LIMIT 15
  `;

  for (const r of sample) {
    console.log(`\n--- ${r.id.slice(0, 8)} ---`);
    console.log(`  title:     ${(r.title ?? "").slice(0, 90)}`);
    console.log(`  url:       ${r.source_url}`);
    console.log(`  published: ${r.published_at?.toISOString?.().slice(0, 10) ?? r.published_at}`);
    console.log(`  deleted:   ${r.deleted_at?.toISOString?.().slice(0, 10) ?? r.deleted_at}`);
    const { status, location, bodyHint } = await fetchStatus(r.source_url);
    console.log(`  HTTP:      ${status}${location ? ` -> ${location}` : ""}${bodyHint}`);
  }

  console.log("\n=== King URL pattern audit ===");
  const patterns = await sql`
    SELECT
      CASE
        WHEN source_url LIKE '%/news/press-releases/%' THEN '/news/press-releases/'
        WHEN source_url LIKE '%/imo/media/%' THEN '/imo/media/'
        WHEN source_url LIKE '%/public/index.cfm%' THEN '/public/index.cfm'
        WHEN source_url LIKE '%king.senate.gov/newsroom%' THEN '/newsroom'
        ELSE 'other'
      END as pattern,
      deleted_at IS NOT NULL as is_deleted,
      count(*)::int as n
    FROM press_releases WHERE senator_id = 'king-angus'
    GROUP BY 1, 2 ORDER BY 1, 2
  `;
  for (const r of patterns) console.log(`  ${r.pattern.padEnd(28)} deleted=${r.is_deleted} count=${r.n}`);

  console.log("\n=== Heinrich URL pattern audit ===");
  const hPatterns = await sql`
    SELECT
      regexp_replace(source_url, '^https?://([^/]+).*$', '\\1') as host,
      deleted_at IS NOT NULL as is_deleted,
      count(*)::int as n
    FROM press_releases WHERE senator_id = 'heinrich-martin'
    GROUP BY 1, 2 ORDER BY 1, 2
  `;
  for (const r of hPatterns) console.log(`  ${r.host.padEnd(40)} deleted=${r.is_deleted} count=${r.n}`);

  console.log("\n=== Graham URL pattern audit ===");
  const gPatterns = await sql`
    SELECT
      regexp_replace(source_url, '^https?://([^/]+)(/[^/]+/?[^/]*).*$', '\\1\\2') as url_root,
      deleted_at IS NOT NULL as is_deleted,
      count(*)::int as n
    FROM press_releases WHERE senator_id = 'graham-lindsey'
    GROUP BY 1, 2 ORDER BY 1, 2 LIMIT 20
  `;
  for (const r of gPatterns) console.log(`  ${(r.url_root ?? "").padEnd(60)} deleted=${r.is_deleted} count=${r.n}`);
}

main().catch((e) => { console.error(e); process.exit(1); });

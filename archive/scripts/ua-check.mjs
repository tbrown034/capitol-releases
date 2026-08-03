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

const UAS = {
  python: "python-httpx/0.27.0",
  curl: "curl/8.6.0",
  capitol: "CapitolReleasesBot/1.0 (+https://capitolreleases.com/about)",
  safari:
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
};

async function probe(url, ua) {
  const controller = new AbortController();
  const t = setTimeout(() => controller.abort(), 8000);
  try {
    const res = await fetch(url, {
      method: "GET",
      redirect: "follow",
      headers: { "User-Agent": ua },
      signal: controller.signal,
    });
    clearTimeout(t);
    return res.status;
  } catch (e) {
    clearTimeout(t);
    return `ERR:${e.message?.slice(0, 30) ?? e}`;
  }
}

async function main() {
  const senators = ["king-angus", "heinrich-martin", "graham-lindsey"];
  for (const sid of senators) {
    console.log(`\n=== ${sid} (5 deleted URLs) ===`);
    const sample = await sql`
      SELECT source_url FROM press_releases
      WHERE senator_id = ${sid} AND deleted_at IS NOT NULL
      ORDER BY random() LIMIT 5
    `;
    for (const r of sample) {
      const u = r.source_url;
      const results = await Promise.all(
        Object.entries(UAS).map(async ([name, ua]) => [name, await probe(u, ua)])
      );
      const summary = results.map(([n, s]) => `${n}=${s}`).join(" ");
      console.log(`  ${summary}  ${u.slice(0, 70)}...`);
    }
  }
}

main().catch((e) => { console.error(e); process.exit(1); });

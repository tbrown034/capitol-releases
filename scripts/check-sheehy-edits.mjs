import { neon } from "@neondatabase/serverless";
import { readFileSync } from "node:fs";
import { createHash } from "node:crypto";

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
  console.log("=== Sample 5 Sheehy 'edits': compare current body to archived prior body ===");
  const rows = await sql`
    SELECT pr.id, pr.title, pr.body_text as current_body, pr.content_hash as current_hash,
           cv.body_text as prior_body, cv.content_hash as prior_hash, cv.captured_at
    FROM content_versions cv
    JOIN press_releases pr ON pr.id = cv.press_release_id
    WHERE pr.senator_id = 'sheehy-tim'
    ORDER BY cv.captured_at DESC
    LIMIT 5
  `;
  for (const r of rows) {
    const sha = (s) => s ? createHash("sha256").update(s).digest("hex").slice(0, 12) : "(null)";
    const norm = (s) => (s ?? "").replace(/\s+/g, " ").trim();
    const curN = norm(r.current_body);
    const prevN = norm(r.prior_body);
    console.log(`\n  ${r.title.slice(0, 70)}`);
    console.log(`    current_hash: ${r.current_hash} sha(body): ${sha(r.current_body)}  len=${(r.current_body ?? "").length}`);
    console.log(`    prior_hash:   ${r.prior_hash} sha(body): ${sha(r.prior_body)}  len=${(r.prior_body ?? "").length}`);
    console.log(`    normalized identical? ${curN === prevN ? "YES (whitespace-only diff)" : "NO -- real text change"}`);
    if (curN !== prevN) {
      // Show first 100 chars of each side
      const curStart = curN.slice(0, 120);
      const prvStart = prevN.slice(0, 120);
      if (curStart !== prvStart) {
        console.log(`    cur start: ${curStart}`);
        console.log(`    prv start: ${prvStart}`);
      } else {
        console.log(`    starts match -- diff later in body`);
      }
    }
  }
}

main().catch((e) => { console.error(e); process.exit(1); });

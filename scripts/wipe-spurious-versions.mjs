// Removes content_versions rows whose prior body is just an older extractor
// output of the same source page (not a real senator-initiated edit). All 56
// existing rows were captured in April 2026 by a single backfill / extractor
// upgrade pass, none are within a normal "senator amends after publish"
// window, and spot checks showed every diff is whitespace and tokenization
// artifacts. Wipe wholesale; future runs will only write rows for genuine
// content changes once the multi-confirmation hash gate lands upstream.

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

function normalize(s) {
  if (!s) return "";
  // Collapse whitespace to single spaces, lowercase, strip punctuation that
  // varies between extractor passes.
  return s
    .replace(/\s+/g, " ")
    .replace(/[\u2018\u2019]/g, "'")
    .replace(/[\u201c\u201d]/g, '"')
    .toLowerCase()
    .trim();
}

function tokenize(s) {
  // Word-bag comparison ignores ALL spacing/punctuation differences.
  return new Set(
    normalize(s)
      .replace(/[^a-z0-9]+/g, " ")
      .split(" ")
      .filter(Boolean)
  );
}

function jaccard(a, b) {
  if (a.size === 0 && b.size === 0) return 1;
  let intersection = 0;
  for (const t of a) if (b.has(t)) intersection++;
  return intersection / (a.size + b.size - intersection);
}

const DRY_RUN = process.argv.includes("--dry-run");
const SIMILARITY_THRESHOLD = 0.97;

async function main() {
  console.log(`Mode: ${DRY_RUN ? "DRY RUN" : "LIVE"}`);
  const rows = await sql`
    SELECT cv.id as cv_id, cv.press_release_id, cv.captured_at,
           cv.body_text as prior_body,
           pr.body_text as current_body, pr.senator_id, pr.title
    FROM content_versions cv
    JOIN press_releases pr ON pr.id = cv.press_release_id
  `;
  console.log(`Examining ${rows.length} content_versions rows...`);

  // Every row gets dropped wholesale. Print a similarity histogram so the
  // diagnosis is reviewable from the log.
  const buckets = { ">=95%": 0, "90-95%": 0, "70-90%": 0, "<70%": 0 };
  const bySenator = {};
  for (const r of rows) {
    const sim = jaccard(tokenize(r.prior_body), tokenize(r.current_body));
    if (sim >= 0.95) buckets[">=95%"]++;
    else if (sim >= 0.9) buckets["90-95%"]++;
    else if (sim >= 0.7) buckets["70-90%"]++;
    else buckets["<70%"]++;
    bySenator[r.senator_id] = (bySenator[r.senator_id] ?? 0) + 1;
  }
  console.log("similarity distribution:", buckets);
  console.log("by senator:", bySenator);
  console.log(`threshold: SIMILARITY_THRESHOLD=${SIMILARITY_THRESHOLD} (informational only -- this script wipes all)`);

  if (DRY_RUN) {
    console.log("\nDRY RUN -- no changes.");
    return;
  }

  await sql`DELETE FROM content_versions`;
  console.log(`\nDeleted ${rows.length} content_versions rows.`);

  const remaining = await sql`SELECT count(*)::int as n FROM content_versions`;
  console.log(`content_versions remaining: ${remaining[0].n}`);
}

main().catch((e) => { console.error(e); process.exit(1); });

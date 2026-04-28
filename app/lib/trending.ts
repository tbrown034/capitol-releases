import { sql } from "./db";

const STOPWORDS = [
  "senator","senators","press","release","statement",
  "announce","announces","urge","urges","call","calls","join","joins",
  "lead","leads","support","supports","introduce","introduces",
  "legislation","bipartisan","their","about","after","would","could",
  "should","which","where","other","there","these","those","being",
  "through","between","under","during","before","above","below",
  "against","without","within","along","among","across","behind",
  "beyond","since","until","while","around","inside","outside",
  "today","more","than","from","this","that","with","have","will",
  "into","over","your","what","when","they","them","also",
];

/**
 * Trending now: words from titles in the last 30 days vs the 30 days before,
 * with the delta. Returns up to 30 stems.
 */
export async function getTrendingWithDelta() {
  return sql`
    WITH recent AS (
      SELECT DISTINCT pr.id,
        regexp_replace(
          lower(unnest(string_to_array(
            regexp_replace(pr.title, '[^a-zA-Z ]', '', 'g'), ' '
          ))),
          's$', ''
        ) as word
      FROM press_releases pr
      WHERE pr.published_at >= NOW() - interval '30 days'
        AND pr.deleted_at IS NULL
        AND pr.content_type != 'photo_release'
    ),
    prior AS (
      SELECT DISTINCT pr.id,
        regexp_replace(
          lower(unnest(string_to_array(
            regexp_replace(pr.title, '[^a-zA-Z ]', '', 'g'), ' '
          ))),
          's$', ''
        ) as word
      FROM press_releases pr
      WHERE pr.published_at >= NOW() - interval '60 days'
        AND pr.published_at < NOW() - interval '30 days'
        AND pr.deleted_at IS NULL
        AND pr.content_type != 'photo_release'
    ),
    rcounts AS (
      SELECT word, count(*)::int as cnt FROM recent
      WHERE length(word) > 4
        AND word != ALL(${STOPWORDS}::text[])
      GROUP BY word
    ),
    pcounts AS (
      SELECT word, count(*)::int as cnt FROM prior
      WHERE length(word) > 4
        AND word != ALL(${STOPWORDS}::text[])
      GROUP BY word
    )
    SELECT
      r.word,
      r.cnt as recent_count,
      coalesce(p.cnt, 0) as prior_count,
      r.cnt - coalesce(p.cnt, 0) as delta
    FROM rcounts r
    LEFT JOIN pcounts p ON p.word = r.word
    WHERE r.cnt >= 3
    ORDER BY r.cnt DESC
    LIMIT 30
  `;
}

/**
 * For a list of terms, return the top 3 senators by full-text mentions
 * since Jan 1, 2025. One row per (term, senator).
 */
export async function getTopicOwnership(terms: string[]) {
  if (terms.length === 0) return [] as TopicOwnerRow[];
  const cleaned = terms
    .map((t) => t.trim().replace(/[^a-zA-Z0-9 \-']/g, "").slice(0, 40))
    .filter(Boolean);
  if (cleaned.length === 0) return [] as TopicOwnerRow[];

  const results = await Promise.all(
    cleaned.map(
      (term) => sql`
        SELECT ${term}::text as term,
               s.id as senator_id,
               s.full_name,
               s.party,
               s.state,
               count(pr.id)::int as count
        FROM senators s
        JOIN press_releases pr ON pr.senator_id = s.id
        WHERE s.status = 'active'
          AND s.chamber = 'senate'
          AND pr.deleted_at IS NULL
          AND pr.content_type != 'photo_release'
          AND pr.published_at IS NOT NULL
          AND pr.published_at >= '2025-01-01'
          AND pr.fts @@ websearch_to_tsquery('english', ${term})
        GROUP BY s.id, s.full_name, s.party, s.state
        ORDER BY count DESC
        LIMIT 3
      `
    )
  );

  return results.flat() as TopicOwnerRow[];
}

export type TopicOwnerRow = {
  term: string;
  senator_id: string;
  full_name: string;
  party: "D" | "R" | "I";
  state: string;
  count: number;
};

/**
 * Party skew: log-odds for words used disproportionately by Democrats vs
 * Republicans (titles, since 2025-01-01). Returns top tilted terms in each
 * direction.
 */
export async function getPartySkew(limit = 12) {
  return sql`
    WITH all_words AS (
      SELECT pr.id,
             lower(unnest(string_to_array(
               regexp_replace(coalesce(pr.title, ''), '[^a-zA-Z ]', ' ', 'g'),
               ' '
             ))) as word,
             s.party
      FROM press_releases pr
      JOIN senators s ON s.id = pr.senator_id
      WHERE pr.deleted_at IS NULL
        AND pr.content_type != 'photo_release'
        AND pr.published_at >= '2025-01-01'
        AND s.status = 'active'
        AND s.chamber = 'senate'
        AND s.party IN ('D','R')
    ),
    cleaned AS (
      SELECT regexp_replace(word, 's$', '') as word, party
      FROM all_words
      WHERE length(word) > 4
        AND word != ALL(${STOPWORDS}::text[])
    ),
    counts AS (
      SELECT word,
             sum(CASE WHEN party='D' THEN 1 ELSE 0 END)::numeric as d_count,
             sum(CASE WHEN party='R' THEN 1 ELSE 0 END)::numeric as r_count
      FROM cleaned
      GROUP BY word
      HAVING count(*) >= 12
    ),
    totals AS (
      SELECT
        sum(d_count) as d_total,
        sum(r_count) as r_total
      FROM counts
    ),
    scored AS (
      SELECT
        c.word,
        c.d_count::int as d_count,
        c.r_count::int as r_count,
        ln(((c.d_count + 1) / (t.d_total + 1)) /
           ((c.r_count + 1) / (t.r_total + 1))) as log_odds
      FROM counts c, totals t
    ),
    picked AS (
      (SELECT word, d_count, r_count, log_odds, 'D'::text as side
         FROM scored ORDER BY log_odds DESC LIMIT ${limit})
      UNION ALL
      (SELECT word, d_count, r_count, log_odds, 'R'::text as side
         FROM scored ORDER BY log_odds ASC LIMIT ${limit})
    )
    SELECT word, d_count, r_count, log_odds, side
    FROM picked
    ORDER BY side, abs(log_odds) DESC
  `;
}

/**
 * For a single term: weekly counts since Jan 2025 + top 1 headline per
 * spike week (highest-volume weeks).
 */
export async function getTermTimeline(term: string) {
  const cleaned = term.trim().replace(/[^a-zA-Z0-9 \-']/g, "").slice(0, 40);
  if (!cleaned) return { weekly: [], spikeHeadlines: [], term: "" };

  const weekly = (await sql`
    SELECT to_char(date_trunc('week', published_at), 'YYYY-MM-DD') as week,
           count(*)::int as count
    FROM press_releases
    WHERE published_at >= '2025-01-01'
      AND published_at IS NOT NULL
      AND deleted_at IS NULL
      AND content_type != 'photo_release'
      AND fts @@ websearch_to_tsquery('english', ${cleaned})
    GROUP BY week
    ORDER BY week
  `) as { week: string; count: number }[];

  const top5 = [...weekly]
    .sort((a, b) => b.count - a.count)
    .slice(0, 5)
    .map((r) => r.week);

  const spikeHeadlines =
    top5.length === 0
      ? []
      : ((await sql`
          SELECT DISTINCT ON (date_trunc('week', pr.published_at))
                 to_char(date_trunc('week', pr.published_at), 'YYYY-MM-DD') as week,
                 pr.title,
                 pr.source_url,
                 to_char(pr.published_at, 'YYYY-MM-DD') as published_at,
                 s.full_name as senator_name,
                 s.party,
                 s.state,
                 s.id as senator_id
          FROM press_releases pr
          JOIN senators s ON s.id = pr.senator_id
          WHERE pr.published_at >= '2025-01-01'
            AND pr.published_at IS NOT NULL
            AND pr.deleted_at IS NULL
            AND pr.content_type != 'photo_release'
            AND pr.fts @@ websearch_to_tsquery('english', ${cleaned})
            AND to_char(date_trunc('week', pr.published_at), 'YYYY-MM-DD')
                = ANY(${top5}::text[])
          ORDER BY date_trunc('week', pr.published_at), pr.published_at
        `) as TermSpikeHeadline[]);

  return { weekly, spikeHeadlines, term: cleaned };
}

export type TermSpikeHeadline = {
  week: string;
  title: string;
  source_url: string;
  published_at: string;
  senator_name: string;
  party: "D" | "R" | "I";
  state: string;
  senator_id: string;
};

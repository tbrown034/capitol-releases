import { sql } from "./db";
import type { FeedItem, ContentType } from "./db";

export const TX_CHAMBER = "tx_senate" as const;
export const TX_TOTAL_SEATS = 31;

export type TxSenator = {
  id: string;
  full_name: string;
  party: "D" | "R" | "I";
  district: number;
  official_url: string;
  press_release_url: string | null;
  release_count: number;
  latest_release: string | null;
  earliest_release: string | null;
};

export async function getTxRoster(): Promise<TxSenator[]> {
  const rows = (await sql`
    SELECT
      s.id, s.full_name, s.party,
      (s.scrape_config->>'district')::int AS district,
      s.official_url, s.press_release_url,
      count(pr.id)::int AS release_count,
      max(pr.published_at) AS latest_release,
      min(pr.published_at) AS earliest_release
    FROM senators s
    LEFT JOIN press_releases pr
      ON pr.senator_id = s.id
     AND pr.deleted_at IS NULL
     AND pr.content_type != 'photo_release'
    WHERE s.chamber = ${TX_CHAMBER}
    GROUP BY s.id
    ORDER BY (s.scrape_config->>'district')::int
  `) as TxSenator[];
  return rows.map((r) => {
    if (r.district == null) {
      const m = r.id.match(/^tx-d(\d{2})-/);
      return { ...r, district: m ? Number(m[1]) : 0 };
    }
    return r;
  });
}

export async function getTxStats() {
  const rows = (await sql`
    SELECT
      count(DISTINCT pr.id)::int AS total_releases,
      count(DISTINCT pr.senator_id)::int AS senators_with_releases,
      count(DISTINCT s.id)::int AS total_senators,
      min(pr.published_at) AS earliest,
      max(pr.published_at) AS latest
    FROM senators s
    LEFT JOIN press_releases pr
      ON pr.senator_id = s.id
     AND pr.deleted_at IS NULL
     AND pr.content_type != 'photo_release'
    WHERE s.chamber = ${TX_CHAMBER}
  `) as {
    total_releases: number;
    senators_with_releases: number;
    total_senators: number;
    earliest: string | null;
    latest: string | null;
  }[];
  return rows[0];
}

export async function getTxLatestReleases(limit = 12) {
  return (await sql`
    SELECT pr.id, pr.senator_id, pr.title, pr.published_at, pr.body_text,
           pr.source_url, pr.scraped_at, pr.content_type,
           s.full_name AS senator_name, s.party, s.state
    FROM press_releases pr
    JOIN senators s ON s.id = pr.senator_id
    WHERE s.chamber = ${TX_CHAMBER}
      AND pr.deleted_at IS NULL
      AND pr.content_type != 'photo_release'
    ORDER BY LEAST(pr.published_at, pr.scraped_at) DESC NULLS LAST
    LIMIT ${limit}
  `) as FeedItem[];
}

export async function getTxMonthlyVolume() {
  return (await sql`
    SELECT to_char(date_trunc('month', published_at), 'YYYY-MM-DD') AS month,
           count(*)::int AS count
    FROM press_releases pr
    JOIN senators s ON s.id = pr.senator_id
    WHERE s.chamber = ${TX_CHAMBER}
      AND pr.deleted_at IS NULL
      AND pr.content_type != 'photo_release'
      AND pr.published_at >= '2025-01-01'
    GROUP BY month
    ORDER BY month
  `) as { month: string; count: number }[];
}

export async function getTxTopicTrends(limit = 24) {
  // Per-corpus topic extraction. Senate of Texas surnames + state-government
  // procedural vocabulary are filtered out to surface real subject matter.
  return (await sql`
    WITH stems AS (
      SELECT DISTINCT pr.id,
        regexp_replace(
          lower(unnest(string_to_array(
            regexp_replace(pr.title, '[^a-zA-Z ]', '', 'g'), ' '
          ))),
          's$', ''
        ) AS word
      FROM press_releases pr
      JOIN senators s ON s.id = pr.senator_id
      WHERE s.chamber = ${TX_CHAMBER}
        AND pr.deleted_at IS NULL
        AND pr.content_type != 'photo_release'
    ),
    surnames AS (
      SELECT DISTINCT regexp_replace(lower(split_part(full_name, ' ', -1)), 's$', '') AS s
      FROM senators WHERE chamber = ${TX_CHAMBER}
    )
    SELECT word, count(*)::int AS count
    FROM stems
    WHERE length(word) > 4
      AND word NOT IN (SELECT s FROM surnames)
      AND word NOT IN (
        'texas','senator','senate','press','release','statement','today',
        'about','their','after','would','should','which','where','these',
        'those','being','through','before','during','against','within',
        'among','sponsored','introduce','announce','support','passe',
        'announces','passes','passed','introduces','introduced','signed',
        'urging','urges','calls','statements','releases','letter','letters',
        'committee','district','member','members','official','president',
        'governor','speaker','house','representative','representatives',
        'video','watch','highlight','highlights','listen','photo','photos',
        'release','passage','regarding','sponsor','sponsors','sponsored'
      )
    GROUP BY word
    HAVING count(*) >= 3
    ORDER BY count DESC
    LIMIT ${limit}
  `) as { word: string; count: number }[];
}

export async function getTxSenatorTopicTrends(senatorId: string, limit = 12) {
  // For a single TX senator. Compares title-word frequency in the most
  // recent 60 days vs prior 60 days. Only emits words appearing >=2 times in
  // the recent window — at TX volume that's the floor for any signal.
  return (await sql`
    WITH word_releases AS (
      SELECT DISTINCT pr.id,
                      lower(unnest(string_to_array(
                        regexp_replace(
                          coalesce(pr.title, '') || ' ' || coalesce(pr.body_text, ''),
                          '[^a-zA-Z ]', ' ', 'g'
                        ),
                        ' '
                      ))) AS word,
                      pr.published_at
      FROM press_releases pr
      WHERE pr.senator_id = ${senatorId}
        AND pr.deleted_at IS NULL
        AND pr.content_type != 'photo_release'
        AND pr.published_at >= NOW() - INTERVAL '120 days'
    )
    SELECT word,
           count(*) FILTER (WHERE published_at >= NOW() - interval '60 days')::int AS recent_count,
           count(*) FILTER (WHERE published_at <  NOW() - interval '60 days')::int AS prior_count
    FROM word_releases
    WHERE length(word) > 4
      AND word NOT IN (
        'texas','senator','senate','press','release','statement','today',
        'about','their','after','would','should','which','where','these',
        'those','being','through','before','during','against','within',
        'among','sponsored','introduce','announce','support','passe',
        'announces','passes','passed','introduces','introduced','signed',
        'urging','urges','calls','statements','releases','letter','letters',
        'committee','district','member','members','official','president',
        'governor','passage','regarding','blanco','bettencourt','hinojosa',
        'nichols','eckhardt','zaffirini','kolkhorst','huffman','parker',
        'west','birdwell','middleton','hughes','paxton','sparks','cook',
        'johnson','flores','miles','alvarado','rehmet','hagenbuch',
        'campbell','menendez','schwertner','perry','hall','king','gutierrez'
      )
    GROUP BY word
    HAVING count(*) FILTER (WHERE published_at >= NOW() - interval '60 days') >= 2
    ORDER BY recent_count DESC, prior_count ASC
    LIMIT ${limit}
  `) as { word: string; recent_count: number; prior_count: number }[];
}

export async function getTxSenatorSignatureTopics(
  senatorId: string,
  limit = 12
) {
  // Words this senator uses disproportionately vs the rest of the TX
  // chamber. Uses log-odds with Laplace smoothing — same approach as the
  // US senator page, but computed within the TX chamber only so
  // distinctive vocabulary is relative to peers.
  return (await sql`
    WITH all_words AS (
      SELECT pr.id,
             lower(unnest(string_to_array(
               regexp_replace(coalesce(pr.title, ''), '[^a-zA-Z ]', ' ', 'g'),
               ' '
             ))) AS word,
             (pr.senator_id = ${senatorId}) AS is_self
      FROM press_releases pr
      JOIN senators s ON s.id = pr.senator_id
      WHERE s.chamber = ${TX_CHAMBER}
        AND pr.deleted_at IS NULL
        AND pr.content_type != 'photo_release'
        AND pr.published_at >= '2025-01-01'
    ),
    filtered AS (
      SELECT word, is_self FROM all_words
      WHERE length(word) > 4
        AND word NOT IN (
          'texas','senator','senate','press','release','statement','today',
          'about','their','after','would','should','which','where','these',
          'those','being','through','before','during','against','within',
          'among','sponsored','introduce','announce','support','passe',
          'announces','passes','passed','introduces','introduced','signed',
          'urging','urges','calls','statements','releases','letter','letters',
          'committee','district','member','members','official','president',
          'governor','passage','regarding','sponsor','sponsors','sponsored',
          'release','releases','statement','statements','letter','letters'
        )
    ),
    counts AS (
      SELECT word,
             count(*) FILTER (WHERE is_self)::numeric AS self_n,
             count(*) FILTER (WHERE NOT is_self)::numeric AS rest_n
      FROM filtered
      GROUP BY word
    ),
    totals AS (
      SELECT sum(self_n) AS self_total, sum(rest_n) AS rest_total FROM counts
    )
    SELECT word,
           self_n::int AS self_count,
           rest_n::int AS rest_count,
           ln((self_n + 1) / (totals.self_total - self_n + 1)) -
           ln((rest_n + 1) / (totals.rest_total - rest_n + 1)) AS log_odds
    FROM counts, totals
    WHERE self_n >= 2
    ORDER BY log_odds DESC
    LIMIT ${limit}
  `) as {
    word: string;
    self_count: number;
    rest_count: number;
    log_odds: string;
  }[];
}

export async function getTxSearchFacets(filters: {
  search: string;
  party?: string;
  type?: string;
  district?: string;
}) {
  // Lightweight facet bar for /texas/search. Counts party split + type split
  // (district is used as the primary filter elsewhere so not faceted).
  const search = filters.search;
  if (!search) {
    return {
      party: { D: 0, R: 0, I: 0 },
      type: {} as Partial<Record<ContentType, number>>,
    };
  }

  const partyRows = (await sql`
    SELECT s.party AS key, count(*)::int AS count
    FROM press_releases pr
    JOIN senators s ON s.id = pr.senator_id
    WHERE s.chamber = ${TX_CHAMBER}
      AND pr.deleted_at IS NULL
      AND pr.content_type != 'photo_release'
      AND pr.fts @@ plainto_tsquery('english', ${search})
    GROUP BY s.party
  `) as { key: string; count: number }[];

  const typeRows = (await sql`
    SELECT pr.content_type AS key, count(*)::int AS count
    FROM press_releases pr
    JOIN senators s ON s.id = pr.senator_id
    WHERE s.chamber = ${TX_CHAMBER}
      AND pr.deleted_at IS NULL
      AND pr.content_type != 'photo_release'
      AND pr.fts @@ plainto_tsquery('english', ${search})
    GROUP BY pr.content_type
  `) as { key: string; count: number }[];

  const party = { D: 0, R: 0, I: 0 };
  for (const r of partyRows) {
    if (r.key === "D" || r.key === "R" || r.key === "I") party[r.key] = r.count;
  }
  const type: Partial<Record<ContentType, number>> = {};
  for (const r of typeRows) {
    if (r.key) type[r.key as ContentType] = r.count;
  }
  return { party, type };
}

// Active TX session windows (89th Legislature regular session + any specials
// or interim periods). Used to annotate timelines. Hard-coded for now —
// each Texas legislature is a 2-year span and dates are public record.
export const TX_SESSION_WINDOWS = [
  { name: "89th regular session", start: "2025-01-14", end: "2025-06-02" },
];

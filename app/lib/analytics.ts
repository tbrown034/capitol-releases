import { sql } from "./db";

export async function getWeeklyActivity() {
  return sql`
    SELECT to_char(date_trunc('week', published_at), 'YYYY-MM-DD') as week,
           count(*)::int as count,
           s.party
    FROM press_releases pr
    JOIN senators s ON s.id = pr.senator_id
    WHERE published_at IS NOT NULL
      AND pr.deleted_at IS NULL AND pr.content_type != 'photo_release'
      AND pr.published_at >= '2025-01-01'
    GROUP BY week, s.party
    ORDER BY week
  `;
}

export async function getSenatorActivity() {
  return sql`
    SELECT s.id, s.full_name, s.party, s.state,
           to_char(date_trunc('week', pr.published_at), 'YYYY-MM-DD') as week,
           count(*)::int as count
    FROM press_releases pr
    JOIN senators s ON s.id = pr.senator_id
    WHERE pr.published_at IS NOT NULL
      AND pr.deleted_at IS NULL AND pr.content_type != 'photo_release'
      AND pr.published_at >= '2025-01-01'
      AND s.status = 'active'
      AND s.chamber = 'senate'
    GROUP BY s.id, s.full_name, s.party, s.state, week
    ORDER BY s.full_name, week
  `;
}

export async function getTopSenatorsByPeriod(days = 30) {
  return sql`
    SELECT s.id, s.full_name, s.party, s.state,
           count(pr.id)::int as count
    FROM press_releases pr
    JOIN senators s ON s.id = pr.senator_id
    WHERE pr.published_at >= NOW() - make_interval(days => ${days})
      AND pr.deleted_at IS NULL AND pr.content_type != 'photo_release'
      AND s.chamber = 'senate'
    GROUP BY s.id, s.full_name, s.party, s.state
    ORDER BY count DESC
    LIMIT 15
  `;
}

export async function getTopicTrends() {
  // Simple keyword-based topic extraction from titles
  return sql`
    SELECT word, count(*)::int as count
    FROM (
      SELECT DISTINCT pr.id, lower(unnest(string_to_array(
        regexp_replace(pr.title, '[^a-zA-Z ]', '', 'g'), ' '
      ))) as word
      FROM press_releases pr
      WHERE pr.published_at >= NOW() - interval '30 days'
        AND pr.deleted_at IS NULL AND pr.content_type != 'photo_release'
    ) words
    WHERE length(word) > 4
      AND word NOT IN ('senator','senators','press','release','statement',
        'announces','urges','calls','joins','leads','supports','introduces',
        'legislation','bipartisan','their','about','after','would','could',
        'should','which','where','other','there','these','those','being',
        'through','between','under','during','before','above','below',
        'against','without','within','along','among','across','behind',
        'beyond','since','until','while','around','inside','outside')
    GROUP BY word
    HAVING count(*) >= 3
    ORDER BY count DESC
    LIMIT 30
  `;
}

export async function getSenatorDailyActivity(senatorId: string) {
  return sql`
    SELECT to_char(published_at::date, 'YYYY-MM-DD') as day,
           count(*)::int as count
    FROM press_releases
    WHERE senator_id = ${senatorId}
      AND published_at IS NOT NULL
      AND deleted_at IS NULL
      AND content_type != 'photo_release'
      AND published_at >= '2025-01-01'
    GROUP BY day
    ORDER BY day
  `;
}

export async function getSenatorSignatureTopics(
  senatorId: string,
  excludeNames: string[] = [],
  limit = 12
) {
  // Log-odds ratio with Laplace smoothing: words this senator uses
  // disproportionately vs the rest of the chamber. Titles only to keep it cheap.
  const exclusions = excludeNames
    .map((n) => n.toLowerCase())
    .filter((n) => n.length > 0);
  return sql`
    WITH all_words AS (
      SELECT pr.id,
             lower(unnest(string_to_array(
               regexp_replace(coalesce(pr.title, ''), '[^a-zA-Z ]', ' ', 'g'),
               ' '
             ))) as word,
             (pr.senator_id = ${senatorId}) as is_self
      FROM press_releases pr
      JOIN senators s ON s.id = pr.senator_id
      WHERE pr.deleted_at IS NULL AND pr.content_type != 'photo_release'
        AND pr.published_at >= '2025-01-01'
        AND s.status = 'active'
        AND s.chamber = 'senate'
    ),
    name_filtered AS (
      SELECT word, is_self FROM all_words
      WHERE NOT (word = ANY(${exclusions}::text[]))
    ),
    filtered AS (
      SELECT word, is_self
      FROM name_filtered
      WHERE length(word) > 4
        AND word NOT IN ('senator','senators','press','release','statement',
          'announces','urges','calls','joins','leads','supports','introduces',
          'legislation','bipartisan','their','about','after','would','could',
          'should','which','where','other','there','these','those','being',
          'through','between','under','during','before','above','below',
          'against','without','within','along','among','across','behind',
          'beyond','since','until','while','around','inside','outside',
          'today','washington','office','united','states','american','americans',
          'members','member','following','every','first','again','including',
          'continue','continues','important','provide','provides','release',
          'releases','statement','letter','letters','floor','remark','remarks')
    ),
    counts AS (
      SELECT word,
             count(*) FILTER (WHERE is_self)::numeric as self_n,
             count(*) FILTER (WHERE NOT is_self)::numeric as rest_n
      FROM filtered
      GROUP BY word
    ),
    totals AS (
      SELECT sum(self_n) as self_total, sum(rest_n) as rest_total FROM counts
    )
    SELECT word,
           self_n::int as self_count,
           rest_n::int as rest_count,
           ln((self_n + 1) / (totals.self_total - self_n + 1)) -
           ln((rest_n + 1) / (totals.rest_total - rest_n + 1)) as log_odds
    FROM counts, totals
    WHERE self_n >= 3
    ORDER BY log_odds DESC
    LIMIT ${limit}
  `;
}

export async function getSenatorTopicTrends(
  senatorId: string,
  excludeNames: string[] = [],
  limit = 12
) {
  const exclusions = excludeNames
    .map((n) => n.toLowerCase())
    .filter((n) => n.length > 0);
  return sql`
    WITH word_releases AS (
      SELECT DISTINCT pr.id,
                      lower(unnest(string_to_array(
                        regexp_replace(
                          coalesce(pr.title, '') || ' ' || coalesce(pr.body_text, ''),
                          '[^a-zA-Z ]', ' ', 'g'
                        ),
                        ' '
                      ))) as word,
                      pr.published_at
      FROM press_releases pr
      WHERE pr.senator_id = ${senatorId}
        AND pr.deleted_at IS NULL AND pr.content_type != 'photo_release'
        AND pr.published_at >= NOW() - interval '60 days'
    )
    SELECT word,
           count(*) FILTER (WHERE published_at >= NOW() - interval '30 days')::int as recent_count,
           count(*) FILTER (WHERE published_at <  NOW() - interval '30 days')::int as prior_count
    FROM word_releases
    WHERE NOT (word = ANY(${exclusions}::text[]))
      AND length(word) > 4
      AND word NOT IN ('senator','senators','press','release','statement',
        'announces','urges','calls','joins','leads','supports','introduces',
        'legislation','bipartisan','their','about','after','would','could',
        'should','which','where','other','there','these','those','being',
        'through','between','under','during','before','above','below',
        'against','without','within','along','among','across','behind',
        'beyond','since','until','while','around','inside','outside',
        'today','washington','office','united','states','american','americans',
        'members','member','following','every','first','every','every','again',
        'including','continue','continues','important','provide','provides')
    GROUP BY word
    HAVING count(*) FILTER (WHERE published_at >= NOW() - interval '30 days') >= 2
    ORDER BY recent_count DESC, prior_count ASC
    LIMIT ${limit}
  `;
}

export async function getDailyVolume(days = 90) {
  return sql`
    SELECT to_char(published_at, 'YYYY-MM-DD') as day,
           count(*)::int as count
    FROM press_releases
    WHERE published_at >= NOW() - make_interval(days => ${days})
      AND published_at IS NOT NULL
      AND deleted_at IS NULL
      AND content_type != 'photo_release'
    GROUP BY day
    ORDER BY day
  `;
}

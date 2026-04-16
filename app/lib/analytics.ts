import { sql } from "./db";

export async function getWeeklyActivity() {
  return sql`
    SELECT date_trunc('week', published_at)::date as week,
           count(*)::int as count,
           s.party
    FROM press_releases pr
    JOIN senators s ON s.id = pr.senator_id
    WHERE published_at IS NOT NULL
    GROUP BY week, s.party
    ORDER BY week
  `;
}

export async function getSenatorActivity() {
  return sql`
    SELECT s.id, s.full_name, s.party, s.state,
           date_trunc('week', pr.published_at)::date as week,
           count(*)::int as count
    FROM press_releases pr
    JOIN senators s ON s.id = pr.senator_id
    WHERE pr.published_at IS NOT NULL
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

export async function getDailyVolume(days = 90) {
  return sql`
    SELECT published_at::date as day,
           count(*)::int as count
    FROM press_releases
    WHERE published_at >= NOW() - make_interval(days => ${days})
      AND published_at IS NOT NULL
    GROUP BY day
    ORDER BY day
  `;
}

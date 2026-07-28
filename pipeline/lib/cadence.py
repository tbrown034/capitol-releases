"""Per-source publishing cadence, for staleness checks that fit the source.

A fixed "silent for N days means broken" rule cannot work across this
corpus. A US senator publishes several times a week year-round. The
Colorado House Republicans went 77 days without a release in 2026 and
nothing was wrong -- a minority caucus out of session simply stops
talking. Texas is starker still: its legislature meets in odd years only,
so a Texas source has no regular session in 2026 at all.

Rather than hand-maintaining a session calendar per jurisdiction -- which
would need sourcing for 50 states, would go stale every year, and would
still miss special sessions -- staleness is measured against each source's
OWN history. The question becomes "has this source ever been quiet this
long before?" instead of "is this longer than some global constant?"

That makes the threshold self-tuning. A part-time legislature naturally
has long historical gaps, so it earns a long threshold without anyone
declaring one. A daily publisher earns a short one. Sessions, recesses and
interim periods are absorbed automatically because they are already in the
history the profile is built from.

The tradeoff, stated plainly: a source that has been broken for its entire
recorded history looks healthy, because its history is the baseline. That
failure mode belongs to the health check -- HTTP status and selector
match -- which is a separate signal and does not depend on this one.
"""

from dataclasses import dataclass

# A source needs a real history before its own gaps mean anything. Below
# this many observed gaps, fall back to the global default rather than
# trusting a percentile computed from a handful of points.
MIN_GAPS_FOR_PROFILE = 8

# Used when a source has too little history to profile. Deliberately loose:
# a false silence alert on a brand-new source teaches people to ignore
# alerts, which costs more than a late detection.
DEFAULT_STALE_DAYS = 45

# Never alert below this, no matter how metronomic a source looks. Even a
# daily publisher takes a holiday week.
MIN_STALE_DAYS = 10

# Multiplier on the observed 95th-percentile gap. A source that has gone
# quiet for longer than 1.5x its own worst normal stretch is worth a look.
GAP_TOLERANCE = 1.5


# A cohort needs enough members for "my peers are quiet too" to mean
# anything. Ohio's 33 senators clear this; a one-row jurisdiction like West
# Virginia does not, and falls back to its own history alone.
MIN_COHORT_SIZE = 4


@dataclass
class CadenceProfile:
    official_id: str
    gap_count: int
    p50_days: float
    p95_days: float
    max_days: float
    days_since_last: float
    threshold_days: float
    profiled: bool  # False when the default was used instead of real history
    cohort: str = ""
    cohort_size: int = 0
    cohort_median_silence: float = 0.0

    @property
    def cohort_is_quiet(self) -> bool:
        """True when this source's peers are, typically, as quiet as it is.

        A source's own history cannot explain an ONGOING gap: a gap only
        enters the distribution once it closes. That is why a biennial
        legislature still looked broken -- every Texas senator's history is
        session-time cadence, and the current interim is not in it yet.

        Peers answer what history cannot. The comparison is against the
        cohort's MEDIAN silence rather than a share of members past their
        own thresholds, because a share needs a cutoff and every cutoff is
        arbitrary: measured 2026-07-28, Texas sat at 59% and Missouri at
        52%, straddling a 60% line that would have suppressed one chamber
        and alerted the other for no principled reason.

        Median silence has no such cliff. When the typical Texas senator
        has been quiet for months, one more quiet Texas senator is not
        news. When the typical US House member published two days ago, a
        member silent for sixty days is.
        """
        return (
            self.cohort_size >= MIN_COHORT_SIZE
            and self.cohort_median_silence >= self.threshold_days
        )

    @property
    def is_stale(self) -> bool:
        return self.days_since_last > self.threshold_days and not self.cohort_is_quiet

    def describe(self) -> str:
        cohort_note = ""
        if self.cohort_is_quiet:
            cohort_note = (f" -- suppressed: the median {self.cohort} source "
                           f"({self.cohort_size} total) has been quiet "
                           f"{self.cohort_median_silence:.0f}d, so the body is "
                           f"likely out of session")
        if not self.profiled:
            return (f"{self.official_id}: silent {self.days_since_last:.0f}d "
                    f"(threshold {self.threshold_days:.0f}d, too little history "
                    f"to profile){cohort_note}")
        return (f"{self.official_id}: silent {self.days_since_last:.0f}d, "
                f"but its own median gap is {self.p50_days:.0f}d and its worst "
                f"normal stretch is {self.p95_days:.0f}d "
                f"(threshold {self.threshold_days:.0f}d){cohort_note}")


def build_profiles(conn, jurisdictions: list[str] | None = None) -> list[CadenceProfile]:
    """Compute a cadence profile for every active, collecting source.

    Sources with `expect_empty` semantics (no collection_method) are
    skipped -- a source we never collect from cannot be stale.
    """
    cur = conn.cursor()
    juris_clause = "AND o.jurisdiction = ANY(%s)" if jurisdictions else ""
    params: list = [jurisdictions] if jurisdictions else []

    cur.execute(
        f"""
        WITH dated AS (
            SELECT i.official_id, i.published_at,
                   LAG(i.published_at) OVER (
                       PARTITION BY i.official_id ORDER BY i.published_at
                   ) AS prev
            FROM official_site_items i
            JOIN officials o ON o.id = i.official_id
            WHERE i.deleted_at IS NULL
              AND i.published_at IS NOT NULL
              AND o.status = 'active'
              AND o.collection_method IS NOT NULL
              {juris_clause}
        ),
        gaps AS (
            SELECT official_id,
                   EXTRACT(EPOCH FROM (published_at - prev)) / 86400.0 AS gap_days
            FROM dated
            WHERE prev IS NOT NULL
        )
        SELECT g.official_id,
               COUNT(*)::int,
               PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY g.gap_days),
               PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY g.gap_days),
               MAX(g.gap_days),
               EXTRACT(EPOCH FROM (NOW() - MAX(d.published_at))) / 86400.0,
               MAX(o.jurisdiction) || ':' || COALESCE(MAX(o.chamber), 'exec')
        FROM gaps g
        JOIN dated d ON d.official_id = g.official_id
        JOIN officials o ON o.id = g.official_id
        GROUP BY g.official_id
        """,
        params,
    )

    profiles = []
    for sid, n, p50, p95, gmax, since, cohort in cur.fetchall():
        profiled = n >= MIN_GAPS_FOR_PROFILE
        if profiled:
            threshold = max(float(p95) * GAP_TOLERANCE, MIN_STALE_DAYS)
        else:
            threshold = DEFAULT_STALE_DAYS
        profiles.append(CadenceProfile(
            official_id=sid,
            gap_count=n,
            p50_days=float(p50 or 0),
            p95_days=float(p95 or 0),
            max_days=float(gmax or 0),
            days_since_last=float(since or 0),
            threshold_days=threshold,
            profiled=profiled,
            cohort=cohort or "",
        ))
    cur.close()

    # Second pass: consult the cohort. A source is judged against its own
    # history first, then that verdict is withdrawn if its peers are
    # typically just as quiet -- which is what an adjourned chamber looks
    # like from the outside.
    by_cohort: dict[str, list[CadenceProfile]] = {}
    for p in profiles:
        by_cohort.setdefault(p.cohort, []).append(p)
    for cohort, members in by_cohort.items():
        size = len(members)
        silences = sorted(m.days_since_last for m in members)
        median = silences[size // 2] if size else 0.0
        for m in members:
            m.cohort_size = size
            m.cohort_median_silence = median

    return profiles


def stale_sources(conn, jurisdictions: list[str] | None = None) -> list[CadenceProfile]:
    """Sources quiet for longer than their own history predicts."""
    return [p for p in build_profiles(conn, jurisdictions) if p.is_stale]

"""
Capitol Releases Pipeline -- Unified CLI Entry Point

Usage:
    python -m pipeline update                    # daily updater
    python -m pipeline update --dry-run          # preview what would be collected
    python -m pipeline health                    # run health checks
    python -m pipeline health --method rss       # check RSS senators only
    python -m pipeline test                      # run data quality tests
    python -m pipeline tiers                     # federal vs state quality comparison
    python -m pipeline back-coverage             # flag senators missing 2025 back-coverage
    python -m pipeline health-report             # write docs/data_health.{md,json}
    python -m pipeline tx-truth                  # verify TX corpus against live senate.texas.gov
    python -m pipeline brief                     # generate daily AI brief (Sonnet)
    python -m pipeline brief --weekly            # generate weekly brief (Thu-evening cycle)
    python -m pipeline brief --dry-run           # preview inputs without API call
    python -m pipeline brief-send                # email latest brief to subscribers
    python -m pipeline source-profiles           # validate state source-profile registry
    python -m pipeline floor-speeches update     # daily Senate floor speeches collector (Congressional Record)
    python -m pipeline floor-speeches backfill --since 2025-01-01
    python -m pipeline sync-members              # upsert seed members into senators table (dry-run)
    python -m pipeline sync-members --apply      # actually write
    python -m pipeline stats                     # show database stats
"""

import os
import sys
from pathlib import Path


def _load_dotenv():
    """Source pipeline/.env into os.environ if present.

    Most subcommands need DATABASE_URL and ANTHROPIC_API_KEY; these live in
    pipeline/.env locally and ship via secrets in CI. This used to live only
    inside _show_stats(); promoting it makes every command work the same way
    when run from a fresh shell.
    """
    env_path = Path("pipeline/.env")
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        if line.strip() and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)

    _load_dotenv()

    command = sys.argv[1]
    # Remove the command from argv so subcommand parsers work correctly
    sys.argv = [sys.argv[0]] + sys.argv[2:]

    if command == "update":
        from pipeline.commands.update import main as update_main
        update_main()

    elif command == "health":
        from pipeline.commands.health_check import main as health_main
        health_main()

    elif command == "test":
        import subprocess
        result = subprocess.run(
            [sys.executable, "pipeline/tests/test_data_quality.py"],
            cwd=".",
        )
        sys.exit(result.returncode)

    elif command == "verify-visual":
        from pipeline.commands.visual_verify import main as visual_main
        visual_main()

    elif command == "repair":
        from pipeline.commands.repair import main as repair_main
        repair_main()

    elif command == "deletions":
        from pipeline.commands.detect_deletions import main as deletions_main
        deletions_main()

    elif command == "review":
        from pipeline.commands.review import main as review_main
        review_main()

    elif command == "tiers":
        from pipeline.commands.tier_report import main as tiers_main
        tiers_main()

    elif command == "back-coverage":
        from pipeline.commands.check_back_coverage import main as bc_main
        bc_main()

    elif command in ("health-report", "report"):
        from pipeline.commands.health_report import main as hr_main
        hr_main()

    elif command in ("tx-truth", "tx-verify"):
        from pipeline.commands.tx_truth_check import main as tx_main
        tx_main()

    elif command in ("tx-extract", "tx-bodies"):
        from pipeline.commands.tx_extract_bodies import main as tx_extract_main
        tx_extract_main()

    elif command == "brief":
        from pipeline.commands.brief import main as brief_main
        brief_main()

    elif command == "brief-send":
        from pipeline.commands.brief_send import main as brief_send_main
        brief_send_main()

    elif command == "publish-drafts":
        from pipeline.commands.publish_drafts import main as publish_drafts_main
        sys.exit(publish_drafts_main())

    elif command == "daily-report":
        from pipeline.commands.daily_report import main as daily_report_main
        sys.exit(daily_report_main())

    elif command == "source-profiles":
        from pipeline.commands.source_profiles import main as source_profiles_main
        source_profiles_main()

    elif command == "floor-speeches":
        from pipeline.commands.floor_speeches import main as floor_main
        sys.exit(floor_main())

    elif command == "sync-members":
        from pipeline.commands.sync_members import main as sync_main
        sync_main()

    elif command == "stats":
        _show_stats()

    else:
        print(f"Unknown command: {command}")
        print(__doc__)
        sys.exit(1)


def _show_stats():
    """Show current database statistics."""
    import os
    from pathlib import Path

    env_path = Path("pipeline/.env")
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.strip() and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

    import psycopg2
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM official_site_items")
    total = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM official_site_items WHERE published_at IS NOT NULL")
    dated = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM official_site_items WHERE body_text IS NOT NULL AND length(body_text) > 100")
    with_body = cur.fetchone()[0]

    cur.execute("SELECT COUNT(DISTINCT official_id) FROM official_site_items")
    senators = cur.fetchone()[0]

    cur.execute("SELECT MIN(published_at), MAX(published_at) FROM official_site_items WHERE published_at IS NOT NULL")
    min_date, max_date = cur.fetchone()

    cur.execute("SELECT COUNT(*) FROM official_site_items WHERE date_source IS NOT NULL")
    provenance = cur.fetchone()[0]

    cur.execute("""
        SELECT collection_method, COUNT(*)
        FROM officials
        GROUP BY collection_method
        ORDER BY COUNT(*) DESC
    """)
    methods = cur.fetchall()

    cur.execute("""
        SELECT COUNT(*) FROM scrape_runs
        WHERE run_type = 'daily' AND finished_at IS NOT NULL
    """)
    daily_runs = cur.fetchone()[0]

    cur.close()
    conn.close()

    print(f"\n{'='*50}")
    print(f"  CAPITOL RELEASES -- DATABASE STATS")
    print(f"{'='*50}")
    print(f"  Total releases:      {total:>8,}")
    print(f"  With dates:          {dated:>8,} ({dated/total*100:.0f}%)")
    print(f"  With body text:      {with_body:>8,} ({with_body/total*100:.0f}%)")
    print(f"  With date provenance:{provenance:>8,}")
    print(f"  Senators with data:  {senators:>8}")
    print(f"  Date range:          {min_date.date()} to {max_date.date()}")
    print(f"  Daily update runs:   {daily_runs:>8}")
    print(f"\n  Collection methods:")
    for method, count in methods:
        print(f"    {method or 'unset':15s} {count:>3}")
    print(f"{'='*50}\n")


if __name__ == "__main__":
    main()

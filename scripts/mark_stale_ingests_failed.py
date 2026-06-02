from pathlib import Path
import sys

import psycopg

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.config import get_settings


def main() -> None:
    settings = get_settings()
    sql = """
        UPDATE ingest_runs
        SET
            status = 'failed',
            error = 'Marked failed after worker stopped before completion.',
            completed_at = clock_timestamp()
        WHERE status = 'running'
        RETURNING id, source
    """
    with psycopg.connect(settings.database_url) as conn:
        rows = conn.execute(sql).fetchall()
        conn.commit()

    for run_id, source in rows:
        print(f"Marked {run_id} ({source}) failed.")

    print(f"Marked {len(rows)} stale ingest run(s) failed.")


if __name__ == "__main__":
    main()

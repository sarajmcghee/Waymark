from pathlib import Path

import psycopg

from app.config import get_settings


MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "db" / "migrations"


def main() -> None:
    settings = get_settings()
    migration_paths = sorted(MIGRATIONS_DIR.glob("*.sql"))

    if not migration_paths:
        raise SystemExit("No migration files found.")

    with psycopg.connect(settings.database_url) as conn:
        with conn.cursor() as cur:
            for path in migration_paths:
                print(f"Applying {path.name}")
                cur.execute(path.read_text())
        conn.commit()

    print("Migrations applied.")


if __name__ == "__main__":
    main()

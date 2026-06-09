import argparse
from pathlib import Path
import sys
from typing import Any

import psycopg
from psycopg.rows import dict_row

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.config import get_settings
from scripts.import_geofabrik import consolidate_route_relations


def load_existing_relations(
    conn: psycopg.Connection,
    *,
    source: str,
) -> dict[str, dict[str, Any]]:
    sql = """
        SELECT
            relation->>'id' AS relation_id,
            relation,
            array_agg(DISTINCT source_id) AS way_ids
        FROM trails
        CROSS JOIN LATERAL jsonb_array_elements(
            CASE
                WHEN jsonb_typeof(raw_properties->'osm_route_relations') = 'array'
                    THEN raw_properties->'osm_route_relations'
                ELSE '[]'::jsonb
            END
        ) AS relation
        WHERE source = %(source)s
          AND source_id NOT LIKE 'relation:%%'
        GROUP BY relation->>'id', relation
    """
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(sql, {"source": source})
        rows = cur.fetchall()

    return {
        row["relation_id"]: {
            **row["relation"],
            "way_ids": row["way_ids"],
            "tags": row["relation"],
        }
        for row in rows
        if row["relation_id"]
    }


def normalize_existing_trails(*, source: str) -> tuple[int, int]:
    settings = get_settings()
    with psycopg.connect(settings.database_url) as conn:
        source_row = conn.execute(
            """
            SELECT source_url
            FROM trails
            WHERE source = %(source)s
            LIMIT 1
            """,
            {"source": source},
        ).fetchone()
        if not source_row:
            raise RuntimeError(f"No trails found for source {source}.")

        updated = conn.execute(
            """
            UPDATE trails
            SET
                length_meters = COALESCE(
                    length_meters,
                    ST_Length(geography(geometry))
                ),
                is_route_segment = true,
                route_relation_ids = ARRAY(
                    SELECT DISTINCT relation->>'id'
                    FROM jsonb_array_elements(
                        raw_properties->'osm_route_relations'
                    ) AS relation
                    WHERE relation->>'id' IS NOT NULL
                ),
                updated_at = now()
            WHERE source = %(source)s
              AND source_id NOT LIKE 'relation:%%'
              AND jsonb_typeof(raw_properties->'osm_route_relations') = 'array'
              AND jsonb_array_length(raw_properties->'osm_route_relations') > 0
            """,
            {"source": source},
        ).rowcount
        conn.commit()

        relations = load_existing_relations(conn, source=source)
        consolidated = consolidate_route_relations(
            conn,
            source=source,
            source_url=source_row[0],
            relations=relations,
        )
        conn.commit()

    return updated, consolidated


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backfill lengths and consolidate existing OSM route segments."
    )
    parser.add_argument(
        "--source",
        required=True,
        help="Existing Geofabrik source, such as osm-geofabrik-tennessee.",
    )
    args = parser.parse_args()

    updated, consolidated = normalize_existing_trails(source=args.source)
    print(f"Updated {updated} route segments.")
    print(f"Consolidated {consolidated} route relations.")


if __name__ == "__main__":
    main()

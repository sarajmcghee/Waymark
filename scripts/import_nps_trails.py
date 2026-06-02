from pathlib import Path
import sys

import httpx
import psycopg

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.config import get_settings
from app.ingest import _create_ingest_run, _finish_ingest_run, _insert_feature
from app.presets import NPS_PUBLIC_TRAILS_QUERY_URL, NPS_TRAIL_OUT_FIELDS


def import_nps_trails() -> int:
    settings = get_settings()
    source = "nps-public-trails-all"
    page_size = 1000
    max_pages = 40
    inserted = 0

    with psycopg.connect(settings.database_url) as conn:
        run_id = _create_ingest_run(
            conn,
            source=source,
            source_url=NPS_PUBLIC_TRAILS_QUERY_URL,
            source_type="arcgis",
            source_filter="1=1",
            requested_count=page_size * max_pages,
        )
        conn.commit()

        try:
            for page_index in range(max_pages):
                response = httpx.get(
                    NPS_PUBLIC_TRAILS_QUERY_URL,
                    params={
                        "f": "geojson",
                        "where": "1=1",
                        "outFields": NPS_TRAIL_OUT_FIELDS,
                        "returnGeometry": "true",
                        "resultRecordCount": page_size,
                        "resultOffset": page_index * page_size,
                    },
                    timeout=120,
                )
                response.raise_for_status()
                features = response.json().get("features", [])

                if not features:
                    break

                for feature in features:
                    if _insert_feature(
                        conn,
                        source=source,
                        source_url=NPS_PUBLIC_TRAILS_QUERY_URL,
                        feature=feature,
                    ):
                        inserted += 1

                conn.commit()
                print(f"Imported page {page_index + 1}: {inserted} accepted so far")

                if len(features) < page_size:
                    break

            _finish_ingest_run(
                conn,
                run_id=run_id,
                accepted_count=inserted,
                status="succeeded",
            )
            conn.commit()
        except Exception as exc:
            _finish_ingest_run(
                conn,
                run_id=run_id,
                accepted_count=inserted,
                status="failed",
                error=str(exc),
            )
            conn.commit()
            raise

    return inserted


def main() -> None:
    count = import_nps_trails()
    print(f"Imported {count} NPS public trail features.")


if __name__ == "__main__":
    main()

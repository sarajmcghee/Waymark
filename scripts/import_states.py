import json
from pathlib import Path
import sys
from typing import Any

import httpx
import psycopg
from psycopg.types.json import Jsonb

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.config import get_settings


TIGERWEB_STATES_URL = (
    "https://tigerweb.geo.census.gov/arcgis/rest/services/"
    "TIGERweb/State_County/MapServer/0/query"
)


def fetch_states() -> list[dict[str, Any]]:
    features: list[dict[str, Any]] = []
    page_size = 10
    offset = 0

    while True:
        response = httpx.get(
            TIGERWEB_STATES_URL,
            params={
                "f": "geoJSON",
                "where": "1=1",
                "outFields": "GEOID,STUSAB,NAME",
                "returnGeometry": "true",
                "outSR": "4326",
                "resultRecordCount": str(page_size),
                "resultOffset": str(offset),
            },
            timeout=120,
        )
        response.raise_for_status()

        if "json" not in response.headers.get("content-type", "").lower():
            raise RuntimeError(
                "Census TIGERweb returned a non-JSON response: "
                f"{response.text[:200]}"
            )

        page = response.json()["features"]
        if not page:
            return features

        features.extend(page)
        offset += page_size


def import_states() -> int:
    settings = get_settings()
    features = fetch_states()

    sql = """
        INSERT INTO states (
            fips,
            abbreviation,
            name,
            geometry,
            source,
            source_url,
            raw_properties
        )
        VALUES (
            %(fips)s,
            %(abbreviation)s,
            %(name)s,
            ST_Multi(
                ST_CollectionExtract(
                    ST_MakeValid(ST_SetSRID(ST_GeomFromGeoJSON(%(geometry)s), 4326)),
                    3
                )
            ),
            %(source)s,
            %(source_url)s,
            %(raw_properties)s
        )
        ON CONFLICT (fips)
        DO UPDATE SET
            abbreviation = EXCLUDED.abbreviation,
            name = EXCLUDED.name,
            geometry = EXCLUDED.geometry,
            source = EXCLUDED.source,
            source_url = EXCLUDED.source_url,
            raw_properties = EXCLUDED.raw_properties,
            updated_at = now()
    """

    with psycopg.connect(settings.database_url) as conn:
        with conn.cursor() as cur:
            for feature in features:
                properties = feature["properties"]
                cur.execute(
                    sql,
                    {
                        "fips": properties["GEOID"],
                        "abbreviation": properties["STUSAB"],
                        "name": properties["NAME"],
                        "geometry": json.dumps(feature["geometry"]),
                        "source": "us-census-tigerweb-states",
                        "source_url": TIGERWEB_STATES_URL,
                        "raw_properties": Jsonb(properties),
                    },
                )
        conn.commit()

    return len(features)


def main() -> None:
    count = import_states()
    print(f"Imported {count} state boundaries.")


if __name__ == "__main__":
    main()

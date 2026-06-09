import argparse
import csv
from io import TextIOWrapper
from pathlib import Path
import sys
import tempfile
from zipfile import ZipFile

import httpx
import psycopg
from psycopg.types.json import Jsonb

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.config import get_settings


CENSUS_PLACES_URL = (
    "https://www2.census.gov/geo/docs/maps-data/data/gazetteer/"
    "2025_Gazetteer/2025_Gaz_place_national.zip"
)


def download_file(url: str, destination: Path) -> None:
    headers = {"User-Agent": "Waymark/0.1 (Census place importer)"}
    with httpx.stream(
        "GET",
        url,
        headers=headers,
        follow_redirects=True,
        timeout=300,
    ) as response:
        response.raise_for_status()
        with destination.open("wb") as file:
            for chunk in response.iter_bytes():
                file.write(chunk)


def place_rows(zip_path: Path):
    with ZipFile(zip_path) as archive:
        text_files = [
            name for name in archive.namelist() if name.lower().endswith(".txt")
        ]
        if not text_files:
            raise RuntimeError("The Census archive does not contain a text file.")

        with archive.open(text_files[0]) as raw_file:
            text_file = TextIOWrapper(raw_file, encoding="utf-8-sig", newline="")
            reader = csv.DictReader(text_file, delimiter="|")
            for row in reader:
                yield {
                    key.strip(): value.strip()
                    for key, value in row.items()
                    if key is not None and value is not None
                }


def import_cities(*, url: str, file_path: Path | None) -> int:
    settings = get_settings()
    sql = """
        INSERT INTO cities (
            geoid,
            name,
            state,
            geometry,
            source,
            source_url,
            raw_properties
        )
        VALUES (
            %(geoid)s,
            %(name)s,
            %(state)s,
            ST_SetSRID(ST_MakePoint(%(lng)s, %(lat)s), 4326),
            %(source)s,
            %(source_url)s,
            %(raw_properties)s
        )
        ON CONFLICT (geoid)
        DO UPDATE SET
            name = EXCLUDED.name,
            state = EXCLUDED.state,
            geometry = EXCLUDED.geometry,
            source = EXCLUDED.source,
            source_url = EXCLUDED.source_url,
            raw_properties = EXCLUDED.raw_properties,
            updated_at = now()
    """

    with tempfile.TemporaryDirectory() as temp_dir:
        zip_path = file_path or Path(temp_dir) / "census-places.zip"
        if not zip_path.exists():
            print(f"Downloading {url}")
            download_file(url, zip_path)

        count = 0
        batch: list[dict] = []
        with psycopg.connect(settings.database_url) as conn:
            with conn.cursor() as cur:
                for row in place_rows(zip_path):
                    batch.append(
                        {
                            "geoid": row["GEOID"],
                            "name": row["NAME"],
                            "state": row["USPS"].upper(),
                            "lng": float(row["INTPTLONG"]),
                            "lat": float(row["INTPTLAT"]),
                            "source": "us-census-gazetteer-places-2025",
                            "source_url": url,
                            "raw_properties": Jsonb(row),
                        }
                    )
                    count += 1

                    if len(batch) >= 1000:
                        cur.executemany(sql, batch)
                        conn.commit()
                        print(f"Imported {count} Census places")
                        batch.clear()

                if batch:
                    cur.executemany(sql, batch)
            conn.commit()

    return count


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Import U.S. Census place centroids for city searches."
    )
    parser.add_argument("--url", default=CENSUS_PLACES_URL)
    parser.add_argument(
        "--file",
        type=Path,
        help="Optional local Census Gazetteer ZIP instead of downloading.",
    )
    args = parser.parse_args()

    count = import_cities(url=args.url, file_path=args.file)
    print(f"Imported {count} Census places.")


if __name__ == "__main__":
    main()

import argparse
import tempfile
from pathlib import Path
import sys
from typing import Any

import httpx
import osmium
import psycopg

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.config import get_settings
from app.ingest import _create_ingest_run, _finish_ingest_run, _insert_feature


GEOFABRIK_US_BASE_URL = "https://download.geofabrik.de/north-america/us"

TRAIL_HIGHWAYS = {
    "bridleway",
    "cycleway",
    "footway",
    "path",
    "pedestrian",
    "steps",
    "track",
}

TRAIL_ROUTES = {
    "foot",
    "hiking",
    "mtb",
}


def region_url(region: str) -> str:
    return f"{GEOFABRIK_US_BASE_URL}/{region}-latest.osm.pbf"


def download_extract(url: str, destination: Path) -> None:
    with httpx.stream("GET", url, follow_redirects=True, timeout=300) as response:
        response.raise_for_status()
        with destination.open("wb") as file:
            for chunk in response.iter_bytes():
                file.write(chunk)


def is_trail_like(tags: dict[str, str]) -> bool:
    highway = tags.get("highway")
    route = tags.get("route")

    if highway in TRAIL_HIGHWAYS:
        return True
    if route in TRAIL_ROUTES:
        return True
    if tags.get("foot") in {"yes", "designated", "permissive"} and highway:
        return True
    if tags.get("sac_scale"):
        return True

    return False


def allowed_uses(tags: dict[str, str]) -> list[str]:
    uses: list[str] = []

    if tags.get("foot") in {"yes", "designated", "permissive"} or tags.get("highway") in {
        "footway",
        "path",
        "steps",
    }:
        uses.append("hiking")
    if tags.get("bicycle") in {"yes", "designated", "permissive"}:
        uses.append("biking")
    if tags.get("horse") in {"yes", "designated", "permissive"} or tags.get("highway") == "bridleway":
        uses.append("horse")

    return uses or ["unknown"]


class TrailWayHandler(osmium.SimpleHandler):
    def __init__(
        self,
        conn: psycopg.Connection,
        *,
        source: str,
        source_url: str,
        limit: int | None,
    ) -> None:
        super().__init__()
        self.conn = conn
        self.source = source
        self.source_url = source_url
        self.limit = limit
        self.accepted = 0
        self.seen = 0

    def way(self, way: Any) -> None:
        if self.limit is not None and self.accepted >= self.limit:
            return

        tags = {tag.k: tag.v for tag in way.tags}
        if not is_trail_like(tags):
            return

        coordinates = []
        for node in way.nodes:
            if not node.location.valid():
                return
            coordinates.append([node.lon, node.lat])

        if len(coordinates) < 2:
            return

        properties = {
            **tags,
            "source_id": str(way.id),
            "name": tags.get("name"),
            "surface": tags.get("surface"),
            "difficulty": tags.get("sac_scale") or tags.get("mtb:scale"),
            "allowed_uses": allowed_uses(tags),
            "managing_agency": tags.get("operator") or tags.get("owner"),
            "status": tags.get("access") or "unknown",
        }
        feature = {
            "type": "Feature",
            "id": way.id,
            "geometry": {
                "type": "LineString",
                "coordinates": coordinates,
            },
            "properties": properties,
        }

        if _insert_feature(
            self.conn,
            source=self.source,
            source_url=self.source_url,
            feature=feature,
        ):
            self.accepted += 1

        self.seen += 1
        if self.accepted and self.accepted % 1000 == 0:
            self.conn.commit()
            print(f"Imported {self.accepted} OSM trail-like ways")


def import_geofabrik(
    *,
    region: str,
    url: str | None,
    limit: int | None,
    keep_file: Path | None,
) -> int:
    source_url = url or region_url(region)
    source = f"osm-geofabrik-{region}"
    settings = get_settings()

    with tempfile.TemporaryDirectory() as temp_dir_name:
        pbf_path = keep_file or Path(temp_dir_name) / f"{region}.osm.pbf"
        if not pbf_path.exists():
            print(f"Downloading {source_url}")
            download_extract(source_url, pbf_path)

        with psycopg.connect(settings.database_url) as conn:
            run_id = _create_ingest_run(
                conn,
                source=source,
                source_url=source_url,
                source_type="geofabrik-osm-pbf",
                source_filter="trail-like OSM ways",
                requested_count=limit,
            )
            conn.commit()

            handler = TrailWayHandler(conn, source=source, source_url=source_url, limit=limit)
            try:
                handler.apply_file(str(pbf_path), locations=True)
                _finish_ingest_run(
                    conn,
                    run_id=run_id,
                    accepted_count=handler.accepted,
                    status="succeeded",
                )
                conn.commit()
            except Exception as exc:
                _finish_ingest_run(
                    conn,
                    run_id=run_id,
                    accepted_count=handler.accepted,
                    status="failed",
                    error=str(exc),
                )
                conn.commit()
                raise

    return handler.accepted


def main() -> None:
    parser = argparse.ArgumentParser(description="Import trail-like OSM ways from Geofabrik.")
    parser.add_argument("region", help="Geofabrik region slug, such as tennessee.")
    parser.add_argument("--url", help="Override Geofabrik .osm.pbf URL.")
    parser.add_argument("--limit", type=int, help="Optional max number of trail-like ways.")
    parser.add_argument(
        "--file",
        type=Path,
        help="Optional local .osm.pbf path to read instead of downloading.",
    )
    args = parser.parse_args()

    count = import_geofabrik(
        region=args.region,
        url=args.url,
        limit=args.limit,
        keep_file=args.file,
    )
    print(f"Imported {count} Geofabrik trail-like ways for {args.region}.")


if __name__ == "__main__":
    main()

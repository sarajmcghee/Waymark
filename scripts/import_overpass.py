import argparse
from pathlib import Path
import sys
from typing import Any

import httpx
import psycopg

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.config import get_settings
from app.ingest import _create_ingest_run, _finish_ingest_run, _insert_feature


DEFAULT_OVERPASS_URL = "https://overpass-api.de/api/interpreter"
USER_AGENT = "Waymark/0.1 (trail data importer)"
TRAIL_HIGHWAY_REGEX = "^(path|footway|bridleway|track|steps|pedestrian|cycleway)$"


def state_query(state: str, limit: int, timeout: int) -> str:
    return f"""
    [out:json][timeout:{timeout}];
    area["ISO3166-2"="US-{state.upper()}"][admin_level=4]->.searchArea;
    (
      way(area.searchArea)["highway"~"{TRAIL_HIGHWAY_REGEX}"];
      way(area.searchArea)["route"~"^(hiking|foot|mtb)$"];
      way(area.searchArea)["sac_scale"];
    );
    out geom {limit};
    """


def query_for_request(
    *,
    state: str | None,
    bbox: str | None,
    limit: int,
    timeout: int,
) -> str:
    if state:
        return state_query(state, limit, timeout)
    if bbox:
        return bbox_query(bbox, limit, timeout)

    raise ValueError("state or bbox is required.")


def bbox_query(bbox: str, limit: int, timeout: int) -> str:
    west, south, east, north = [part.strip() for part in bbox.split(",")]
    osm_bbox = f"{south},{west},{north},{east}"
    return f"""
    [out:json][timeout:{timeout}];
    (
      way["highway"~"{TRAIL_HIGHWAY_REGEX}"]({osm_bbox});
      way["route"~"^(hiking|foot|mtb)$"]({osm_bbox});
      way["sac_scale"]({osm_bbox});
    );
    out geom {limit};
    """


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


def element_feature(element: dict[str, Any]) -> dict[str, Any] | None:
    geometry = element.get("geometry") or []
    coordinates = [[point["lon"], point["lat"]] for point in geometry]
    if len(coordinates) < 2:
        return None

    tags = element.get("tags") or {}
    return {
        "type": "Feature",
        "id": element["id"],
        "geometry": {
            "type": "LineString",
            "coordinates": coordinates,
        },
        "properties": {
            **tags,
            "source_id": str(element["id"]),
            "name": tags.get("name"),
            "surface": tags.get("surface"),
            "difficulty": tags.get("sac_scale") or tags.get("mtb:scale"),
            "allowed_uses": allowed_uses(tags),
            "managing_agency": tags.get("operator") or tags.get("owner"),
            "status": tags.get("access") or "unknown",
        },
    }


def import_overpass(
    *,
    endpoint: str,
    source: str,
    query: str,
    limit: int,
) -> int:
    settings = get_settings()
    inserted = 0

    with psycopg.connect(settings.database_url) as conn:
        run_id = _create_ingest_run(
            conn,
            source=source,
            source_url=endpoint,
            source_type="overpass-osm-json",
            source_filter=query.strip(),
            requested_count=limit,
        )
        conn.commit()

        try:
            response = httpx.post(
                endpoint,
                data={"data": query},
                headers={"User-Agent": USER_AGENT},
                timeout=300,
            )
            if response.is_error:
                raise RuntimeError(
                    f"Overpass returned {response.status_code}: {response.text[:500]}"
                )
            payload = response.json()

            for element in payload.get("elements", []):
                if element.get("type") != "way":
                    continue

                feature = element_feature(element)
                if not feature:
                    continue

                if _insert_feature(
                    conn,
                    source=source,
                    source_url=endpoint,
                    feature=feature,
                ):
                    inserted += 1

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


def import_overpass_request(
    *,
    source: str,
    state: str | None,
    bbox: str | None,
    limit: int,
    timeout: int = 180,
    endpoint: str = DEFAULT_OVERPASS_URL,
) -> int:
    return import_overpass(
        endpoint=endpoint,
        source=source,
        query=query_for_request(state=state, bbox=bbox, limit=limit, timeout=timeout),
        limit=limit,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Import trail-like OSM ways from Overpass.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--state", help="Two-letter U.S. state abbreviation, such as TN.")
    group.add_argument("--bbox", help="Bounding box as west,south,east,north.")
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--endpoint", default=DEFAULT_OVERPASS_URL)
    args = parser.parse_args()

    if args.state:
        source = f"osm-overpass-{args.state.lower()}"
        query = state_query(args.state, args.limit, args.timeout)
    else:
        source = "osm-overpass-bbox"
        query = bbox_query(args.bbox, args.limit, args.timeout)

    count = import_overpass(
        endpoint=args.endpoint,
        source=source,
        query=query,
        limit=args.limit,
    )
    print(f"Imported {count} Overpass trail-like ways into {source}.")


if __name__ == "__main__":
    main()

import argparse
import tempfile
from pathlib import Path
import sys
from typing import Any

import httpx
import osmium
import psycopg
from psycopg.types.json import Jsonb

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.cache import (
    GEOFABRIK_STATE_SLUGS,
    mark_cache_failed,
    mark_cache_fetching,
    mark_cache_fresh,
)
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


def state_for_region(region: str) -> str | None:
    return next(
        (
            abbreviation
            for abbreviation, slug in GEOFABRIK_STATE_SLUGS.items()
            if slug == region
        ),
        None,
    )


def download_extract(url: str, destination: Path) -> None:
    headers = {"User-Agent": "Waymark/0.1 (Geofabrik trail importer)"}

    def stream_to_file(client: httpx.Client) -> None:
        with client.stream("GET", url) as response:
            response.raise_for_status()
            with destination.open("wb") as file:
                for chunk in response.iter_bytes():
                    file.write(chunk)

    try:
        with httpx.Client(
            headers=headers,
            follow_redirects=True,
            timeout=300,
        ) as client:
            stream_to_file(client)
    except httpx.ConnectError:
        destination.unlink(missing_ok=True)
        print("Initial connection failed; retrying Geofabrik over IPv4.")
        transport = httpx.HTTPTransport(local_address="0.0.0.0", retries=2)
        with httpx.Client(
            transport=transport,
            headers=headers,
            follow_redirects=True,
            timeout=300,
        ) as client:
            stream_to_file(client)


def is_trail_like(tags: dict[str, str]) -> bool:
    highway = tags.get("highway")
    route = tags.get("route")

    if tags.get("footway") == "sidewalk":
        return False
    if highway in TRAIL_HIGHWAYS:
        return True
    if route in TRAIL_ROUTES:
        return True
    if tags.get("foot") in {"yes", "designated", "permissive"} and highway:
        return True
    if tags.get("sac_scale"):
        return True

    return False


def allowed_uses(
    tags: dict[str, str],
    route_relations: list[dict[str, str]] | None = None,
) -> list[str]:
    uses: list[str] = []
    relation_routes = {
        relation["route"]
        for relation in route_relations or []
        if relation.get("route")
    }

    if (
        tags.get("foot") in {"yes", "designated", "permissive"}
        or tags.get("highway") in {"footway", "path", "steps"}
        or relation_routes.intersection({"foot", "hiking"})
    ):
        uses.append("hiking")
    if (
        tags.get("bicycle") in {"yes", "designated", "permissive"}
        or "mtb" in relation_routes
    ):
        uses.append("biking")
    if (
        tags.get("horse") in {"yes", "designated", "permissive"}
        or tags.get("highway") == "bridleway"
    ):
        uses.append("horse")

    return uses or ["unknown"]


def trail_type(
    tags: dict[str, str],
    route_relations: list[dict[str, str]] | None = None,
) -> str:
    relation_routes = {
        relation["route"]
        for relation in route_relations or []
        if relation.get("route")
    }
    if "mtb" in relation_routes:
        return "mountain_bike_route"
    if relation_routes.intersection({"foot", "hiking"}):
        return "hiking_route"
    if tags.get("footway") == "sidewalk":
        return "sidewalk"
    if tags.get("sac_scale"):
        return "alpine_hiking_trail"

    return {
        "bridleway": "equestrian_trail",
        "cycleway": "cycling_path",
        "footway": "footpath",
        "path": "path",
        "pedestrian": "pedestrian_path",
        "steps": "steps",
        "track": "track",
    }.get(tags.get("highway"), "trail")


class TrailRelationHandler(osmium.SimpleHandler):
    def __init__(self) -> None:
        super().__init__()
        self.way_relations: dict[int, list[dict[str, str]]] = {}
        self.relations: dict[str, dict[str, Any]] = {}
        self.relation_count = 0

    def relation(self, relation: Any) -> None:
        tags = {tag.k: tag.v for tag in relation.tags}
        if tags.get("type") != "route" or tags.get("route") not in TRAIL_ROUTES:
            return

        metadata = {
            "id": str(relation.id),
            "route": tags["route"],
            "name": tags.get("name", ""),
            "ref": tags.get("ref", ""),
            "network": tags.get("network", ""),
            "operator": tags.get("operator", ""),
            "difficulty": tags.get("sac_scale") or tags.get("mtb:scale", ""),
            "surface": tags.get("surface", ""),
        }
        way_ids = []
        for member in relation.members:
            if member.type == "w":
                self.way_relations.setdefault(member.ref, []).append(metadata)
                way_ids.append(str(member.ref))
        self.relations[metadata["id"]] = {
            **metadata,
            "way_ids": way_ids,
            "tags": tags,
        }
        self.relation_count += 1


class TrailWayHandler(osmium.SimpleHandler):
    def __init__(
        self,
        conn: psycopg.Connection,
        *,
        source: str,
        source_url: str,
        limit: int | None,
        way_relations: dict[int, list[dict[str, str]]] | None = None,
    ) -> None:
        super().__init__()
        self.conn = conn
        self.source = source
        self.source_url = source_url
        self.limit = limit
        self.way_relations = way_relations or {}
        self.accepted = 0
        self.seen = 0

    def way(self, way: Any) -> None:
        if self.limit is not None and self.accepted >= self.limit:
            return

        tags = {tag.k: tag.v for tag in way.tags}
        route_relations = self.way_relations.get(way.id, [])
        if not is_trail_like(tags) and not route_relations:
            return

        coordinates = []
        for node in way.nodes:
            if not node.location.valid():
                return
            coordinates.append([node.lon, node.lat])

        if len(coordinates) < 2:
            return

        named_relation = next(
            (relation for relation in route_relations if relation.get("name")),
            {},
        )
        properties = {
            **tags,
            "source_id": str(way.id),
            "name": tags.get("name") or named_relation.get("name"),
            "trail_type": trail_type(tags, route_relations),
            "surface": tags.get("surface"),
            "difficulty": tags.get("sac_scale") or tags.get("mtb:scale"),
            "allowed_uses": allowed_uses(tags, route_relations),
            "managing_agency": (
                tags.get("operator")
                or tags.get("owner")
                or named_relation.get("operator")
            ),
            "status": tags.get("access") or "unknown",
            "osm_route_relations": route_relations,
            "is_route_segment": bool(route_relations),
            "route_relation_ids": [
                relation["id"] for relation in route_relations
            ],
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


def consolidate_route_relations(
    conn: psycopg.Connection,
    *,
    source: str,
    source_url: str,
    relations: dict[str, dict[str, Any]],
) -> int:
    sql = """
        WITH member_geometries AS (
            SELECT geometry
            FROM trails
            WHERE source = %(source)s
              AND source_id = ANY(%(way_ids)s)
        ),
        merged AS (
            SELECT ST_Multi(
                ST_CollectionExtract(
                    ST_LineMerge(
                        ST_UnaryUnion(ST_Collect(geometry))
                    ),
                    2
                )
            ) AS geometry
            FROM member_geometries
        )
        INSERT INTO trails (
            name,
            geometry,
            length_meters,
            trail_type,
            difficulty,
            surface,
            allowed_uses,
            managing_agency,
            status,
            is_route_segment,
            route_relation_ids,
            source,
            source_id,
            source_url,
            raw_properties
        )
        SELECT
            %(name)s,
            geometry,
            ST_Length(geography(geometry)),
            %(trail_type)s,
            %(difficulty)s,
            %(surface)s,
            %(allowed_uses)s,
            %(managing_agency)s,
            'unknown',
            false,
            %(route_relation_ids)s,
            %(source)s,
            %(source_id)s,
            %(source_url)s,
            %(raw_properties)s
        FROM merged
        WHERE geometry IS NOT NULL
          AND NOT ST_IsEmpty(geometry)
        ON CONFLICT (source, source_id)
        WHERE source_id IS NOT NULL
        DO UPDATE SET
            name = EXCLUDED.name,
            geometry = EXCLUDED.geometry,
            length_meters = EXCLUDED.length_meters,
            trail_type = EXCLUDED.trail_type,
            difficulty = EXCLUDED.difficulty,
            surface = EXCLUDED.surface,
            allowed_uses = EXCLUDED.allowed_uses,
            managing_agency = EXCLUDED.managing_agency,
            is_route_segment = false,
            route_relation_ids = EXCLUDED.route_relation_ids,
            source_url = EXCLUDED.source_url,
            raw_properties = EXCLUDED.raw_properties,
            updated_at = now()
        RETURNING id
    """
    consolidated = 0
    for relation_id, relation in relations.items():
        way_ids = relation["way_ids"]
        if not way_ids:
            continue

        route = relation["route"]
        allowed = ["biking"] if route == "mtb" else ["hiking"]
        trail_kind = "mountain_bike_route" if route == "mtb" else "hiking_route"
        name = (
            relation.get("name")
            or relation.get("ref")
            or f"OSM {route} route {relation_id}"
        )
        row = conn.execute(
            sql,
            {
                "source": source,
                "way_ids": way_ids,
                "name": name,
                "trail_type": trail_kind,
                "difficulty": relation.get("difficulty") or None,
                "surface": relation.get("surface") or None,
                "allowed_uses": allowed,
                "managing_agency": relation.get("operator") or None,
                "route_relation_ids": [relation_id],
                "source_id": f"relation:{relation_id}",
                "source_url": source_url,
                "raw_properties": Jsonb(
                    {
                        "osm_relation_id": relation_id,
                        "osm_relation": relation["tags"],
                        "member_way_ids": way_ids,
                        "member_way_count": len(way_ids),
                    }
                ),
            },
        ).fetchone()
        if row:
            consolidated += 1

        if consolidated and consolidated % 100 == 0:
            conn.commit()
            print(f"Consolidated {consolidated} OSM route relations")

    return consolidated


def import_geofabrik(
    *,
    region: str,
    state: str | None,
    url: str | None,
    limit: int | None,
    keep_file: Path | None,
) -> int:
    source_url = url or region_url(region)
    source = f"osm-geofabrik-{region}"
    state = state.upper() if state else state_for_region(region)
    settings = get_settings()

    with tempfile.TemporaryDirectory() as temp_dir_name:
        pbf_path = keep_file or Path(temp_dir_name) / f"{region}.osm.pbf"
        index_path = Path(temp_dir_name) / f"{region}.locations"
        if not pbf_path.exists():
            print(f"Downloading {source_url}")
            download_extract(source_url, pbf_path)

        with psycopg.connect(settings.database_url) as conn:
            run_id = _create_ingest_run(
                conn,
                source=source,
                source_url=source_url,
                source_type="geofabrik-osm-pbf",
                source_filter="trail-like OSM ways and hiking/foot/MTB route members",
                requested_count=limit,
            )
            mark_cache_fetching(
                conn,
                provider="geofabrik",
                source=source,
                state=state,
                bbox=None,
            )
            conn.commit()

            handler = TrailWayHandler(
                conn,
                source=source,
                source_url=source_url,
                limit=limit,
            )
            try:
                relation_handler = TrailRelationHandler()
                relation_handler.apply_file(str(pbf_path))
                print(
                    "Found "
                    f"{relation_handler.relation_count} hiking/foot/MTB route relations "
                    f"covering {len(relation_handler.way_relations)} ways"
                )
                handler = TrailWayHandler(
                    conn,
                    source=source,
                    source_url=source_url,
                    limit=limit,
                    way_relations=relation_handler.way_relations,
                )
                handler.apply_file(
                    str(pbf_path),
                    locations=True,
                    idx=f"sparse_file_array,{index_path}",
                )
                consolidated = consolidate_route_relations(
                    conn,
                    source=source,
                    source_url=source_url,
                    relations=relation_handler.relations,
                )
                print(f"Consolidated {consolidated} OSM route relations")
                _finish_ingest_run(
                    conn,
                    run_id=run_id,
                    accepted_count=handler.accepted + consolidated,
                    status="succeeded",
                )
                mark_cache_fresh(
                    conn,
                    provider="geofabrik",
                    source=source,
                    state=state,
                    bbox=None,
                    feature_count=handler.accepted + consolidated,
                    ttl_days=30,
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
                mark_cache_failed(
                    conn,
                    provider="geofabrik",
                    source=source,
                    state=state,
                    bbox=None,
                    error=str(exc),
                )
                conn.commit()
                raise

    return handler.accepted


def main() -> None:
    parser = argparse.ArgumentParser(description="Import trail-like OSM ways from Geofabrik.")
    parser.add_argument("region", help="Geofabrik region slug, such as tennessee.")
    parser.add_argument(
        "--state",
        help="Optional state abbreviation. It is inferred for standard U.S. state slugs.",
    )
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
        state=args.state,
        url=args.url,
        limit=args.limit,
        keep_file=args.file,
    )
    print(f"Imported {count} Geofabrik trail-like ways for {args.region}.")


if __name__ == "__main__":
    main()

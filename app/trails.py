from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from psycopg import Connection
from psycopg.rows import dict_row

from app.cache import (
    get_cache_entry,
    is_fresh,
    mark_cache_failed,
    mark_cache_fetching,
    mark_cache_fresh,
    source_for_request,
)
from app.db import get_connection
from app.models import (
    CityPlace,
    FeatureCollection,
    StateBoundary,
    TrailFeature,
    WanderlyTrail,
)
from scripts.import_overpass import import_overpass_request

router = APIRouter(prefix="/api", tags=["trails"])

HIKE_INTENT_SQL = """
    'hiking' = ANY(allowed_uses)
    AND COALESCE(trail_type, '') IN (
        'hiking_route',
        'alpine_hiking_trail',
        'footpath',
        'path',
        'track',
        'steps',
        'trail'
    )
    AND COALESCE(raw_properties->>'footway', '') NOT IN (
        'sidewalk',
        'crossing'
    )
    AND (
        COALESCE(raw_properties->>'foot', '') <> 'no'
        OR source_id LIKE 'relation:%%'
    )
"""


def _is_hike_intent(row: dict[str, Any]) -> bool:
    raw = row["raw_properties"] or {}
    return (
        "hiking" in (row["allowed_uses"] or [])
        and row["trail_type"]
        in {
            "hiking_route",
            "alpine_hiking_trail",
            "footpath",
            "path",
            "track",
            "steps",
            "trail",
        }
        and raw.get("footway") not in {"sidewalk", "crossing"}
        and (
            raw.get("foot") != "no"
            or str(row.get("source_id") or "").startswith("relation:")
        )
    )


def _feature_from_row(row: dict[str, Any]) -> TrailFeature:
    return TrailFeature(
        id=row["id"],
        geometry=row["geometry"],
        properties={
            "name": row["name"],
            "length_meters": row["length_meters"],
            "trail_type": row["trail_type"],
            "difficulty": row["difficulty"],
            "surface": row["surface"],
            "allowed_uses": row["allowed_uses"] or [],
            "managing_agency": row["managing_agency"],
            "status": row["status"],
            "hike_intent": _is_hike_intent(row),
            "is_route_segment": row["is_route_segment"],
            "route_relation_ids": row["route_relation_ids"] or [],
            "source": row["source"],
            "source_id": row["source_id"],
            "source_url": row["source_url"],
            "raw_properties": row["raw_properties"] or {},
        },
    )


@router.get("/trails", response_model=FeatureCollection)
def list_trails(
    bbox: str | None = Query(
        default=None,
        description="Optional minLng,minLat,maxLng,maxLat filter.",
    ),
    source: str | None = Query(default=None),
    provider: str | None = Query(default=None, pattern="^(osm|nps|geofabrik)$"),
    fetch_if_missing: bool = Query(default=False),
    state: str | None = Query(
        default=None,
        description="State abbreviation or name, such as TN or North Carolina.",
    ),
    status: str | None = Query(default=None),
    use: str | None = Query(default=None, description="Allowed use, such as hiking."),
    trail_type: str | None = Query(default=None),
    include_sidewalks: bool = Query(default=False),
    hike_intent: bool = Query(default=False),
    include_segments: bool = Query(default=False),
    min_length_km: float | None = Query(default=None, ge=0),
    max_length_km: float | None = Query(default=None, gt=0),
    difficulty: str | None = Query(default=None),
    surface: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    conn: Connection = Depends(get_connection),
) -> FeatureCollection:
    source = _ensure_data_if_requested(
        conn,
        provider=provider,
        source=source,
        state=state,
        bbox=bbox,
        fetch_if_missing=fetch_if_missing,
        limit=limit,
    )

    params: dict[str, Any] = {"limit": limit}
    conditions: list[str] = []
    _validate_length_range(min_length_km, max_length_km)

    if bbox:
        parts = [float(part.strip()) for part in bbox.split(",")]
        if len(parts) != 4:
            raise HTTPException(status_code=400, detail="bbox must contain four numbers.")
        params.update(
            {
                "min_lng": parts[0],
                "min_lat": parts[1],
                "max_lng": parts[2],
                "max_lat": parts[3],
            }
        )
        conditions.append(
            """
            geometry && ST_MakeEnvelope(
                %(min_lng)s, %(min_lat)s, %(max_lng)s, %(max_lat)s, 4326
            )
            """
        )

    if source:
        params["source"] = source
        conditions.append("source = %(source)s")

    if state:
        params["state"] = state
        conditions.append(
            """
            EXISTS (
                SELECT 1
                FROM states
                WHERE (
                    abbreviation = upper(%(state)s)
                    OR lower(name) = lower(%(state)s)
                )
                AND ST_Intersects(trails.geometry, states.geometry)
            )
            """
        )

    if status:
        params["status"] = status
        conditions.append("status = %(status)s")

    if use:
        params["use"] = use.lower()
        conditions.append("%(use)s = ANY(allowed_uses)")

    if trail_type:
        params["trail_type"] = trail_type
        conditions.append("trail_type = %(trail_type)s")

    if not include_sidewalks:
        conditions.append(
            """
            COALESCE(trail_type, '') <> 'sidewalk'
            AND COALESCE(raw_properties->>'footway', '') <> 'sidewalk'
            """
        )

    if hike_intent:
        conditions.append(HIKE_INTENT_SQL)

    if not include_segments:
        conditions.append("NOT is_route_segment")

    if min_length_km is not None:
        params["min_length_m"] = min_length_km * 1000
        conditions.append("length_meters >= %(min_length_m)s")

    if max_length_km is not None:
        params["max_length_m"] = max_length_km * 1000
        conditions.append("length_meters <= %(max_length_m)s")

    if difficulty:
        params["difficulty"] = difficulty
        conditions.append("difficulty = %(difficulty)s")

    if surface:
        params["surface"] = surface
        conditions.append("surface = %(surface)s")

    where = ""
    if conditions:
        where = "WHERE " + " AND ".join(conditions)

    sql = f"""
        SELECT *, ST_AsGeoJSON(geometry)::json AS geometry
        FROM trails
        {where}
        ORDER BY name NULLS LAST, created_at DESC
        LIMIT %(limit)s
    """

    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(sql, params)
        features = [_feature_from_row(row) for row in cur.fetchall()]

    return FeatureCollection(features=features)


@router.get("/trails.geojson", response_model=FeatureCollection)
def trails_geojson(
    bbox: str | None = None,
    source: str | None = None,
    provider: str | None = Query(default=None, pattern="^(osm|nps|geofabrik)$"),
    fetch_if_missing: bool = False,
    state: str | None = None,
    status: str | None = None,
    use: str | None = None,
    trail_type: str | None = None,
    include_sidewalks: bool = False,
    hike_intent: bool = False,
    include_segments: bool = False,
    min_length_km: float | None = Query(default=None, ge=0),
    max_length_km: float | None = Query(default=None, gt=0),
    difficulty: str | None = None,
    surface: str | None = None,
    limit: int = Query(default=500, ge=1, le=2000),
    conn: Connection = Depends(get_connection),
) -> FeatureCollection:
    return list_trails(
        bbox=bbox,
        source=source,
        provider=provider,
        fetch_if_missing=fetch_if_missing,
        state=state,
        status=status,
        use=use,
        trail_type=trail_type,
        include_sidewalks=include_sidewalks,
        hike_intent=hike_intent,
        include_segments=include_segments,
        min_length_km=min_length_km,
        max_length_km=max_length_km,
        difficulty=difficulty,
        surface=surface,
        limit=limit,
        conn=conn,
    )


def _ensure_data_if_requested(
    conn: Connection,
    *,
    provider: str | None,
    source: str | None,
    state: str | None,
    bbox: str | None,
    fetch_if_missing: bool,
    limit: int,
) -> str | None:
    if not provider:
        return source

    if source:
        return source

    resolved_source = source_for_request(provider, state, bbox)
    if not fetch_if_missing:
        return resolved_source

    if provider == "geofabrik":
        if not state:
            raise HTTPException(
                status_code=400,
                detail="state is required when provider=geofabrik.",
            )

        entry = get_cache_entry(
            conn,
            provider=provider,
            source=resolved_source,
            state=state.upper(),
            bbox=None,
        )
        if is_fresh(entry):
            return resolved_source

        region = resolved_source.removeprefix("osm-geofabrik-")
        raise HTTPException(
            status_code=409,
            detail=(
                f"Geofabrik data is not cached for {state}. "
                f"Run `python scripts/import_geofabrik.py {region} "
                f"--state {state.upper()}` in a Render shell or background worker, "
                "then retry the request."
            ),
        )

    if provider != "osm":
        raise HTTPException(
            status_code=400,
            detail="On-demand fetching currently supports provider=osm only.",
        )

    if not state and not bbox:
        raise HTTPException(
            status_code=400,
            detail="state or bbox is required for on-demand OSM fetching.",
        )

    if limit > 500:
        raise HTTPException(
            status_code=400,
            detail="On-demand OSM fetch limit cannot exceed 500.",
        )

    entry = get_cache_entry(
        conn,
        provider=provider,
        source=resolved_source,
        state=state,
        bbox=bbox,
    )
    if is_fresh(entry):
        return resolved_source

    mark_cache_fetching(
        conn,
        provider=provider,
        source=resolved_source,
        state=state,
        bbox=bbox,
    )
    conn.commit()

    try:
        count = import_overpass_request(
            source=resolved_source,
            state=state,
            bbox=bbox,
            limit=limit,
        )
        mark_cache_fresh(
            conn,
            provider=provider,
            source=resolved_source,
            state=state,
            bbox=bbox,
            feature_count=count,
        )
        conn.commit()
    except Exception as exc:
        mark_cache_failed(
            conn,
            provider=provider,
            source=resolved_source,
            state=state,
            bbox=bbox,
            error=str(exc),
        )
        conn.commit()
        raise HTTPException(status_code=502, detail=f"OSM fetch failed: {exc}") from exc

    return resolved_source


@router.get("/states", response_model=list[StateBoundary])
def list_states(conn: Connection = Depends(get_connection)) -> list[StateBoundary]:
    sql = """
        SELECT abbreviation, name, fips
        FROM states
        ORDER BY name
    """
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(sql)
        return [StateBoundary(**row) for row in cur.fetchall()]


@router.get("/trails/nearby", response_model=FeatureCollection)
def nearby_trails(
    lat: float | None = Query(default=None, ge=-90, le=90),
    lng: float | None = Query(default=None, ge=-180, le=180),
    city: str | None = Query(default=None, min_length=1),
    state: str | None = Query(default=None, min_length=2),
    radius_km: float = Query(default=10, gt=0, le=100),
    include_sidewalks: bool = Query(default=False),
    hike_intent: bool = Query(default=False),
    include_segments: bool = Query(default=False),
    min_length_km: float | None = Query(default=None, ge=0),
    max_length_km: float | None = Query(default=None, gt=0),
    limit: int = Query(default=100, ge=1, le=500),
    conn: Connection = Depends(get_connection),
) -> FeatureCollection:
    _validate_length_range(min_length_km, max_length_km)
    lat, lng = _resolve_nearby_origin(
        conn,
        lat=lat,
        lng=lng,
        city=city,
        state=state,
    )
    sql = """
        SELECT *, ST_AsGeoJSON(geometry)::json AS geometry
        FROM trails
        WHERE geometry && ST_Envelope(
            ST_Buffer(
                geography(ST_SetSRID(ST_MakePoint(%(lng)s, %(lat)s), 4326)),
                %(radius_m)s
            )::geometry
        )
        AND ST_DWithin(
            geography(geometry),
            geography(ST_SetSRID(ST_MakePoint(%(lng)s, %(lat)s), 4326)),
            %(radius_m)s
        )
        AND (
            %(include_sidewalks)s
            OR (
                COALESCE(trail_type, '') <> 'sidewalk'
                AND COALESCE(raw_properties->>'footway', '') <> 'sidewalk'
            )
        )
        AND (
            NOT %(hike_intent)s
            OR (
                'hiking' = ANY(allowed_uses)
                AND COALESCE(trail_type, '') IN (
                    'hiking_route',
                    'alpine_hiking_trail',
                    'footpath',
                    'path',
                    'track',
                    'steps',
                    'trail'
                )
                AND COALESCE(raw_properties->>'footway', '') NOT IN (
                    'sidewalk',
                    'crossing'
                )
                AND (
                    COALESCE(raw_properties->>'foot', '') <> 'no'
                    OR source_id LIKE 'relation:%%'
                )
            )
        )
        AND (%(include_segments)s OR NOT is_route_segment)
        AND (
            %(min_length_m)s IS NULL
            OR length_meters >= %(min_length_m)s
        )
        AND (
            %(max_length_m)s IS NULL
            OR length_meters <= %(max_length_m)s
        )
        ORDER BY
            CASE WHEN name IS NULL OR trim(name) = '' THEN 1 ELSE 0 END,
            ST_Distance(
                geography(geometry),
                geography(ST_SetSRID(ST_MakePoint(%(lng)s, %(lat)s), 4326))
            )
        LIMIT %(limit)s
    """
    params = {
        "lat": lat,
        "lng": lng,
        "radius_m": radius_km * 1000,
        "include_sidewalks": include_sidewalks,
        "hike_intent": hike_intent,
        "include_segments": include_segments,
        "min_length_m": (
            min_length_km * 1000 if min_length_km is not None else None
        ),
        "max_length_m": (
            max_length_km * 1000 if max_length_km is not None else None
        ),
        "limit": limit,
    }

    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(sql, params)
        features = [_feature_from_row(row) for row in cur.fetchall()]

    return FeatureCollection(features=features)


def _normalized_difficulty(
    raw_difficulties: list[str],
    trail_types: list[str],
    distance_miles: float,
) -> str:
    values = " ".join(raw_difficulties + trail_types).lower()
    hard_markers = (
        "alpine",
        "demanding",
        "difficult",
        "expert",
        "black",
        "class 4",
        "class 5",
    )
    moderate_markers = (
        "mountain_hiking",
        "mountain hiking",
        "moderate",
        "intermediate",
        "class 2",
        "class 3",
    )

    tagged_difficulty = "easy"
    if any(marker in values for marker in hard_markers):
        tagged_difficulty = "hard"
    elif any(marker in values for marker in moderate_markers):
        tagged_difficulty = "moderate"

    distance_difficulty = "easy"
    if distance_miles >= 8:
        distance_difficulty = "hard"
    elif distance_miles >= 3:
        distance_difficulty = "moderate"

    rank = {"easy": 0, "moderate": 1, "hard": 2}
    return max(
        (tagged_difficulty, distance_difficulty),
        key=rank.__getitem__,
    )


def _wanderly_category(distance_miles: float, difficulty: str) -> str:
    if difficulty == "hard" or distance_miles >= 8:
        return "major_hike"
    if difficulty == "moderate" or distance_miles >= 3:
        return "moderate_hike"
    return "walk"


def _estimated_duration_hours(length_meters: float, difficulty: str) -> float:
    base_hours = (length_meters / 1000) / 5
    difficulty_factor = {
        "easy": 1.0,
        "moderate": 1.15,
        "hard": 1.35,
    }[difficulty]
    return round(base_hours * difficulty_factor, 2)


@router.get(
    "/wanderly/trails/nearby",
    response_model=list[WanderlyTrail],
    response_model_by_alias=True,
)
def wanderly_nearby_trails(
    lat: float = Query(..., ge=-90, le=90),
    lng: float = Query(..., ge=-180, le=180),
    radius_km: float = Query(default=30, gt=0, le=100),
    limit: int = Query(default=100, ge=1, le=500),
    conn: Connection = Depends(get_connection),
) -> list[WanderlyTrail]:
    sql = """
        WITH candidates AS (
            SELECT
                id,
                trim(name) AS name,
                geometry,
                difficulty,
                trail_type
            FROM trails
            WHERE name IS NOT NULL
              AND trim(name) <> ''
              AND NOT is_route_segment
              AND """ + HIKE_INTENT_SQL + """
              AND geometry && ST_Envelope(
                  ST_Buffer(
                      geography(
                          ST_SetSRID(ST_MakePoint(%(lng)s, %(lat)s), 4326)
                      ),
                      %(radius_m)s
                  )::geometry
              )
              AND ST_DWithin(
                  geography(geometry),
                  geography(
                      ST_SetSRID(ST_MakePoint(%(lng)s, %(lat)s), 4326)
                  ),
                  %(radius_m)s
              )
        ),
        grouped AS (
            SELECT
                lower(name) AS name_key,
                min(id::text) AS id,
                min(name) AS name,
                array_remove(array_agg(DISTINCT difficulty), NULL)
                    AS raw_difficulties,
                array_remove(array_agg(DISTINCT trail_type), NULL)
                    AS trail_types,
                ST_Multi(
                    ST_CollectionExtract(
                        ST_LineMerge(
                            ST_UnaryUnion(ST_Collect(geometry))
                        ),
                        2
                    )
                ) AS geometry
            FROM candidates
            GROUP BY lower(name)
        ),
        measured AS (
            SELECT
                id,
                name,
                raw_difficulties,
                trail_types,
                geometry,
                ST_Length(geography(geometry)) AS length_meters,
                ST_Y(ST_Centroid(geometry)) AS center_lat,
                ST_X(ST_Centroid(geometry)) AS center_lng,
                ST_Distance(
                    geography(geometry),
                    geography(
                        ST_SetSRID(ST_MakePoint(%(lng)s, %(lat)s), 4326)
                    )
                ) AS distance_from_origin
            FROM grouped
            WHERE geometry IS NOT NULL
              AND NOT ST_IsEmpty(geometry)
        )
        SELECT *
        FROM measured
        WHERE length_meters > 0
        ORDER BY
            CASE WHEN 'hiking_route' = ANY(trail_types) THEN 0 ELSE 1 END,
            distance_from_origin,
            name
        LIMIT %(limit)s
    """
    params = {
        "lat": lat,
        "lng": lng,
        "radius_m": radius_km * 1000,
        "limit": limit,
    }

    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()

    trails = []
    for row in rows:
        length_meters = float(row["length_meters"])
        distance_miles = round(length_meters / 1609.344, 2)
        difficulty = _normalized_difficulty(
            row["raw_difficulties"] or [],
            row["trail_types"] or [],
            distance_miles,
        )
        trails.append(
            WanderlyTrail(
                id=row["id"],
                name=row["name"],
                distance_miles=distance_miles,
                estimated_duration_hours=_estimated_duration_hours(
                    length_meters,
                    difficulty,
                ),
                difficulty=difficulty,
                category=_wanderly_category(distance_miles, difficulty),
                center_lat=float(row["center_lat"]),
                center_lng=float(row["center_lng"]),
            )
        )

    return trails


def _validate_length_range(
    min_length_km: float | None,
    max_length_km: float | None,
) -> None:
    if (
        min_length_km is not None
        and max_length_km is not None
        and min_length_km > max_length_km
    ):
        raise HTTPException(
            status_code=400,
            detail="min_length_km cannot exceed max_length_km.",
        )


def _resolve_nearby_origin(
    conn: Connection,
    *,
    lat: float | None,
    lng: float | None,
    city: str | None,
    state: str | None,
) -> tuple[float, float]:
    has_coordinates = lat is not None or lng is not None
    has_city = city is not None or state is not None

    if has_coordinates and has_city:
        raise HTTPException(
            status_code=400,
            detail="Use either lat/lng or city/state, not both.",
        )

    if has_coordinates:
        if lat is None or lng is None:
            raise HTTPException(
                status_code=400,
                detail="Both lat and lng are required.",
            )
        return lat, lng

    if not city or not state:
        raise HTTPException(
            status_code=400,
            detail="Provide either lat/lng or city/state.",
        )

    sql = """
        SELECT
            ST_Y(geometry) AS lat,
            ST_X(geometry) AS lng
        FROM cities
        WHERE (
            lower(name) = lower(%(city)s)
            OR name ILIKE %(city_prefix)s
        )
          AND state = upper(%(state)s)
        ORDER BY
            CASE WHEN lower(name) = lower(%(city)s) THEN 0 ELSE 1 END,
            length(name),
            name
        LIMIT 1
    """
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            sql,
            {
                "city": city.strip(),
                "city_prefix": f"{city.strip()}%",
                "state": state.strip(),
            },
        )
        place = cur.fetchone()

    if not place:
        raise HTTPException(
            status_code=404,
            detail=f"City not found: {city}, {state.upper()}.",
        )

    return place["lat"], place["lng"]


@router.get("/cities", response_model=list[CityPlace])
def list_cities(
    query: str = Query(..., min_length=2),
    state: str | None = Query(default=None, min_length=2),
    limit: int = Query(default=10, ge=1, le=50),
    conn: Connection = Depends(get_connection),
) -> list[CityPlace]:
    conditions = ["name ILIKE %(query)s"]
    params: dict[str, Any] = {
        "query": f"{query.strip()}%",
        "limit": limit,
    }
    if state:
        conditions.append("state = upper(%(state)s)")
        params["state"] = state.strip()

    sql = f"""
        SELECT
            name,
            state,
            ST_Y(geometry) AS lat,
            ST_X(geometry) AS lng
        FROM cities
        WHERE {" AND ".join(conditions)}
        ORDER BY name, state
        LIMIT %(limit)s
    """
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(sql, params)
        return [CityPlace(**row) for row in cur.fetchall()]


@router.get("/trails/{trail_id}", response_model=TrailFeature)
def get_trail(
    trail_id: UUID,
    conn: Connection = Depends(get_connection),
) -> TrailFeature:
    sql = """
        SELECT *, ST_AsGeoJSON(geometry)::json AS geometry
        FROM trails
        WHERE id = %(trail_id)s
    """
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(sql, {"trail_id": trail_id})
        row = cur.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Trail not found.")

    return _feature_from_row(row)

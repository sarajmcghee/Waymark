from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from psycopg import Connection
from psycopg.rows import dict_row

from app.db import get_connection
from app.models import FeatureCollection, TrailFeature

router = APIRouter(prefix="/api", tags=["trails"])


def _feature_from_row(row: dict[str, Any]) -> TrailFeature:
    return TrailFeature(
        id=row["id"],
        geometry=row["geometry"],
        properties={
            "name": row["name"],
            "length_meters": row["length_meters"],
            "difficulty": row["difficulty"],
            "surface": row["surface"],
            "allowed_uses": row["allowed_uses"] or [],
            "managing_agency": row["managing_agency"],
            "status": row["status"],
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
    limit: int = Query(default=100, ge=1, le=500),
    conn: Connection = Depends(get_connection),
) -> FeatureCollection:
    params: dict[str, Any] = {"limit": limit}
    where = ""

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
        where = """
            WHERE geometry && ST_MakeEnvelope(
                %(min_lng)s, %(min_lat)s, %(max_lng)s, %(max_lat)s, 4326
            )
        """

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
    limit: int = Query(default=500, ge=1, le=2000),
    conn: Connection = Depends(get_connection),
) -> FeatureCollection:
    return list_trails(bbox=bbox, limit=limit, conn=conn)


@router.get("/trails/nearby", response_model=FeatureCollection)
def nearby_trails(
    lat: float = Query(..., ge=-90, le=90),
    lng: float = Query(..., ge=-180, le=180),
    radius_km: float = Query(default=10, gt=0, le=100),
    limit: int = Query(default=100, ge=1, le=500),
    conn: Connection = Depends(get_connection),
) -> FeatureCollection:
    sql = """
        SELECT *, ST_AsGeoJSON(geometry)::json AS geometry
        FROM trails
        WHERE ST_DWithin(
            geography(geometry),
            geography(ST_SetSRID(ST_MakePoint(%(lng)s, %(lat)s), 4326)),
            %(radius_m)s
        )
        ORDER BY ST_Distance(
            geography(geometry),
            geography(ST_SetSRID(ST_MakePoint(%(lng)s, %(lat)s), 4326))
        )
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
        features = [_feature_from_row(row) for row in cur.fetchall()]

    return FeatureCollection(features=features)


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

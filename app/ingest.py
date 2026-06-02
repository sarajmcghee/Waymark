from typing import Any
import json

import httpx
from fastapi import APIRouter, Depends
from psycopg import Connection
from psycopg.types.json import Jsonb

from app.auth import require_admin
from app.db import get_connection
from app.models import ArcgisIngestRequest, GeoJsonIngestRequest

router = APIRouter(prefix="/api/ingest", tags=["ingest"])


def _coerce_multiline(geometry: dict[str, Any]) -> dict[str, Any] | None:
    geom_type = geometry.get("type")

    if geom_type == "LineString":
        return {"type": "MultiLineString", "coordinates": [geometry.get("coordinates", [])]}
    if geom_type == "MultiLineString":
        return geometry

    return None


def _pick(properties: dict[str, Any], names: list[str]) -> Any:
    lowered = {key.lower(): value for key, value in properties.items()}
    for name in names:
        value = lowered.get(name.lower())
        if value not in (None, ""):
            return value
    return None


def _length_meters(properties: dict[str, Any]) -> float | None:
    meters = _pick(properties, ["length_meters", "length_m", "meters"])
    if meters not in (None, ""):
        return float(meters)

    miles = _pick(properties, ["miles", "length_miles", "mi"])
    if miles not in (None, ""):
        return float(miles) * 1609.344

    kilometers = _pick(properties, ["kilometers", "length_km", "km"])
    if kilometers not in (None, ""):
        return float(kilometers) * 1000

    return None


def _insert_feature(
    conn: Connection,
    *,
    source: str,
    source_url: str | None,
    feature: dict[str, Any],
) -> bool:
    geometry = _coerce_multiline(feature.get("geometry") or {})
    if not geometry:
        return False

    properties = feature.get("properties") or {}
    source_id = str(
        feature.get("id")
        or _pick(
            properties,
            [
                "source_id",
                "objectid",
                "globalid",
                "id",
                "trail_id",
                "featureid",
                "geometryid",
            ],
        )
        or ""
    )

    allowed_uses = []
    uses_value = _pick(properties, ["allowed_uses", "uses", "use_type", "trailuse", "trluse"])
    if isinstance(uses_value, list):
        allowed_uses = [str(value).lower() for value in uses_value]
    elif isinstance(uses_value, str):
        allowed_uses = [
            value.strip().lower()
            for value in uses_value.replace(";", ",").split(",")
            if value.strip()
        ]

    sql = """
        INSERT INTO trails (
            name,
            geometry,
            length_meters,
            difficulty,
            surface,
            allowed_uses,
            managing_agency,
            status,
            source,
            source_id,
            source_url,
            raw_properties
        )
        VALUES (
            %(name)s,
            ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(%(geometry)s), 4326)),
            %(length_meters)s,
            %(difficulty)s,
            %(surface)s,
            %(allowed_uses)s,
            %(managing_agency)s,
            %(status)s,
            %(source)s,
            NULLIF(%(source_id)s, ''),
            %(source_url)s,
            %(raw_properties)s
        )
        ON CONFLICT (source, source_id)
        WHERE source_id IS NOT NULL
        DO UPDATE SET
            name = EXCLUDED.name,
            geometry = EXCLUDED.geometry,
            length_meters = EXCLUDED.length_meters,
            difficulty = EXCLUDED.difficulty,
            surface = EXCLUDED.surface,
            allowed_uses = EXCLUDED.allowed_uses,
            managing_agency = EXCLUDED.managing_agency,
            status = EXCLUDED.status,
            source_url = EXCLUDED.source_url,
            raw_properties = EXCLUDED.raw_properties,
            updated_at = now()
    """
    conn.execute(
        sql,
        {
            "name": _pick(
                properties,
                ["name", "trail_name", "trailname", "route_name", "trlname", "maplabel"],
            ),
            "geometry": json.dumps(geometry),
            "length_meters": _length_meters(properties),
            "difficulty": _pick(
                properties,
                ["difficulty", "difficulty_rating", "sac_scale", "trlclass"],
            ),
            "surface": _pick(properties, ["surface", "surface_type", "trlsurface"]),
            "allowed_uses": allowed_uses,
            "managing_agency": _pick(
                properties,
                ["managing_agency", "agency", "manager", "maintainer", "unitname"],
            ),
            "status": _pick(properties, ["status", "access", "trlstatus", "opentopublic"])
            or "unknown",
            "source": source,
            "source_id": source_id,
            "source_url": source_url,
            "raw_properties": Jsonb(properties),
        },
    )
    return True


@router.post("/geojson")
def ingest_geojson(
    request: GeoJsonIngestRequest,
    _: dict = Depends(require_admin),
    conn: Connection = Depends(get_connection),
) -> dict[str, int | str]:
    inserted = 0
    for feature in request.features:
        if _insert_feature(
            conn,
            source=request.source,
            source_url=str(request.source_url) if request.source_url else None,
            feature=feature,
        ):
            inserted += 1

    conn.commit()
    return {"source": request.source, "accepted": inserted}


@router.post("/arcgis")
def ingest_arcgis(
    request: ArcgisIngestRequest,
    _: dict = Depends(require_admin),
    conn: Connection = Depends(get_connection),
) -> dict[str, int | str]:
    params = {
        "f": "geojson",
        "where": request.where,
        "outFields": request.out_fields,
        "returnGeometry": "true",
        "resultRecordCount": request.result_record_count,
    }
    response = httpx.get(str(request.url), params=params, timeout=60)
    response.raise_for_status()
    collection = response.json()

    inserted = 0
    for feature in collection.get("features", []):
        if _insert_feature(
            conn,
            source=request.source,
            source_url=str(request.url),
            feature=feature,
        ):
            inserted += 1

    conn.commit()
    return {"source": request.source, "accepted": inserted}

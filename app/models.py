from typing import Any
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, HttpUrl


class TrailProperties(BaseModel):
    name: str | None = None
    length_meters: float | None = None
    trail_type: str | None = None
    difficulty: str | None = None
    surface: str | None = None
    allowed_uses: list[str] = Field(default_factory=list)
    managing_agency: str | None = None
    status: str = "unknown"
    is_route_segment: bool = False
    route_relation_ids: list[str] = Field(default_factory=list)
    source: str
    source_id: str | None = None
    source_url: str | None = None
    raw_properties: dict[str, Any] = Field(default_factory=dict)


class TrailFeature(BaseModel):
    type: str = "Feature"
    id: UUID
    geometry: dict[str, Any]
    properties: TrailProperties


class FeatureCollection(BaseModel):
    type: str = "FeatureCollection"
    features: list[TrailFeature]


class GeoJsonIngestRequest(BaseModel):
    source: str
    source_url: HttpUrl | None = None
    features: list[dict[str, Any]]


class ArcgisIngestRequest(BaseModel):
    source: str
    url: HttpUrl
    where: str = "1=1"
    out_fields: str = "*"
    result_record_count: int = 2000
    max_pages: int = 1


class IngestRun(BaseModel):
    id: UUID
    source: str
    source_url: str | None = None
    source_type: str
    source_filter: str | None = None
    requested_count: int | None = None
    accepted_count: int
    status: str
    error: str | None = None
    started_at: datetime
    completed_at: datetime | None = None


class StateBoundary(BaseModel):
    abbreviation: str
    name: str
    fips: str


class CityPlace(BaseModel):
    name: str
    state: str
    lat: float
    lng: float

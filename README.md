# Waymark

Waymark is a GIS data service for hiking and outdoor applications. It ingests trail data from public geospatial sources, normalizes it into PostGIS, and exposes clean GeoJSON endpoints that other apps can consume.

## Architecture

```text
External GIS sources -> ingestion jobs -> PostGIS -> FastAPI endpoints -> client apps
                                      \
                                       Firebase Auth for protected writes/admin APIs
```

Firebase is used as the app platform layer: auth, hosting, analytics, storage, and optionally Cloud Functions. PostGIS is the spatial database for trail geometry, bounding box queries, nearby queries, source tracking, and GeoJSON output.

## Quick Start

1. Copy the environment file:

   ```bash
   cp .env.example .env
   ```

2. Start PostGIS:

   ```bash
   docker compose up -d db
   ```

3. Install Python dependencies:

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

4. Apply the schema:

   ```bash
   psql "$DATABASE_URL" -f db/migrations/001_init.sql
   ```

5. Run the API:

   ```bash
   uvicorn app.main:app --reload
   ```

The API will be available at `http://127.0.0.1:8000`.

## Core Endpoints

```http
GET /health
GET /api/trails
GET /api/trails/{trail_id}
GET /api/trails/nearby?lat=35.61&lng=-83.49&radius_km=10
GET /api/trails.geojson
GET /map
GET /admin
POST /api/ingest/geojson
POST /api/ingest/arcgis
GET /api/ingest/runs
GET /api/admin/stats
GET /api/admin/source-presets
```

`/map` is a lightweight local viewer for visually checking imported trail data.
`/admin` is a local control panel for viewing counts, import history, and running source preset imports.

Trail collection endpoints support filters:

```http
GET /api/trails?source=nps-public-trails-grsm
GET /api/trails?status=Existing
GET /api/trails?use=hiking
GET /api/trails?difficulty=Class%203:%20Developed
GET /api/trails?surface=Native
GET /api/trails.geojson?bbox=-84,35,-83,36&limit=500
```

Ingest runs are recorded in `ingest_runs` so admin tools can show source history, accepted counts, status, and errors.

The ingest endpoints are intended for admin workflows and can be protected with Firebase ID token verification by setting `FIREBASE_PROJECT_ID`.

## Data Sources To Start With

- USGS National Digital Trails for nationwide official trail data.
- NPS Public Trails for National Park Service trail geometries.
- OpenStreetMap/Overpass as an enrichment or fallback source.
- Agency-specific ArcGIS FeatureServer endpoints for state and local trail data.

## Development Notes

- Spatial data is stored as `geometry(MultiLineString, 4326)`.
- API responses are GeoJSON-friendly.
- `source`, `source_id`, and `source_url` are first-class fields so downstream apps can display attribution.
- Keep raw source payloads in `raw_properties` for traceability.

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
GET /api/states
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

## Firebase Auth

Local development works without Firebase when Firebase env vars are blank. To require sign-in for admin APIs and `/admin` actions, set:

```bash
FIREBASE_PROJECT_ID=your-project-id
FIREBASE_API_KEY=your-web-api-key
FIREBASE_AUTH_DOMAIN=your-project-id.firebaseapp.com
FIREBASE_APP_ID=your-web-app-id
```

The API verifies Firebase ID tokens and requires a custom `admin: true` claim for protected admin/import endpoints.

Trail collection endpoints support filters:

```http
GET /api/trails?source=nps-public-trails-grsm
GET /api/trails?state=TN
GET /api/trails?state=North%20Carolina
GET /api/trails?status=Existing
GET /api/trails?use=hiking
GET /api/trails?difficulty=Class%203:%20Developed
GET /api/trails?surface=Native
GET /api/trails.geojson?bbox=-84,35,-83,36&limit=500
GET /api/trails.geojson?state=TN&limit=500
```

Ingest runs are recorded in `ingest_runs` so admin tools can show source history, accepted counts, status, and errors.

ArcGIS ingest supports pagination:

```json
{
  "source": "nps-public-trails-all",
  "url": "https://mapservices.nps.gov/arcgis/rest/services/NationalDatasets/NPS_Public_Trails_Geographic/FeatureServer/0/query",
  "where": "1=1",
  "out_fields": "*",
  "result_record_count": 1000,
  "max_pages": 40
}
```

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

## Render Deployment

Use the Render Postgres internal database URL as `DATABASE_URL` on the Render web service. Do not commit database URLs because they include credentials.

Build command:

```bash
pip install -r requirements.txt
```

Start command:

```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

After setting `DATABASE_URL`, run migrations from a Render shell:

```bash
python scripts/migrate.py
```

Import U.S. state boundaries so `state=TN` style filters work:

```bash
python scripts/import_states.py
```

Then open `/admin` on the deployed service and run the source preset imports.
Use **All NPS Public Trails** to load nationwide NPS trail coverage, then consumers can query by state:

```http
GET /api/trails.geojson?state=TN&limit=500
GET /api/trails.geojson?state=California&limit=500
```

For the full national NPS import, prefer running this in a Render shell:

```bash
python scripts/import_nps_trails.py
```

## Geofabrik / OpenStreetMap Imports

Waymark can also import trail-like OpenStreetMap ways from Geofabrik `.osm.pbf` extracts. Import one state/region at a time.

Test a small import:

```bash
python scripts/import_geofabrik.py tennessee --limit 100
```

Import a full state extract:

```bash
python scripts/import_geofabrik.py tennessee
```

The source name will be:

```text
osm-geofabrik-tennessee
```

Then query it with:

```http
GET /api/trails.geojson?state=TN&source=osm-geofabrik-tennessee&limit=500
```

Geofabrik data comes from OpenStreetMap, so it is broader than official NPS data but should be treated as community-maintained data.

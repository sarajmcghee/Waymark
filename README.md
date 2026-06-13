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
GET /api/trails/nearby?city=Nashville&state=TN&radius_km=25
GET /api/trails.geojson
GET /api/states
GET /api/cities?query=Nash&state=TN
GET /map
GET /admin
POST /api/ingest/geojson
POST /api/ingest/arcgis
GET /api/ingest/runs
GET /api/admin/stats
GET /api/admin/source-presets
```

`/map` is a lightweight local viewer for visually checking imported trail data.
It accepts city/radius URL parameters, for example
`/map?city=Chattanooga&state=TN&radius_km=30&limit=100`.
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
GET /api/trails?trail_type=hiking_route
GET /api/trails?hike_intent=true
GET /api/trails?include_segments=true
GET /api/trails?min_length_km=3&max_length_km=15
GET /api/trails?difficulty=Class%203:%20Developed
GET /api/trails?surface=Native
GET /api/trails.geojson?bbox=-84,35,-83,36&limit=500
GET /api/trails.geojson?state=TN&limit=500
```

Nearby searches accept coordinates or a Census place name:

```http
GET /api/trails/nearby?lat=36.1627&lng=-86.7816&radius_km=25&limit=100
GET /api/trails/nearby?city=Nashville&state=TN&radius_km=25&limit=100
GET /api/cities?query=Nash&state=TN
```

## Wanderly itinerary endpoint

Wanderly can request named, hikeable trails near coordinates:

```http
GET /api/wanderly/trails/nearby?lat=35.0456&lng=-85.3097&radius_km=30&limit=100
```

This endpoint dissolves same-named trail geometry into one result, calculates
distance from the merged geometry, ranks complete OSM hiking routes before
ordinary paths, and excludes unnamed features, sidewalks, crossings, cycling
paths, and route member segments. Its response is tailored to itinerary
generation:

```json
[
  {
    "id": "9aca6b4e-7db9-49df-a86b-2252ca4f25b8",
    "name": "Example Trail",
    "distanceMiles": 4.25,
    "estimatedDurationHours": 1.57,
    "difficulty": "moderate",
    "category": "moderate_hike",
    "centerLat": 35.04,
    "centerLng": -85.31
  }
]
```

Duration assumes a 5 km/h walking pace, with a 15% adjustment for moderate
trails and 35% for hard trails. Difficulty is normalized to `easy`, `moderate`,
or `hard`. Distance provides a minimum difficulty: trails from 3 to under 8
miles are at least moderate, and trails 8 miles or longer are hard. Category is
normalized to `walk`, `moderate_hike`, or `major_hike`.

Standalone OSM sidewalks are excluded from trail responses by default. Clients
that also need pedestrian infrastructure can opt in:

```http
GET /api/trails/nearby?city=Nashville&state=TN&radius_km=25&include_sidewalks=true
```

Load Census place centroids by running the **Import Census cities** GitHub
Actions workflow. It uses the existing `RENDER_DATABASE_URL` repository secret.

Waymark can read state-sized OSM caches imported from Geofabrik:

```http
GET /api/trails.geojson?provider=geofabrik&state=TN&limit=500
```

Geofabrik imports are recorded in `trail_cache_entries`. Large `.osm.pbf`
downloads and parsing run as batch jobs instead of inside API requests, avoiding
Overpass rate limits and web-request timeouts.

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
python scripts/import_geofabrik.py tennessee --state TN --limit 100
```

Import a full state extract:

```bash
python scripts/import_geofabrik.py tennessee --state TN
```

The source name will be:

```text
osm-geofabrik-tennessee
```

Then query it with:

```http
GET /api/trails.geojson?provider=geofabrik&state=TN&limit=500
```

Geofabrik data comes from OpenStreetMap, so it is broader than official NPS data but should be treated as community-maintained data.

The Geofabrik importer makes two passes through each extract. It first collects
`route=hiking`, `route=foot`, and `route=mtb` relations, then imports trail-like
ways plus all member ways from those relations. Route names, references,
networks, operators, and memberships are retained in `raw_properties`.
Normalized `trail_type` values include `hiking_route`, `mountain_bike_route`,
`alpine_hiking_trail`, `footpath`, `path`, `track`, and other path types.

After importing ways, Waymark merges each OSM route relation into one trail
feature and calculates `length_meters` from its PostGIS geography. Member
segments remain stored for traceability but are hidden from API responses by
default. Pass `include_segments=true` to inspect the underlying OSM ways.

For data imported before route consolidation was added, run the **Normalize
existing trails** GitHub Actions workflow. To expand beyond a single state, run
**Expand Geofabrik coverage** and choose Tennessee neighbors or the Southeast.

The importer uses a disk-backed Osmium node-location index to reduce memory use.
State extracts can still require significant temporary disk space and processing
time. Run full imports from a Render shell, background worker, or a larger
instance.

If Render cannot reach Geofabrik directly, download over IPv4 and pass the local
file to the importer:

```bash
curl -4 -L https://download.geofabrik.de/north-america/us/tennessee-latest.osm.pbf -o /tmp/tennessee.osm.pbf
python scripts/import_geofabrik.py tennessee --state TN --file /tmp/tennessee.osm.pbf
```

The recommended hosted import path is the **Import Geofabrik trails** GitHub
Actions workflow. Add the Render Postgres external connection URL as the
`RENDER_DATABASE_URL` repository Actions secret, then run the workflow from the
repository's Actions tab. The default inputs import Tennessee.

Setting `fetch_if_missing=true` checks the Geofabrik cache. If the state has not
been imported, the API returns `409` with the exact import command rather than
calling Overpass:

```http
GET /api/trails.geojson?provider=geofabrik&state=TN&fetch_if_missing=true&limit=500
```

If a worker dies and leaves a run marked `running`, clean it up with:

```bash
python scripts/mark_stale_ingests_failed.py
```

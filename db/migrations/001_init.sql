CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS trails (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name text,
    geometry geometry(MultiLineString, 4326) NOT NULL,
    length_meters double precision,
    difficulty text,
    surface text,
    allowed_uses text[] NOT NULL DEFAULT '{}',
    managing_agency text,
    status text NOT NULL DEFAULT 'unknown',
    source text NOT NULL,
    source_id text,
    source_url text,
    raw_properties jsonb NOT NULL DEFAULT '{}',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS trails_source_source_id_idx
    ON trails (source, source_id)
    WHERE source_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS trails_geometry_gix
    ON trails
    USING gist (geometry);

CREATE INDEX IF NOT EXISTS trails_source_idx
    ON trails (source);

CREATE INDEX IF NOT EXISTS trails_status_idx
    ON trails (status);

CREATE INDEX IF NOT EXISTS trails_allowed_uses_gix
    ON trails
    USING gin (allowed_uses);

CREATE TABLE IF NOT EXISTS trailheads (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name text,
    geometry geometry(Point, 4326) NOT NULL,
    parking_available boolean,
    restroom_available boolean,
    source text NOT NULL,
    source_id text,
    source_url text,
    raw_properties jsonb NOT NULL DEFAULT '{}',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS trailheads_source_source_id_idx
    ON trailheads (source, source_id)
    WHERE source_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS trailheads_geometry_gix
    ON trailheads
    USING gist (geometry);

CREATE TABLE IF NOT EXISTS parks_or_areas (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name text NOT NULL,
    agency text,
    geometry geometry(MultiPolygon, 4326) NOT NULL,
    source text NOT NULL,
    source_id text,
    source_url text,
    raw_properties jsonb NOT NULL DEFAULT '{}',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS parks_or_areas_source_source_id_idx
    ON parks_or_areas (source, source_id)
    WHERE source_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS parks_or_areas_geometry_gix
    ON parks_or_areas
    USING gist (geometry);

CREATE TABLE IF NOT EXISTS states (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    fips text NOT NULL UNIQUE,
    abbreviation text NOT NULL UNIQUE,
    name text NOT NULL UNIQUE,
    geometry geometry(MultiPolygon, 4326) NOT NULL,
    source text NOT NULL,
    source_url text,
    raw_properties jsonb NOT NULL DEFAULT '{}',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS states_geometry_gix
    ON states
    USING gist (geometry);

CREATE TABLE IF NOT EXISTS trail_cache_entries (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    cache_key text NOT NULL UNIQUE,
    provider text NOT NULL,
    source text NOT NULL,
    state text,
    bbox text,
    status text NOT NULL DEFAULT 'missing',
    feature_count integer NOT NULL DEFAULT 0,
    error text,
    fetched_at timestamptz,
    expires_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (provider, source, state, bbox)
);

CREATE INDEX IF NOT EXISTS trail_cache_entries_lookup_idx
    ON trail_cache_entries (provider, state, bbox, status);

CREATE TABLE IF NOT EXISTS ingest_runs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source text NOT NULL,
    source_url text,
    source_type text NOT NULL,
    source_filter text,
    requested_count integer,
    accepted_count integer NOT NULL DEFAULT 0,
    status text NOT NULL DEFAULT 'running',
    error text,
    started_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz
);

CREATE INDEX IF NOT EXISTS ingest_runs_source_idx
    ON ingest_runs (source);

CREATE INDEX IF NOT EXISTS ingest_runs_started_at_idx
    ON ingest_runs (started_at DESC);

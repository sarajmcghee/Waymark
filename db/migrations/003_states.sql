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

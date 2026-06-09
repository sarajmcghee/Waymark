CREATE TABLE IF NOT EXISTS cities (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    geoid text NOT NULL UNIQUE,
    name text NOT NULL,
    state text NOT NULL,
    geometry geometry(Point, 4326) NOT NULL,
    source text NOT NULL,
    source_url text,
    raw_properties jsonb NOT NULL DEFAULT '{}',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS cities_name_state_idx
    ON cities (lower(name), state);

CREATE INDEX IF NOT EXISTS cities_geometry_gix
    ON cities
    USING gist (geometry);

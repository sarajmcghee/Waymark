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

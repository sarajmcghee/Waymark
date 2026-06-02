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

CREATE INDEX IF NOT EXISTS trails_status_idx
    ON trails (status);

CREATE INDEX IF NOT EXISTS trails_allowed_uses_gix
    ON trails
    USING gin (allowed_uses);

ALTER TABLE trails
    ADD COLUMN IF NOT EXISTS is_route_segment boolean NOT NULL DEFAULT false;

ALTER TABLE trails
    ADD COLUMN IF NOT EXISTS route_relation_ids text[] NOT NULL DEFAULT '{}';

CREATE INDEX IF NOT EXISTS trails_route_segment_idx
    ON trails (is_route_segment);

CREATE INDEX IF NOT EXISTS trails_route_relation_ids_gix
    ON trails
    USING gin (route_relation_ids);

UPDATE trails
SET
    length_meters = ST_Length(geography(geometry)),
    updated_at = now()
WHERE length_meters IS NULL;

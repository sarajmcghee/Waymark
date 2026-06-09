ALTER TABLE trails
    ADD COLUMN IF NOT EXISTS trail_type text;

CREATE INDEX IF NOT EXISTS trails_trail_type_idx
    ON trails (trail_type);

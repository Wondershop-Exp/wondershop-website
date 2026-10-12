-- 2026-10-12, per Shruti: "Carnival Stalls & Mascots" partners — their
-- answers (services, heads-up time, zones ...) and their catalogues.
ALTER TABLE vendor_master ADD COLUMN IF NOT EXISTS carnival_profile JSONB;
CREATE TABLE IF NOT EXISTS vendor_catalogues (
    id            SERIAL PRIMARY KEY,
    vendor_id     INTEGER NOT NULL REFERENCES vendor_master(vendor_id) ON DELETE CASCADE,
    filename      TEXT,
    content_type  TEXT,
    size_bytes    INTEGER,
    file_data     BYTEA NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_vendor_catalogues_vendor ON vendor_catalogues(vendor_id);

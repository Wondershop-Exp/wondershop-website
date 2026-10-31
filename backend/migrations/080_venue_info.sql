-- 080: Venue & society information form (2026-10-31, per Shruti — replaces
-- the Google Form). One link per booking (venue.html?t=<token>), answers in
-- JSONB, venue photos/videos with placement tags. Safe to run again.
CREATE TABLE IF NOT EXISTS venue_info (
    id              SERIAL PRIMARY KEY,
    lead_id         INTEGER NOT NULL UNIQUE REFERENCES leads(lead_id) ON DELETE CASCADE,
    token           TEXT NOT NULL UNIQUE,
    answers         JSONB NOT NULL DEFAULT '{}'::jsonb,
    tnc_accepted_at TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by      TEXT,
    opened_at       TIMESTAMPTZ,
    updated_at      TIMESTAMPTZ,
    submitted_at    TIMESTAMPTZ,
    emailed_at      TIMESTAMPTZ,
    whatsapp_at     TIMESTAMPTZ
);
CREATE TABLE IF NOT EXISTS venue_media (
    id          SERIAL PRIMARY KEY,
    lead_id     INTEGER NOT NULL REFERENCES leads(lead_id) ON DELETE CASCADE,
    kind        TEXT NOT NULL,            -- 'image' | 'video'
    mime        TEXT NOT NULL,
    filename    TEXT,
    size_bytes  INTEGER NOT NULL,
    data        BYTEA NOT NULL,
    tags        JSONB NOT NULL DEFAULT '[]'::jsonb,
    caption     TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS venue_media_lead_idx ON venue_media (lead_id);

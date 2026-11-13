-- 085: Venue master (2026-11-13, per Shruti — "in some cases, 1 party can have
-- multiple venue recce. we would like to build a venue master with all the
-- details and then link a venue to a party/booking/lead").
--   venues        one row per venue; permanent details in answers (same keys
--                 as the venue form: lift, rules, ceiling, plugs, medical...)
--   lead_venues   which venues a lead/booking is considering (shortlisted /
--                 final / not chosen). A venue can be linked to many parties.
--   venue_media   now also holds photos/videos added straight to a venue
--                 (venue_id set, lead_id NULL). Safe to run again.
CREATE TABLE IF NOT EXISTS venues (
    id          SERIAL PRIMARY KEY,
    name        TEXT NOT NULL,
    answers     JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by  TEXT,
    updated_at  TIMESTAMPTZ,
    updated_by  TEXT
);
CREATE INDEX IF NOT EXISTS venues_name_idx ON venues (LOWER(name));

CREATE TABLE IF NOT EXISTS lead_venues (
    id          SERIAL PRIMARY KEY,
    lead_id     INTEGER NOT NULL REFERENCES leads(lead_id) ON DELETE CASCADE,
    venue_id    INTEGER NOT NULL REFERENCES venues(id) ON DELETE CASCADE,
    status      TEXT NOT NULL DEFAULT 'shortlisted',   -- shortlisted | final | rejected
    note        TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by  TEXT,
    UNIQUE (lead_id, venue_id)
);
CREATE INDEX IF NOT EXISTS lead_venues_venue_idx ON lead_venues (venue_id);

ALTER TABLE venue_media ALTER COLUMN lead_id DROP NOT NULL;
ALTER TABLE venue_media ADD COLUMN IF NOT EXISTS venue_id INTEGER REFERENCES venues(id) ON DELETE CASCADE;
CREATE INDEX IF NOT EXISTS venue_media_venue_idx ON venue_media (venue_id);

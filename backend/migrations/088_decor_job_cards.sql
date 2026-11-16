-- 088: Decorator job card (2026-11-16, per Shruti — "help make a job card for
-- decorators ... we'll start with the decorator first").
--
-- One job card per booking, filled in from the booking page (pre-filled from
-- the booking, the team adds what's missing) and sent to the decorator as a
-- WhatsApp image + short text + a link (decor-job.html?t=<token>). The link
-- needs no login: the long random token IS the access control (same trust
-- level as the packing list's staff link). The decorator never sees the
-- client's name or phone — only the Wondershop coordinator — and sees the
-- child's name only when the team ticks "decorator needs the child's name"
-- (e.g. name lights).
--
--   decor_job_cards   data  = what the team typed (components, materials,
--                             amount, coordinator, to-return box, photo list)
--                     auto  = booking details frozen at the last save (date,
--                             times, venue, maps link, age, theme, package,
--                             decor pictures) — what the decorator's link shows
--   decor_job_photos  completion photos, one per photo box (slot); a new
--                     upload to the same box replaces the old one. kind='ref'
--                     rows are extra decor reference pictures the team adds.
-- Applied on startup (db_ensure.py). Safe to run again.
CREATE TABLE IF NOT EXISTS decor_job_cards (
    id           SERIAL PRIMARY KEY,
    lead_id      INTEGER NOT NULL UNIQUE REFERENCES leads(lead_id) ON DELETE CASCADE,
    token        TEXT NOT NULL UNIQUE,
    decorator    TEXT,
    data         JSONB NOT NULL DEFAULT '{}'::jsonb,
    auto         JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by   TEXT,
    updated_at   TIMESTAMPTZ,
    updated_by   TEXT,
    copied_at    TIMESTAMPTZ,          -- last time the team copied the WhatsApp message
    opened_at    TIMESTAMPTZ,          -- first time the decorator opened the link
    approved_at  TIMESTAMPTZ,
    approved_by  TEXT
);

CREATE TABLE IF NOT EXISTS decor_job_photos (
    id           SERIAL PRIMARY KEY,
    card_id      INTEGER NOT NULL REFERENCES decor_job_cards(id) ON DELETE CASCADE,
    kind         TEXT NOT NULL DEFAULT 'done',   -- 'done' (completion photo) | 'ref' (extra reference picture)
    slot         TEXT NOT NULL,
    token        TEXT NOT NULL UNIQUE,           -- image URL token
    image        BYTEA NOT NULL,
    image_type   TEXT NOT NULL,
    size_bytes   INTEGER NOT NULL,
    source       TEXT NOT NULL DEFAULT 'decorator',   -- 'decorator' | 'team'
    uploaded_by  TEXT,
    uploaded_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (card_id, kind, slot)
);
CREATE INDEX IF NOT EXISTS decor_job_photos_card_idx ON decor_job_photos (card_id);

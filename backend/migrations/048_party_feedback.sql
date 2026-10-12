-- 048: post-event feedback (2026-10-12, per Shruti — "let's also work on
-- feedback form for our events ... overall rating, rating for host(s),
-- volunteers, activities, decor, food, cake, music, mascot ... any
-- remarks ... phone friendly, so that we can send a whatsapp and mail").
-- One row per booking: the link token, which categories to ask about
-- (picked in admin, pre-ticked from what was booked), and the answers.
-- Safe to run more than once (applied on startup by db_ensure.py).

CREATE TABLE IF NOT EXISTS party_feedback (
    id            SERIAL PRIMARY KEY,
    lead_id       INTEGER NOT NULL UNIQUE,
    token         VARCHAR(40) NOT NULL UNIQUE,
    categories    JSONB NOT NULL DEFAULT '[]'::jsonb,
    host_names    TEXT,
    created_by    TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    emailed_at    TIMESTAMPTZ,
    whatsapp_at   TIMESTAMPTZ,
    opened_at     TIMESTAMPTZ,
    submitted_at  TIMESTAMPTZ,
    overall       SMALLINT,
    ratings       JSONB NOT NULL DEFAULT '{}'::jsonb,
    remarks       TEXT,
    respondent    TEXT,
    google_clicked_at TIMESTAMPTZ
);

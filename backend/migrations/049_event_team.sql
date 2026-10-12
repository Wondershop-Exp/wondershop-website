-- 049: event team per booking (2026-10-12, per Shruti — "one activity can
-- have many volunteers ... for spy, we have 4-8 stations, every station can
-- have 1-2 volunteers - shall we track the volunteers for every event? ...
-- we can also add payment"). One row per person per role on a booking:
-- who, what they did (role + activity/station), optional hours, the amount
-- agreed (varies by person) and whether it's been paid.
-- 2026-10-12 follow-up: every cost for the event goes here (partners of
-- any kind, transport, printing ...), with bill date and how it was paid
-- (Gpay / Cash / ...) — replaces the team's expense sheet. Admin only.
-- Safe to run more than once (applied on startup by db_ensure.py).

CREATE TABLE IF NOT EXISTS event_team (
    id           SERIAL PRIMARY KEY,
    lead_id      INTEGER NOT NULL,
    sort_order   INTEGER NOT NULL DEFAULT 0,
    person_name  TEXT NOT NULL,
    role         VARCHAR(40),
    assigned_to  TEXT,
    hours        NUMERIC(5, 2),
    amount       NUMERIC(10, 2),
    bill_date    DATE,
    paid_via     VARCHAR(30),
    paid         BOOLEAN NOT NULL DEFAULT FALSE,
    paid_at      TIMESTAMPTZ,
    notes        TEXT,
    updated_by   TEXT,
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_event_team_lead ON event_team (lead_id);
ALTER TABLE event_team ADD COLUMN IF NOT EXISTS bill_date DATE;
ALTER TABLE event_team ADD COLUMN IF NOT EXISTS paid_via VARCHAR(30);
CREATE TABLE IF NOT EXISTS app_flags (key VARCHAR(80) PRIMARY KEY, set_at TIMESTAMPTZ NOT NULL DEFAULT NOW());

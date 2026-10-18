-- 2026-10-18 Sorting Hat party app: one event code per confirmed booking.
CREATE TABLE IF NOT EXISTS sorting_hat_events (
    lead_id             INTEGER PRIMARY KEY,
    code                VARCHAR(12) UNIQUE NOT NULL,
    config              JSONB NOT NULL DEFAULT '{}'::jsonb,
    results             JSONB NOT NULL DEFAULT '[]'::jsonb,
    results_updated_at  TIMESTAMPTZ,
    device_id           VARCHAR(64),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS sorting_hat_audio (
    id          SERIAL PRIMARY KEY,
    lead_id     INTEGER NOT NULL,
    name        VARCHAR(160),
    mime        VARCHAR(80),
    data        BYTEA NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_sh_audio_lead ON sorting_hat_audio(lead_id);

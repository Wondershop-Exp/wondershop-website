-- Spy Agent Registration pages (2026-09-22, per Shruti follow-up — "how
-- will I trigger the form for every party... give an option for bookings
-- with spy on it to upload the invite and then generate this page").
--
-- One row per booking that has this turned on. share_token is the ONLY
-- thing in the public registration link
-- (spy-agent-registration.html?t=<share_token>) — same trust model as
-- packaging_lists.share_token: a long random token IS the access
-- control, no login needed for the parents filling in the form.
--
-- The invite image is stored directly in Postgres as BYTEA, the same
-- pattern already used for vendor_master.cancelled_cheque_file, and is
-- served back by a dedicated GET endpoint — keeps this self-contained,
-- no external image host to manage.

CREATE TABLE IF NOT EXISTS spy_registration_pages (
    id                   SERIAL PRIMARY KEY,
    lead_id              INTEGER NOT NULL REFERENCES leads(lead_id),
    share_token          VARCHAR(64) NOT NULL UNIQUE,
    invite_image         BYTEA,
    invite_image_name    VARCHAR(255),
    invite_image_type    VARCHAR(100),
    created_on           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_on           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_spy_reg_lead UNIQUE (lead_id)
);

CREATE INDEX IF NOT EXISTS idx_spy_reg_token ON spy_registration_pages (share_token);

CREATE TRIGGER trg_spy_reg_updated_on
    BEFORE UPDATE ON spy_registration_pages
    FOR EACH ROW EXECUTE FUNCTION set_updated_on();

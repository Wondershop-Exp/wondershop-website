-- 041: decor reference images (2026-10-06, per Shruti).
-- "give an option to upload a reference image for the decor in the sales &
-- booking panels for a booking. during upload, ask if this reference image
-- can be displayed on the website as well. if the user checks that box,
-- then ask for more inputs like the theme, category, cost, age, gender.
-- Use this image in the pdf and email that goes for this lead/booking."
--
-- The image is stored in Postgres as BYTEA (same as the spy invite and the
-- vendor cheque). public_token is the unguessable id used in the image URL
-- (emails / website); is_current marks the one image used for its lead's
-- quotation/emails; show_on_website puts it on Build-a-Birthday's decor
-- step straight away (theme/tier/cost/age_group/gender describe it there).
-- lead_id is a plain column (no foreign key) so the test-data scripts and
-- renumber_leads.py handle it like the other *lead_id columns.
--
-- Safe to run more than once.

CREATE TABLE IF NOT EXISTS decor_reference_images (
    id               SERIAL PRIMARY KEY,
    lead_id          INTEGER,
    public_token     VARCHAR(40) NOT NULL UNIQUE,
    image            BYTEA NOT NULL,
    image_type       VARCHAR(20) NOT NULL,
    image_name       TEXT,
    is_current       BOOLEAN NOT NULL DEFAULT TRUE,
    show_on_website  BOOLEAN NOT NULL DEFAULT FALSE,
    theme            TEXT,
    tier             VARCHAR(20),
    cost             NUMERIC(10, 2),
    age_group        VARCHAR(20),
    gender           VARCHAR(10),
    uploaded_by      TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_decor_ref_lead ON decor_reference_images (lead_id) WHERE is_current;
CREATE INDEX IF NOT EXISTS idx_decor_ref_web ON decor_reference_images (show_on_website) WHERE show_on_website;

-- 045: reference photos for custom activities (2026-10-08, per Shruti —
-- "for the custom activities, give an option to upload a reference photo
-- which will come up in the pdf as well"). Image stored as BYTEA like the
-- decor reference photos (041); public_token is the unguessable id the
-- activity entry keeps (lead_sales_playbook.activities[].photo_token).
-- Safe to run more than once (applied on startup by db_ensure.py).

CREATE TABLE IF NOT EXISTS activity_ref_images (
    id            SERIAL PRIMARY KEY,
    lead_id       INTEGER,
    public_token  VARCHAR(40) NOT NULL UNIQUE,
    image         BYTEA NOT NULL,
    image_type    VARCHAR(20) NOT NULL,
    image_name    TEXT,
    uploaded_by   TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_activity_ref_lead ON activity_ref_images (lead_id);

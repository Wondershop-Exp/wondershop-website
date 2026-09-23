-- Spy Agent Registration: optional T-Shirt Size question (2026-09-23, per
-- Shruti — "for some spy registration, we might need to ask additional
-- questions like tshirt size ... a question, an image to upload (optional)
-- with a dropdown with options"). Scoped to t-shirt size specifically for
-- now (not a general custom-question builder) — one enable toggle, one
-- admin-typed comma-separated list of size options, and one optional size
-- chart image, re-uploaded fresh per event since the chart can change.

ALTER TABLE spy_registration_pages
    ADD COLUMN IF NOT EXISTS tshirt_size_enabled     BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS tshirt_size_options      TEXT,           -- comma-separated, admin-typed, e.g. "18, 20, 22, 24, 26, 28"
    ADD COLUMN IF NOT EXISTS tshirt_chart_image       BYTEA,
    ADD COLUMN IF NOT EXISTS tshirt_chart_image_name  VARCHAR(255),
    ADD COLUMN IF NOT EXISTS tshirt_chart_image_type  VARCHAR(50);

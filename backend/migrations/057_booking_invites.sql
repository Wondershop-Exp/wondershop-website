-- 057: Final e-invite on a booking (2026-10-14, per Shruti — "we'll upload
-- the final invite on the bookings page for our record keeping. if it's a
-- new invite, we'll add it to our website as well ... For spy, we don't need
-- to ask to reupload ... just add the checkbox").
-- One row per booking. A Spy booking keeps its image in
-- spy_registration_pages (the registration-page invite) and only uses the
-- website columns here. show_on_website = it appears on Build-a-Birthday's
-- E-Invite step (routers/booking_invites.py, builder.html loadSiteInvites).
-- Also applied on startup (db_ensure.py).
CREATE TABLE IF NOT EXISTS booking_invites (
    lead_id           INTEGER PRIMARY KEY,
    invite_image      BYTEA,
    invite_image_type VARCHAR(40),
    invite_image_name VARCHAR(200),
    uploaded_by       VARCHAR(100),
    uploaded_at       TIMESTAMPTZ,
    show_on_website   BOOLEAN NOT NULL DEFAULT FALSE,
    website_name      VARCHAR(120),
    website_theme     VARCHAR(60),
    website_by        VARCHAR(100),
    website_at        TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_booking_invites_web ON booking_invites (show_on_website) WHERE show_on_website;

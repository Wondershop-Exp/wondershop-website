-- ─────────────────────────────────────────────────────────────────────────────
-- Add venue Google Maps link + venue contact person, and split the return-gift
-- delivery contact into name + phone (previously a single free-text field).
-- Customer-entered on the checkout step (Your Details / Return Gifts blocks).
-- ─────────────────────────────────────────────────────────────────────────────

-- Venue — Google Maps share link (customer searches/pins their exact venue on
-- Google Maps externally, then pastes the resulting link here) + an on-site
-- contact person (e.g. watchman, event coordinator) our team can reach.
ALTER TABLE leads ADD COLUMN IF NOT EXISTS venue_maps_link      VARCHAR(500);
ALTER TABLE leads ADD COLUMN IF NOT EXISTS venue_contact_name   VARCHAR(255);
ALTER TABLE leads ADD COLUMN IF NOT EXISTS venue_contact_phone  VARCHAR(20);

-- Return-gift delivery contact — previously a single `gift_delivery_contact`
-- free-text field (name only, despite the generic column name). That column
-- keeps holding the name; this adds the phone number as its own column.
ALTER TABLE leads ADD COLUMN IF NOT EXISTS gift_delivery_contact_phone VARCHAR(20);

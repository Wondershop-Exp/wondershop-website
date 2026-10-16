-- 065: next-year leads from past bookings (2026-10-16, per Shruti). A week
-- after a party (completed or cancelled), the Sales module creates a lead for
-- the child's next birthday; source_booking_id points back to that booking
-- so it is created once only. Also applied on startup (db_ensure.py).

ALTER TABLE leads ADD COLUMN IF NOT EXISTS source_booking_id INTEGER;
CREATE INDEX IF NOT EXISTS idx_leads_source_booking ON leads (source_booking_id);
-- Set on a booking once its next-year lead has been handled (created,
-- merged into an existing lead, or skipped as a duplicate).
ALTER TABLE leads ADD COLUMN IF NOT EXISTS next_year_done BOOLEAN NOT NULL DEFAULT FALSE;

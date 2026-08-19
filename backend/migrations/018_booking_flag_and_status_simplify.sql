-- ─────────────────────────────────────────────────────────────────────────────
-- Split leads vs. bookings + simplify booking status (2026-08-19, per Shruti,
-- follow-up to 017_lead_status_workflow.sql):
--   "3. convert to booking and save status buttons are not eligible for
--    confirmed bookings. For confirmed bookings, only give option to cancel"
--   "4. Create 2 tables on admin panel - 1 for leads, 1 for bookings."
--   "5. No need of cancel button for leads. We can use the status to update
--    cancelled/not interested leads"
--   "6. For confirmed bookings, show status as read only. Status: New,
--    Upcoming, Cancelled and Complete."
--
-- Design: is_booking is now the explicit table-membership flag (a row is
-- either a Lead or a Booking, never both) instead of overloading `status`
-- for that purpose. Once is_booking=TRUE, `status` only ever holds 'New'
-- (default, not cancelled) or 'Cancelled' — 'Upcoming'/'Complete' are NEVER
-- stored, they're computed live from event_date at read time (see
-- _booking_display_status() in routers/admin.py), so they can never go
-- stale and there's no lazy cron-style UPDATE needed any more. 'Converted'/
-- 'Completed' (from migration 017) are retired as stored values — any row
-- that reached them is now a real booking (is_booking=TRUE, status reset to
-- 'New' so Cancelled-vs-not is the only thing that stored value tracks).
-- ─────────────────────────────────────────────────────────────────────────────

ALTER TABLE leads ADD COLUMN IF NOT EXISTS is_booking BOOLEAN NOT NULL DEFAULT FALSE;

-- Backfill: anything already Converted/Completed (or the older 'Booked',
-- just in case 017 hasn't run yet in some environment) is a real booking.
UPDATE leads SET is_booking = TRUE WHERE status IN ('Converted', 'Completed', 'Booked');
UPDATE leads SET status = 'New' WHERE status IN ('Converted', 'Completed', 'Booked');

ALTER TABLE leads DROP CONSTRAINT IF EXISTS leads_status_check;
ALTER TABLE leads ADD CONSTRAINT leads_status_check CHECK (status IN (
    'New', 'Initial Discussions Done', 'Proposal Sent', 'Negotiations Ongoing',
    'Not Interested', 'DND', 'Cancelled'
));

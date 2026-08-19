-- ─────────────────────────────────────────────────────────────────────────────
-- Lead → Booking status workflow (2026-08-19, per Shruti — admin panel
-- request #1 item 6 + item 3):
--   "give an option to convert a lead into a booking on the summary page
--    and the lead detail page. The status to be new when the lead comes in
--    by default. Other options - Initial discussions done, proposal sent,
--    negotiations ongoing, converted, not interested, DND. Add another
--    dropdown for reason of non convert ... seeking more discount, went
--    ahead with a competitor, play area, we did not pitch on time, venue
--    monopoly, others - please enter"
--   "status should change to completed once the event date has passed. if
--    the event is cancelled, then the status remains cancelled forever"
--
-- leads.status previously had a fixed 7-value CHECK constraint from a much
-- earlier admin workflow ('New', 'Followup', 'Not Interested', 'DND',
-- 'Raised by Mistake', 'Proposal Sent', 'Booked') that never actually
-- shipped in admin.html — this migrates any existing rows to the closest
-- new-vocabulary equivalent, then replaces the constraint with the full
-- set Shruti asked for, plus 'Completed'/'Cancelled' for post-conversion
-- bookings (see routers/admin.py's _auto_complete_past_bookings()).
-- ─────────────────────────────────────────────────────────────────────────────

-- 1. Migrate existing rows to the closest new-vocabulary value BEFORE the
--    new CHECK constraint goes on (old values would violate it otherwise).
UPDATE leads SET status = 'Initial Discussions Done' WHERE status = 'Followup';
UPDATE leads SET status = 'Not Interested'            WHERE status = 'Raised by Mistake';
UPDATE leads SET status = 'Converted'                 WHERE status = 'Booked';

-- 2. Widen the column — 'Initial Discussions Done' (25 chars) and
--    'Negotiations Ongoing' (21 chars) don't fit the old VARCHAR(20).
ALTER TABLE leads ALTER COLUMN status TYPE VARCHAR(40);

-- 3. Replace the CHECK constraint with the full new vocabulary.
ALTER TABLE leads DROP CONSTRAINT IF EXISTS leads_status_check;
ALTER TABLE leads ADD CONSTRAINT leads_status_check CHECK (status IN (
    'New', 'Initial Discussions Done', 'Proposal Sent', 'Negotiations Ongoing',
    'Converted', 'Not Interested', 'DND', 'Completed', 'Cancelled'
));

-- 4. Reason-for-non-conversion — asked only when a lead is marked Not
--    Interested / DND. 'Others' pairs with the free-text column.
ALTER TABLE leads ADD COLUMN IF NOT EXISTS non_convert_reason VARCHAR(100);
ALTER TABLE leads ADD COLUMN IF NOT EXISTS non_convert_reason_other TEXT;

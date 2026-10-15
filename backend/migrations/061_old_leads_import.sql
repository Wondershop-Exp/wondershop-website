-- 061: old / existing leads brought into the Sales Quotation Module
-- (2026-10-15, per Shruti) — Instagram, Wonderfest Feb 2026, Powai Rotary
-- Christmas Stall 2025 and Google leads from the old Google Sheet, shown to
-- the team on the same rolling rule as WSR Repeat leads.
--   earlier_conversations — everything we discussed with the lead before
--                           (call dates, remarks, party details, other sources
--                           it came through; a summary when it booked with us).
--   date_precision        — 'exact' or 'month'. A month-only birthday is stored
--                           as the 1st of that month and shown 3 months before it.
-- One rule for every scheduled lead (2026-10-15, per Shruti): visible 90 days
-- before an exact date, 3 months before a month-only one. The UPDATE below
-- moves the WSR Repeat leads (loaded 2026-10-12 on a 60-day rule) onto it.
-- Also applied on startup (db_ensure.py); safe to run again.

ALTER TABLE leads ADD COLUMN IF NOT EXISTS earlier_conversations TEXT;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS date_precision VARCHAR(10);
UPDATE leads SET show_from = event_date - 90
 WHERE show_from IS NOT NULL AND event_date IS NOT NULL AND COALESCE(date_precision, 'exact') = 'exact'
   AND show_from <> event_date - 90;

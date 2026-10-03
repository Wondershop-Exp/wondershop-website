-- 040: "To be confirmed" items on a booking (2026-10-03, per Shruti).
-- "for activities with price on request, highlight it to the ops team. Add
-- a to be confirmed section on admin bookings page with these items. even
-- custom pinata and custom einvite should come here."
--
-- Which items are to be confirmed is computed live from the booking's
-- current selections (price-on-request activities, Custom Design piñata,
-- Custom Design e-invite). This column only stores what ops has done with
-- each one: {"<item key>": {"status": "confirmed"|"pending", "price": 12000,
-- "note": "...", "by": "...", "at": "2026-10-03T10:00:00"}}. A confirmed
-- price is added to the booking's Total MRP.
--
-- Safe to run more than once. Until it's run, the section still shows
-- (everything as pending) but can't be saved.

ALTER TABLE leads ADD COLUMN IF NOT EXISTS tbc_items JSONB;

-- Spy Agent Registration: pickup/drop time (2026-09-23, per Shruti — "add
-- pickup and drop time in that as well. pickup and drop time to be picked
-- up from the invite or admin as per the info available. incase there is
-- a conflict - ask the user to confirm the actual drop and pickup time
-- and update admin. Give option to the user to hide it as well").
--
-- One drop-off/pick-up time pair per party, alongside the existing invite
-- image on spy_registration_pages:
--   - Admin sets them from admin.html (pickup_drop_source = 'admin').
--   - If they're not set yet (and show_pickup_drop is true), the public
--     registration page asks the parent to confirm the times they were
--     told — that submission becomes the new official time
--     (pickup_drop_source = 'parent') and is logged to
--     booking_change_log so admin sees it was parent-confirmed.
--   - show_pickup_drop lets admin hide the whole block from the public
--     page (e.g. before times are finalised) regardless of whether a
--     time is on file.

ALTER TABLE spy_registration_pages
    ADD COLUMN IF NOT EXISTS drop_off_time          VARCHAR(5),   -- 'HH:MM' 24h, same convention as leads.event_time
    ADD COLUMN IF NOT EXISTS pick_up_time            VARCHAR(5),
    ADD COLUMN IF NOT EXISTS show_pickup_drop        BOOLEAN NOT NULL DEFAULT TRUE,
    ADD COLUMN IF NOT EXISTS pickup_drop_source       VARCHAR(10),  -- 'admin' | 'parent'
    ADD COLUMN IF NOT EXISTS pickup_drop_updated_at   TIMESTAMPTZ;

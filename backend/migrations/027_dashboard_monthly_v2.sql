-- 2026-09-11, per Shruti — the monthly dashboard rebuild (Realized / Booked
-- / Potential revenue AND bookings, each with its own target). The old
-- dashboard_monthly_overrides table (migration 026) already holds a
-- per-month revenue target plus manually-entered Instagram/Carried Forward
-- numbers; the new design drops the Instagram/Carried Forward funnel
-- (replaced by the GA4-based Traffic & Leads Funnel, once GA4 is connected)
-- but still needs a *bookings* target alongside the existing revenue one —
-- Shruti sets bookings and revenue targets separately, they don't imply
-- each other. Old columns are left in place (harmless, not read by the new
-- dashboard) rather than dropped, since they hold real data she entered by
-- hand.
ALTER TABLE dashboard_monthly_overrides
    ADD COLUMN IF NOT EXISTS bookings_target INTEGER;

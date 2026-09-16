-- ─────────────────────────────────────────────────────────────────────────────
-- 029: fix the "Convert to Booking" / "Save Status" fetch-error bug, and
-- add Venue Type to the sales module (2026-09-16, per Shruti's bug report
-- on the sales leads page).
--
-- Root cause of the fetch error: routers/admin.py's update_lead_status()
-- runs `UPDATE leads SET status = ..., non_convert_reason = ...,
-- non_convert_reason_other = ... WHERE lead_id = :id` for every real lead
-- row (confirmed by testing directly against the live API: the same call
-- against a nonexistent lead_id returns a clean 404, but against any real
-- lead_id it fails outright with a connection-level error — a crash, not a
-- validation error). Those two columns were supposed to have been added by
-- migration 017_lead_status_workflow.sql, but the live database doesn't
-- have them. Re-adding them here is a total no-op if they already exist
-- (IF NOT EXISTS) and a direct fix if they don't — unlike re-running 017
-- itself, which would also reset the leads.status CHECK constraint back to
-- its pre-018 vocabulary and is NOT safe to blindly re-run.
-- ─────────────────────────────────────────────────────────────────────────────

ALTER TABLE leads ADD COLUMN IF NOT EXISTS non_convert_reason VARCHAR(100);
ALTER TABLE leads ADD COLUMN IF NOT EXISTS non_convert_reason_other TEXT;

-- Venue Type — new field for the sales module's Client & Event Details
-- section (2026-09-16, per Shruti: "add venue type in event details").
-- Lives on the playbook (not `leads`) since it's specific to this module,
-- same pattern as venue_handover_time/packup_time already there.
ALTER TABLE lead_sales_playbook ADD COLUMN IF NOT EXISTS venue_type VARCHAR(50);

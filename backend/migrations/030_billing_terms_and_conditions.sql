-- ─────────────────────────────────────────────────────────────────────────────
-- 030: Terms & Conditions field on the sales module's Confirm Booking &
-- Balance section (2026-09-16, per Shruti: "add a t&c column, to be input
-- by the salesman - optional"). Free text, lives on the playbook (same
-- pattern as notes_special_instructions / notes_changes_updates) since
-- it's specific to this module, not the customer-facing booking record.
-- ─────────────────────────────────────────────────────────────────────────────

ALTER TABLE lead_sales_playbook ADD COLUMN IF NOT EXISTS terms_conditions TEXT;

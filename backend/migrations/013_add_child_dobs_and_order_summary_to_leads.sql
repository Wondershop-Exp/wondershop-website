-- ─────────────────────────────────────────────────────────────────────────────
-- (2026-08-14, per Shruti — "dob should be saved in database as well. are
-- there any other fields that are being inputted by the user and not saved
-- in db?"). Two groups of fields were being collected from the customer on
-- every checkout and used to build the email/order-form, but were NEVER
-- written to the `leads` table — so once the email was sent, the only place
-- this data existed was in that one email (or the Google Sheet, if the
-- Apps Script webhook was actually redeployed with the latest columns).
--
--   1. child_dobs — added to LeadSubmitRequest earlier (2026-08-14) as
--      sheet-only "for now"; now also persisted to the DB.
--   2. order_grand_total / order_discount_pct / order_advance /
--      order_balance — the order-summary figures shown in the confirmation
--      email (see _build_html_email's order_rows in leads.py). Needed in
--      the DB so support/ops can look up what a customer was actually
--      shown (total, discount, advance, pending) without having to dig up
--      the original email.
-- ─────────────────────────────────────────────────────────────────────────────

ALTER TABLE leads ADD COLUMN IF NOT EXISTS child_dobs VARCHAR(255);
ALTER TABLE leads ADD COLUMN IF NOT EXISTS order_grand_total DECIMAL(10,2);
ALTER TABLE leads ADD COLUMN IF NOT EXISTS order_discount_pct DECIMAL(5,2);
ALTER TABLE leads ADD COLUMN IF NOT EXISTS order_advance DECIMAL(10,2);
ALTER TABLE leads ADD COLUMN IF NOT EXISTS order_balance DECIMAL(10,2);

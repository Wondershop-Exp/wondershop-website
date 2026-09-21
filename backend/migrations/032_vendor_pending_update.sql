-- ─────────────────────────────────────────────────────────────────────────────
-- 032: Vendor onboarding — existing vendors submitting the form.
-- (2026-09-21, per Shruti: "form match on mobile number and update the existing
-- vendor instead" of creating a duplicate row.)
--
-- When someone submits the public onboarding form with a mobile number that is
-- already in vendor_master, the form no longer creates a second row:
--   * fields that are BLANK on the existing vendor are filled in directly;
--   * anything that would CHANGE an existing value, and ALL bank details / the
--     cancelled-cheque file, are held here as a "pending update" until a team
--     member approves them in the Partners tab. The public form can never
--     overwrite or add payment details on its own — otherwise anyone who knows
--     a vendor's phone number could redirect that vendor's payments.
--
-- Safe to run more than once. Run it BEFORE deploying the matching code.
-- ─────────────────────────────────────────────────────────────────────────────

ALTER TABLE vendor_master ADD COLUMN IF NOT EXISTS pending_update                JSONB;
ALTER TABLE vendor_master ADD COLUMN IF NOT EXISTS pending_submitted_on          TIMESTAMPTZ;
ALTER TABLE vendor_master ADD COLUMN IF NOT EXISTS pending_cheque_file           BYTEA;
ALTER TABLE vendor_master ADD COLUMN IF NOT EXISTS pending_cheque_filename       VARCHAR(255);
ALTER TABLE vendor_master ADD COLUMN IF NOT EXISTS pending_cheque_content_type   VARCHAR(100);

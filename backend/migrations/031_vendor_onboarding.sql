-- ─────────────────────────────────────────────────────────────────────────────
-- 031: Vendor onboarding — self-service form + bank/payment details
-- (2026-09-17, per Shruti: "create vendor onboarding form... we'll ask the
-- details from the vendor, including uploading a cancelled check or adding
-- account details for payment").
--
-- Extends vendor_master (rather than a separate table) so a self-submitted
-- vendor lands as an ordinary row in the Vendors tab admin.html already
-- has — just inactive and flagged as pending review, the same way a new
-- lead shows up as "New" rather than needing a whole separate screen.
--
-- The cancelled cheque file is stored as BYTEA directly in Postgres, not
-- an external object store — there's no cloud storage integration in this
-- project (Railway's own filesystem is ephemeral; see config.py's
-- GA4_SERVICE_ACCOUNT_JSON comment: "Railway has no file uploads"), and at
-- vendor-onboarding volumes (one image/PDF per vendor, a few hundred
-- vendors at most) a few hundred MB in Postgres is a non-issue. It's only
-- ever read back through the authenticated admin endpoint added alongside
-- this migration — never served publicly.
-- ─────────────────────────────────────────────────────────────────────────────

ALTER TABLE vendor_master ADD COLUMN IF NOT EXISTS bank_account_holder_name VARCHAR(255);
ALTER TABLE vendor_master ADD COLUMN IF NOT EXISTS bank_name                VARCHAR(255);
ALTER TABLE vendor_master ADD COLUMN IF NOT EXISTS bank_account_number      VARCHAR(34);
ALTER TABLE vendor_master ADD COLUMN IF NOT EXISTS bank_ifsc_code           VARCHAR(11);

-- One file per vendor (a cancelled cheque OR a bank passbook/statement
-- photo showing the same details) — filename/content_type kept alongside
-- the bytes so the admin download endpoint can serve it with a sensible
-- name and the right Content-Type instead of a generic blob.
ALTER TABLE vendor_master ADD COLUMN IF NOT EXISTS cancelled_cheque_file          BYTEA;
ALTER TABLE vendor_master ADD COLUMN IF NOT EXISTS cancelled_cheque_filename      VARCHAR(255);
ALTER TABLE vendor_master ADD COLUMN IF NOT EXISTS cancelled_cheque_content_type  VARCHAR(100);

-- 'admin_entered' (the default — matches every existing row, all of which
-- were typed in by the team) vs 'self_submitted' (came through the public
-- onboarding form). onboarding_reviewed starts TRUE for existing rows
-- (nothing to review — they were entered by the team already) and is set
-- explicitly to FALSE by the public submit endpoint; it flips back to TRUE
-- the moment an admin opens and saves that vendor record in admin.html, so
-- the "pending review" flag clears naturally on review — whether the admin
-- activates the vendor or deliberately leaves it inactive.
ALTER TABLE vendor_master ADD COLUMN IF NOT EXISTS onboarding_source VARCHAR(20) NOT NULL DEFAULT 'admin_entered'
    CHECK (onboarding_source IN ('admin_entered', 'self_submitted'));
ALTER TABLE vendor_master ADD COLUMN IF NOT EXISTS onboarding_reviewed BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE vendor_master ADD COLUMN IF NOT EXISTS submitted_on TIMESTAMPTZ;

-- New self-submitted vendors arrive inactive until reviewed — a public
-- form must never be able to publish an active-looking vendor record
-- un-reviewed. is_active already defaults to TRUE at the table level, so
-- the submit endpoint sets it to FALSE explicitly on insert; nothing to
-- change here.

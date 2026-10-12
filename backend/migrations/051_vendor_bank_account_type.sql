-- 2026-10-12: account type (savings / current) on partner bank details.
ALTER TABLE vendor_master ADD COLUMN IF NOT EXISTS bank_account_type TEXT;

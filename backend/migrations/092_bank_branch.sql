-- 092: bank branch name on partners (2026-11-27, per Shruti: "add branch name as well").
-- Optional; shown with the other bank details. Safe to run again.
ALTER TABLE vendor_master ADD COLUMN IF NOT EXISTS bank_branch_name VARCHAR(150);

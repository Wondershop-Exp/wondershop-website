-- 047: private "update your details" links for partners (2026-10-10, per Shruti).
-- "there are some volunteers who have filled in some details, but left some
-- open. how can I ask them to update the missing fields?"
--
-- From the Partners tab the team makes a link for one partner. It opens the
-- partner form already filled with what they gave before, so they only add
-- what is missing. Only a SHA-256 hash of the link's secret is stored; the link
-- expires after 14 days and stops working once the partner submits.
--
-- Safe to run more than once (listed in db_ensure.SAFE_MIGRATIONS).

ALTER TABLE vendor_master ADD COLUMN IF NOT EXISTS update_token_hash VARCHAR(64);
ALTER TABLE vendor_master ADD COLUMN IF NOT EXISTS update_token_expires TIMESTAMPTZ;
CREATE INDEX IF NOT EXISTS idx_vendor_master_update_token ON vendor_master (update_token_hash);

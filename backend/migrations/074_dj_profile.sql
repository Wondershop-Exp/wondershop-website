-- 074: DJ rates (2026-10-21, per Shruti).
-- Partners who pick "DJ" on vendor-onboarding.html tick the Mumbai zones they
-- serve and quote, per zone: 2 tops + DJ with console + 2 mics, 1 top + DJ with
-- console + 2 mics, and the extra cost of 4 LED lights with stands and of a
-- smoke machine. Kept as one JSON object on the partner's vendor_master row.
--
-- Safe to run more than once (listed in db_ensure.SAFE_MIGRATIONS).

ALTER TABLE vendor_master ADD COLUMN IF NOT EXISTS dj_profile JSONB;

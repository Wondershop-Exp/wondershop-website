-- 059: Host profile (2026-10-14, per Shruti).
-- Partners who pick "Host" on vendor-onboarding.html answer extra questions
-- (years of experience, strengths, what makes them different, comfort with
-- kids / large kids' events / corporate events, open to adult events and to
-- training, own game props, zones, Instagram, video links, how we can help
-- them grow). The answers are kept as one JSON object on the partner's
-- vendor_master row. Their event photos go in vendor_catalogues (migration 053),
-- the same table carnival partners' catalogues use.
--
-- Safe to run more than once (listed in db_ensure.SAFE_MIGRATIONS).

ALTER TABLE vendor_master ADD COLUMN IF NOT EXISTS host_profile JSONB;

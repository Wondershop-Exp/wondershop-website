-- ─────────────────────────────────────────────────────────────────────────────
-- Scratch-card rewards that are a SERVICE (Free Tattoo Artist, Free Bubble
-- Artist) can be added straight onto the customer's CURRENT booking, right
-- from the scratch-card reveal screen, instead of only being usable later.
-- This column records that the customer opted in, so ops sees it on the
-- Sheet/DB without digging through remarks (2026-08-12, per Shruti).
-- ─────────────────────────────────────────────────────────────────────────────

ALTER TABLE leads ADD COLUMN IF NOT EXISTS redeemed_reward_service VARCHAR(50);
ALTER TABLE leads ADD COLUMN IF NOT EXISTS redeemed_reward_service_at TIMESTAMPTZ;

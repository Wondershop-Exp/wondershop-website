-- ─────────────────────────────────────────────────────────────────────────────
-- BUG FIX (2026-08-12, per Shruti): "tattoo/bubble addon not working on the
-- scratch card". Root cause — /api/leads/redeem-service (the "add my Free
-- Tattoo/Bubble Artist reward to today's booking?" flow triggered right from
-- the scratch-card reveal) runs:
--     SELECT lead_id, ..., reward_type, redeemed_reward_service FROM leads ...
-- but `reward_type` was NEVER an actual column on `leads` — 001/002's
-- schemas don't define it, no later migration added it, and submit_lead()'s
-- INSERT never wrote it either (reward_type only ever existed transiently
-- on the request payload, used to build the confirmation email). So this
-- SELECT has always failed with "column reward_type does not exist",
-- meaning the "Yes, add it!" button on the scratch-card reveal could never
-- successfully redeem a Tattoo/Bubble Artist reward for ANY customer.
-- Adding the column here + writing to it in submit_lead() (see leads.py)
-- fixes it going forward. Refund/Discount rewards were unaffected — they
-- don't go through this endpoint at all.
-- ─────────────────────────────────────────────────────────────────────────────

ALTER TABLE leads ADD COLUMN IF NOT EXISTS reward_type VARCHAR(20);
ALTER TABLE leads ADD COLUMN IF NOT EXISTS reward_label VARCHAR(255);
ALTER TABLE leads ADD COLUMN IF NOT EXISTS reward_value DECIMAL(10,2);
ALTER TABLE leads ADD COLUMN IF NOT EXISTS reward_expiry DATE;

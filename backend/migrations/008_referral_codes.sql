-- ─────────────────────────────────────────────────────────────────────────────
-- Refer & Earn — every confirmed booking gets a personal, memorable
-- referral code (first name + last 4 digits of their mobile, reused across
-- every booking they make). Rules enforced in leads.py:
--   - Many different friends can use the same code (not single-use overall).
--   - Each phone number may redeem a referral code only once, ever.
--   - The code owner cannot redeem their own code.
--   - Referrer earns Rs.500 credit (applied manually by ops) per successful
--     redemption of their code — tracked here for ops to action.
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS referral_codes (
    code            VARCHAR(20) PRIMARY KEY,
    owner_lead_id   INTEGER,                  -- the booking that first earned this code
    owner_name      VARCHAR(255),
    owner_phone     VARCHAR(20) NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_referral_codes_phone ON referral_codes(owner_phone);

CREATE TABLE IF NOT EXISTS referral_redemptions (
    id                       SERIAL PRIMARY KEY,
    code                     VARCHAR(20) NOT NULL REFERENCES referral_codes(code),
    redeemed_by_phone        VARCHAR(20) NOT NULL,   -- the friend who redeemed it
    redeemed_lead_id         INTEGER,                -- the friend's booking
    referrer_reward_amount   DECIMAL(10,2) DEFAULT 500,
    referrer_reward_settled  BOOLEAN NOT NULL DEFAULT FALSE,  -- ops ticks this once credited
    redeemed_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_referral_redemptions_phone ON referral_redemptions(redeemed_by_phone);
CREATE INDEX IF NOT EXISTS idx_referral_redemptions_code  ON referral_redemptions(code);

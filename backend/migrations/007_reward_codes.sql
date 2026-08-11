-- ─────────────────────────────────────────────────────────────────────────────
-- Scratch-card "10% off next booking" reward codes — unique per winner,
-- redeemable exactly once, and only against the mobile number that won it.
-- Customer-facing rule is stated in the reward's Terms & Conditions and
-- re-stated in the confirmation email; enforced server-side in leads.py
-- (_issue_reward_code / _redeem_coupon_code / validate_coupon).
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS reward_codes (
    code              VARCHAR(20) PRIMARY KEY,
    phone             VARCHAR(20) NOT NULL,     -- mobile number the code was issued to
    discount_pct      DECIMAL(5,2) NOT NULL DEFAULT 10,
    min_spend         DECIMAL(10,2) DEFAULT 15000,
    issued_lead_id    INTEGER,                  -- the booking that won this code
    issued_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expiry_date       DATE,
    redeemed          BOOLEAN NOT NULL DEFAULT FALSE,
    redeemed_lead_id  INTEGER,                  -- the booking it was redeemed on
    redeemed_at       TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_reward_codes_phone ON reward_codes(phone);

-- Records which reward code (if any) was applied/redeemed on this booking,
-- for traceability alongside the Sheet's "Coupon Code Redeemed" column.
ALTER TABLE leads ADD COLUMN IF NOT EXISTS redeemed_coupon_code VARCHAR(20);

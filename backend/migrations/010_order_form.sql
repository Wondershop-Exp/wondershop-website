-- ─────────────────────────────────────────────────────────────────────────────
-- Order execution form — printer-friendly A4 form (Excel + PDF) attached to
-- the team notification email so ops can execute the booking (2026-08-12,
-- per Shruti).
--
-- V1 scope: auto-fill only what we already capture on the booking (leads
-- columns + builder_snapshot). Anything genuinely manual (vendor assigned,
-- Event Ops Lead, payment mode, pinata bags/fillings, gift-wrap instructions,
-- schedule) prints as a blank line for ops to fill by hand — no separate
-- internal tool needed yet. Kept intentionally small; a vendor/inventory
-- management table set can follow once that internal tool gets built.
-- ─────────────────────────────────────────────────────────────────────────────

ALTER TABLE leads ADD COLUMN IF NOT EXISTS event_time VARCHAR(20);
ALTER TABLE leads ADD COLUMN IF NOT EXISTS event_sales_lead VARCHAR(255);

-- ─── sales_lead_codes — personal attribution codes per salesperson ───────
-- Entered in the same "Coupon / Referral Code" box at checkout as reward/
-- referral codes. Gives the customer NO discount — purely attributes the
-- booking to the salesperson for the order form's "Event Sales Lead" field.

CREATE TABLE IF NOT EXISTS sales_lead_codes (
    code       VARCHAR(20) PRIMARY KEY,
    lead_name  VARCHAR(255) NOT NULL,
    active     BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

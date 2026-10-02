-- 039: Return Gift orders billed separately (2026-10-02, per Shruti).
-- "Return gifts are subject to stock availability ... we'll send a separate
-- payment link after our team confirms the stock availability ... show a
-- separate section in billing on cart, email and sales panel as well, where
-- ops team needs to confirm the order, post which, we'll share a payment
-- link with the customer on email and whatsapp."
--
-- Return Gifts (+ gift packaging / thank-you note) are no longer part of
-- the event's Grand Total / advance on new bookings; they're a separate
-- bill tracked by these columns. The admin Bookings page and the sales
-- panel show a "Return Gift Order" box that moves through:
--   pending_stock -> stock_confirmed -> link_sent -> paid   (or unavailable)
--
-- RUN THIS BEFORE deploying the matching backend. Website checkout keeps
-- working without it (the gift-order write is best-effort), but the
-- booking page's Return Gift Order box can't save until these exist.
-- Safe to run more than once. Existing bookings stay NULL (= gifts still
-- inside their Grand Total, exactly as they were billed).

ALTER TABLE leads ADD COLUMN IF NOT EXISTS gift_order_status     VARCHAR(20);
ALTER TABLE leads ADD COLUMN IF NOT EXISTS gift_order_total      NUMERIC(10,2);
ALTER TABLE leads ADD COLUMN IF NOT EXISTS gift_payment_link     TEXT;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS gift_order_note       TEXT;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS gift_order_updated_by VARCHAR(100);
ALTER TABLE leads ADD COLUMN IF NOT EXISTS gift_order_updated_at TIMESTAMPTZ;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS gift_link_sent_at     TIMESTAMPTZ;

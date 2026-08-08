-- ─────────────────────────────────────────────────────────────────────────────
-- Add return-gift delivery details capture to leads
-- Customer-entered delivery info from the builder's Return Gifts step
-- (Delivery Details block: address, Google Maps link, address type, delivery
-- coordination contact, required-by date).
-- ─────────────────────────────────────────────────────────────────────────────

ALTER TABLE leads ADD COLUMN IF NOT EXISTS gift_delivery_address      VARCHAR(500);
ALTER TABLE leads ADD COLUMN IF NOT EXISTS gift_delivery_maps_link    VARCHAR(500);
ALTER TABLE leads ADD COLUMN IF NOT EXISTS gift_delivery_address_type VARCHAR(50);
ALTER TABLE leads ADD COLUMN IF NOT EXISTS gift_delivery_contact      VARCHAR(255);
ALTER TABLE leads ADD COLUMN IF NOT EXISTS gift_required_by_date      DATE;

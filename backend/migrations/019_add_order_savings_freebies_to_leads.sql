-- ─────────────────────────────────────────────────────────────────────────────
-- Add order_total_savings / order_freebies_text to `leads` (2026-08-24, per
-- Shruti — Turn 5, Image 3c): "Don't show the discount/freebie bar at
-- checkout page. Add the freebies and discounts in the order summary. The
-- same should be visible on the admin page and the emails that goes to the
-- customers and the operations team."
--
-- order_discount_pct (existing column) is a percentage of the grand total
-- and doesn't capture freebie item value (see builder.html's trueMRP()) —
-- order_total_savings is the full ₹ savings figure (auto/flat discount +
-- unlocked freebie items, same basis as the bottom bar / checkout Order
-- Summary / Review page), and order_freebies_text is a human-readable list
-- of which freebies were unlocked (e.g. "Free E-Invite, Free Tattoo
-- Artist"). Both are sent from builder.html's doCo() alongside the existing
-- order_grand_total/order_discount_pct/order_advance/order_balance fields —
-- see LeadSubmitRequest in routers/leads.py.
-- ─────────────────────────────────────────────────────────────────────────────

ALTER TABLE leads ADD COLUMN IF NOT EXISTS order_total_savings NUMERIC;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS order_freebies_text TEXT;

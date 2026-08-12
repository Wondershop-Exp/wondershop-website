-- ─────────────────────────────────────────────────────────────────────────────
-- (2026-08-12, per Shruti): "save and display payment method". payment_method
-- has existed on LeadSubmitRequest since the Order Summary email work, and
-- _build_html_email / _format_order_summary_block already read
-- req.payment_method to show it in the confirmation emails — but nothing on
-- the frontend ever actually SENT it (builder.html's checkout payload never
-- included it), and even if it had, submit_lead()'s INSERT never wrote it to
-- the leads table, so there was never anywhere for the team to look it up
-- outside of that one email at send-time. Adding the column here + wiring
-- the INSERT (see leads.py) + sending it from builder.html's checkout
-- payload fixes all three.
-- ─────────────────────────────────────────────────────────────────────────────

ALTER TABLE leads ADD COLUMN IF NOT EXISTS payment_method VARCHAR(20);

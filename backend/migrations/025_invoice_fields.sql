-- ─────────────────────────────────────────────────────────────────────────────
-- Invoice fields on leads (2026-09-11, per Shruti — "let's finalize this...
-- This needs to go as an attachment when the user confirms the order. also,
-- had a manual trigger to send the update invoice from admin")
--
-- invoice_number is generated once, the first time an invoice is built for a
-- lead (booking confirmation), and reused on every later resend so a
-- customer never receives two different invoice numbers for the same
-- booking. invoice_generated_at / invoice_sent_at track the most recent
-- build/send, so admin.html can show "last sent" and the manual resend
-- button always reflects an up-to-date invoice.
-- ─────────────────────────────────────────────────────────────────────────────

ALTER TABLE leads ADD COLUMN IF NOT EXISTS invoice_number VARCHAR(50);
ALTER TABLE leads ADD COLUMN IF NOT EXISTS invoice_generated_at TIMESTAMPTZ;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS invoice_sent_at TIMESTAMPTZ;

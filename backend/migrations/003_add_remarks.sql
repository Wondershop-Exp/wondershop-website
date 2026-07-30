-- ─────────────────────────────────────────────────────────────────────────────
-- Add remarks/special-requests capture to leads
-- Customer-entered free text from package pages (e.g. spy-basic.html) and the
-- builder's per-step remarks boxes, combined into one string on the frontend
-- before submission.
-- ─────────────────────────────────────────────────────────────────────────────

ALTER TABLE leads ADD COLUMN IF NOT EXISTS remarks TEXT;

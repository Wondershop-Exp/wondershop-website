-- ─────────────────────────────────────────────────────────────────────────────
-- Packing list submission (2026-09-10, per Shruti)
--
-- "once the checklist is done, give a submit button. ask for a confirmation
-- that all materials has been packed in suitcases and ready to load? on
-- submit, inform Shruti on whatsapp." — pack.html shows a Submit button
-- once every item is checked, the staff member confirms in a dialog, and
-- the submission is recorded here (once — see the /pack/{token}/submit
-- endpoint's idempotency check in routers/packaging.py, which skips the
-- WhatsApp send on a second submit rather than re-notifying).
-- ─────────────────────────────────────────────────────────────────────────────

ALTER TABLE packaging_lists ADD COLUMN IF NOT EXISTS submitted_at TIMESTAMPTZ;
ALTER TABLE packaging_lists ADD COLUMN IF NOT EXISTS submitted_by VARCHAR(255);

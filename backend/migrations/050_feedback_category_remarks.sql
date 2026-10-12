-- 2026-10-12: a remarks box for each rated service on the feedback form.
ALTER TABLE party_feedback ADD COLUMN IF NOT EXISTS category_remarks JSONB;

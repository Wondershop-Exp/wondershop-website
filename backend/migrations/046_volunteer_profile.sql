-- 046: Event Volunteer profile (2026-10-10, per Shruti).
-- Partners who pick "Event Volunteer" on vendor-onboarding.html answer extra
-- questions (date of birth, education, experience, skills, roles, comfort with
-- the public, why they want to volunteer with Wondershop, open to training, zones) and accept the
-- volunteer terms. The answers are kept as one JSON object on the partner's
-- vendor_master row; the team can edit them in the Partners tab. The resume is
-- BYTEA like the cancelled cheque and only served through the admin API.
--
-- Safe to run more than once (listed in db_ensure.SAFE_MIGRATIONS).

ALTER TABLE vendor_master ADD COLUMN IF NOT EXISTS volunteer_profile JSONB;
ALTER TABLE vendor_master ADD COLUMN IF NOT EXISTS volunteer_tnc_accepted_at TIMESTAMPTZ;
ALTER TABLE vendor_master ADD COLUMN IF NOT EXISTS volunteer_tnc_version VARCHAR(20);
ALTER TABLE vendor_master ADD COLUMN IF NOT EXISTS resume_file BYTEA;
ALTER TABLE vendor_master ADD COLUMN IF NOT EXISTS resume_filename TEXT;
ALTER TABLE vendor_master ADD COLUMN IF NOT EXISTS resume_content_type VARCHAR(100);

-- 079: per-party Boy/Girl override for the Spy registration page (2026-10-29,
-- per Shruti: "change their to her/him based on the gender"). Used when the
-- booking itself has no gender on file. NULL = use the booking's gender.
-- Safe to run again.
ALTER TABLE spy_registration_pages ADD COLUMN IF NOT EXISTS child_gender_override TEXT;

-- ─────────────────────────────────────────────────────────────────────────────
-- (2026-08-17, per Shruti — "for 'what does the birthday child like most?' -
-- if the customer chooses something else - give a text to input this. Save
-- this in DB and add it to the order form and email. this input will be
-- helpful for us to improve these selections").
--
-- `interests` — comma-joined category labels picked on Step 0 (e.g.
--   "Science & Experiments, Sports & Games").
-- `interest_other` — free text entered when "Something Else" was picked,
--   so the team can see what customers actually meant and spot patterns
--   worth adding as a proper category later.
-- ─────────────────────────────────────────────────────────────────────────────

ALTER TABLE leads ADD COLUMN IF NOT EXISTS interests VARCHAR(500);
ALTER TABLE leads ADD COLUMN IF NOT EXISTS interest_other VARCHAR(500);

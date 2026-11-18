-- 089: private host link to see who has registered for their Spy party
-- (2026-11-17, per Shruti: "a lot of parents keep asking about registrations,
-- can we give them a link to see the registrations, only for their party").
-- Separate from share_token, which guests get - so guests can't see the list.
-- Filled in lazily by the backend the first time admin opens the panel.
-- Safe to run again.
ALTER TABLE spy_registration_pages ADD COLUMN IF NOT EXISTS host_token TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS spy_registration_pages_host_token_uq ON spy_registration_pages (host_token);
